#!/usr/bin/env python
import sys
import asyncio
sys.path.append("/home/ken-ichi/rpi-rgb-led-matrix/bindings/python")
#sys.path.append("/home/ken-ichi/rpi-rgb-led-matrix/bindings/python/samples")
#from samplebase import SampleBase
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions

from collections import deque

import serial

serial_port = serial.Serial(port='/dev/ttyACM0', baudrate=115200, parity= 'N', timeout=0.06)


import math
from toio import *

MAT_W_MARGIN = 30
MAT_H_MARGIN = 20
#simple mat
#MAT_TL = Point(98 + MAT_W_MARGIN, 142 + MAT_H_MARGIN)
#MAT_BR = Point(402 - MAT_W_MARGIN, 358 - MAT_H_MARGIN) 
# No. 8 mat
#MAT_TL = Point(340 + MAT_W_MARGIN, 683 + MAT_H_MARGIN)
#MAT_BR = Point(644 - MAT_W_MARGIN, 898 - MAT_H_MARGIN)
# No. 9 mat
MAT_TL = Point(645 + MAT_W_MARGIN, 35 + MAT_H_MARGIN)
MAT_BR = Point(949 - MAT_W_MARGIN, 240 - MAT_H_MARGIN)
# No. 10 mat
#MAT_TL = Point(645 + MAT_W_MARGIN, 251 + MAT_H_MARGIN)
#MAT_BR = Point(949 - MAT_W_MARGIN, 466 - MAT_H_MARGIN)

MAT_WIDTH = MAT_BR.x - MAT_TL.x
MAT_HEIGHT = MAT_BR.y - MAT_TL.y
MAT_CENTER = Point(int(MAT_TL.x + MAT_WIDTH / 2), int(MAT_TL.y + MAT_HEIGHT/2))

FRAME_H = 240
FRAME_W = 320
MAT_SCALE = MAT_WIDTH / FRAME_W

# Configuration for the matrix
options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 3
options.parallel = 1
options.hardware_mapping = 'adafruit-hat'
options.gpio_slowdown= 2
options.pixel_mapper_config='V-mapper:Z'

matrix = RGBMatrix(options = options)
matrix.Clear()
print("matrix", matrix.width, matrix.height)
font = graphics.Font()
font.LoadFont("/home/ken-ichi/rpi-rgb-led-matrix/fonts/7x13.bdf")
offscreen_canvas = matrix.CreateFrameCanvas()
white = graphics.Color(255, 255, 255)
red = graphics.Color(255, 0, 0)
green = graphics.Color(0, 255, 0)
blue = graphics.Color(0, 0, 255)
yellow = graphics.Color(255,255,0)
skyblue = graphics.Color(0x3c, 0x79, 255)

NUMOFCUBES = 3
formation_offset = [[[0, 0], [-50, 0], [50, 0]],
                    [[0, -20], [-30, 20], [30, 20]]
]

formation_mode = 0

cube_names = []

targets_index = [1, 1, 1]
targets = [
    [    
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_TL.x + 50, MAT_TL.y+ 50), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_TL.x + 100, MAT_TL.y + 50), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_CENTER.x - 50, MAT_CENTER.y -50), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_CENTER.x - 50, MAT_CENTER.y +50), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    ],
    [
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_BR.x, MAT_TL.y), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_BR.x - 100, MAT_TL.y), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_CENTER.x + 50, MAT_CENTER.y -50), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    ],
    [
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_TL.x, MAT_BR.y), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_TL.x + 100, MAT_BR.y), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_CENTER.x - 50, MAT_CENTER.y +50), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),        
    ],
]

