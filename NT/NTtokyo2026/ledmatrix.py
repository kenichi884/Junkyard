import math

import asyncio
import zmq
import zmq.asyncio  # zmqのasyncioサポートをインポート

from evdev import InputDevice, categorize, ecodes # gamepad

from enum import Enum
import sys
import math
#sys.path.append("~/rpi-rgb-led-matrix/bindings/python")
#sys.path.append("~/rpi-rgb-led-matrix/bindings/python/samples")
#from samplebase import SampleBase
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions
import time
from collections import deque

GAME_TITLE = "DRAGON"
GAME_TITLE2 = "SPLIT"
REMAIN_TIME = 60
score = 0
start_time = 0  # UTC epoc

from stackchan_motion import (
    StackChanBLE,
    find_stackchan,
    YAW_CENTER,
    PITCH_CENTER,
    DEFAULT_SPEED,
    YAW_MIN_ANGLE,
    YAW_MAX_ANGLE,
    PITCH_MIN_ANGLE,
    PITCH_MAX_ANGLE,
)

class State(Enum):
    POSITIONING = 0
    OPERATING = 1

class GameStatus(Enum):
    PRACTICE = 0
    PLAYING = 1
    GAMEOVER = 2

status = State.OPERATING
game_status = GameStatus.PRACTICE

# Configuration for the matrix
options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 3
options.parallel = 1
options.hardware_mapping = 'adafruit-hat'
options.pixel_mapper_config='V-mapper:Z'
# indoor panel setting
#options.gpio_slowdown= 4 
# outdoor panel setting
options.gpio_slowdown = 8
options.multiplexing = 1


matrix = RGBMatrix(options = options)

# ZMQ 
#context = zmq.Context.instance()
context = zmq.asyncio.Context()
socket = context.socket(zmq.SUB)
socket.connect("ipc:///tmp/toio_notify") # recv from nustoio.py and gamepad.py
#socket.subscribe('cube/')
#socket.subscribe("")
socket.setsockopt_string(zmq.SUBSCRIBE, "")
send_socket = context.socket(zmq.PUB) # send to nustoio.py (CUT event)
send_socket.bind("ipc:///tmp/event")\

stackchan_socket = context.socket(zmq.PUB)
stackchan_socket.bind("ipc:///tmp/stackchan")


pos_queue = deque() # 自機位置キュー(軌跡描画用)
POS_QUEUE_SIZE = 10
g1x, g1y = 0, 0  # gate1 x y
g2x, g2y = 0, 0  # gate2 x y
sx, sy = 0, 0  # sword x y 自機位置
sangle = 0
prev_sx, prev_sy = 0,0 # sword ひとつ前の位置


prev_side = 0
def checkSide(x, y, x1, y1, x2, y2):
    global prev_side
    bias = 2
    box_in = False
    vx1 = x2 - x1
    vy1 = y2 - y1
    vx2 = x - x1
    vy2 = y - y1
    s = vx1 * vy2 - vy1 * vx2 
    if s > 0 :
        s = 1
    else:
        s = -1
    # sの符号が変わったときが線をまたいだとき
    xi = False
    yi = False
    if vx1 > 0:
        if (x2 + bias) > x and (x1 - bias) < x:
            xi = True
    else:
        if (x1 + bias) > x and (x2 - bias)< x:
            xi = True
    if vy1 > 0:
        if (y2 + bias) > y and (y1 - bias) < y:
            yi = True
    else:
        if (y1 + bias) > x and (y2 - bias) < y:
            yi = True
    if xi and yi :
        box_in = True 

    #
    if box_in and prev_side != s:
        print("cut the rope", s, xi, yi)
        prev_side = s
        return True
    prev_side = s
    return False

def ccw(ax, ay, bx, by, cx, cy):
    """
    点A, B, Cが反時計回り(Counter-Clockwise)に並んでいるかを判定する。
    戻り値:
        正の値 -> 反時計回り (Cが直線ABの左側)
        負の値 -> 時計回り (Cが直線ABの右側)
        0     -> 共線（一直線上）
    """
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

