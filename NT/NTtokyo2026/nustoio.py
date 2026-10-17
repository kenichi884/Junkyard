
import platform
import logging
import asyncio
from bleak import BleakScanner, BleakClient
from bleak import _logger as logger
from bleak.uuids import uuid16_dict
from toio import *
import zmq
import zmq.asyncio  # zmqのasyncioサポートをインポート
from enum import Enum
import time
import random
import math

#ZZCUBE_ID = {"E0N", "f5r", "i6k"}
CUBE_ID = {"H9M", "h3e", "m1T"}

# 117 160   383 162
# 116 336   383 338

MAT_W_MARGIN = 20 # 25
MAT_H_MARGIN = 20 # 
#simple mat
#MAT_TL = Point(98 + MAT_W_MARGIN, 142 + MAT_H_MARGIN)
#MAT_BR = Point(402 - MAT_W_MARGIN, 358 - MAT_H_MARGIN) 
# No. 8 mat
MAT_TL = Point(340 + MAT_W_MARGIN, 683 + MAT_H_MARGIN)
MAT_BR = Point(644 - MAT_W_MARGIN, 898 - MAT_H_MARGIN)
# No. 9 mat
#MAT_TL = Point(645 + MAT_W_MARGIN, 35 + MAT_H_MARGIN)
#MAT_BR = Point(949 - MAT_W_MARGIN, 250 - MAT_H_MARGIN)
# No. 10 mat
#MAT_TL = Point(645 + MAT_W_MARGIN, 251 + MAT_H_MARGIN)
#MAT_BR = Point(949 - MAT_W_MARGIN, 466 - MAT_H_MARGIN)

MAT_WIDTH = MAT_BR.x - MAT_TL.x
MAT_HEIGHT = MAT_BR.y - MAT_TL.y
MAT_CENTER = Point(int(MAT_TL.x + MAT_WIDTH / 2), int(MAT_TL.y + MAT_HEIGHT/2))

class State(Enum):
    POSITIONING = 0
    OPERATING = 1
    GAMEOVER = 2

status = State.OPERATING


UART_TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e" #Nordic NUS characteristic for TX
UART_RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e" #Nordic NUS characteristic for RX

dataFlag = False #global flag to check for new data


MIN_SPEED = 40
NUMOFCUBES = 3
cube_names = []
cubes = []
cubes_point = [Point(0, 0), Point(0, 0), Point(0, 0)]

#context = zmq.Context.instance()
context = zmq.asyncio.Context()
send_socket = context.socket(zmq.PUB) # send to LEDmatrix
send_socket.bind("ipc:///tmp/toio_notify")
recv_socket = context.socket(zmq.SUB)
recv_socket.connect("ipc:///tmp/event") # recv from ledmatrix.py (CUT event)
recv_socket.subscribe('event/')

sword_location = CubeLocation((0,0))

RGBMATRIX_WIDTH = 64
RGBMATRIX_HEIGHT = 96
ratioX = RGBMATRIX_HEIGHT / MAT_WIDTH
ratioY =  RGBMATRIX_WIDTH / MAT_HEIGHT
def convPoint(cubeX, cubeY):
    x = int((cubeX - MAT_TL.x) * ratioX)
    y = int((cubeY - MAT_TL.y) * ratioY)
    return RGBMATRIX_WIDTH - y, x