async def motor_notification_handler(payload: bytearray, info: NotificationHandlerInfo):
    global formation_mode
    global targets_index
    motor_info = Motor.is_my_data(payload)
    #print(info.get_notified_cube().name, type(motor_info), str(motor_info))
    i = cube_names.index(info.get_notified_cube().name)
    print("notify index ", i, motor_info.request_id, motor_info.response_code, "formation_mode ", formation_mode)

    if formation_mode > 1:
        if motor_info.response_code == MotorResponseCode.SUCCESS or motor_info.response_code == MotorResponseCode.SUCCESS_WITH_OVERWRITE:
            print("targets_index", targets_index[i], " ", len(targets[i]))
            if targets_index[i] >= len(targets[i]):
                print("reached to final target.")
                targets_index[i] = 1 # reset index
                reached_num = 0
                for j in range(NUMOFCUBES):
                    if targets_index[j] == 1:
                        reached_num = reached_num + 1
                if reached_num == NUMOFCUBES  :
                    print("all cubes reached final target.")
                    formation_mode = 0
                return
            targets_index[i] = targets_index[i] + 1
            next_target = targets[i][targets_index[i]:targets_index[i]+1]
            print("next_target ", targets_index[i], " ", next_target)
            await cubes[i].api.motor.motor_control_multiple_targets(
                timeout=5,
                movement_type=MovementType.Linear,
                speed=Speed(
                    max=70, speed_change_type=SpeedChangeType.AccelerationAndDeceleration
                ),
                mode=WriteMode.Append,
                target_list=next_target,
            )
            print("append next_target")
        elif motor_info.response_code == MotorResponseCode.ERROR_TIMEOUT:
            print("multiple target timeout")
            formation_mode = 0
        elif motor_info.response_code == MotorResponseCode.ERROR_ID_MISSED:
            print("multiple target id missed")
            formation_mode = 0
        elif motor_info.response_code == MotorResponseCode.ERROR_FAILED_TO_APPEND:
            print("multiple target append fail")
            formation_mode = 0
        else :
            print("multiple target unknown error", motor_info.response_code)
            formation_mode = 0
    if motor_info.response_code == MotorResponseCode.ERROR_ID_MISSED: # しわのうえ？
        await cubes[i].api.motor.motor_control(50, 50, 10) # ちょっと移動

def convToMatPos(screen : Point):
    scale = MAT_WIDTH/FRAME_W
    mat_x = screen.x * scale + MAT_TL.x
    #mat_x = MAT_BR.x - screen.x * scale
    mat_y = screen.y * scale + MAT_TL.y
    return Point(mat_x, mat_y)

def convToLEDPos(x, y):
    matrix_x = matrix.width * y / 240
    matrix_x = matrix.width - matrix_x
    matrix_y = matrix.height * x / 320
    return Point(matrix_x, matrix_y)

def convMatPosToLEDPos(matpoint : Point):
    y = matpoint.x - MAT_TL.x
    x = matpoint.y - MAT_TL.y
    matrix_x = x * matrix.width / MAT_HEIGHT
    matrix_x = matrix.width - matrix_x
    matrix_y = y * matrix.height / MAT_WIDTH
    return Point(matrix_x, matrix_y)

speed = 0
def idinformation_notification_handler(payload: bytearray, info: NotificationHandlerInfo):
    global offscreen_canvas, green
    id_info = IdInformation.is_my_data(payload)
    #print(info.get_notified_cube().name, str(id_info))
    i = cube_names.index(info.get_notified_cube().name)
    if type(id_info) == PositionIdMissed:
        print("position missed")
        return
    led_pos = convMatPosToLEDPos(id_info.center.point)
    #print("led_pos", led_pos)
    #graphics.DrawCircle(offscreen_canvas, int(led_pos.x), int(led_pos.y), 5, green)
    '''
    if speed > 0:
        s = speed / 5
        hx = int(s * math.cos(math.radians(id_info.center.angle - 90)))  # +90 forward -90 backward
        hy = int(s * math.sin(math.radians(id_info.center.angle - 90))) 
        graphics.DrawLine(offscreen_canvas, led_pos.x, led_pos.y, led_pos.x + hx, led_pos.y + hy, blue)
    '''



cubes = []
async def connectCube():
    global cubes
    global cube_names
    try:
        cube_list = await BLEScanner.scan(num=NUMOFCUBES)
        #cube_list = await BLEScanner.scan_with_id( ["toio-L1L",  "toio-h3e", "toio-i6k", "toio-m1T"], "local_name")
        print("scan complete")
        print("found ", len(cube_list), "cubes")
        assert len(cube_list) == NUMOFCUBES
        #cube_name = ("first", "second", "third", "fourth")
        cubes = MultipleToioCoreCubes(cube_list)
        await cubes.connect()
        print("connected", len(cubes), "cubes")
        assert len(cubes) == NUMOFCUBES
        cube_names = []
        for i in range(NUMOFCUBES):
            print(i, ":", cubes[i].name)
            cube_names.append(cubes[i].name)
            await cubes[i].api.motor.register_notification_handler(motor_notification_handler)
            # await cubes[i].api.id_information.register_notification_handler(idinformation_notification_handler)
    except:
        print("cannot connect cubes")