def checkIntersection(ax, ay, bx, by, cx, cy, dx, dy):
    """
    線分ABと線分CDが交差しているかを判定する。
    """
    # 1. 直線ABに対してCとDが異なる側にあるか、かつ 直線CDに対してAとBが異なる側にあるか
    ccw_ab = ccw(ax, ay, bx, by, cx, cy) * ccw(ax, ay, bx, by, dx, dy)
    ccw_cd = ccw(cx, cy, dx, dy, ax, ay) * ccw(cx, cy, dx, dy, bx, by)
    if ccw_ab < 0 and ccw_cd < 0:
        return True
        '''
    # 2. 端点がもう一方の線分上にある場合（ccwが0になる特殊なケース）の処理
    # お互いのx, y座標の範囲（バウンディングボックス）が重なっているかを確認
    def on_segment(P, Q, R):
        # 点Rが線分PQのバウンディングボックス内にあるか
        return min(P[0], Q[0]) <= R[0] <= max(P[0], Q[0]) and min(P[1], Q[1]) <= R[1] <= max(P[1], Q[1])

    if ccw(A, B, C) == 0 and on_segment(A, B, C): return True
    if ccw(A, B, D) == 0 and on_segment(A, B, D): return True
    if ccw(C, D, A) == 0 and on_segment(C, D, A): return True
    if ccw(C, D, B) == 0 and on_segment(C, D, B): return True
    '''
    return False


cut_count = 0 # cut時のアニメーション用カウンタ
CUT_COUNT_MAX = 20
sword_start_posx = 0
sword_start_posy = 0
move_count = 0 # cutまでにかかったムーブの回数
point = 0 # １回のcutで得たポイント
# core cubeの位置変化のnotify
async def position_notification_handler(i, x, y, angle):
    global g1x,g1y,g2x,g2y
    global sx, sy, prev_sx, prev_sy
    global sangle
    global cut_count
    global pos_queue
    global send_socket 
    global sword_start_posx, sword_start_posy
    global move_count
    global point, score

    if i == 0 and x !=0 : # 自機
        pos_queue.append((x, y))
        prev_sx = sx
        prev_sy = sy
        sx = x
        sy = y
        sangle = angle
        if len(pos_queue) > POS_QUEUE_SIZE:
            pos_queue.popleft()
        #if checkSide(x, y, g1x, g1y, g2x, g2y): # 横切った
        if checkIntersection(prev_sx, prev_sy, x, y, g1x, g1y, g2x, g2y):
            await send_socket.send_string("event/cut")
            await stackchan_socket.send_string("nod")
            cut_count = CUT_COUNT_MAX
            diffx = x - sword_start_posx
            diffy = y - sword_start_posy
            distance = math.sqrt((diffx * diffx) + (diffy * diffy))
            point = 5 - move_count
            if point < 1 :
                point = 1
            print("CUT dist count point", distance, move_count, point)
            score = score + point            
    elif i == 1: # and x !=0 : # gate1
        g1x = x
        g1y = y
        #print("pos notify g1x g1y", g1x, g1y)
    elif i == 2: # and x !=0 : # gate2
        g2x = x
        g2y = y
        #print("pos notify g2x g2y", g2x, g2y)


