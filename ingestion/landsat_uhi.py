from __future__ import annotations

from datetime import date, timedelta
import math

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject


STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "landsat-c2-l2"
LANDSAT_SOURCE = "USGS Landsat Collection 2 Level-2"


def _haversine_grid_km(latitudes: np.ndarray, longitudes: np.ndarray, latitude: float, longitude: float) -> np.ndarray:
    radius = 6371.0088
    lat1 = np.radians(latitude)
    lat2 = np.radians(latitudes)
    dlat = lat2 - lat1
    dlon = np.radians(longitudes - longitude)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * radius * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def summarize_surface_temperature_contrast(
    pixels: pd.DataFrame,
    minimum_pixels: int = 30,
) -> dict:
    """Compare an urban-core built/bare proxy with an outer vegetated reference.

    The output is an exploratory overpass-specific surface-temperature
    contrast, not an official urban heat island estimate.
    """
    required = {"temperature_c", "ndvi", "distance_km"}
    if pixels.empty or not required.issubset(pixels.columns):
        return {"status": "insufficient_pixels", "urban_pixels": 0, "reference_pixels": 0}

    frame = pixels.copy()
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=list(required))
    frame = frame.loc[frame["temperature_c"].between(-40, 80) & frame["ndvi"].between(-1, 1)]
    urban = frame.loc[(frame["distance_km"] <= 5) & (frame["ndvi"] <= 0.20), "temperature_c"]
    vegetated = frame.loc[
        frame["distance_km"].between(10, 25) & (frame["ndvi"] >= 0.35),
        "temperature_c",
    ]
    result = {
        "status": "ready" if len(urban) >= minimum_pixels and len(vegetated) >= minimum_pixels else "insufficient_reference_pixels",
        "urban_pixels": int(len(urban)),
        "reference_pixels": int(len(vegetated)),
        "urban_proxy_median_c": float(urban.median()) if len(urban) else None,
        "vegetated_reference_median_c": float(vegetated.median()) if len(vegetated) else None,
        "surface_temperature_contrast_c": (
            float(urban.median() - vegetated.median())
            if len(urban) >= minimum_pixels and len(vegetated) >= minimum_pixels else None
        ),
        "urban_definition": "within 5 km of city-centre point and NDVI ≤0.20 (built/bare proxy)",
        "reference_definition": "10–25 km from city-centre point and NDVI ≥0.35 (vegetated reference proxy)",
    }
    return result


def _read_asset_on_grid(href: str, bbox: tuple[float, float, float, float], width: int, height: int, resampling: Resampling) -> tuple[np.ndarray, np.ndarray]:
    left, bottom, right, top = bbox
    transform = from_bounds(left, bottom, right, top, width, height)
    destination = np.zeros((height, width), dtype=np.float32)
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_MAX_RETRY="2",
    ):
        with rasterio.open(href) as dataset:
            reproject(
                source=rasterio.band(dataset, 1),
                destination=destination,
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                dst_transform=transform,
                dst_crs="EPSG:4326",
                src_nodata=dataset.nodata,
                dst_nodata=0,
                resampling=resampling,
            )
    return destination, transform


