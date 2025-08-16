#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This script converts an input image to baseline Huffman JPEG,
# builds a hardcoded header, and sends it to a USB display panel.
# Usage: python3 theme_color_v53_huffman.py input_image.jpg

import usb.core
import usb.util
import time
import argparse
import tempfile
from PIL import Image
import struct

# Global variables for endpoints
EP_OUT = None
EP_IN = None

def find_endpoints(dev):
    global EP_OUT, EP_IN
    cfg = dev.get_active_configuration()

    for intf in cfg:
        for ep in intf:
            if usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK:
                direction = usb.util.endpoint_direction(ep.bEndpointAddress)
                if direction == usb.util.ENDPOINT_OUT and EP_OUT is None:
                    EP_OUT = ep
                elif direction == usb.util.ENDPOINT_IN and EP_IN is None:
                    EP_IN = ep
            if EP_OUT and EP_IN:
                break
        if EP_OUT and EP_IN:
            break

    if EP_OUT is None or EP_IN is None:
        raise ValueError("Bulk IN or OUT endpoint not found on the device.")

    print(f"Found bulk OUT endpoint at address: 0x{EP_OUT.bEndpointAddress:02x}")
    print(f"Found bulk IN endpoint at address: 0x{EP_IN.bEndpointAddress:02x}")

def send(dev, data, label=""):
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
    known_header_prefix = bytes.fromhex("1b00a06abe26028effff00000000090000010002000103")
    jpeg_size_part = jpeg_size.to_bytes(4, 'little')
    known_header_suffix = bytes.fromhex("00001234567802000000e0010000e00100000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000")
    header = known_header_prefix + jpeg_size_part + known_header_suffix
    print("Generated hardcoded header length:", len(header))
    print("Generated hardcoded header:", header.hex())
    return header

def prepare_huffman_jpeg(original_path):
    img = Image.open(original_path).convert("RGB")
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    img.save(temp_file.name, format="JPEG", quality=85, optimize=False, progressive=False)
    with open(temp_file.name, "rb") as f:
        jpeg_bytes = f.read()
    print(f"Prepared Huffman JPEG ({len(jpeg_bytes)} bytes)")
    verify_huffman(jpeg_bytes)
    return jpeg_bytes

def verify_huffman(jpeg_bytes):
    if b'\xFF\xC4' in jpeg_bytes:
        print("✅ Huffman tables found (FFC4 marker present)")
    else:
        print("⚠️ No Huffman tables found—check encoding settings")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    args = parser.parse_args()

    dev = usb.core.find(idVendor=0x87ad, idProduct=0x70db)
    if dev is None:
        raise ValueError("Device not found")

    dev.set_configuration()
    find_endpoints(dev)

    jpeg = prepare_huffman_jpeg(args.image)
    jpeg_size = len(jpeg)
    header = build_hardcoded_header(jpeg_size)
    full_payload = header + jpeg

    send(dev, full_payload, "Full Image Payload with Hardcoded Header")
    read_response(dev, "Device Acknowledgment (27 bytes)", expected_size=27)

if __name__ == "__main__":
    main()