async def recv_zmq():
    global status
    global socket
    global sword_start_posx, sword_start_posy
    global move_count
    global game_status
    global start_time
    while True:
        # await で受信を待つ。データがない間は、他のタスク（描画など）に処理を譲る
        topic = await socket.recv_string()
        if topic == "cube/position":
            params = await socket.recv_pyobj()
            #print(params)
            await position_notification_handler(params[0], params[1], params[2], params[3])
        elif topic == "status":  # nustoio.py側でpositioningが終わったことを通知
            param = await socket.recv_pyobj()
            print("status t ", param)
            if param == "operating":
                status = State.OPERATING
            elif param == "positioning":
                status = State.POSITIONING
                pos_queue.clear()
                #move_count = 0
            else:
                print("unknown topic ", topic, param)
        elif topic == "cube/start": # core cube 移動開始
            params = await socket.recv_pyobj() 
            print("cube/start", params)
            sword_start_posx = params.point.x #開始位置の保存、スコアで使えるかと思ったが
            sword_start_posy = params.point.y
            move_count = move_count + 1
        '''
        elif topic == "gamepad/button": # gamepadのボタン押し
            param = await socket.recv_pyobj()
            print("gamepad btn", param)
            if game_status == GameStatus.PRACTICE:
                game_status = GameStatus.PLAYING
                start_time = time.time()
            elif game_status == GameStatus.GAMEOVER:
                game_status = GameStatus.PRACTICE
                score = 0
                point = 0
        '''
        # await asyncio.sleep(0)

async def gamepad():
    global game_status, start_time, score, point
    global send_socket
    global status
    global g1x,g1y,g2x,g2y
    global sx, sy
    # デバイスの準備 (各自のデバイス名に書き換える) python -m evdev.evtest
    dev = InputDevice('/dev/input/event4')
    print(f"Listening on {dev.path} ({dev.name})")
    async for event in dev.async_read_loop():
        # ボタン（押す/離す）などのキーイベント
        if event.type == ecodes.EV_KEY:
            key_event = categorize(event)
            print(f"[KEY] {key_event.keycode}: {key_event.keystate}")
            if key_event.keycode[0] == 'BTN_A' and key_event.keystate == 1:
                print("A pressed")
                print("game_status", game_status)
                print("cube_status", status)
                #ゲート、自分の位置座標、カットフラグをプリントして確認
                print("sx sy", sx, sy)
                print("g1x g1y  g2x g2y", g1x, g1y, g2x, g2y)
            elif key_event.keycode[0] == 'BTN_B' and key_event.keystate == 1:
                print("B pressed")
                if game_status == GameStatus.PRACTICE:
                    game_status = GameStatus.PLAYING
                    score = 0
                    point = 0
                    await send_socket.send_string("event/gamestart")
                    start_time = time.time()
                elif game_status == GameStatus.GAMEOVER:
                    game_status = GameStatus.PRACTICE
                    score = 0
                    point = 0
