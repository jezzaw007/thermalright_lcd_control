# SPDX-License-Identifier: Apache-2.0
# Copyright © 2025 Rejeb Ben Rejeb

from thermalright_lcd_control.common.usb.hid_device import HidDevice
from thermalright_lcd_control.common.usb.winusb_device import WinUsbDevice
from thermalright_lcd_control.common.device_selector import load_gui_config, find_supported_device
from thermalright_lcd_control.common.logging_config import get_service_logger



def run_service(config_file: str = "./resources/gui_config.yaml"):
    logger = get_service_logger()
    logger.info("Device controller service started")

    try:
        # Load GUI config and auto-select device
        config = load_gui_config(config_file)
        device_config = find_supported_device(config)

        if not device_config:
            raise RuntimeError("No supported USB device found")

        # Choose backend
        driver = device_config.get("driver", "hid")
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
