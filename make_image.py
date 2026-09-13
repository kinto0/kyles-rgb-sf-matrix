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

from datetime import timedelta
from typing import List
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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
OUTFILE = "sf_geocolor.png"
FRAMES_DIR = "frames"

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


def list_frame_times() -> List[int]:
    """Return unique raster start times (unix ms) from the 24h archive, oldest first."""
    params = {
        "where": "1=1",
        "outFields": "start_time,name",
        "returnGeometry": "false",
        "orderByFields": "start_time ASC",
        "f": "json",
        "resultRecordCount": 1000,
    }
    resp = requests.get(QUERY_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
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
        x, y = 1, 25
        for ch in text:
            x += _blit_glyph(pixels, x, y, ch, (255, 255, 255), (0, 0, 0), paint_outline) + 1
    return stamped


def load_saved_frames():
    """Load previously saved frames from disk (used by matrix.py skip mode)."""
    if not os.path.isdir(FRAMES_DIR):
        if os.path.exists(OUTFILE):
            return [(Image.open(OUTFILE).convert("RGB"), 0)]
        return []
    frames = []
    for name in sorted(os.listdir(FRAMES_DIR)):
        if not name.endswith(".png"):
            continue
        try:
            time_ms = int(os.path.splitext(name)[0])
        except ValueError:
            continue
        path = os.path.join(FRAMES_DIR, name)
        frames.append((Image.open(path).convert("RGB"), time_ms))
    return frames


def make(limit=None):
    bbox = bbox_for_point(LAT, LON, HALF_WIDTH_KM, HALF_HEIGHT_KM)
    os.makedirs(FRAMES_DIR, exist_ok=True)

    all_times = list_frame_times()
    times = all_times
    if limit and len(times) > limit:
        if limit == 1:
            times = [times[-1]]
        else:
            idxs = [int(round(i * (len(times) - 1) / float(limit - 1))) for i in range(limit)]
            times = [times[i] for i in idxs]

    frames_by_time = {}

    def download(time_ms: int):
        img = fetch_frame(bbox, time_ms)
        return time_ms, img

    four_hours_ago = (datetime.now() - timedelta(hours=4)).timestamp() * 1000
    times_in_last_hour = [t for t in times if t > four_hours_ago]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(download, t) for t in times_in_last_hour]
        print(f"Fetching {len(futures)} archive frames")
        for future in as_completed(futures):
            try:
                time_ms, img = future.result()
            except Exception as e:
                print(e)
                continue
            frames_by_time[time_ms] = img
            img.save(os.path.join(FRAMES_DIR, f"{time_ms}.png"))
            print(f"Saved frame {time_ms}")
    keep = {f"{t}.png" for t in all_times}
    for name in os.listdir(FRAMES_DIR):
        if name.endswith(".png") and name not in keep:
            os.remove(os.path.join(FRAMES_DIR, name))

    frames = []
    for t in times:
        img = frames_by_time.get(t)
        if img is None:
            path = os.path.join(FRAMES_DIR, f"{t}.png")
            if os.path.exists(path):
                img = Image.open(path).convert("RGB")
        if img is not None:
            frames.append((img, t))
    if frames:
        frames[-1][0].save(OUTFILE)
        print(f"Saved {OUTFILE} ({len(frames)} frames, size {frames[-1][0].size})")
    return frames
