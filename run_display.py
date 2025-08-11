#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright © 2025 Rejeb Ben Rejeb

"""
Run the Thermalright LCD slideshow from project root.

Usage:

  # Preferred (from project root):
  PYTHONPATH=src python -m thermalright_lcd_control.device_controller.display.run_display resources/gui_config.yaml
  # To enable packet-level logging:
  PYTHONPATH=src python -m thermalright_lcd_control.device_controller.display.run_display resources/gui_config.yaml --debug

  # Or as a standalone script:
  python run_display.py resources/gui_config.yaml [--debug]
"""

import sys
import logging
import argparse
from pathlib import Path

try:
    from thermalright_lcd_control.device_controller.display.display_device import (
        load_device,
        ChiZhuDisplay
    )
except ImportError:
    print("ERROR: Cannot import display module. Ensure you're in the project root")
    print("       and that PYTHONPATH=src is set if running as a module.")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Run Thermalright LCD slideshow")
    parser.add_argument("config", type=str, help="Path to gui_config.yaml")
    parser.add_argument("--debug", action="store_true", help="Enable verbose USB packet logging")
    args = parser.parse_args()

    # Setup logger
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger = logging.getLogger("thermalright.device_controller")
    logger.info("Device controller logger configured for development mode (console)")

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        logger.error(f"Config file not found: {cfg_path}")
        sys.exit(1)

    try:
        # Load device
        device = load_device(str(cfg_path))
        if not device:
            logger.error("No compatible display device found.")
            sys.exit(1)

        # Patch instance method if debug is enabled
        if args.debug and isinstance(device, ChiZhuDisplay):
            def verbose_run():
                logger.info("✅ verbose_run() is active and executing")
                logger.debug("Verbose run loop started")
                while True:
                    img, delay_time = device._get_generator().get_frame_with_duration()
                    if img is None:
                        logger.warning("No image returned from generator")
                        continue

                    logger.debug(f"Frame size: {img.size}, delay: {delay_time}")
                    img_bytes = device.get_header() + device._encode_image(img)
                    logger.debug(f"Encoded image bytes: {len(img_bytes)}")

                    frame_packets = device._prepare_frame_packets(img_bytes)
                    logger.debug(f"Chunk size: {device.chunk_size}, packets: {len(frame_packets)}")

                    if not frame_packets:
                        logger.warning("No packets prepared for transmission")
                        continue

                    for i, packet in enumerate(frame_packets):
                        logger.debug(f"Packet {i}: size={len(packet)}, head={packet[:8].hex()}")
                        device.dev.write(device.endpoint_out, packet)

                    time.sleep(delay_time)

            device.run = verbose_run

        logger.info(f"Device loaded: {device.__class__.__name__}")

        # Send init sequence if supported
        if hasattr(device, "send_init_sequence"):
            logger.info("Sending init sequence...")
            device.send_init_sequence()

        # Start display loop
        device.run()

    except Exception as e:
        logger.exception(f"Error during run: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
