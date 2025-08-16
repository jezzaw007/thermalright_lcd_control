#!/usr/bin/env python3

import usb.core
import usb.util
import sys

def safe_get_string(dev, index):
    """
    Try to read a string descriptor from the device.
    If the device doesn’t support them or on permission errors,
    return "Unknown".
    """
    try:
        return usb.util.get_string(dev, index) or "Unknown"
    except (ValueError, usb.core.USBError):
        return "Unknown"

def find_usb_displays():
    print("[*] Scanning connected USB display devices...\n")
    devices = usb.core.find(find_all=True)
    if devices is None:
        print("No USB devices found.")
        return

    for dev in devices:
        vid = f"{dev.idVendor:04x}"
        pid = f"{dev.idProduct:04x}"
        combo = f"{vid}:{pid}"

        print("=" * 60)
        print(f"Device      : {combo}")
        print(f"Manufacturer: {safe_get_string(dev, dev.iManufacturer)}")
        print(f"Product     : {safe_get_string(dev, dev.iProduct)}")
        print(f"Serial No.  : {safe_get_string(dev, dev.iSerialNumber)}\n")

        for cfg in dev:
            print(f"-- Configuration {cfg.bConfigurationValue}")
            for intf in cfg:
                print(f"   Interface {intf.bInterfaceNumber}, "
                      f"AltSetting {intf.bAlternateSetting}, "
                      f"Class 0x{intf.bInterfaceClass:02x}")

                # Try to check and detach kernel driver on Linux, but catch permission errors
                if sys.platform.startswith("linux"):
                    try:
                        active = dev.is_kernel_driver_active(intf.bInterfaceNumber)
                    except usb.core.USBError as e:
                        print(f"      Could not check kernel driver on iface {intf.bInterfaceNumber}: {e}")
                        active = False

                    if active:
                        try:
                            dev.detach_kernel_driver(intf.bInterfaceNumber)
                            print(f"      Detached kernel driver from iface {intf.bInterfaceNumber}")
                        except usb.core.USBError as e:
                            print(f"      Could not detach kernel driver: {e}")

                for ep in intf:
                    dir_flag = usb.util.endpoint_direction(ep.bEndpointAddress)
                    direction = "IN" if dir_flag == usb.util.ENDPOINT_IN else "OUT"
                    print(f"      Endpoint 0x{ep.bEndpointAddress:02x} ({direction}), "
                          f"Attrs 0x{ep.bmAttributes:02x}, "
                          f"MaxPkt {ep.wMaxPacketSize}")
        print()

if __name__ == "__main__":
    find_usb_displays()
