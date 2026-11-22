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
    urban_mask = (frame["distance_km"] <= 5) & (frame["ndvi"] <= 0.20)
    vegetated_mask = frame["distance_km"].between(10, 25) & (frame["ndvi"] >= 0.35)
    urban = frame.loc[urban_mask, "temperature_c"]
    vegetated = frame.loc[vegetated_mask, "temperature_c"]
    uncertainty_column = "st_uncertainty_k" if "st_uncertainty_k" in frame.columns else None
    urban_uncertainty = (
        pd.to_numeric(frame.loc[urban_mask, uncertainty_column], errors="coerce").dropna()
        if uncertainty_column else pd.Series(dtype=float)
    )
    vegetated_uncertainty = (
        pd.to_numeric(frame.loc[vegetated_mask, uncertainty_column], errors="coerce").dropna()
        if uncertainty_column else pd.Series(dtype=float)
    )
    all_uncertainty = pd.to_numeric(frame[uncertainty_column], errors="coerce").dropna() if uncertainty_column else pd.Series(dtype=float)
    result = {
        "status": "ready" if len(urban) >= minimum_pixels and len(vegetated) >= minimum_pixels else "insufficient_reference_pixels",
        "urban_pixels": int(len(urban)),
        "reference_pixels": int(len(vegetated)),
        "urban_proxy_median_c": float(urban.median()) if len(urban) else None,
        "vegetated_reference_median_c": float(vegetated.median()) if len(vegetated) else None,
        "urban_st_uncertainty_median_k": float(urban_uncertainty.median()) if len(urban_uncertainty) else None,
        "vegetated_st_uncertainty_median_k": float(vegetated_uncertainty.median()) if len(vegetated_uncertainty) else None,
        "median_st_uncertainty_k": float(all_uncertainty.median()) if len(all_uncertainty) else None,
        "p90_st_uncertainty_k": float(all_uncertainty.quantile(0.90)) if len(all_uncertainty) else None,
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


def summarize_scene_contrasts(scene_records: list[dict]) -> dict:
    """Summarize independent scene-level urban/reference surface-temperature contrasts."""
    values = [
        float(item["surface_temperature_contrast_c"])
        for item in scene_records
        if item.get("surface_temperature_contrast_c") is not None
    ]
    urban = [
        float(item["urban_proxy_median_c"])
        for item in scene_records
        if item.get("urban_proxy_median_c") is not None
    ]
    vegetated = [
        float(item["vegetated_reference_median_c"])
        for item in scene_records
        if item.get("vegetated_reference_median_c") is not None
    ]
    dates = sorted(str(item.get("acquired", ""))[:10] for item in scene_records if item.get("acquired"))
    uncertainties = [
        float(item["median_st_uncertainty_k"])
        for item in scene_records
        if item.get("median_st_uncertainty_k") is not None
    ]
    return {
        "scene_count": len(values),
        "scene_dates": dates,
        "temporal_span_days": (
            (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days if len(dates) >= 2 else 0
        ),
        "surface_temperature_contrast_c": float(np.median(values)) if values else None,
        "contrast_min_c": float(np.min(values)) if values else None,
        "contrast_max_c": float(np.max(values)) if values else None,
        "urban_proxy_median_c": float(np.median(urban)) if urban else None,
        "vegetated_reference_median_c": float(np.median(vegetated)) if vegetated else None,
        "median_st_uncertainty_k": float(np.median(uncertainties)) if uncertainties else None,
    }


def fetch_landsat_surface_temperature_analysis(
    latitude: float,
    longitude: float,
    days_back: int = 1095,
    radius_km: float = 25.0,
    maximum_scenes: int = 30,
    target_usable_scenes: int = 3,
) -> tuple[pd.DataFrame, dict]:
    """Find recent clear Landsat scenes and summarize a surface-temperature contrast.

    Landsat Collection 2 Level-2 ST_B10, SR_B4/SR_B5, QA_PIXEL, QA_RADSAT,
    and ST_QA assets are read from Microsoft Planetary Computer COGs.
    Temperatures and reflectance are scaled using USGS product factors.
    The contrast uses an approximate built/bare urban-core proxy and a
    vegetated outer reference. Multiple usable scenes are aggregated when
    available; fewer scenes are explicitly identified as limited evidence.
    """
    diagnostics = {
        "status": "no_scene",
        "source": LANDSAT_SOURCE,
        "scene_id": None,
        "acquired": None,
        "cloud_cover_scene_pct": None,
        "surface_temperature_contrast_c": None,
        "contrast_min_c": None,
        "contrast_max_c": None,
        "urban_proxy_median_c": None,
        "vegetated_reference_median_c": None,
        "urban_pixels": 0,
        "reference_pixels": 0,
        "valid_pixels": 0,
        "pixel_size_m": round((2.0 * float(radius_km) * 1000.0) / 250, 1),
        "scene_count": 0,
        "scene_dates": [],
        "temporal_span_days": 0,
        "median_st_uncertainty_k": None,
        "st_uncertainty_source": "USGS ST_QA band (0.01 K scale), when available",
    }
    empty = pd.DataFrame(columns=[
        "latitude", "longitude", "temperature_c", "ndvi", "distance_km",
        "surface_class", "st_uncertainty_k",
    ])
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
        return empty, diagnostics

    scene_records: list[dict] = []
    latest_map = None
    latest_scene = None
    last_error = None
    width = height = 250
    left, bottom, right, top = bbox

    for raw_item in items:
        try:
            item = planetary_computer.sign(raw_item)
        except Exception as exc:
            last_error = str(exc)
            continue
        assets = item.assets
        required_assets = {"lwir11", "qa_pixel", "red", "nir08"}
        if not required_assets.issubset(assets):
            continue
        scene_cloud = item.properties.get("eo:cloud_cover")
        try:
            lst_dn, _ = _read_asset_on_grid(
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
            if "qa" in assets:
                st_qa_dn, _ = _read_asset_on_grid(
                    assets["qa"].href, bbox, width, height, Resampling.nearest
                )
                st_uncertainty_k = st_qa_dn * 0.01
            else:
                st_uncertainty_k = np.full((height, width), np.nan, dtype=float)

            qa_values = qa.astype(np.uint16)
            invalid_qa_bits = (
                (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3)
                | (1 << 4) | (1 << 5) | (1 << 7)
            )
            valid = (lst_dn > 0) & ((qa_values & invalid_qa_bits) == 0)

            # QA_RADSAT bit 9 flags Landsat 8/9 Band 10 saturation and
            # bit 11 flags terrain occlusion.
            if "qa_radsat" in assets:
                qa_radsat, _ = _read_asset_on_grid(
                    assets["qa_radsat"].href, bbox, width, height, Resampling.nearest
                )
                radsat_values = qa_radsat.astype(np.uint16)
                valid &= (radsat_values & ((1 << 9) | (1 << 11))) == 0

            if "qa" in assets:
                valid &= st_qa_dn > 0

            temperature_k = lst_dn * 0.00341802 + 149.0
            temperature_c = temperature_k - 273.15
            red = red_dn * 0.0000275 - 0.2
            nir = nir_dn * 0.0000275 - 0.2
            denominator = nir + red
            ndvi = np.divide(
                nir - red,
                denominator,
                out=np.full_like(denominator, np.nan, dtype=float),
                where=np.abs(denominator) > 1e-6,
            )
            valid &= (
                np.isfinite(temperature_c)
                & (temperature_c >= -40)
                & (temperature_c <= 80)
                & np.isfinite(ndvi)
                & (ndvi >= -1)
                & (ndvi <= 1)
                & (red_dn > 0)
                & (nir_dn > 0)
            )

            rows, cols = np.indices((height, width))
            pixel_lon = left + (cols + 0.5) * ((right - left) / width)
            pixel_lat = top - (rows + 0.5) * ((top - bottom) / height)
            distance = _haversine_grid_km(pixel_lat, pixel_lon, latitude, longitude)
            valid &= distance <= radius_km

            pixels = pd.DataFrame({
                "temperature_c": temperature_c[valid],
                "ndvi": ndvi[valid],
                "distance_km": distance[valid],
                "st_uncertainty_k": st_uncertainty_k[valid],
            })
            contrast = summarize_surface_temperature_contrast(pixels)
            if contrast["status"] != "ready":
                last_error = f"Scene {item.id} had too few clear pixels in the urban/reference pools."
                continue

            acquired = item.properties.get("datetime")
            scene_record = {
                **contrast,
                "scene_id": item.id,
                "acquired": acquired,
                "cloud_cover_scene_pct": float(scene_cloud) if scene_cloud is not None else None,
                "valid_pixels": int(valid.sum()),
            }
            scene_records.append(scene_record)

            if latest_map is None:
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
                latest_map = pd.DataFrame({
                    "latitude": pixel_lat[sample_mask].ravel(),
                    "longitude": pixel_lon[sample_mask].ravel(),
                    "temperature_c": temperature_c[sample_mask].ravel(),
                    "ndvi": ndvi[sample_mask].ravel(),
                    "distance_km": distance[sample_mask].ravel(),
                    "surface_class": sample_classes[sample_mask].ravel(),
                    "st_uncertainty_k": st_uncertainty_k[sample_mask].ravel(),
                })
                latest_scene = scene_record

            if len(scene_records) >= max(1, int(target_usable_scenes)):
                break
        except Exception as exc:
            last_error = str(exc)
            continue

    if not scene_records or latest_map is None or latest_scene is None:
        diagnostics["status"] = "no_usable_scene"
        diagnostics["error"] = last_error or "No recent scene had enough valid urban and vegetated-reference pixels."
        return empty, diagnostics

    temporal = summarize_scene_contrasts(scene_records)
    diagnostics.update(temporal)
    diagnostics.update({
        "status": "ready",
        "scene_id": latest_scene["scene_id"],
        "acquired": latest_scene["acquired"],
        "cloud_cover_scene_pct": latest_scene["cloud_cover_scene_pct"],
        "valid_pixels": latest_scene["valid_pixels"],
        "urban_pixels": latest_scene["urban_pixels"],
        "reference_pixels": latest_scene["reference_pixels"],
        "urban_definition": latest_scene["urban_definition"],
        "reference_definition": latest_scene["reference_definition"],
        "scene_contrasts": [
            {
                "scene_id": item["scene_id"],
                "date": str(item["acquired"])[:10],
                "contrast_c": item["surface_temperature_contrast_c"],
                "urban_median_c": item["urban_proxy_median_c"],
                "vegetated_median_c": item["vegetated_reference_median_c"],
                "valid_pixels": item["valid_pixels"],
                "cloud_cover_scene_pct": item["cloud_cover_scene_pct"],
            }
            for item in scene_records
        ],
        "source": LANDSAT_SOURCE,
    })
    return latest_map, diagnostics
