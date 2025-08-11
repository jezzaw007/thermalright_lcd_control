import os
import glob
import io

from PIL import Image
import usb.core
import usb.util
import usb.control
from usb.core import USBError


class WinUsbDevice:
    def __init__(self, vid, pid, interface=0):
        self.dev = usb.core.find(idVendor=vid, idProduct=pid)
        assert self.dev, f"Device {vid:04x}:{pid:04x} not found"

        # detach any OS driver and claim the interface
        if self.dev.is_kernel_driver_active(interface):
            self.dev.detach_kernel_driver(interface)

        self.dev.set_configuration()
        usb.util.claim_interface(self.dev, interface)

        # find the OUT endpoint
        cfg = self.dev.get_active_configuration()
        self.ep_out = usb.util.find_descriptor(
            cfg[(interface, 0)],
            custom_match=lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress)
                == usb.util.ENDPOINT_OUT
        )
        assert self.ep_out, f"No OUT endpoint on interface {interface}"
        self.interface = interface

    def send_header(self, hdr_bytes: bytes):
        """
        Send the 3-byte header using a vendor-class control transfer.
        Falls back to HID Set_Report if the vendor request is NAK’d.
        """
        intf = self.interface
        report_id = hdr_bytes[0]

        # 1) Try Vendor-class, Interface recipient
        bmType = usb.util.build_request_type(
            usb.util.CTRL_OUT,
            usb.util.CTRL_TYPE_VENDOR,
            usb.util.CTRL_RECIPIENT_INTERFACE
        )
        bRequest = 0x01   # typical for WinUSB panels, but may need tweaking
        wValue = (0x02 << 8) | report_id
        wIndex = intf

        try:
            print(f"Trying VENDOR ctrl_transfer (bm={bmType:02x}, bReq={bRequest:02x})")
            self.dev.ctrl_transfer(bmType, bRequest, wValue, wIndex, hdr_bytes, timeout=1000)
            return
        except USBError as e:
            print("Vendor transfer failed:", e)

        # 2) Fallback → HID Set_Report (Class-Interface)
        bmType = usb.util.build_request_type(
            usb.util.CTRL_OUT,
            usb.util.CTRL_TYPE_CLASS,
            usb.util.CTRL_RECIPIENT_INTERFACE
        )
        bRequest = 0x09
        print(f"Falling back to HID Set_Report (bm={bmType:02x}, bReq={bRequest:02x})")
        self.dev.ctrl_transfer(bmType, bRequest, wValue, wIndex, hdr_bytes, timeout=1000)

    def send_frame(self, jpeg_data: bytes, report_id: int, packet_size: int):
        print(f"Sending JPEG frame: {len(jpeg_data)} bytes total")
        offset = 0
        while offset < len(jpeg_data):
            chunk = jpeg_data[offset : offset + packet_size - 1]
            packet = bytes([report_id]) + chunk
            packet += b'\x00' * (packet_size - len(packet))
            self.dev.write(self.ep_out.bEndpointAddress, packet, timeout=1000)
            offset += len(chunk)

    def reset(self):
        print("WinUSB reset called")
        # If your panel needs a reset control-transfer, do it here.

    def run(self, source="resources/frames/"):
        """
        Load and stream all .jpg / .png from `source` folder (or single file).
        Converts PNG→JPEG on the fly via Pillow.
        """
        print("WinUSB run called")

        # gather files
        if os.path.isdir(source):
            patterns = [os.path.join(source, "*.jpg"),
                        os.path.join(source, "*.png")]
            files = sorted(sum((glob.glob(p) for p in patterns), []))
            if not files:
                raise RuntimeError(f"No images found in {source!r}")
        elif os.path.isfile(source):
            files = [source]
        else:
            raise RuntimeError(f"Source {source!r} is not valid")

        for path in files:
            ext = os.path.splitext(path)[1].lower()
            print(f"Loading {os.path.basename(path)}")
            if ext == ".png":
                with Image.open(path) as img:
                    buf = io.BytesIO()
                    img.convert("RGB").save(buf, format="JPEG", quality=90)
                    data = buf.getvalue()
            else:
                with open(path, "rb") as f:
                    data = f.read()

            report_id = 1
            hdr = bytes([report_id,
                         len(data) & 0xFF,
                         (len(data) >> 8) & 0xFF])

            self.send_header(hdr)
            self.send_frame(data, report_id, self.ep_out.wMaxPacketSize)

        self.close()
        print("All frames sent, device closed")

    def close(self):
        usb.util.release_interface(self.dev, self.interface)
        usb.util.dispose_resources(self.dev)
