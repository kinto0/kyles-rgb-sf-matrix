from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
import time
import make_image


options = RGBMatrixOptions()
options.show_refresh_rate = 0
options.rows = 32
options.cols = 64
options.drop_privileges = False
options.brightness = 100
options.hardware_mapping = "adafruit-hat-pwm"
# options.limit_refresh_rate_hz = 60
options.pwm_bits = 3

matrix = RGBMatrix(options = options)

print("Press CTRL-C to stop.")
while True:
    make_image.make()
    image = Image.open('sf_geocolor.png')
    matrix.SetImage(image.convert('RGB'), 0, 0)
    time.sleep(100)