def fetch_landsat_surface_temperature_analysis(
    latitude: float,
    longitude: float,
    days_back: int = 1095,
    radius_km: float = 25.0,
    maximum_scenes: int = 15,
) -> tuple[pd.DataFrame, dict]:
    """Find a clear recent Landsat scene and calculate a surface-temperature contrast.

    Landsat Collection 2 L2 assets are read from public Microsoft Planetary
    Computer COGs. Surface temperature is scaled per USGS documentation.
    QA_PIXEL cloud/shadow/snow/fill/water pixels are excluded. Output samples
    are intentionally downsampled for map rendering.
    """
    diagnostics = {
        "status": "no_scene",
        "source": LANDSAT_SOURCE,
        "scene_id": None,
        "acquired": None,
        "cloud_cover_scene_pct": None,
        "surface_temperature_contrast_c": None,
        "urban_proxy_median_c": None,
        "vegetated_reference_median_c": None,
        "urban_pixels": 0,
        "reference_pixels": 0,
        "valid_pixels": 0,
        "pixel_size_m": 200,
    }
    empty = pd.DataFrame(columns=["latitude", "longitude", "temperature_c", "ndvi", "distance_km", "surface_class"])
    radius_lat = float(radius_km) / 111.32
    radius_lon = float(radius_km) / (111.32 * max(0.15, abs(math.cos(math.radians(latitude)))))
    bbox = (longitude - radius_lon, latitude - radius_lat, longitude + radius_lon, latitude + radius_lat)
    start_date = (date.today() - timedelta(days=int(days_back))).isoformat()
    end_date = date.today().isoformat()

    catalog = pystac_client.Client.open(STAC_URL)
    search = catalog.search(
        collections=[COLLECTION],
        bbox=list(bbox),
        datetime=f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
        query={"eo:cloud_cover": {"lt": 65}},
        sortby=[{"field": "properties.datetime", "direction": "desc"}],
        max_items=maximum_scenes,
    )
    items = list(search.items())
    if not items:
        diagnostics["status"] = "no_scene"
        return empty, diagnostics

    # Try newest scenes first; QA_PIXEL filtering below decides if a scene is
    # actually usable over this city window.
    last_error = None
    for raw_item in items:
        item = planetary_computer.sign(raw_item)
        assets = item.assets
        required_assets = {"lwir11", "qa_pixel", "red", "nir08"}
        if not required_assets.issubset(assets):
            continue
        scene_cloud = item.properties.get("eo:cloud_cover")
        try:
            width = 250
            height = 250
            lst_dn, transform = _read_asset_on_grid(
                assets["lwir11"].href, bbox, width, height, Resampling.bilinear
            )
            qa, _ = _read_asset_on_grid(
                assets["qa_pixel"].href, bbox, width, height, Resampling.nearest
            )
            red_dn, _ = _read_asset_on_grid(
                assets["red"].href, bbox, width, height, Resampling.bilinear
            )
            nir_dn, _ = _read_asset_on_grid(
                assets["nir08"].href, bbox, width, height, Resampling.bilinear
            )

            # USGS Collection 2 L2 surface-temperature scale and offset.
            temperature_k = lst_dn * 0.00341802 + 149.0
            temperature_c = temperature_k - 273.15
            red = red_dn * 0.0000275 - 0.2
            nir = nir_dn * 0.0000275 - 0.2
            ndvi = (nir - red) / np.maximum(nir + red, 1e-6)

            qa_values = qa.astype(np.uint16)
            invalid_bits = (
                (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3)
                | (1 << 4) | (1 << 5) | (1 << 7)
            )
            valid = (
                (lst_dn > 0)
                & ((qa_values & invalid_bits) == 0)
                & np.isfinite(temperature_c)
                & (temperature_c >= -40)
                & (temperature_c <= 80)
                & np.isfinite(ndvi)
                & (ndvi >= -1)
                & (ndvi <= 1)
            )
            rows, cols = np.indices((height, width))
            left, bottom, right, top = bbox
            pixel_lon = left + (cols + 0.5) * ((right - left) / width)
            pixel_lat = top - (rows + 0.5) * ((top - bottom) / height)
            distance = _haversine_grid_km(pixel_lat, pixel_lon, latitude, longitude)
            valid &= distance <= radius_km

            pixels = pd.DataFrame({
                "temperature_c": temperature_c[valid],
                "ndvi": ndvi[valid],
                "distance_km": distance[valid],
            })
            contrast = summarize_surface_temperature_contrast(pixels)
            if contrast["status"] != "ready":
                last_error = f"Scene {item.id} had too few clear pixels in the urban/reference pools."
                continue

            # Downsample valid observations for a responsive map; keep measured
            # raster values, not an interpolated surface.
            sample_mask = valid & ((rows % 3) == 0) & ((cols % 3) == 0)
            sample_classes = np.where(
                (distance <= 5) & (ndvi <= 0.20),
                "Urban-core proxy",
                np.where(
                    (distance >= 10) & (distance <= 25) & (ndvi >= 0.35),
                    "Vegetated reference",
                    "Other valid pixel",
                ),
            )
            pixels_map = pd.DataFrame({
                "latitude": pixel_lat[sample_mask].ravel(),
                "longitude": pixel_lon[sample_mask].ravel(),
                "temperature_c": temperature_c[sample_mask].ravel(),
                "ndvi": ndvi[sample_mask].ravel(),
                "distance_km": distance[sample_mask].ravel(),
                "surface_class": sample_classes[sample_mask].ravel(),
            })
            diagnostics.update(contrast)
            diagnostics.update({
                "status": "ready",
                "scene_id": item.id,
                "acquired": item.properties.get("datetime"),
                "cloud_cover_scene_pct": float(scene_cloud) if scene_cloud is not None else None,
                "valid_pixels": int(valid.sum()),
                "pixel_size_m": round((2.0 * float(radius_km) * 1000.0) / width, 1),
                "source": LANDSAT_SOURCE,
            })
            return pixels_map, diagnostics
        except Exception as exc:
            last_error = str(exc)
            continue

    diagnostics["status"] = "no_usable_scene"
    diagnostics["error"] = last_error or "No suitable thermal scenes were found."
    return empty, diagnostics
