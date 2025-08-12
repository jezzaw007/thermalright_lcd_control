#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This version updates the script to reflect the precise timings and dynamic
# header data found in the latest Wireshark trace.
# The previous time.sleep() has been removed, and the header now includes
# the dynamic bytes observed in the trace.
# python3 theme_color_v45.py composite_test.jpg --aggregate-transfer --poll-in --finalize


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
            # Shortened the timeout since the actual delay is very quick
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

def build_dynamic_header(jpeg_size, payload_length, frame_number):
    """
    Builds the dynamic header based on the Wireshark trace.
    The header starts with `1b 00` and contains a dynamic 4-byte value.
    This implementation uses a placeholder value for now, but in a full
    implementation, this would be a calculated value (e.g., a timestamp or counter).
    """
    # Header from Frame 13
    dynamic_header_1 = bytes.fromhex("1b00a0ead98c8cbfffff0000000009000001000200010330810000")
    
    # Header from Frame 15
    dynamic_header_2 = bytes.fromhex("1b0010a0eb8a8cbf ff ff 00 00 00 00 09 00 00 01 00 02 00 01 03 30 81 00 00")

    # This part contains the `12 34 56 78` signature
    core_header_part = bytes.fromhex("1234567802000000e0010000e0010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000")
    
    # Append a length value, likely the total payload size
    length_part = payload_length.to_bytes(4, 'little')

    if frame_number == 1:
        return dynamic_header_1 + core_header_part + length_part
    else:
        # Use a hardcoded value from the second frame for demonstration
        return dynamic_header_2 + core_header_part + length_part

def build_finalize(style):
    if style == "windows":
        return bytes.fromhex("1b007072d28c8cbfffff000000000900")
    elif style == "zero":
        return bytes([0] * 27)
    elif style == "none":
        return b""
    elif style == "mp4":
        return bytes.fromhex("1b00ff000000000000000000000000000000")
    return bytes.fromhex("1b00a0caf38c8cbfffff0000000000000900")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--init-method", choices=["bulk"], default="bulk")
    parser.add_argument("--packet-mode", choices=["raw"], default="raw")
    parser.add_argument("--aggregate-transfer", action="store_true")
    parser.add_argument("--header-mode", choices=["default", "windows"], default="default")
    parser.add_argument("--post-preheader-delay", type=float, default=0.1)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--log-response", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--finalize-style", choices=["default", "windows", "zero", "none", "mp4"], default="default")
    parser.add_argument("--finalize-repeat", type=int, default=1)
    parser.add_argument("--trigger-packet", action="store_true")
    parser.add_argument("--poll-in", action="store_true")
    parser.add_argument("--poll-delay", type=float, default=0.1)
    parser.add_argument("--poll-repeat", type=int, default=1)
    parser.add_argument("--control-commit", action="store_true")
    parser.add_argument("--debug-usb", action="store_true")
    args = parser.parse_args()

    dev = usb.core.find(idVendor=0x87ad, idProduct=0x70db)
    if dev is None:
        raise ValueError("Device not found")
    
    dev.set_configuration()
    find_endpoints(dev)

    with open(args.image, "rb") as f:
        jpeg = f.read()
    print(f"Prepared {len(jpeg)} bytes of JPEG data")

    # --- Handshake based on Wireshark trace (Frames 13 & 14) ---

    # 1. Construct the complete payload with the dynamic header.
    # The total length is the length of the JPEG data plus the header size.
    payload_length = len(jpeg)
    header = build_dynamic_header(len(jpeg), payload_length, frame_number=1)
    full_payload = header + jpeg
    
    # 2. Send the entire packet at once.
    send(dev, full_payload, "Full Image Payload with Header")

    # 3. Read the acknowledgment from the device.
    # The device sends a 27-byte response after receiving the image.
    read_response(dev, "Device Acknowledgment (27 bytes)", expected_size=27)

    # --- The trace shows the pattern repeats for subsequent frames ---
    
    if args.finalize:
        finalize_packet = build_finalize(args.finalize_style)
        for i in range(args.finalize_repeat):
            send(dev, finalize_packet, f"Finalize {i+1}")

    if args.trigger_packet:
        trigger = bytes.fromhex("1b00ff00000000000000000000000000")
        send(dev, trigger, "Trigger")

    if args.control_commit:
        try:
            response = dev.ctrl_transfer(0x40, 0x01, 0, 0, [])
            print("Control commit sent")
        except usb.core.USBError as e:
            print("Control commit failed:", e)

if __name__ == "__main__":
    main()
