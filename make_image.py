"""
Generate a 32x64 GeoColor image of San Francisco using NOAA's MERGED_GeoColor
ArcGIS Image Service.

This is the *actual* CIRA/NOAA GeoColor product (true-color RGB by day,
IR + static VIIRS city-lights composite by night) -- not something we're
reconstructing from raw bands. It's served as a georeferenced image service,
so we just ask it directly for the SF bounding box at the exact pixel size
we want. No S3 / netCDF / xarray / pyproj needed -- just `requests` + `pillow`.

Install deps:
    pip install requests pillow

Note: This is a public NOAA-operated ArcGIS ImageServer, not something under
our control -- if you get an error/blank response, the service may be
temporarily restarting; retry after a few seconds.
"""

import math
from io import BytesIO

import requests
from PIL import Image

BASE_URL = "https://satellitemaps.nesdis.noaa.gov/arcgis/rest/services/MERGED_GeoColor/ImageServer/exportImage"

LAT, LON = 37.7749, -122.4194   # San Francisco
OUT_W, OUT_H = 64, 32            # (width, height) of final image
HALF_WIDTH_KM = 14               # real-world half-width of the crop
HALF_HEIGHT_KM = 7              # real-world half-height (2x width, matches OUT_W:OUT_H)
OUTFILE = "sf_geocolor.png"


def bbox_for_point(lat: float, lon: float, half_w_km: float, half_h_km: float) -> str:
    """Build a lon/lat bounding box string of the requested real-world size."""
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(lat))  # longitude degrees shrink with latitude

    dlat = half_h_km / km_per_deg_lat
    dlon = half_w_km / km_per_deg_lon

    xmin, xmax = lon - dlon, lon + dlon
    ymin, ymax = lat - dlat, lat + dlat
    return f"{xmin},{ymin},{xmax},{ymax}"


def make():
    bbox = bbox_for_point(LAT, LON, HALF_WIDTH_KM, HALF_HEIGHT_KM)

    params = {
        "bbox": bbox,
        "bboxSR": 4326,
        "size": f"{OUT_W},{OUT_H}",
        "imageSR": 4326,
        "format": "png",
        "f": "image",
    }
    print(params)

    resp = requests.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()

    img = Image.open(BytesIO(resp.content)).convert("RGB")
    img = img.resize((OUT_W, OUT_H), Image.LANCZOS)  # guarantee exact size regardless of service response
    img.save(OUTFILE)
    print(f"Saved {OUTFILE} at size {img.size}")

