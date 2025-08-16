#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This script uses a hardcoded, known-good Windows header
# and a small JPEG file to test if the image itself is the issue.
# python3 theme_color_v52.py composite_test_small.jpg


import usb.core
import usb.util
import time
import argparse
import threading
import io
import struct

# Global variables for endpoints
EP_OUT = None
EP_IN = None

def find_endpoints(dev):
    """
    Programmatically finds the bulk IN and OUT endpoints.
    """
    global EP_OUT, EP_IN
    cfg = dev.get_active_configuration()
    
    out_interface_number = -1
    in_interface_number = -1

    for intf in cfg:
        for ep in intf:
            if usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK:
                direction = usb.util.endpoint_direction(ep.bEndpointAddress)
                if direction == usb.util.ENDPOINT_OUT and EP_OUT is None:
                    EP_OUT = ep
                    out_interface_number = intf.bInterfaceNumber
                elif direction == usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN and EP_IN is None:
                    EP_IN = ep
                    in_interface_number = intf.bInterfaceNumber
            
            if EP_OUT and EP_IN:
                break
        if EP_OUT and EP_IN:
            break

    if EP_OUT is None or EP_IN is None:
        raise ValueError("Bulk IN or OUT endpoint not found on the device.")

    print(f"Found bulk OUT endpoint at address: 0x{EP_OUT.bEndpointAddress:02x} on interface {out_interface_number}.")
    print(f"Found bulk IN endpoint at address: 0x{EP_IN.bEndpointAddress:02x} on interface {in_interface_number}.")

def send(dev, data, label=""):
    """
    Sends data to the bulk OUT endpoint.
    """
    try:
        print(f"[{label}] Sending {len(data)} bytes. First 128 bytes in hex: {data[:128].hex()}")
        bytes_sent = dev.write(EP_OUT.bEndpointAddress, data, timeout=5000)
        
        if bytes_sent != len(data):
            print(f"[{label}] Warning: Sent {bytes_sent} of {len(data)} bytes.")
        
        print(f"[{label}] Sent {bytes_sent} bytes.")

    except usb.core.USBError as e:
        print(f"[{label}] USBError: {e}")
        raise

def read_response(dev, label="", expected_size=None):
    """
    Polls the bulk IN endpoint for a response and handles truncated packets.
    """
    try:
        read_size = EP_IN.wMaxPacketSize
        response = bytearray()
        
        while True:
            chunk = dev.read(EP_IN.bEndpointAddress, read_size, timeout=500)
            response.extend(chunk)
            if len(chunk) < read_size:
                break
        
        if expected_size and len(response) != expected_size:
            print(f"[{label}] Warning: Received unexpected size ({len(response)} bytes), expected {expected_size} bytes.")
        
        print(f"[{label}] IN response ({len(response)} bytes): {bytes(response).hex()}")
        return bytes(response)
        
    except usb.core.USBError as e:
        print(f"[{label}] No response or timeout: {e}")
        return None

def build_hardcoded_header(jpeg_size):
    """
    Builds a header using a hardcoded, static Windows payload.
    This is for testing purposes only to isolate header generation issues.
    """
    # This is a sample header. You MUST replace it with a real header
    # from a successful Windows trace, and adjust the payload size.
    # The size must match your new, smaller JPEG file.
    
    # 1. Hardcoded static and dynamic parts
    known_header_prefix = bytes.fromhex("1b00a06abe26028effff00000000090000010002000103")

    # 2. JPEG size field (4 bytes, little-endian)
    jpeg_size_part = jpeg_size.to_bytes(4, 'little')

    # 3. Hardcoded static parts after the size field
    known_header_suffix = bytes.fromhex("00001234567802000000e0010000e00100000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000")

    header = known_header_prefix + jpeg_size_part + known_header_suffix
    
    print("Generated hardcoded header length:", len(header))
    print("Generated hardcoded header:", header.hex())

    return header

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    args = parser.parse_args()

    dev = usb.core.find(idVendor=0x87ad, idProduct=0x70db)
    if dev is None:
        raise ValueError("Device not found")
    
    dev.set_configuration()
    find_endpoints(dev)

    with open(args.image, "rb") as f:
        jpeg = f.read()
    print(f"Prepared {len(jpeg)} bytes of JPEG data")

    # Use a smaller JPEG file for this test
    jpeg_size = len(jpeg)
    header = build_hardcoded_header(jpeg_size)
    
    full_payload = header + jpeg
    send(dev, full_payload, "Full Image Payload with Hardcoded Header")

    read_response(dev, "Device Acknowledgment (27 bytes)", expected_size=27)

if __name__ == "__main__":
    main()
