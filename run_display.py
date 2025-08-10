#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright © 2025 Rejeb Ben Rejeb

"""
Run the Thermalright LCD slideshow from project root.

Usage:

  # Preferred (from project root):
  PYTHONPATH=src python -m thermalright_lcd_control.device_controller.display.run_display resources/gui_config.yaml

  # Or as a standalone script:
  python run_display.py resources/gui_config.yaml
"""

import sys
import logging
from pathlib import Path

try:
    # entrypoint into the display module
    from thermalright_lcd_control.device_controller.display.display_device import load_device
except ImportError:
    print("ERROR: Cannot import display module. Ensure you're in the project root")
    print("       and that PYTHONPATH=src is set if running as a module.")
    sys.exit(1)


def main():
    # Basic logger setup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # parse config path
    if len(sys.argv) < 2:
        print("Usage: python run_display.py <path_to_gui_config.yaml>")
        sys.exit(1)

    cfg_path = Path(sys.argv[1])
    if not cfg_path.is_file():
        print(f"ERROR: Config file not found: {cfg_path}")
        sys.exit(1)

    # load & run
    try:
        device = load_device(str(cfg_path))
        if not device:
            print("No compatible display device found.")
            sys.exit(1)

        print(f"Device loaded: {device.__class__.__name__}")
        device.run()

    except Exception as e:
        print(f"Error during run: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