g1_moving = False
g2_moving = False
g_moving_count = 0
async def motor_notification_handler(payload: bytearray, info: NotificationHandlerInfo):
    global status
    global g1_moving, g2_moving, g_moving_count
    global send_socket
    global repositioning_start_time
    motor_info = Motor.is_my_data(payload)
    i = cube_names.index(info.get_notified_cube().name)
    print("motor notify index ", i, motor_info.request_id, motor_info.response_code)
    #  MotorResponseCode.ERROR_ID_MISSED のときどうする？
    # SUCCESS = 0x00
    # ERROR_TIMEOUT = 0x01
    # ERROR_ID_MISSED = 0x02
    # ERROR_INVALID_PARAMETER = 0x03
    # ERROR_INVALID_CUBE_STATE = 0x04
    # SUCCESS_WITH_OVERWRITE = 0x05
    # ERROR_NOT_SUPPORTED = 0x06
    # ERROR_FAILED_TO_APPEND = 0x07
    
    if (i == 1 and g1_moving == True and 
        (motor_info.response_code == MotorResponseCode.SUCCESS or
         motor_info.response_code == MotorResponseCode.ERROR_TIMEOUT or
         motor_info.response_code == MotorResponseCode.SUCCESS_WITH_OVERWRITE or
         motor_info.response_code == MotorResponseCode.ERROR_ID_MISSED
        )):
        g_moving_count = g_moving_count + 1
        g1_moving = False
    if (i == 2 and g2_moving == True and
        (motor_info.response_code == MotorResponseCode.SUCCESS or
         motor_info.response_code == MotorResponseCode.ERROR_TIMEOUT or
         motor_info.response_code == MotorResponseCode.SUCCESS_WITH_OVERWRITE or
         motor_info.response_code == MotorResponseCode.ERROR_ID_MISSED
        )):
        g_moving_count = g_moving_count + 1
        g2_moving = False
    if g_moving_count > 1:  # 2つのgateが移動を終えたときにoperatingに遷移
        status = State.OPERATING
        await send_socket.send_string("status", zmq.SNDMORE)
        await send_socket.send_pyobj("operating")
        print("send socket status/operating")
        g_moving_count = 0
        repositioning_start_time = 0
    '''
    # gate のどちらかが移動を終えたときにoperatingに遷移
    if i != 0 and status == State.POSITIONING and motor_info.response_code ==  MotorResponseCode.SUCCESS:
        status = State.OPERATING
        await send_socket.send_string("status", zmq.SNDMORE)
        await send_socket.send_pyobj("operating")
        print("send socket status/operating")
        '''

async def idinformation_notification_handler(payload: bytearray, info: NotificationHandlerInfo):
    global sword_location, cubes_point
    global status
    global send_socket
    #ZMQでNotificationHandlerInfo投げる
    id_info = IdInformation.is_my_data(payload)
    i = cube_names.index(info.get_notified_cube().name)
    x = 0
    y = 0
    angle = 0
    if type(id_info) == PositionIdMissed:
        x = 0
        y = 0
        angle = 0
        cubes_point[i] = Point(0, 0)
    else:
        cubes_point[i] = id_info.center.point
        x, y = convPoint(id_info.center.point.x, id_info.center.point.y)
        angle = id_info.center.angle
    if i==0:
        if type(id_info) == PositionIdMissed:
            sword_location.point = Point(0, 0)
        else:
            sword_location.point = id_info.center.point
            sword_location.angle = id_info.center.angle
    #print(i, info.get_notified_cube().name, str(id_info))
    # 常におくってはいけないか？
    if status != State.POSITIONING:
        await send_socket.send_string("cube/position", zmq.SNDMORE)
        await send_socket.send_pyobj((i, x, y, angle))

async def button_notification_handler(payload: bytearray, info: NotificationHandlerInfo):
    global cubes, cubes_point
    button_info = Button.is_my_data(payload)
    i = cube_names.index(info.get_notified_cube().name)
    print("button notify index ", i, button_info)
    if button_info.state == ButtonState.RELEASED:
        print(i, ":", cubes_point[i])



async def connectCube():
    global cubes
    global cube_names
    try:
        #cube_list = await BLEScanner.scan(num=NUMOFCUBES)
        #cube_list = await BLEScanner.scan_with_id( cube_id = {"E0N", "i6k", "f5r"}, sort = "local_name")
        cube_list = await BLEScanner.scan_with_id( cube_id = CUBE_ID, sort = "local_name")
        print("scan complete")
        print("found ", len(cube_list), "cubes")
        assert len(cube_list) == NUMOFCUBES
        #cube_name = ("cutter", "dimos", "fobos")
        #cubes = MultipleToioCoreCubes(cube_list, names=cube_name)
        cubes = MultipleToioCoreCubes(cube_list)
        await cubes.connect()
        print("connected", len(cubes), "cubes")
        assert len(cubes) == NUMOFCUBES
        cube_names = []
        for i in range(NUMOFCUBES):
            print(i, ":", cubes[i].name)
            cube_names.append(cubes[i].name)
            await cubes[i].api.motor.register_notification_handler(motor_notification_handler)
            await cubes[i].api.id_information.register_notification_handler(idinformation_notification_handler)
            await cubes[i].api.button.register_notification_handler(button_notification_handler)
    except:
        print("cannot connect cubes")

