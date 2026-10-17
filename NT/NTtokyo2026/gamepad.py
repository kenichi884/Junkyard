from evdev import InputDevice, categorize, ecodes
import zmq

context = zmq.Context.instance()
send_socket = context.socket(zmq.PUB) # send to LEDmatrix
send_socket.bind("ipc:///tmp/toio_notify")

# デバイスの準備 (各自のデバイス名に書き換える) python -m evdev.evtest
dev = InputDevice('/dev/input/event5')
print(f"Listening on {dev.path} ({dev.name})")

# メインループ
for event in dev.read_loop():
    # ボタン（押す/離す）などのキーイベント
    if event.type == ecodes.EV_KEY:
        key_event = categorize(event)
        print(f"[KEY] {key_event.keycode}: {key_event.keystate}")
        if key_event.keycode[0] == 'BTN_A' and key_event.keystate == 1:
            print("A pressed")
            send_socket.send_string("gamepad/button", zmq.SNDMORE)
            send_socket.send_pyobj('B') # ボタン刻印で
        elif key_event.keycode[0] == 'BTN_B' and key_event.keystate == 1:
            send_socket.send_string("gamepad/button", zmq.SNDMORE)
            send_socket.send_pyobj('A') # ボタン刻印で
    # スティックの傾きやトリガーなどのキーイベント
    #elif event.type == ecodes.EV_ABS:
    #    abs_event = categorize(event)
    #    print(f"[ABS] {abs_event.event.code}: {abs_event.event.value}")
    