"""
Interactive Terminal Controller for M5 Stack-chan BLE
Allows real-time control of Stack-chan's neck (Yaw & Pitch) and facial expressions via terminal prompts.
"""

# ichiro 44:1B:F6:E2:5B:CE
# jiro

import asyncio
import logging
import sys
import zmq
import zmq.asyncio  # zmqのasyncioサポートをインポート

context = zmq.asyncio.Context()
socket = context.socket(zmq.SUB)
socket.connect("ipc:///tmp/stackchan") # recv from ledmatrix.py
socket.setsockopt_string(zmq.SUBSCRIBE, "")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

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
from stackchan_avatar import StackChanAvatarBLE, EXPRESSION_PRESETS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("StackChanInteractive")


async def recv_zmq(bot_motion: StackChanBLE, bot_avatar: StackChanAvatarBLE):
    global socket
    current_yaw = YAW_CENTER
    current_pitch = PITCH_CENTER
    step = 100

    while True:
        try:
            cmd = await socket.recv_string()
            print("ZMQ cmd", cmd)
            cmd = cmd.strip().lower()
            if not cmd:
                continue

            if cmd in ("q", "quit", "exit"):
                print("Exiting...")
                break

            elif cmd == "w":
                current_pitch = min(PITCH_MAX_ANGLE, current_pitch + step)
                await bot_motion.send_motion(yaw_angle=current_yaw, pitch_angle=current_pitch)

            elif cmd == "s":
                current_pitch = max(PITCH_MIN_ANGLE, current_pitch - step)
                await bot_motion.send_motion(yaw_angle=current_yaw, pitch_angle=current_pitch)

            elif cmd == "a":
                current_yaw = max(YAW_MIN_ANGLE, current_yaw - step)
                await bot_motion.send_motion(yaw_angle=current_yaw, pitch_angle=current_pitch)

            elif cmd == "d":
                current_yaw = min(YAW_MAX_ANGLE, current_yaw + step)
                await bot_motion.send_motion(yaw_angle=current_yaw, pitch_angle=current_pitch)

            elif cmd == "c":
                current_yaw = YAW_CENTER
                current_pitch = PITCH_CENTER
                await bot_motion.reset_position()

            elif cmd == "nod":
                await bot_motion.send_motion(yaw_angle=current_yaw, pitch_angle=250, pitch_speed=600)
                await asyncio.sleep(0.6)
                await bot_motion.send_motion(yaw_angle=current_yaw, pitch_angle=650, pitch_speed=600)
                await asyncio.sleep(0.6)
                await bot_motion.send_motion(yaw_angle=current_yaw, pitch_angle=current_pitch, pitch_speed=500)

            elif cmd == "shake":
                await bot_motion.send_motion(yaw_angle=-400, pitch_angle=current_pitch, yaw_speed=700)
                await asyncio.sleep(0.6)
                await bot_motion.send_motion(yaw_angle=400, pitch_angle=current_pitch, yaw_speed=700)
                await asyncio.sleep(0.6)
                await bot_motion.send_motion(yaw_angle=current_yaw, pitch_angle=current_pitch, yaw_speed=500)

            elif cmd.startswith("set "):
                parts = cmd.split()
                if len(parts) >= 3:
                    try:
                        y = int(parts[1])
                        p = int(parts[2])
                        current_yaw = max(YAW_MIN_ANGLE, min(YAW_MAX_ANGLE, y))
                        current_pitch = max(PITCH_MIN_ANGLE, min(PITCH_MAX_ANGLE, p))
                        await bot_motion.send_motion(yaw_angle=current_yaw, pitch_angle=current_pitch)
                    except ValueError:
                        print("Invalid numbers. Usage: set <yaw> <pitch>")
                else:
                    print("Usage: set <yaw> <pitch>")

            elif cmd == "blink":
                await bot_avatar.blink(count=1)

            elif cmd == "list":
                print("\nAvailable Expressions:")
                for name, data in EXPRESSION_PRESETS.items():
                    print(f"  - {name:<12} : {data['description']}")
                print()

            elif cmd.startswith("exp ") or cmd.startswith("face "):
                parts = cmd.split(maxsplit=1)
                if len(parts) > 1:
                    exp_name = parts[1].strip()
                    if exp_name in EXPRESSION_PRESETS:
                        await bot_avatar.send_expression(exp_name)
                    else:
                        print(f"Unknown expression: '{exp_name}'. Type 'list' to view options.")
                else:
                    print("Usage: exp <expression_name>")

            elif cmd in EXPRESSION_PRESETS:
                # Direct preset name entered
                await bot_avatar.send_expression(cmd)

            else:
                print(f"Unknown command: '{cmd}'. (w/a/s/d, c, nod, shake, exp <name>, blink, list, q)")

            print(f"Current Position -> Yaw: {current_yaw}, Pitch: {current_pitch}")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break


async def main():
    address = sys.argv[1] if len(sys.argv) > 1 else None

    target_device = None
    if not address:
        target_device = await find_stackchan()
        if not target_device:
            print("Stack-chan device not found. Pass address manually: python stackchan_interactive.py <MAC>")
            return
        address = target_device.address

    # Initialize client (sharing the same underlying client/connection)
    bot_motion = StackChanBLE(device=target_device, address=address)
    bot_avatar = StackChanAvatarBLE(device=target_device, address=address)

    try:
        if await bot_motion.connect():
            # Share the connected BleakClient instance
            bot_avatar.client = bot_motion.client
            await bot_motion.reset_position()
            await bot_avatar.send_expression("neutral")
            await recv_zmq(bot_motion, bot_avatar)
    finally:
        await bot_motion.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
