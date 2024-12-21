import zmq
import math

import asyncio

from toio import *

MAT_MARGIN = 40
#simple mat
#MAT_TL = (98, 142)
#MAT_BR = (402, 358)
# dev.mat #11 #12
MAT_TL = Point(645 + MAT_MARGIN, 467 + MAT_MARGIN)
MAT_BR = Point(949 - MAT_MARGIN, 898 - MAT_MARGIN)
MAT_WIDTH = MAT_BR.x - MAT_TL.x
MAT_HEIGHT = MAT_BR.y - MAT_TL.y
MAT_CENTER = Point(int(MAT_TL.x + MAT_WIDTH / 2), int(MAT_TL.y + MAT_HEIGHT/2))

FRAME_H = 648
FRAME_W = 1152
MAT_SCALE = MAT_WIDTH / FRAME_W

formation_offset = [[[-50, 0], [0, -50], [0, 50], [50, 0]],
                    [[-60, 0], [-20, 0], [20, 0], [60, 0]]
]

formation_mode = 0

cube_names = []

targets_index = [1, 1, 1, 1]
targets = [
    [    
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_TL.x, MAT_TL.y), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_TL.x + 100, MAT_TL.y), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_CENTER.x - 50, MAT_CENTER.y -50), angle=0),
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
    [
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_BR.x, MAT_BR.y), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_BR.x - 100, MAT_BR.y), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),
    TargetPosition(
        cube_location=CubeLocation(point=Point(MAT_CENTER.x + 50, MAT_CENTER.y +50), angle=0),
        rotation_option=RotationOption.WithoutRotation,
    ),        
    ]
]

async def notification_handler(payload: bytearray, info: NotificationHandlerInfo):
    global formation_mode
    global targets_index
    motor_info = Motor.is_my_data(payload)
    #print(info.get_notified_cube().name, type(motor_info), str(motor_info))
    i = cube_names.index(info.get_notified_cube().name)
    print("notify index ", i, motor_info.request_id, motor_info.response_code)
    if formation_mode > 0:
        if motor_info.response_code == MotorResponseCode.SUCCESS:
            if targets_index[i] >= len(targets[i]):
                print("reached to final target.")
                targets_index[i] = 1 # reset index
                reached_num = 0
                for j in range(4):
                    if targets_index[j] == 1:
                        reached_num = reached_num + 1
                if reached_num == 4 :
                    print("all cubes reached final target.")
                    formation_mode = 0
                return
            targets_index[i] = targets_index[i] + 1
            next_target = targets[i][targets_index[i]:targets_index[i]+1]
            await cubes[i].api.motor.motor_control_multiple_targets(
                timeout=5,
                movement_type=MovementType.Linear,
                speed=Speed(
                    max=50, speed_change_type=SpeedChangeType.AccelerationAndDeceleration
                ),
                mode=WriteMode.Append,
                target_list=next_target,
            )
        elif motor_info.response_code == MotorResponseCode.ERROR_TIMEOUT:
            print("multiple target timeout")
            formation_mode = 0


cubes = []
async def connectCube():
    global cubes
    global cube_names
    try:
        #cube_list = await BLEScanner.scan(num=4)
        cube_list = await BLEScanner.scan_with_id( ["toio-L1L",  "toio-h3e", "toio-i6k", "toio-m1T"], "local_name")
        print("scan complete")
        print("found ", len(cube_list), "cubes")
        assert len(cube_list) == 4
        cube_name = ("first", "second", "third", "fourth")
        cubes = MultipleToioCoreCubes(cube_list, cube_name)
        await cubes.connect()
        print("connected", len(cubes), "cubes")
        assert len(cubes) == 4
        cube_names = []
        for i in range(4):
            print(i, ":", cubes[i].name)
            cube_names.append(cubes[i].name)
            await cubes[i].api.motor.register_notification_handler(notification_handler)
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
    formation = 0
    rad = math.radians(-deg)
    for i in range(4):
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
    for i in range(4):
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

def convToMatPos(screen : Point):
    if MAT_HEIGHT > MAT_WIDTH : # rotate
        scale = MAT_HEIGHT/FRAME_W
        mat_y = screen.x * scale + MAT_TL.y
        mat_x = screen.y * scale + MAT_TL.x
        #print(mat_x, mat_y)
    else :
        scale = MAT_WIDTH/FRAME_W
        mat_x = screen.x * scale + MAT_TL.x
        mat_y = screen.y * scale + MAT_TL.y
    return Point(mat_x, mat_y)


context = zmq.Context.instance()
socket = context.socket(zmq.SUB)
socket.connect("ipc://aaa")
socket.subscribe('hand/')


async def main():
    global cubes
    global formation_mode
    await connectCube()
    prev_pos = MAT_CENTER
    prev_degree = 0
    while True:
        topic = socket.recv_string()
        if topic == "hand/position" and formation_mode == 0:
            (x, y, degree) = socket.recv_pyobj()
            pos = Point(x, y)
            target_pos = convToMatPos(pos)
            delta = target_pos.distance(prev_pos)
            if delta < 5.0  and abs(prev_degree - degree) % 360 < 3.0:
                continue
            print(delta)
            read_data = await cubes[0].api.id_information.read()
            if type(read_data) == PositionId:
                current_pos = read_data.center.point
                formation = 0
                current_pos = current_pos - Point(formation_offset[formation][0][0], formation_offset[formation][0][1])
                distance = target_pos.distance(current_pos)
                #print("distance ", distance)
            else:
                #print("ID lost")
                distance = 0.0
            #print(distance)
            prev_pos = target_pos
            prev_degree = degree
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
            print(int(target_pos.x), int(target_pos.y), int(degree), "speed", int(speed) )
            await moveCubes(int(target_pos.x), int(target_pos.y), int(speed), int(degree))
        elif topic == "hand/gesture":
            gesture = socket.recv_pyobj()
            print("gesture ", gesture)
            if gesture == "2enter":
                formation_mode = 1
                await moveFormation()


asyncio.run(main())

