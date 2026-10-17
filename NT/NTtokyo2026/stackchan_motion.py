"""
M5 Stack-chan BLE Motion Control Script using bleak
Reference: https://github.com/m5stack/StackChan/tree/main/app
"""

import argparse
import asyncio
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
logger = logging.getLogger("StackChanBLE")

# ---------------------------------------------------------
# Stack-chan BLE UUID Definitions (from M5Stack StackChan App)
# ---------------------------------------------------------
# Service UUID (Default / Dance & Avatar mode)
SERVICE_UUID = "e2e5e5e0-1234-5678-1234-56789abcdef0"
# Service UUID Alternate (Pairing / WiFi mode)
SERVICE_UUID_ALT = "e2e5e5ff-1234-5678-1234-56789abcdef0"

# Characteristic UUIDs
MOTION_CHAR_UUID = "e2e5e5e1-1234-5678-1234-56789abcdef0"
AVATAR_CHAR_UUID = "e2e5e5e2-1234-5678-1234-56789abcdef0"
CONFIG_CHAR_UUID = "e2e5e5e3-1234-5678-1234-56789abcdef0"
RGB_CHAR_UUID    = "e2e5e5e4-1234-5678-1234-56789abcdef0"

# Servo angle and speed range limits
YAW_MIN_ANGLE = -1280
YAW_MAX_ANGLE = 1280
PITCH_MIN_ANGLE = 0
PITCH_MAX_ANGLE = 900
PITCH_CENTER = 450
YAW_CENTER = 0
DEFAULT_SPEED = 500


