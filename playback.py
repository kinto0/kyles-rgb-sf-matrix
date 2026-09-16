"""Shared frame loading/playback timing for the hardware loop and the emulator."""

import make_image

FRAME_HOLD_SEC = 0.4
REFRESH_INTERVAL_SEC = 10 * 60


def load_frames(limit=None):
    try:
        frames = make_image.make(limit=limit)
    except Exception as e:
        print(e)
        frames = make_image.load_saved_frames()
    if limit and len(frames) > limit:
        step = max(1, len(frames) // limit)
        frames = frames[::step][:limit]
    return frames


def prepare(frames):
    prepared = []
    for image, time_ms in frames:
        rgb = image.convert("RGB")
        if time_ms:
            rgb = make_image.overlay_time(rgb, time_ms)
        prepared.append(rgb)
    return prepared