async def nus_notification_handler(sender, data):
    global sword_location
    global send_socket
    #print("{0}: {1}".format(sender, data))
    args = data.split()
    cmd = args[0].decode()
    if status == State.OPERATING: # repositioning　とgame overのときは動かない
        if(cmd == "ANGLE"):
            param1 = args[1].decode()
            degree = int(param1)
            print(cmd, degree)
            await cubes[0].api.motor.motor_control_target(
                timeout = 3, 
                movement_type = MovementType.Curve,
                speed =  Speed(max=50, speed_change_type=SpeedChangeType.AccelerationAndDeceleration),
                target=TargetPosition(
                    cube_location=CubeLocation(point=Point(sword_location.point.x, sword_location.point.y), angle= degree),
                    rotation_option=RotationOption.AbsoluteOptimal))
        elif(cmd == "FWD"):
            param1 = args[1].decode()
            speed  = int(param1)
            if speed < MIN_SPEED:
                speed = MIN_SPEED
            print(cmd, speed)
            await send_socket.send_string("cube/start", zmq.SNDMORE)
            print("sdl ", sword_location)
            x, y = convPoint(sword_location.point.x, sword_location.point.y)
            await send_socket.send_pyobj(CubeLocation(point = Point(x, y), angle = sword_location.angle))
            await cubes[0].api.motor.motor_control(speed, speed, 500)
        elif(cmd == "BACK"):
            param1 = args[1].decode()
            speed  = int(param1)
            if speed < MIN_SPEED:
                speed = MIN_SPEED
            print(cmd, speed)
            await send_socket.send_string("cube/start", zmq.SNDMORE)
            x, y = convPoint(sword_location.point.x, sword_location.point.y)
            await send_socket.send_pyobj(CubeLocation(point = Point(x, y), angle = sword_location.angle))
            await cubes[0].api.motor.motor_control(- speed, - speed, 300)
    global dataFlag
    dataFlag = True

#not used
async def recv_zmq():
    global recv_socket
    while True:
        topic = await recv_socket.recv_string()
        print(topic)
        # await asyncio.sleep(0.01)

def calc_new_point(p : Point):
    if p.x > MAT_CENTER.x:
        x1 = MAT_CENTER.x
        x2 = p.x
    else:
        x1 = p.x
        x2 = MAT_CENTER.x
    if p.y > MAT_CENTER.y:
        y1 = MAT_CENTER.y
        y2 = p.y
    else:
        y1 = p.y
        y2 = MAT_CENTER.y 
    return Point(random.randint(x1, x2), random.randint(y1, y2))

def calc_new_positions(p1 :Point, p2 :Point):
    d = 0
    while d < 60:
        next_p1 = calc_new_point(p1)
        next_p2 = calc_new_point(p2)
        d = next_p1.distance(next_p2)
        print("distance ", d)
    return next_p1, next_p2


REPOSITIONING_TIME_LIMIT = 8 #sec

async def repositioning_timer():
    global status
    global send_socket
    global g_moving_count
    await asyncio.sleep(REPOSITIONING_TIME_LIMIT )
    if status == State.POSITIONING:
        # motor のターゲット移動notifyが来なかったときの救済措置　　Operationgに移行
        status = State.OPERATING
        await send_socket.send_string("status", zmq.SNDMORE)
        await send_socket.send_pyobj("operating")
        print("send socket status/operating")
        g_moving_count = 0

