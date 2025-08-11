# src/thermalright_lcd_control/device_controller/device_controller.py

# SPDX-License-Identifier: Apache-2.0
# Copyright © 2025 Rejeb Ben Rejeb

from __future__ import annotations

from ..common.usb.hid_device       import HidDevice
from ..common.usb.winusb_device    import WinUsbDevice
from ..common.device_selector      import load_gui_config, find_supported_device
from ..common.logging_config       import get_service_logger


def run_service(config_file: str = "./resources/gui_config.yaml") -> None:
    logger = get_service_logger()
    logger.info("Device controller service started")

    try:
        # Load GUI config and auto-select device
        config = load_gui_config(config_file)
        device_config = find_supported_device(config)

        if not device_config:
            raise RuntimeError("No supported USB device found")

        # Choose backend based on driver field (default to HID)
        driver = device_config.get("driver", "hid").lower()
        DeviceClass = WinUsbDevice if driver == "winusb" else HidDevice

        # Instantiate device
        device = DeviceClass(
            vid=int(device_config["vid"], 16),
            pid=int(device_config["pid"], 16),
            interface=device_config.get("interface", 0)
        )

        # Run device logic
        device.reset()
        device.run()

    except KeyboardInterrupt:
        logger.info("Device controller service stopped by user")
    except Exception as e:
        logger.error(f"Device controller service error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_service()