class StackChanBLE:
    """Stack-chan BLE Client for motion and avatar control."""

    def __init__(self, device: Optional[BLEDevice] = None, address: Optional[str] = None):
        self.device = device
        self.address = address or (device.address if device else None)
        self.client: Optional[BleakClient] = None

    async def connect(self, timeout: float = 15.0) -> bool:
        """Connect to the Stack-chan device."""
        target = self.device or self.address
        if not target:
            raise ValueError("No device or address specified for connection.")

        logger.info(f"Connecting to Stack-chan at {self.address or self.device}...")
        self.client = BleakClient(target, timeout=timeout)
        await self.client.connect()

        if self.client.is_connected:
            logger.info("Successfully connected to Stack-chan!")
            # Log available services for verification
            for service in self.client.services:
                logger.debug(f"Discovered Service: {service.uuid} ({service.description})")
            return True
        else:
            logger.error("Failed to connect.")
            return False

    async def disconnect(self):
        """Disconnect from the Stack-chan device."""
        if self.client and self.client.is_connected:
            logger.info("Disconnecting from Stack-chan...")
            await self.client.disconnect()
            logger.info("Disconnected.")

    async def send_motion(
        self,
        yaw_angle: Optional[int] = None,
        pitch_angle: Optional[int] = None,
        yaw_speed: int = DEFAULT_SPEED,
        pitch_speed: int = DEFAULT_SPEED,
        yaw_rotate: Optional[int] = None,
        pitch_rotate: Optional[int] = None,
        yaw_spring: Optional[Dict[str, float]] = None,
        pitch_spring: Optional[Dict[str, float]] = None,
    ) -> bool:
        """
        Send neck motion command to Stack-chan.

        Args:
            yaw_angle: Horizontal angle (-1280 to 1280, 0 is center)
            pitch_angle: Vertical angle (0 to 900, 450 is center/level)
            yaw_speed: Movement speed (0 to 1000, default 500)
            pitch_speed: Movement speed (0 to 1000, default 500)
            yaw_rotate: Continuous rotation speed (-1000 to 1000, alternative to yaw_angle)
            pitch_rotate: Continuous rotation speed (alternative to pitch_angle)
            yaw_spring: Optional spring physics params: {"stiffness": 170.0, "damping": 26.0}
            pitch_spring: Optional spring physics params: {"stiffness": 170.0, "damping": 26.0}
        """
        if not self.client or not self.client.is_connected:
            logger.error("Client is not connected.")
            return False

        # Build pitchServo payload
        pitch_servo: Dict[str, Any] = {}
        if pitch_rotate is not None and pitch_rotate != 0:
            pitch_servo["rotate"] = int(pitch_rotate)
            pitch_servo["speed"] = int(pitch_speed)
        elif pitch_spring is not None:
            pitch_servo["angle"] = int(pitch_angle if pitch_angle is not None else PITCH_CENTER)
            pitch_servo["spring"] = pitch_spring
        else:
            angle = PITCH_CENTER if pitch_angle is None else pitch_angle
            angle = max(PITCH_MIN_ANGLE, min(PITCH_MAX_ANGLE, angle))
            pitch_servo["angle"] = int(angle)
            pitch_servo["speed"] = int(pitch_speed)

        # Build yawServo payload
        yaw_servo: Dict[str, Any] = {}
        if yaw_rotate is not None and yaw_rotate != 0:
            yaw_servo["rotate"] = int(yaw_rotate)
            yaw_servo["speed"] = int(yaw_speed)
        elif yaw_spring is not None:
            yaw_servo["angle"] = int(yaw_angle if yaw_angle is not None else YAW_CENTER)
            yaw_servo["spring"] = yaw_spring
        else:
            angle = YAW_CENTER if yaw_angle is None else yaw_angle
            angle = max(YAW_MIN_ANGLE, min(YAW_MAX_ANGLE, angle))
            yaw_servo["angle"] = int(angle)
            yaw_servo["speed"] = int(yaw_speed)

        payload = {
            "type": "bleMotion",
            "pitchServo": pitch_servo,
            "yawServo": yaw_servo,
        }

        json_str = json.dumps(payload, separators=(",", ":"))
        logger.info(f"Sending motion JSON: {json_str}")

        data = json_str.encode("utf-8")
        await self.client.write_gatt_char(MOTION_CHAR_UUID, data, response=True)
        return True

    async def send_avatar(
        self,
        left_eye_weight: int = 100,
        right_eye_weight: int = 100,
        mouth_weight: int = 0,
        left_eye_rotation: int = 0,
        right_eye_rotation: int = 0,
    ) -> bool:
        """
        Send avatar face expression command to Stack-chan.
        """
        if not self.client or not self.client.is_connected:
            logger.error("Client is not connected.")
            return False

        payload = {
            "type": "bleAvatar",
            "leftEye": {
                "x": 0,
                "y": 0,
                "rotation": left_eye_rotation,
                "weight": left_eye_weight,
                "size": 0,
            },
            "rightEye": {
                "x": 0,
                "y": 0,
                "rotation": right_eye_rotation,
                "weight": right_eye_weight,
                "size": 0,
            },
            "mouth": {
                "x": 0,
                "y": 0,
                "rotation": 0,
                "weight": mouth_weight,
                "size": 0,
            },
        }

        json_str = json.dumps(payload, separators=(",", ":"))
        logger.info(f"Sending avatar JSON: {json_str}")
        data = json_str.encode("utf-8")
        await self.client.write_gatt_char(AVATAR_CHAR_UUID, data, response=True)
        return True

    async def reset_position(self, speed: int = DEFAULT_SPEED):
        """Move neck back to default center position."""
        logger.info("Resetting neck position to center (Yaw: 0, Pitch: 450)...")
        await self.send_motion(yaw_angle=YAW_CENTER, pitch_angle=PITCH_CENTER, yaw_speed=speed, pitch_speed=speed)

    async def demo_motion_routine(self):
        """Perform a demonstration sequence of neck motions."""
        logger.info("=== Starting Stack-chan Neck Motion Demo ===")

        # 1. Center position
        logger.info("[1/5] Center Position (Looking straight)")
        await self.send_motion(yaw_angle=0, pitch_angle=450, yaw_speed=500, pitch_speed=500)
        await asyncio.sleep(1.2)

        # 2. Nodding motion (Up and Down)
        logger.info("[2/5] Nodding motion (Look down, then up, then center)")
        await self.send_motion(yaw_angle=0, pitch_angle=250, yaw_speed=600, pitch_speed=600)  # Down
        await asyncio.sleep(0.8)
        await self.send_motion(yaw_angle=0, pitch_angle=650, yaw_speed=600, pitch_speed=600)  # Up
        await asyncio.sleep(0.8)
        await self.send_motion(yaw_angle=0, pitch_angle=250, yaw_speed=600, pitch_speed=600)  # Down
        await asyncio.sleep(0.8)
        await self.send_motion(yaw_angle=0, pitch_angle=450, yaw_speed=500, pitch_speed=500)  # Center
        await asyncio.sleep(1.0)

        # 3. Head shake motion (Left and Right)
        logger.info("[3/5] Head shaking motion (Turn left, turn right, center)")
        await self.send_motion(yaw_angle=-450, pitch_angle=450, yaw_speed=700, pitch_speed=500)  # Left
        await asyncio.sleep(0.8)
        await self.send_motion(yaw_angle=450, pitch_angle=450, yaw_speed=700, pitch_speed=500)   # Right
        await asyncio.sleep(0.8)
        await self.send_motion(yaw_angle=-300, pitch_angle=450, yaw_speed=700, pitch_speed=500)  # Left
        await asyncio.sleep(0.6)
        await self.send_motion(yaw_angle=300, pitch_angle=450, yaw_speed=700, pitch_speed=500)   # Right
        await asyncio.sleep(0.6)
        await self.send_motion(yaw_angle=0, pitch_angle=450, yaw_speed=500, pitch_speed=500)     # Center
        await asyncio.sleep(1.0)

        # 4. Diagonal look around
        logger.info("[4/5] Looking around diagonally")
        await self.send_motion(yaw_angle=-400, pitch_angle=600, yaw_speed=500, pitch_speed=500) # Up-Left
        await asyncio.sleep(1.0)
        await self.send_motion(yaw_angle=400, pitch_angle=300, yaw_speed=500, pitch_speed=500)  # Down-Right
        await asyncio.sleep(1.0)

        # 5. Return to home
        logger.info("[5/5] Returning to home position")
        await self.reset_position()
        await asyncio.sleep(1.0)

        logger.info("=== Motion Demo Finished Successfully! ===")