async def moveCubes(px, py, spd, deg):
    global cubes
    if px < MAT_TL.x :
        px = MAT_TL.x
    if  px > MAT_BR.x :
        px = MAT_BR.x
    if  py < MAT_TL.y :
        py = MAT_TL.y
    if py > MAT_BR.y:
        py = MAT_BR.y
    formation = 1
    rad = math.radians(-deg)
    for i in range(NUMOFCUBES):
        #x = formation_offset[formation][i][0]
        #y = formation_offset[formation][i][1]
        x = int(formation_offset[formation][i][0] * math.cos(rad) - formation_offset[formation][i][1] * math.sin(rad))
        y = int(formation_offset[formation][i][0] * math.sin(rad) + formation_offset[formation][i][1] * math.cos(rad))
        await cubes[i].api.motor.motor_control_target(
            timeout=5,
            movement_type=MovementType.Linear,
            speed=Speed(
                max=spd, speed_change_type=SpeedChangeType.Constant
            ),
            target=TargetPosition(
                cube_location=CubeLocation(point=Point(px + x, py + y,), angle=deg),
                rotation_option=RotationOption.WithoutRotation,
            ),
        )

async def moveFormation():
    for i in range(NUMOFCUBES):
        first_targets = targets[i][0:2]
        await cubes[i].api.motor.motor_control_multiple_targets(
            timeout=5,
            movement_type=MovementType.Linear,
            speed=Speed(
                max=50, speed_change_type=SpeedChangeType.AccelerationAndDeceleration
            ),
            mode=WriteMode.Append,
            target_list=first_targets,
        )

async def moveCircle():
    global formation_mode
    await cubes[0].api.motor.motor_control_target(    
        timeout=5,
        movement_type=MovementType.Linear,
        speed=Speed(
            max=70, speed_change_type=SpeedChangeType.Constant
        ),
        target=TargetPosition(
            cube_location=CubeLocation(point=MAT_CENTER, angle=90),
            rotation_option=RotationOption.WithoutRotation,
            ),
    )
    await asyncio.sleep(3)
    await cubes[0].api.motor.motor_control(50, 0)
    await asyncio.sleep(3)
    await cubes[0].api.motor.motor_control(0, 0)
    formation_mode = 0

    print("exit formation_mode circle")

smoke_vector_queue = deque([], 10)
smoke_point_queue = deque([], 10)
def updateSmokePos():
    for i in range(len(smoke_vector_queue)):
        smoke_point_queue[i] = smoke_point_queue[i] + smoke_vector_queue[i] * 3
    

