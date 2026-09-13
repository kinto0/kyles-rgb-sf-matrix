from rgbmatrix import RGBMatrix, RGBMatrixOptions
import time
import playback

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

print("Press CTRL-C to stop.")
while True:
    print("loading frames")
    frames = playback.prepare(playback.load_frames())
    if not frames:
        print("no frames to display")
        time.sleep(5)
        continue

    for _ in range(playback.PLAYS_BEFORE_REFRESH):
        print(f"playing {playback.PLAYS_BEFORE_REFRESH} times")
        for i, image in enumerate(frames):
            print(f"switching frames {i} of {len(frames)}")
            canvas.SetImage(image, 0, 0)
            canvas = matrix.SwapOnVSync(canvas)
            if i == len(frames) - 1:
                time.sleep(playback.FRAME_HOLD_SEC * 3)
            else:
                time.sleep(playback.FRAME_HOLD_SEC)