async def find_stackchan(timeout: float = 7.0) -> Optional[BLEDevice]:
    """Scan and find a nearby Stack-chan BLE device."""
    logger.info(f"Scanning for M5 Stack-chan devices ({timeout}s timeout)...")

    target_uuids = {SERVICE_UUID.lower(), SERVICE_UUID_ALT.lower()}
    discovered_target: Optional[BLEDevice] = None

    def detection_callback(device: BLEDevice, adv_data: AdvertisementData):
        nonlocal discovered_target
        if discovered_target is not None:
            return

        # Check advertised service UUIDs
        adv_uuids = [u.lower() for u in adv_data.service_uuids]
        matches_uuid = bool(target_uuids.intersection(adv_uuids))

        # Check device name
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

    if not discovered_target:
        logger.warning("Stack-chan device not found automatically via advertisement filter.")
    return discovered_target


async def list_all_devices(timeout: float = 5.0):
    """Scan and print all nearby BLE devices to assist the user."""
    logger.info(f"Scanning all BLE devices for {timeout} seconds...")
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    print("\n--- Discovered BLE Devices ---")
    for address, (device, adv) in devices.items():
        name = device.name or adv.local_name or "Unknown"
        uuids = ", ".join(adv.service_uuids) if adv.service_uuids else "None"
        print(f"Address: {device.address} | Name: {name:<20} | RSSI: {adv.rssi:3d} dBm | Services: {uuids}")
    print("------------------------------\n")


async def main():
    parser = argparse.ArgumentParser(
        description="M5 Stack-chan BLE Avatar Neck Motion Controller",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--address", "-a",
        type=str,
        default=None,
        help="BLE address / MAC of the Stack-chan (e.g. 'AA:BB:CC:DD:EE:FF')",
    )
    parser.add_argument(
        "--scan", "-s",
        action="store_true",
        help="Scan and list all nearby BLE devices and exit",
    )
    parser.add_argument(
        "--yaw", "-y",
        type=int,
        default=None,
        help="Yaw angle (-1280 to 1280, 0 is center)",
    )
    parser.add_argument(
        "--pitch", "-p",
        type=int,
        default=None,
        help="Pitch angle (0 to 900, 450 is center)",
    )
    parser.add_argument(
        "--speed",
        type=int,
        default=DEFAULT_SPEED,
        help="Motion speed (0 to 1000, default 500)",
    )
    parser.add_argument(
        "--demo", "-d",
        action="store_true",
        help="Run neck motion demonstration sequence (default if no specific angle is given)",
    )

    args = parser.parse_args()

    if args.scan:
        await list_all_devices()
        return

    # Find device
    target_device: Optional[BLEDevice] = None
    target_address = args.address

    if not target_address:
        target_device = await find_stackchan()
        if not target_device:
            logger.error("Could not find Stack-chan automatically.")
            logger.info("Tip: Use '--scan' to list nearby devices or '--address <MAC>' to connect directly.")
            sys.exit(1)
        target_address = target_device.address

    # Initialize StackChanBLE
    bot = StackChanBLE(device=target_device, address=target_address)

    try:
        connected = await bot.connect()
        if not connected:
            sys.exit(1)

        if args.yaw is not None or args.pitch is not None:
            # Single motion command specified
            y = args.yaw if args.yaw is not None else YAW_CENTER
            p = args.pitch if args.pitch is not None else PITCH_CENTER
            logger.info(f"Moving neck to Yaw: {y}, Pitch: {p} with speed {args.speed}")
            await bot.send_motion(yaw_angle=y, pitch_angle=p, yaw_speed=args.speed, pitch_speed=args.speed)
            await asyncio.sleep(1.0)
        else:
            # Run demo sequence
            await bot.demo_motion_routine()

    except Exception as e:
        logger.error(f"Error during BLE operation: {e}", exc_info=True)
    finally:
        await bot.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