# CUT発生時、１秒回ってから次の場所に移動
async def repositioning():
    global status
    global g1_moving, g2_moving
    global send_socket
    status = State.POSITIONING
    repositioning_timer_task = asyncio.create_task(repositioning_timer())
    #await repositioning_timer_task
    await send_socket.send_string("status", zmq.SNDMORE)
    await send_socket.send_pyobj("positioning")
    speed = 70
    await cubes[1].api.motor.motor_control(- speed, speed, 900)
    await cubes[2].api.motor.motor_control(speed, - speed, 900)
    await asyncio.sleep(1.0)

    if cubes_point[1].y < cubes_point[2].y :
        if cubes_point[1].x < MAT_CENTER.x:
            next_point1, next_point2 = calc_new_positions(Point(MAT_BR.x, MAT_TL.y), Point(MAT_BR.x, MAT_BR.y))
            #next_point1 =Point(random.randint(MAT_CENTER.x, MAT_BR.x), random.randint(MAT_TL.y, MAT_CENTER.y))  
            #next_point2 =Point(random.randint(MAT_CENTER.x, MAT_BR.x), random.randint(MAT_CENTER.y, MAT_BR.y))  
        else:
            next_point1, next_point2 = calc_new_positions(Point(MAT_TL.x, MAT_TL.y), Point(MAT_TL.x, MAT_BR.y))
            #next_point1 =Point(random.randint(MAT_TL.x, MAT_CENTER.x), random.randint(MAT_TL.y, MAT_CENTER.y))  
            #next_point2 =Point(random.randint(MAT_TL.x, MAT_CENTER.x), random.randint(MAT_CENTER.y, MAT_BR.y)) 
        vector1 = next_point1 - next_point2
        vector2 = next_point2 - next_point1
        angle1 = int(math.degrees(math.atan2(vector1.y, vector1.x)))
        angle2 = int(math.degrees(math.atan2(vector2.y, vector2.x)))
        if angle1 < 0:
            angle1 = angle1 + 360
        if angle2 < 0:
            angle2 = angle2 + 360
        
        print("reposition angle ", angle1, angle2)
        tgt1=[
            TargetPosition(cube_location=CubeLocation(point=Point(cubes_point[1].x, MAT_TL.y)),
                        rotation_option=RotationOption.AbsoluteOptimal),
            TargetPosition(cube_location=CubeLocation(point=next_point1, angle = angle1),
                    rotation_option=RotationOption.AbsoluteOptimal)]
        tgt2=[
            TargetPosition(cube_location=CubeLocation(point=Point(cubes_point[2].x, MAT_BR.y)),
                        rotation_option=RotationOption.AbsoluteOptimal),
            TargetPosition(cube_location=CubeLocation(point=next_point2, angle = angle2),
                    rotation_option=RotationOption.AbsoluteOptimal)]            
    else:
        if cubes_point[1].x < MAT_CENTER.x:
            next_point1, next_point2 = calc_new_positions(Point(MAT_BR.x, MAT_BR.y), Point(MAT_BR.x, MAT_TL.y))
            #next_point1 =Point(random.randint(MAT_CENTER.x, MAT_BR.x), random.randint(MAT_CENTER.y, MAT_BR.y))  
            #next_point2 =Point(random.randint(MAT_CENTER.x, MAT_BR.x), random.randint(MAT_TL.y, MAT_CENTER.y))  
        else:
            next_point1, next_point2 = calc_new_positions(Point(MAT_TL.x, MAT_BR.y), Point(MAT_TL.x, MAT_TL.y))
            #next_point1 =Point(random.randint(MAT_TL.x, MAT_CENTER.x), random.randint(MAT_CENTER.y, MAT_BR.y))  
            #next_point2 =Point(random.randint(MAT_TL.x, MAT_CENTER.x), random.randint(MAT_TL.y, MAT_CENTER.y)) 
        vector1 = next_point1 - next_point2
        vector2 = next_point2 - next_point1
        angle1 = int(math.degrees(math.atan2(vector1.y, vector1.x)))
        angle2 = int(math.degrees(math.atan2(vector2.y, vector2.x)))
        if angle1 < 0:
            angle1 = angle1 + 360
        if angle2 < 0:
            angle2 = angle2 + 360
        print("reposition angle ", angle1, angle2)
        tgt1=[
            TargetPosition(cube_location=CubeLocation(point=Point(cubes_point[1].x, MAT_BR.y)),
                        rotation_option=RotationOption.AbsoluteOptimal),
            TargetPosition(cube_location=CubeLocation(point=next_point1, angle = angle1),
                        rotation_option=RotationOption.AbsoluteOptimal)]
        tgt2=[
            TargetPosition(cube_location=CubeLocation(point=Point(cubes_point[2].x, MAT_TL.y)),
                        rotation_option=RotationOption.AbsoluteOptimal),
                        TargetPosition(cube_location=CubeLocation(point=next_point2, angle = angle2),
                        rotation_option=RotationOption.AbsoluteOptimal)]     
    '''
    await cubes[1].api.motor.motor_control_target(
                timeout = 3, 
                movement_type = MovementType.Curve,
                speed =  Speed(max=50, speed_change_type=SpeedChangeType.AccelerationAndDeceleration),
                target = tgt1)
    await cubes[2].api.motor.motor_control_target(
                timeout = 3, 
                movement_type = MovementType.Curve,
                speed =  Speed(max=50, speed_change_type=SpeedChangeType.AccelerationAndDeceleration),
                target = tgt2)
    '''
    # swordがマットの端にいる場合、gateのどちらかが当たるので、ずらす
    if cubes_point[0].y < (MAT_TL.y + 20) :
        await cubes[0].api.motor.motor_control_target(
                timeout = 3, 
                movement_type = MovementType.Curve,
                speed =  Speed(max=50, speed_change_type=SpeedChangeType.AccelerationAndDeceleration),
                target = TargetPosition(cube_location=CubeLocation(point=Point(cubes_point[0].x, cubes_point[0].y + 30)),
                        rotation_option=RotationOption.AbsoluteOptimal))
        await asyncio.sleep(1)
    elif cubes_point[0].y > (MAT_BR.y - 20) :
        await cubes[0].api.motor.motor_control_target(
                timeout = 3, 
                movement_type = MovementType.Curve,
                speed =  Speed(max=50, speed_change_type=SpeedChangeType.AccelerationAndDeceleration),
                target = TargetPosition(cube_location=CubeLocation(point=Point(cubes_point[0].x, cubes_point[0].y - 30)),
                        rotation_option=RotationOption.AbsoluteOptimal))
        await asyncio.sleep(1)
    # ゲートを動かす
    g1_moving = True
    await cubes[1].api.motor.motor_control_multiple_targets(
            timeout=6,
            movement_type=MovementType.Curve,
            speed=Speed(
                max=50, speed_change_type=SpeedChangeType.AccelerationAndDeceleration
            ),
            mode=WriteMode.Overwrite,
            target_list=tgt1)
    g2_moving = True
    await cubes[2].api.motor.motor_control_multiple_targets(
            timeout=6,
            movement_type=MovementType.Curve,
            speed=Speed(
                max=50, speed_change_type=SpeedChangeType.AccelerationAndDeceleration
            ),
            mode=WriteMode.Overwrite,
            target_list=tgt2)


