"""
Emulate the 64x32 LED matrix on a desktop, without the HAT or rgbmatrix.

Plays the same frames/time overlay as matrix.py in a scaled pixel window,
and writes preview.html so you can scrub the animation in a browser.

  .venv/bin/python preview.py
  .venv/bin/python preview.py skip
  .venv/bin/python preview.py --limit 24
"""

from __future__ import print_function

import argparse
import base64
import os
from io import BytesIO

import make_image
import playback

SCALE = 12
PREVIEW_HTML = "preview.html"


def parse_args():
    parser = argparse.ArgumentParser(description="Emulate the LED matrix animation")
    parser.add_argument("mode", nargs="?", help="pass 'skip' to reuse saved frames")
    parser.add_argument("--limit", type=int, default=None, help="max frames to fetch/play")
    parser.add_argument("--scale", type=int, default=SCALE, help="pixel size in the window")
    parser.add_argument("--html", default=PREVIEW_HTML, help="path for the browser preview")
    parser.add_argument("--no-window", action="store_true", help="only write HTML, do not open Tk")
    return parser.parse_args()


def write_html(frames, path, hold_sec, scale):
    payloads = []
    for img in frames:
        buf = BytesIO()
        img.save(buf, format="PNG")
        payloads.append(base64.b64encode(buf.getvalue()).decode("ascii"))

    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>LED matrix preview</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 16px;
      background: #111;
      color: #ddd;
      font: 14px/1.4 -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    .panel {{
      padding: 10px;
      background: #050505;
      border: 2px solid #222;
      box-shadow: 0 0 40px #000;
    }}
    .panel img {{
      width: {width}px;
      height: {height}px;
      image-rendering: pixelated;
      image-rendering: crisp-edges;
      display: block;
      background: #000;
    }}
    .meta {{ color: #888; }}
  </style>
</head>
<body>
  <div class="panel"><img id="led" alt="LED matrix preview"></div>
  <div class="meta" id="meta"></div>
  <script>
    const frames = {payloads};
    const holdMs = {hold_ms};
    const img = document.getElementById("led");
    const meta = document.getElementById("meta");
    let i = 0;
    function tick() {{
      img.src = "data:image/png;base64," + frames[i];
      meta.textContent = "frame " + (i + 1) + " / " + frames.length;
      i = (i + 1) % frames.length;
    }}
    tick();
    setInterval(tick, holdMs);
  </script>
</body>
</html>
""".format(
        width=make_image.OUT_W * scale,
        height=make_image.OUT_H * scale,
        payloads=repr(payloads),
        hold_ms=int(hold_sec * 1000),
    )
    with open(path, "w") as f:
        f.write(html)
    print("Wrote", os.path.abspath(path), "({} frames)".format(len(frames)))


def run_window(frames, scale, hold_sec):
    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except Exception as e:
        print("Tk preview unavailable:", e)
        return False

    scaled = [
        img.resize((make_image.OUT_W * scale, make_image.OUT_H * scale), Image.NEAREST)
        for img in frames
    ]

    root = tk.Tk()
    root.title("LED matrix preview ({}x{})".format(make_image.OUT_W, make_image.OUT_H))
    root.configure(bg="#111111")
    panel = tk.Label(root, bd=8, bg="#050505")
    panel.pack(padx=16, pady=16)
    status = tk.Label(root, fg="#888888", bg="#111111")
    status.pack(pady=(0, 12))

    photos = [ImageTk.PhotoImage(img) for img in scaled]
    state = {"i": 0}

    def tick():
        i = state["i"]
        panel.configure(image=photos[i])
        status.configure(text="frame {} / {}".format(i + 1, len(photos)))
        state["i"] = (i + 1) % len(photos)
        root.after(int(hold_sec * 1000), tick)

    tick()
    print("Close the window to stop.")
    root.mainloop()
    return True


def main():
    args = parse_args()
    skip = args.mode == "skip"
    frames = playback.prepare(playback.load_frames(skip=skip, limit=args.limit))
    if not frames:
        raise SystemExit("no frames to display")

    write_html(frames, args.html, playback.FRAME_HOLD_SEC, args.scale)
    if args.no_window:
        return
    run_window(frames, args.scale, playback.FRAME_HOLD_SEC)


if __name__ == "__main__":
    main()
