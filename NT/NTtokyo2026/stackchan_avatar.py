"""
M5 Stack-chan BLE Avatar Expression Controller using bleak
Reference: https://github.com/m5stack/StackChan/tree/main/app
"""

import argparse
import asyncio
import copy
import json
import logging
import sys
from typing import Optional, Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("StackChanAvatar")

# ---------------------------------------------------------
# Stack-chan BLE UUID Definitions
# ---------------------------------------------------------
SERVICE_UUID     = "e2e5e5e0-1234-5678-1234-56789abcdef0"
SERVICE_UUID_ALT = "e2e5e5ff-1234-5678-1234-56789abcdef0"
AVATAR_CHAR_UUID = "e2e5e5e2-1234-5678-1234-56789abcdef0"
RGB_CHAR_UUID    = "e2e5e5e4-1234-5678-1234-56789abcdef0"

# ---------------------------------------------------------
# Expression Presets (Based on Stack-chan firmware & app specifications)
# ---------------------------------------------------------
EXPRESSION_PRESETS: Dict[str, Dict[str, Any]] = {
    "neutral": {
        "description": "通常（ニュートラル・正面）",
        "leftEye":  {"x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 0},
        "rightEye": {"x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 0},
        "mouth":    {"x": 0, "y": 0, "rotation": 0, "weight": 0,   "size": 0},
        "rgb": "#00FFCC",
    },
    "happy": {
        "description": "笑顔（にっこり・口を開けて喜ぶ）",
        "leftEye":  {"x": 0, "y": 0, "rotation": 1550,  "weight": 72, "size": 0},
        "rightEye": {"x": 0, "y": 0, "rotation": -1550, "weight": 72, "size": 0},
        "mouth":    {"x": 0, "y": 0, "rotation": 0,     "weight": 85, "size": 0},
        "rgb": "#FFFF00",
    },
    "wink": {
        "description": "ウインク（左目を閉じる）",
        "leftEye":  {"x": 0, "y": 0, "rotation": 0, "weight": 0,   "size": 0},
        "rightEye": {"x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 0},
        "mouth":    {"x": 0, "y": 0, "rotation": 0, "weight": 50,  "size": 0},
        "rgb": "#FF66CC",
    },
    "wink_right": {
        "description": "ウインク（右目を閉じる）",
        "leftEye":  {"x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 0},
        "rightEye": {"x": 0, "y": 0, "rotation": 0, "weight": 0,   "size": 0},
        "mouth":    {"x": 0, "y": 0, "rotation": 0, "weight": 50,  "size": 0},
        "rgb": "#FF66CC",
    },
    "angry": {
        "description": "怒り（つり目・引き結んだ口）",
        "leftEye":  {"x": 0, "y": 0, "rotation": 450,  "weight": 70, "size": 0},
        "rightEye": {"x": 0, "y": 0, "rotation": -450, "weight": 70, "size": 0},
        "mouth":    {"x": 0, "y": 5, "rotation": 0,    "weight": 20, "size": 0},
        "rgb": "#FF0000",
    },
    "sad": {
        "description": "悲しい・困り顔（たれ目・への字口）",
        "leftEye":  {"x": 0, "y": 0, "rotation": -400, "weight": 70, "size": 0},
        "rightEye": {"x": 0, "y": 0, "rotation": 400,  "weight": 70, "size": 0},
        "mouth":    {"x": 0, "y": 0, "rotation": 1800, "weight": 10, "size": 0},
        "rgb": "#0066FF",
    },
    "doubt": {
        "description": "疑問・きょとん（片眉上がり・左右非対称）",
        "leftEye":  {"x": 0, "y": -5, "rotation": 250,  "weight": 95, "size": 15},
        "rightEye": {"x": 0, "y": 5,  "rotation": -300, "weight": 65, "size": -10},
        "mouth":    {"x": 10, "y": 0, "rotation": 350,  "weight": 35, "size": 0},
        "rgb": "#FF9900",
    },
    "sleepy": {
        "description": "眠い・ウトウト（半目・小さな口）",
        "leftEye":  {"x": 0, "y": 0, "rotation": -50, "weight": 35, "size": 0},
        "rightEye": {"x": 0, "y": 0, "rotation": 50,  "weight": 35, "size": 0},
        "mouth":    {"x": 0, "y": 0, "rotation": 0,   "weight": 15, "size": 0},
        "rgb": "#9966FF",
    },
    "surprise": {
        "description": "驚き（見開き目・大きく開けた口）",
        "leftEye":  {"x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 35},
        "rightEye": {"x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 35},
        "mouth":    {"x": 0, "y": 0, "rotation": 0, "weight": 95,  "size": 0},
        "rgb": "#FFFFFF",
    },
    "closed": {
        "description": "目を閉じる（まばたき・眠り）",
        "leftEye":  {"x": 0, "y": 0, "rotation": 0, "weight": 0, "size": 0},
        "rightEye": {"x": 0, "y": 0, "rotation": 0, "weight": 0, "size": 0},
        "mouth":    {"x": 0, "y": 0, "rotation": 0, "weight": 0, "size": 0},
        "rgb": "#000000",
    },
}


class StackChanAvatarBLE:
    """Stack-chan BLE Avatar Expression Controller."""

    def __init__(self, device: Optional[BLEDevice] = None, address: Optional[str] = None):
        self.device = device
        self.address = address or (device.address if device else None)
        self.client: Optional[BleakClient] = None
        self._current_avatar: Dict[str, Any] = copy.deepcopy(EXPRESSION_PRESETS["neutral"])

    async def connect(self, timeout: float = 15.0) -> bool:
        """Connect to Stack-chan."""
        target = self.device or self.address
        if not target:
            raise ValueError("No target device or address specified.")

        logger.info(f"Connecting to Stack-chan at {self.address or self.device}...")
        self.client = BleakClient(target, timeout=timeout)
        await self.client.connect()

        if self.client.is_connected:
            logger.info("Successfully connected to Stack-chan!")
            return True
        else:
            logger.error("Failed to connect.")
            return False

    async def disconnect(self):
        """Disconnect from Stack-chan."""
        if self.client and self.client.is_connected:
            logger.info("Disconnecting from Stack-chan...")
            await self.client.disconnect()
            logger.info("Disconnected.")

    async def send_avatar_raw(
        self,
        left_eye: Dict[str, int],
        right_eye: Dict[str, int],
        mouth: Dict[str, int],
    ) -> bool:
        """
        Send raw avatar JSON payload to Stack-chan Avatar Characteristic.

        Each feature dict accepts:
          x: int (-100 ~ 100)
          y: int (-100 ~ 100)
          rotation: int (-1800 ~ 1800)
          weight: int (0 ~ 100, 100 is fully open eye / 0 is closed, mouth 0 is closed / 100 is open)
          size: int (-100 ~ 100)
        """
        if not self.client or not self.client.is_connected:
            logger.error("Client is not connected.")
            return False

        payload = {
            "type": "bleAvatar",
            "leftEye": {
                "x": int(left_eye.get("x", 0)),
                "y": int(left_eye.get("y", 0)),
                "rotation": int(left_eye.get("rotation", 0)),
                "weight": int(left_eye.get("weight", 100)),
                "size": int(left_eye.get("size", 0)),
            },
            "rightEye": {
                "x": int(right_eye.get("x", 0)),
                "y": int(right_eye.get("y", 0)),
                "rotation": int(right_eye.get("rotation", 0)),
                "weight": int(right_eye.get("weight", 100)),
                "size": int(right_eye.get("size", 0)),
            },
            "mouth": {
                "x": int(mouth.get("x", 0)),
                "y": int(mouth.get("y", 0)),
                "rotation": int(mouth.get("rotation", 0)),
                "weight": int(mouth.get("weight", 0)),
                "size": int(mouth.get("size", 0)),
            },
        }

        json_str = json.dumps(payload, separators=(",", ":"))
        logger.info(f"Sending Avatar JSON: {json_str}")
        data = json_str.encode("utf-8")
        await self.client.write_gatt_char(AVATAR_CHAR_UUID, data, response=True)

        self._current_avatar = {
            "leftEye": payload["leftEye"],
            "rightEye": payload["rightEye"],
            "mouth": payload["mouth"],
        }
        return True

    async def send_expression(self, expression_name: str, update_rgb: bool = True) -> bool:
        """
        Apply a preset expression by name.
        Available: neutral, happy, wink, wink_right, angry, sad, doubt, sleepy, surprise, closed
        """
        name = expression_name.lower().strip()
        if name not in EXPRESSION_PRESETS:
            logger.error(f"Unknown expression: '{name}'. Choose from: {list(EXPRESSION_PRESETS.keys())}")
            return False

        preset = EXPRESSION_PRESETS[name]
        logger.info(f"Applying expression '{name}' ({preset.get('description', '')})")

        success = await self.send_avatar_raw(
            left_eye=preset["leftEye"],
            right_eye=preset["rightEye"],
            mouth=preset["mouth"],
        )

        if success and update_rgb and "rgb" in preset:
            rgb_hex = preset["rgb"]
            await self.send_rgb(left_color=rgb_hex, right_color=rgb_hex, duration=0.3)

        return success

    async def blink(self, count: int = 1, closed_duration: float = 0.15, interval: float = 0.1):
        """Perform realistic eye-blinking animation while preserving current mouth state."""
        if not self.client or not self.client.is_connected:
            return

        current_left = copy.deepcopy(self._current_avatar["leftEye"])
        current_right = copy.deepcopy(self._current_avatar["rightEye"])
        current_mouth = copy.deepcopy(self._current_avatar["mouth"])

        # Closed eyes
        closed_left = copy.deepcopy(current_left)
        closed_left["weight"] = 0
        closed_right = copy.deepcopy(current_right)
        closed_right["weight"] = 0

        for i in range(count):
            logger.info(f"Blinking ({i+1}/{count})...")
            # Close eyes
            await self.send_avatar_raw(closed_left, closed_right, current_mouth)
            await asyncio.sleep(closed_duration)
            # Reopen eyes
            await self.send_avatar_raw(current_left, current_right, current_mouth)
            if i < count - 1:
                await asyncio.sleep(interval)

    async def send_rgb(
        self,
        left_color: str = "#00FFCC",
        right_color: str = "#00FFCC",
        duration: float = 0.3,
    ) -> bool:
        """
        Optional: Set Stack-chan's RGB LED neon lights.
        Format: #RRGGBB (e.g. #FF0000 for red)
        """
        if not self.client or not self.client.is_connected:
            return False

        payload = {
            "leftRgbColor": left_color,
            "leftRgbDuration": duration,
            "rightRgbColor": right_color,
            "rightRgbDuration": duration,
        }
        json_str = json.dumps(payload, separators=(",", ":"))
        try:
            await self.client.write_gatt_char(RGB_CHAR_UUID, json_str.encode("utf-8"), response=True)
            return True
        except Exception as e:
            logger.debug(f"RGB Characteristic write skipped or failed: {e}")
            return False

    async def demo_avatar_routine(self):
        """Demonstrate all expression presets in sequence."""
        logger.info("=== Starting Stack-chan Avatar Expression Demo ===")

        demo_list = [
            ("neutral", 1.8),
            ("happy", 2.0),
            ("wink", 1.5),
            ("surprise", 2.0),
            ("doubt", 2.0),
            ("angry", 2.0),
            ("sad", 2.0),
            ("sleepy", 2.0),
            ("neutral", 1.0),
        ]

        for name, wait_sec in demo_list:
            await self.send_expression(name)
            await asyncio.sleep(wait_sec)

        # Blink demonstration
        logger.info("Demonstrating double-blink animation...")
        await self.blink(count=2)
        await asyncio.sleep(1.0)

        # Return to neutral
        logger.info("Resetting expression to neutral...")
        await self.send_expression("neutral")
        await asyncio.sleep(1.0)

        logger.info("=== Expression Demo Finished Successfully! ===")


async def find_stackchan(timeout: float = 7.0) -> Optional[BLEDevice]:
    """Scan and find a nearby Stack-chan BLE device."""
    logger.info(f"Scanning for M5 Stack-chan devices ({timeout}s timeout)...")
    target_uuids = {SERVICE_UUID.lower(), SERVICE_UUID_ALT.lower()}
    discovered_target: Optional[BLEDevice] = None

    def detection_callback(device: BLEDevice, adv_data: AdvertisementData):
        nonlocal discovered_target
        if discovered_target is not None:
            return
        adv_uuids = [u.lower() for u in adv_data.service_uuids]
        matches_uuid = bool(target_uuids.intersection(adv_uuids))
        name = device.name or adv_data.local_name or ""
        name_lower = name.lower()
        matches_name = "stackchan" in name_lower or "stack-chan" in name_lower or "m5" in name_lower

        if matches_uuid or (matches_name and matches_uuid):
            logger.info(f"Found Stack-chan device: '{name}' [{device.address}], RSSI: {adv_data.rssi} dBm")
            discovered_target = device

    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    return discovered_target


async def interactive_mode(bot: StackChanAvatarBLE):
    """Real-time console interface to switch expressions with single keystrokes."""
    print("\n" + "=" * 55)
    print(" M5 Stack-chan Avatar Expression Controller (Interactive)")
    print("=" * 55)
    print(" Presets:")
    presets = list(EXPRESSION_PRESETS.keys())
    for i, name in enumerate(presets, 1):
        desc = EXPRESSION_PRESETS[name]["description"]
        print(f"   [{i:2d}] {name:<12} : {desc}")
    print("\n Actions:")
    print("   [b]  blink         : Perform eye blink")
    print("   [bb] double blink  : Perform double blink")
    print("   [q]  quit          : Exit interactive mode")
    print("=" * 55 + "\n")

    loop = asyncio.get_event_loop()
    while True:
        try:
            cmd = await loop.run_in_executor(None, input, "expression> ")
            cmd = cmd.strip().lower()
            if not cmd:
                continue

            if cmd in ("q", "quit", "exit"):
                break
            elif cmd == "b":
                await bot.blink(count=1)
            elif cmd in ("bb", "2b"):
                await bot.blink(count=2)
            elif cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(presets):
                    await bot.send_expression(presets[idx])
                else:
                    print(f"Invalid number. Choose 1 to {len(presets)}.")
            elif cmd in EXPRESSION_PRESETS:
                await bot.send_expression(cmd)
            else:
                print(f"Unknown command or preset: '{cmd}'. Enter 1-{len(presets)} or preset name.")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break


async def main():
    parser = argparse.ArgumentParser(
        description="M5 Stack-chan BLE Avatar Expression Controller",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--address", "-a",
        type=str,
        default=None,
        help="BLE MAC address of Stack-chan (e.g. 'AA:BB:CC:DD:EE:FF')",
    )
    parser.add_argument(
        "--expression", "-e",
        type=str,
        default=None,
        choices=list(EXPRESSION_PRESETS.keys()),
        help="Apply a preset expression (e.g. 'happy', 'wink', 'angry', 'neutral')",
    )
    parser.add_argument(
        "--blink", "-b",
        action="store_true",
        help="Perform a blink animation",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Launch interactive terminal mode to switch expressions live",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available expression presets and exit",
    )
    parser.add_argument(
        "--demo", "-d",
        action="store_true",
        help="Run expression demo sequence (default if no other option specified)",
    )

    args = parser.parse_args()

    if args.list:
        print("\nAvailable Stack-chan Expression Presets:")
        print("-" * 50)
        for name, data in EXPRESSION_PRESETS.items():
            print(f"  - {name:<12} : {data['description']}")
        print("-" * 50 + "\n")
        return

    # Find target device
    target_device: Optional[BLEDevice] = None
    target_address = args.address

    if not target_address:
        target_device = await find_stackchan()
        if not target_device:
            logger.error("Could not find Stack-chan automatically.")
            logger.info("Tip: Specify MAC address via '--address <MAC>'.")
            sys.exit(1)
        target_address = target_device.address

    bot = StackChanAvatarBLE(device=target_device, address=target_address)

    try:
        if not await bot.connect():
            sys.exit(1)

        if args.interactive:
            await interactive_mode(bot)
        elif args.blink:
            await bot.blink(count=1)
        elif args.expression:
            await bot.send_expression(args.expression)
            await asyncio.sleep(1.0)
        else:
            # Default: run expression demo routine
            await bot.demo_avatar_routine()

    except Exception as e:
        logger.error(f"Error during BLE operation: {e}", exc_info=True)
    finally:
        await bot.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