async def run(address):
    global status
    try:
        # toio core cubeに接続
        await connectCube()

        # 1. 周囲のBLE発信をスキャン
        scanner = BleakScanner()
        devices = await scanner.discover()

        clients = []
        for device in devices:
            #print(f'name:{device.name},address:{device.address}')
            if device.address in address:
                client = BleakClient(device)
                clients.append(client)
        # 2. M5Dial とデータのやり取りをする
        for client in clients:
            await client.connect()
            await client.start_notify(UART_RX_UUID, nus_notification_handler)

        while True : 
            topic = await recv_socket.recv_string()
            if topic == "event/cut":
                print("cut")
                await repositioning()
            elif topic == "event/gamestart":
                print("gamestart")
                status = State.OPERATING
            elif topic == "event/gameover":
                print("gameover")
                status = State.GAMEOVER

            #give some time to do other tasks
            await asyncio.sleep(0.01)

            #check if we received data
            global dataFlag
            if dataFlag :
                dataFlag = False

                #echo our received data back to the BLE device
                #data = await client.read_gatt_char(UART_RX_UUID)
                #await client.write_gatt_char(UART_TX_UUID,data)
    except KeyboardInterrupt:
        print("keyboard interrupt")
        await cubes.disconnect()

async def main():
    #this is MAC of our BLE device

    address = (
        #"48:27:E2:E3:16:8D" # M5Dial
        "B0:81:84:97:20:E1" # M5Dial 1.1
    )
    run_task = asyncio.create_task(run(address))
    #zmq_task = asyncio.create_task(recv_zmq())
 
    #await zmq_task
    await run_task
    #

if __name__ == "__main__":
    address = (
        #"48:27:E2:E3:16:8D" # M5Dial
        "B0:81:84:97:20:E1" # M5Dial 1.1
    )
    asyncio.run(run(address))
    #asyncio.run(main())

