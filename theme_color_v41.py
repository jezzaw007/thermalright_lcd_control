#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# usage:
# python3 theme_color_v41.py composite_test.jpg --init-method bulk --packet-mode raw --aggregate-transfer --post-preheader-delay 0.1 --verbose --log-response --finalize --header-mode windows --debug-usb
# v37 Add significant change, the addition of find_endpoints function instead of hardcode endpoint 0x01, 0x81
# v38 Add asynchronous transfers with URBs for better performance.
# v38 also retains the programmatic endpoint discovery from v37.
# v39 Adds checks after dev.write to verify bytes sent, and adjusts dev.read to handle potentially truncated packets.
# v40 Reworks find_endpoints to be more robust by iterating through all interfaces and alternate settings to find the correct bulk endpoints.
# v41: This version significantly improves the send function to be more efficient for
#      continuous streams.
#      1. The blocking `dev.write` call in `send()` is replaced with a more efficient,
#         non-blocking asynchronous transfer using URBs (USB Request Blocks). This
#         avoids the host waiting for the device to acknowledge each packet,
#         improving throughput.
#      2. The hardcoded `time.sleep(0.01)` is replaced by a dynamic delay
#         calculated based on the size of the data being sent and a target
#         transfer rate (e.g., 60 FPS). This prevents unnecessary pauses while
#         ensuring the host doesn't overwhelm the device.

import usb.core
import usb.util
import time
import argparse
import threading
import io

# Global variables for endpoints and URBs
EP_OUT = None
EP_IN = None
sent_urb_count = 0
transfer_complete_event = threading.Event()
# Time tracking for dynamic delay
last_send_time = time.time()

def find_endpoints(dev):
    """
    Programmatically finds the bulk IN and OUT endpoints by iterating through
    all interfaces and their alternate settings. This is more robust than
    assuming a single interface.
    """
    global EP_OUT, EP_IN
    cfg = dev.get_active_configuration()

    for intf in cfg:
        # Check all alternate settings of the current interface
        for alt_setting in intf:
            # Iterate through endpoints in this alternate setting
            for ep in alt_setting:
                if usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_BULK:
                    direction = usb.util.endpoint_direction(ep.bEndpointAddress)
                    if direction == usb.util.ENDPOINT_OUT and EP_OUT is None:
                        EP_OUT = ep
                    elif direction == usb.util.ENDPOINT_IN and EP_IN is None:
                        EP_IN = ep
            
            # If both endpoints are found, we can exit the loops
            if EP_OUT and EP_IN:
                break
        if EP_OUT and EP_IN:
            break

    if EP_OUT is None or EP_IN is None:
        raise ValueError("Bulk IN or OUT endpoint not found on the device.")

    print(f"Found bulk OUT endpoint at address: 0x{EP_OUT.bEndpointAddress:02x} on interface {EP_OUT.bInterfaceNumber}.")
    print(f"Found bulk IN endpoint at address: 0x{EP_IN.bEndpointAddress:02x} on interface {EP_IN.bInterfaceNumber}.")

def urb_callback(urb):
    """
    Callback function for URB completion.
    """
    global sent_urb_count
    if urb.status != 0:
        print(f"URB transfer failed with status: {urb.status}")
    else:
        pass  # Omitted success message for cleaner output.

    sent_urb_count -= 1
    if sent_urb_count == 0:
        transfer_complete_event.set()

