from rgbmatrix import RGBMatrix, RGBMatrixOptions
import time
import playback
from PIL import Image, ImageDraw, ImageFont

MAX_EMPTY_RETRY_INTERVAL_SEC = 15 * 60

options = RGBMatrixOptions()
options.show_refresh_rate = 0
options.rows = 32
options.cols = 64
options.drop_privileges = False
options.brightness = 100
options.hardware_mapping = "adafruit-hat-pwm"
# options.limit_refresh_rate_hz = 60
options.pwm_bits = 11

matrix = RGBMatrix(options = options)
canvas = matrix.CreateFrameCanvas()
no_frames_image = Image.new("RGB", (options.cols, options.rows), (0, 0, 0))
status_draw = ImageDraw.Draw(no_frames_image)
status_font = ImageFont.load_default()
status_draw.text((4, 4), "NOAA FEED", fill=(255, 70, 40), font=status_font)
status_draw.text((4, 18), "NO FRAMES", fill=(255, 200, 0), font=status_font)

print("Press CTRL-C to stop.")
empty_retry_interval = playback.REFRESH_INTERVAL_SEC
while True:
    print("loading frames")
    frames = playback.prepare(playback.load_frames())
    if not frames:
        canvas.SetImage(no_frames_image, 0, 0)
        canvas = matrix.SwapOnVSync(canvas)
        print("no frames to display; retrying in {} seconds".format(empty_retry_interval))
        time.sleep(empty_retry_interval)
        empty_retry_interval = min(
            empty_retry_interval * 2,
            MAX_EMPTY_RETRY_INTERVAL_SEC,
        )
        continue

    empty_retry_interval = playback.REFRESH_INTERVAL_SEC
    refresh_deadline = time.monotonic() + playback.REFRESH_INTERVAL_SEC
    while time.monotonic() < refresh_deadline:
        for i, image in enumerate(frames):
            canvas.SetImage(image, 0, 0)
            canvas = matrix.SwapOnVSync(canvas)
            if i == len(frames) - 1:
                time.sleep(playback.FRAME_HOLD_SEC * 3)
            else:
                time.sleep(playback.FRAME_HOLD_SEC)
            if time.monotonic() >= refresh_deadline:
                break
