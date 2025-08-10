import usb.core
import usb.util


class WinUsbDevice:
    def __init__(self, vid, pid, interface=0):
        self.dev = usb.core.find(idVendor=vid, idProduct=pid)
        assert self.dev, f"Device {vid:04x}:{pid:04x} not found"

        self.dev.set_configuration()
        usb.util.claim_interface(self.dev, interface)

        cfg = self.dev.get_active_configuration()
        self.ep_out = usb.util.find_descriptor(
            cfg[(interface, 0)],
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
        )

        assert self.ep_out, f"No OUT endpoint found for interface {interface}"
        self.interface = interface

    def send_header(self, hdr_bytes):
        print(f"Sending header: {len(hdr_bytes)} bytes")
        bmRequestType = 0x21
        bRequest = 0x09
        wValue = (0x02 << 8) | hdr_bytes[0]
        wIndex = self.interface
        self.dev.ctrl_transfer(bmRequestType, bRequest, wValue, wIndex, hdr_bytes)

    def send_frame(self, jpeg_data, report_id, packet_size):
        print(f"Sending JPEG frame: {len(jpeg_data)} bytes")
        off = 0
        while off < len(jpeg_data):
            chunk = jpeg_data[off:off + packet_size - 1]
            packet = bytes([report_id]) + chunk
            packet += b'\x00' * (packet_size - len(packet))
            self.dev.write(self.ep_out.bEndpointAddress, packet, timeout=1000)
            off += len(chunk)

    def reset(self):
        print("WinUSB reset called")
        # Optional: send a control transfer or clear buffers

    def run(self):
        print("WinUSB run called")
        # TODO: Add logic to load image, encode JPEG, and send via send_header + send_frame

    def close(self):
        usb.util.release_interface(self.dev, self.interface)
        usb.util.dispose_resources(self.dev)
