"""
Generate 32x64 GeoColor frames of San Francisco from NOAA's
MERGEDGC_Last_24hr ArcGIS Image Service.

This is the *actual* CIRA/NOAA GeoColor product (true-color RGB by day,
IR + static VIIRS city-lights composite by night). The 24-hour service is
time-enabled, with a new mosaic every 10 or 15 minutes.

Install deps:
    pip install requests pillow

Note: This is a public NOAA-operated ArcGIS ImageServer, not something under
our control -- if you get an error/blank response, the service may be
temporarily restarting; retry after a few seconds.
"""

from typing import List
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO

import requests
from PIL import Image

ARCHIVE_URL = "https://satellitemaps.nesdis.noaa.gov/arcgis/rest/services/MERGEDGC_Last_24hr/ImageServer"
EXPORT_URL = f"{ARCHIVE_URL}/exportImage"
QUERY_URL = f"{ARCHIVE_URL}/query"

LAT, LON = 37.7749, -122.4194   # San Francisco
OUT_W, OUT_H = 64, 32            # (width, height) of final image
HALF_WIDTH_KM = 14               # real-world half-width of the crop
HALF_HEIGHT_KM = 7               # real-world half-height (2x width, matches OUT_W:OUT_H)
RETENTION_HOURS = 3

# Keep fetched images available for refreshes without writing them to disk.
_FRAME_CACHE = {}

# 3x5 digits for a 64x32 panel
_DIGITS = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "001", "001", "001"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    ":": ["0", "1", "0", "1", "0"],
    " ": ["0", "0", "0", "0", "0"],
}


def bbox_for_point(lat: float, lon: float, half_w_km: float, half_h_km: float) -> str:
    """Build a lon/lat bounding box string of the requested real-world size."""
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(lat))  # longitude degrees shrink with latitude

    dlat = half_h_km / km_per_deg_lat
    dlon = half_w_km / km_per_deg_lon

    xmin, xmax = lon - dlon, lon + dlon
    ymin, ymax = lat - dlat, lat + dlat
    return f"{xmin},{ymin},{xmax},{ymax}"


def list_frame_times(after_time_ms: int) -> List[int]:
    """Return unique raster start times newer than the given timestamp."""
    after_time = datetime.fromtimestamp(after_time_ms / 1000, timezone.utc)
    params = {
        "where": f"start_time > TIMESTAMP '{after_time:%Y-%m-%d %H:%M:%S}'",
        "outFields": "start_time,name",
        "returnGeometry": "false",
        "orderByFields": "start_time ASC",
        "f": "json",
        "resultRecordCount": 1000,
    }
    resp = requests.get(QUERY_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        error = data["error"]
        raise RuntimeError(
            f"NOAA timestamp query failed: {error.get('message', error)}"
        )
    times = []
    seen = set()
    for feature in data.get("features", []):
        attrs = feature.get("attributes") or {}
        t = attrs.get("start_time")
        name = attrs.get("name") or ""
        if t is None or t in seen:
            continue
        if "overview" in name.lower():
            continue
        seen.add(t)
        times.append(t)
    return times


def fetch_frame(bbox: str, time_ms: int) -> Image.Image:
    params = {
        "bbox": bbox,
        "bboxSR": 4326,
        "size": f"{OUT_W},{OUT_H}",
        "imageSR": 4326,
        "format": "png",
        "f": "image",
        "time": time_ms,
    }
    resp = requests.get(EXPORT_URL, params=params, timeout=30)
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    return img.resize((OUT_W, OUT_H), Image.LANCZOS)


def _blit_glyph(pixels, x, y, glyph, color, outline, paint_outline):
    rows = _DIGITS[glyph]
    width = len(rows[0])
    for gy, row in enumerate(rows):
        for gx, bit in enumerate(row):
            if bit != "1":
                continue
            px, py = x + gx, y + gy
            if paint_outline:
                for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nx, ny = px + ox, py + oy
                    if 0 <= nx < OUT_W and 0 <= ny < OUT_H:
                        pixels[nx, ny] = outline
            else:
                pixels[px, py] = color
    return width


def overlay_time(img: Image.Image, time_ms: int) -> Image.Image:
    """Stamp local HH:MM in the top-left corner of a copy of the frame."""
    stamped = img.copy()
    when = datetime.fromtimestamp(time_ms / 1000)
    text = when.strftime("%H:%M")
    pixels = stamped.load()
    for paint_outline in (True, False):
        x, y = 46, 26
        for ch in text:
            x += _blit_glyph(pixels, x, y, ch, (255, 255, 255), (0, 0, 0), paint_outline) + 1
    return stamped


def load_saved_frames():
    """Return every frame currently held in the in-memory cache."""
    return [
        (_FRAME_CACHE[time_ms], time_ms)
        for time_ms in sorted(_FRAME_CACHE)
    ]


def make(limit=None):
    bbox = bbox_for_point(LAT, LON, HALF_WIDTH_KM, HALF_HEIGHT_KM)

    cutoff = int((time.time() - RETENTION_HOURS * 60 * 60) * 1000)
    for time_ms in list(_FRAME_CACHE):
        if time_ms < cutoff:
            del _FRAME_CACHE[time_ms]

    most_recent_time = max(_FRAME_CACHE, default=0)
    new_times = list_frame_times(max(cutoff, most_recent_time))
    times = sorted(
        time_ms for time_ms in set(_FRAME_CACHE).union(new_times)
        if time_ms >= cutoff
    )
    if limit and len(times) > limit:
        if limit == 1:
            times = [times[-1]]
        else:
            idxs = [int(round(i * (len(times) - 1) / float(limit - 1))) for i in range(limit)]
            times = [times[i] for i in idxs]

    def download(time_ms: int):
        img = fetch_frame(bbox, time_ms)
        return time_ms, img

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(download, time_ms)
            for time_ms in times
            if time_ms > most_recent_time
        ]
        print(f"Fetching {len(futures)} archive frames")
        for future in as_completed(futures):
            try:
                time_ms, img = future.result()
            except Exception as e:
                print(e)
                continue
            _FRAME_CACHE[time_ms] = img
            print(f"Cached frame {time_ms}")

    frames = []
    for t in times:
        img = _FRAME_CACHE.get(t)
        if img is not None:
            frames.append((img, t))
    print(f"Using {len(frames)} frames from the last {RETENTION_HOURS} hours")
    return frames
