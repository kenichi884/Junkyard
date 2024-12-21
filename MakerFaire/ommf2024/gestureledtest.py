#!/usr/bin/env python
import sys
import asyncio
sys.path.append("/home/ken-ichi/rpi-rgb-led-matrix/bindings/python")
#sys.path.append("/home/ken-ichi/rpi-rgb-led-matrix/bindings/python/samples")
#from samplebase import SampleBase
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions

from collections import deque

import serial

serial_port = serial.Serial(port='/dev/ttyACM0', baudrate=9600, parity= 'N')

# Configuration for the matrix
options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 3
options.parallel = 1
options.hardware_mapping = 'adafruit-hat'
options.gpio_slowdown= 4
options.pixel_mapper_config='V-mapper:Z'

matrix = RGBMatrix(options = options)

def convPos(x, y):
    matrix_x = matrix.width * y / 240
    matrix_x = matrix.width - matrix_x
    matrix_y = matrix.height * x / 320
    return matrix_x, matrix_y

async def main():
    matrix.Clear()
    print("matrix", matrix.width, matrix.height)
    font = graphics.Font()
    font.LoadFont("/home/ken-ichi/rpi-rgb-led-matrix/fonts/7x13.bdf")
    offscreen_canvas = matrix.CreateFrameCanvas()
    white = graphics.Color(255, 255, 255)
    red = graphics.Color(255, 0, 0)
    green = graphics.Color(0, 255, 0)

    tcommand = 'T'
    tcommand = tcommand.encode('utf-8')
    serial_port.write(tcommand)
    
    pos_queue = deque()

    
    while True:
        data=serial_port.readline() 
        data=data.rstrip()
        data=data.decode('utf-8')
        params = data.split(',')
        palm_valid = int(params[0])
        palm_x = int(params[1])
        palm_y = int(params[2])
        palm_radian = int(params[3])
        palm_brightness = int(params[4])
        rotation = int(params[5])
        gesture_type = int(params[6])
        cursor_type = int(params[7])
        select = int(params[8])
        print(params)
            
        
        offscreen_canvas.Clear()
        if palm_valid :
            x , y = convPos(palm_x, palm_y)
            print(x, y)
            pos_queue.append([x, y])
        if len(pos_queue) > 5:
            pos_queue.popleft()
        for p in pos_queue:
            graphics.DrawCircle(offscreen_canvas, p[0], p[1], 2, white)
        if len(params) > 8 : # has tip info
            for i in range(5):
                if int(params[12 +i*4]) > 0:
                    x, y = convPos(int(params[10 +i*4]), int(params[11 +i*4]))
                    graphics.DrawCircle(offscreen_canvas, x, y, 1, red)
        
        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

asyncio.run(main())