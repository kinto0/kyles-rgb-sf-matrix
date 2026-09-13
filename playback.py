"""Shared frame loading/playback timing for the hardware loop and the emulator."""

import sys

import make_image

FRAME_HOLD_SEC = 0.4
PLAYS_BEFORE_REFRESH = 100


def should_skip(argv=None):
    argv = sys.argv if argv is None else argv
    return len(argv) > 1 and argv[1] == "skip"


def load_frames(skip=None, limit=None):
    if skip is None:
        skip = should_skip()
    if skip:
        print("skipping query")
        frames = make_image.load_saved_frames()
    else:
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