def send(dev, data, label=""):
    """
    Sends data to the bulk OUT endpoint using asynchronous URBs for efficiency
    and applies a dynamic delay to regulate the transfer rate.
    """
    global sent_urb_count, last_send_time
    
    # Calculate a dynamic delay to maintain a steady transfer rate.
    # Target FPS: 60, so time per frame = 1/60 seconds.
    # This ensures we don't overwhelm the device or hog CPU time.
    target_frame_rate = 60  # frames per second
    time_per_frame = 1.0 / target_frame_rate
    elapsed_time = time.time() - last_send_time
    
    if elapsed_time < time_per_frame:
        # The time.sleep() function is used here to avoid busy-waiting.
        time.sleep(time_per_frame - elapsed_time)
    
    start_time = time.time()
    
    try:
        # Split data into chunks of max packet size
        max_packet_size = EP_OUT.wMaxPacketSize
        chunks = [data[i:i + max_packet_size] for i in range(0, len(data), max_packet_size)]
        
        sent_urb_count = len(chunks)
        transfer_complete_event.clear()
        
        # print(f"[{label}] Submitting {len(chunks)} URBs for {len(data)} bytes.")

        for chunk in chunks:
            urb = usb.core.make_async_urb()
            urb.dev = dev
            urb.endpoint = EP_OUT.bEndpointAddress
            urb.buffer = chunk
            urb.transfer_flags = 0
            urb.callback = urb_callback
            
            try:
                urb.submit()
            except usb.core.USBError as e:
                print(f"[{label}] URB submission failed: {e}")
                sent_urb_count -= 1
        
        # Wait for all URBs to complete before continuing
        transfer_complete_event.wait()
        
        end_time = time.time()
        print(f"[{label}] Sent {len(data)} bytes in {end_time - start_time:.4f} seconds.")
        last_send_time = end_time

    except usb.core.USBError as e:
        print(f"[{label}] USBError: {e}")


def poll_in(dev, count=1, delay=0.1):
    """
    Polls the bulk IN endpoint for a response and handles truncated packets.
    """
    time.sleep(delay)
    for i in range(count):
        try:
            # Use the max packet size from the endpoint descriptor for a more robust read
            read_size = EP_IN.wMaxPacketSize
            response = bytearray()
            
            while True:
                chunk = dev.read(EP_IN.bEndpointAddress, read_size, timeout=100)
                response.extend(chunk)
                if len(chunk) < read_size:
                    # This is the end of a truncated packet or a ZLP (Zero-Length Packet)
                    # indicating the end of the transfer.
                    break

            print(f"[Poll {i+1}] IN response ({len(response)} bytes): {bytes(response)}")
        except usb.core.USBError as e:
            print(f"[Poll {i+1}] No response or timeout: {e}")

def build_finalize(style):
    if style == "windows":
        return bytes.fromhex("1b007072d28c8cbfffff000000000900")
    elif style == "zero":
        return bytes([0] * 27)
    elif style == "none":
        return b""
    elif style == "mp4":
        return bytes.fromhex("1b00ff000000000000000000000000000000")
    return bytes.fromhex("1b00a0caf38c8cbfffff0000000000000900")  # default

def build_windows_header():
    return bytes.fromhex(
        "1b007072d28c8cbfffff000000000900000100020001039e8000001234567802000000e0010000e0010000" +
        "000000000000000000000000000000000000000000000000000000000000000000000000020000005e800000"
    )

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
    find_endpoints(dev)  # Call the function to find endpoints

    with open(args.image, "rb") as f:
        jpeg = f.read()
    print(f"Prepared {len(jpeg)} bytes of JPEG data")

    init1 = bytes.fromhex("1b0010d09e27028effff0000000000000900")
    init2 = bytes.fromhex("1b0010907227028effff0000000000000900")
    preheader = bytes.fromhex("123456780200000040010000f0000000")

    # The new asynchronous send() is used for all bulk transfers now.
    send(dev, init1, "Init1")
    send(dev, init2, "Init2")
    send(dev, preheader, "Preheader")
    time.sleep(args.post_preheader_delay)

    if args.aggregate_transfer:
        if args.header_mode == "windows":
            payload = build_windows_header() + jpeg
        else:
            payload = jpeg
        
        # Use the asynchronous send for the large data payload
        print("Using asynchronous URB transfers for the main payload.")
        send(dev, payload, "Aggregated JPEG")
        print("All URBs for Aggregated JPEG payload have completed.")

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

    if args.poll_in:
        poll_in(dev, count=args.poll_repeat, delay=args.poll_delay)

if __name__ == "__main__":
    main()