async def main():
    global offscreen_canvas, white, red, yellow, blue, green
    global speed

    tcommand = 'T'
    tcommand = tcommand.encode('utf-8')
    serial_port.write(tcommand)
    
    #palmpos_queue = deque()

    global cubes
    global formation_mode
    await connectCube()
    prev_pos = MAT_CENTER

    prev_gesture_type = 0
    gesture_hold_frame = 0
    current_gesture_type = 0
    while True:
        data=serial_port.readline() 
        data=data.decode('utf-8')
        data.strip
        data.rstrip
        params = data.split(',')
        if len(params) == 0 :
            continue
        params[0].strip
        params[0].rstrip
        if params[0] == '':
            print('serial null')
            continue
        palm_valid = int(params[0])
        palm_x = int(params[1])
        palm_y = int(params[2])
        palm_radian = int(params[3])
        palm_brightness = int(params[4])
        rotation = int(params[5])
        gesture_type = int(params[6])
        cursor_type = int(params[7])
        select = int(params[8])
        #print(params)
        offscreen_canvas.Clear()
        #offscreen_canvas.Fill(0x3c, 0x79, 255)
        #draw smoke
        if gesture_type == prev_gesture_type:
            gesture_hold_frame = gesture_hold_frame + 1
            if gesture_hold_frame > 10:
                current_gesture_type = gesture_type
                gesture_hold_frame = 0
        else:
            gesture_hold_frame = 0
        prev_gesture_type = gesture_type
        if current_gesture_type == 1: 
            for i in range(1):
                read_data = await cubes[i].api.id_information.read()
                if type(read_data) == PositionId:
                    smoke_v = Point(math.cos(math.radians(read_data.center.angle - 90)), math.sin(math.radians(read_data.center.angle - 90)))
                    smoke_vector_queue.append(smoke_v)
                    led_pos = convMatPosToLEDPos( read_data.center.point)
                    smoke_point_queue.append(led_pos)
        #elif current_gesture_type == 3 and formation_mode == 0:
        #    formation_mode = 1
        #    print("enter formation_mode 1 circle")
        #    tasks = [moveCircle()]
        #    await asyncio.gather(*tasks)
        #print("current gesture type", current_gesture_type, " ", formation_mode)
        updateSmokePos()
        for s in smoke_point_queue: # smoke
            graphics.DrawCircle(offscreen_canvas, s.x, s.y, 1, white)
        if palm_valid and formation_mode == 0:
            pos = Point(palm_x, palm_y)
            target_pos = convToMatPos(pos)
            #print(target_pos)
            delta = target_pos.distance(prev_pos)
            #if delta < 5.0  and abs(prev_degree - degree) % 360 < 3.0:
            if delta > 5.0:
                #print(delta)
                read_data = await cubes[0].api.id_information.read()
                if type(read_data) == PositionId:
                    current_pos = read_data.center.point
                    formation = 0
                    current_pos = current_pos - Point(formation_offset[formation][0][0], formation_offset[formation][0][1])
                    distance = target_pos.distance(current_pos)
                    #print("distance ", distance)
                    degree = math.atan2(target_pos.y - current_pos.y, target_pos.x - current_pos.x)
                    degree = math.degrees(degree)
                    #print("degree", degree)
                    led_pos = convMatPosToLEDPos(current_pos)
                    #print("led_pos ", led_pos)
                    #graphics.DrawCircle(offscreen_canvas, led_pos.x, led_pos.y, 5, green)
                    #hx = int(20 * math.cos(math.radians(read_data.center.angle + 90)))  # +90 forward -90 backward
                    #hy = int(20 * math.sin(math.radians(read_data.center.angle + 90))) 
                    #graphics.DrawLine(offscreen_canvas, led_pos.x, led_pos.y, led_pos.x + hx, led_pos.y + hy, blue)
                else:
                    #print("ID lost")
                    distance = 0.0
                #print(distance)
                prev_pos = target_pos
                #prev_degree = degree
                #speed = distance * 0.8
                speed = delta * 6
                if speed > 60:
                    speed = 60
                elif speed > 50:
                    speed = 50
                elif speed > 40:
                    speed = 40
                elif speed > 30:
                    speed = 30
                elif speed > 20:
                    speed = 20
                else:
                    speed = 15
                #speed = speed - (speed % 25)
                #print(int(target_pos.x), int(target_pos.y), int(degree), "speed", int(speed) )
                degree = 0
                await moveCubes(int(target_pos.x), int(target_pos.y), int(speed), int(degree))

        '''
        if palm_valid :
            ppoint  = convToLEDPos(palm_x, palm_y)
            #print(ppoint)
            palmpos_queue.append(ppoint)
        if len(palmpos_queue) > 5:
            palmpos_queue.popleft()
        for p in palmpos_queue:
            graphics.DrawCircle(offscreen_canvas, p.x, p.y, 2, yellow) # palm pos
        '''
        if palm_valid :
            ppoint  = convToLEDPos(palm_x, palm_y)
            if formation_mode > 0:
                graphics.DrawCircle(offscreen_canvas, ppoint.x, ppoint.y, 2, green) # palm pos
            else:
                graphics.DrawCircle(offscreen_canvas, ppoint.x, ppoint.y, 2, yellow) # palm pos

            if len(params) > 8 : # has tip info
                for i in range(5):
                    if int(params[12 +i*4]) > 0:
                        tpoint = convToLEDPos(int(params[10 +i*4]), int(params[11 +i*4]))
                        graphics.DrawCircle(offscreen_canvas, tpoint.x, tpoint.y, 1, red)
        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

asyncio.run(main())