async def rgbmatrix():
    global pos_queue
    global g1x, g1y, g2x, g2y
    global sx, sy
    global cut_count
    global status
    global move_count
    global game_status, score, start_time
    global point

    matrix.Clear()
    print("matrix size", matrix.width, matrix.height)
    font = graphics.Font()
    font.LoadFont("./fonts/6x13B.bdf")
    smallfont = graphics.Font()
    smallfont.LoadFont("./fonts/5x7.bdf")
    largefont = graphics.Font()
    largefont.LoadFont("./fonts/9x15B.bdf")
    middlefont = graphics.Font()
    middlefont.LoadFont("./fonts/8x13B.bdf")

    offscreen_canvas = matrix.CreateFrameCanvas()

    white = graphics.Color(255, 255, 255)
    yellow = graphics.Color(255, 255, 0)
    cyan = graphics.Color(0, 255, 255)
    magenta = graphics.Color(255, 255, 0)
    blue = graphics.Color(0, 0, 255)
    green = graphics.Color(0, 255, 0)
    red = graphics.Color(255, 0, 0)
    black = graphics.Color(0, 0, 0)

    while True:
        offscreen_canvas.Clear()
        if game_status == GameStatus.PRACTICE:
            graphics.DrawText(offscreen_canvas, largefont, 5, 10, blue, GAME_TITLE)
            graphics.DrawText(offscreen_canvas, largefont, 10, 22, blue, GAME_TITLE2)
        else : # PLAYING or GAMEOVER
            graphics.DrawText(offscreen_canvas, font, 0, 9, cyan, str(score))
            if game_status == GameStatus.PLAYING:
                now_time = time.time()
                remain_time = REMAIN_TIME - int(now_time - start_time)
                m, s = divmod(remain_time, 60)
                timestr = '{:01}:{:02}'.format(m, s)
                graphics.DrawText(offscreen_canvas, font, 40, 9, cyan, timestr)
                if remain_time <= 0 :
                    game_status = GameStatus.GAMEOVER
                    await send_socket.send_string("event/gameover")
            elif game_status == GameStatus.GAMEOVER:
                graphics.DrawText(offscreen_canvas, middlefont, 0, 55, white, "GAMEOVER")
        if status == State.OPERATING:
            circle_size = POS_QUEUE_SIZE 
            for p in reversed(pos_queue):
                circle_size =  circle_size - 1
                if circle_size < 2 :
                    circle_size = 2
                graphics.DrawCircle(offscreen_canvas, p[0], p[1], circle_size / 2, white)
            rad = math.radians(sangle + 90)
            graphics.DrawLine(offscreen_canvas, sx, sy, sx + math.cos(rad) * 8, sy + math.sin(rad) * 8 , cyan)
            if g1x != 0 and g1y != 0:
                graphics.DrawCircle(offscreen_canvas, g1x, g1y, 5, yellow)
            if g2x != 0 and g2y != 0:
                graphics.DrawCircle(offscreen_canvas, g2x, g2y, 5, yellow)
        if g1x != 0 and g1y != 0 and g2x != 0 and g2y != 0:
            # rope
            if status == State.OPERATING:
                graphics.DrawLine(offscreen_canvas, g1x-1, g1y, g2x-1, g2y, yellow)
                graphics.DrawLine(offscreen_canvas, g1x+1, g1y, g2x+1, g2y, yellow)
                graphics.DrawLine(offscreen_canvas, g1x, g1y, g2x, g2y, yellow)
                graphics.DrawLine(offscreen_canvas, g1x, g1y-1, g2x, g2y-1, yellow)
                graphics.DrawLine(offscreen_canvas, g1x, g1y+1, g2x, g2y+1, yellow)
                # box
                #graphics.DrawLine(offscreen_canvas, g1x, g1y, g2x, g1y, cyan)
                #graphics.DrawLine(offscreen_canvas, g2x, g1y, g2x, g2y, cyan)
                #graphics.DrawLine(offscreen_canvas, g2x, g2y, g1x, g2y, cyan)
                #graphics.DrawLine(offscreen_canvas, g1x, g2y, g1x, g1y, cyan)
            else: # State.POSITIONING
                if cut_count > (CUT_COUNT_MAX - 15):
                    graphics.DrawLine(offscreen_canvas, g1x, g1y, sx, sy, red)
                    graphics.DrawLine(offscreen_canvas, sx, sy, g2x, g2y, red)
                    #for i in range(5): #切ったところを消す X とかにする？
                    #    graphics.DrawCircle(offscreen_canvas, sx, sy, i+1, red)
                    graphics.DrawLine(offscreen_canvas, sx -5, sy -5, sx +5, sy +5, red)
                    graphics.DrawLine(offscreen_canvas, sx +5, sy -5, sx -5, sy +5, red)
                if cut_count >  0:
                    graphics.DrawText(offscreen_canvas, font, sx, sy + 10, green, str(point))
                    cut_count = cut_count -1
                    if cut_count == 0:
                        move_count = 0

        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
        await asyncio.sleep(0.05)

async def head():
    while True:
        cmd = "set " + str(int((48 - sy) * 500 / 48))  + " " + str(PITCH_CENTER)
        print("stackchanhead ", sx, sy, cmd)
        await stackchan_socket.send_string(cmd) #首振り
        await asyncio.sleep(1.0)

async def main():
    zmq_task = asyncio.create_task(recv_zmq())
    gamepad_task = asyncio.create_task(gamepad())
    rgbmatrix_task = asyncio.create_task(rgbmatrix())
    head_task = asyncio.create_task(head())
    await zmq_task
    await gamepad_task
    await rgbmatrix_task
    await head_task

    #await asyncio.gather(rgbmatrix(), recv_zmq())

asyncio.run(main())
