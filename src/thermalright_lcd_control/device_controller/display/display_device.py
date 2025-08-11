# SPDX-License-Identifier: Apache-2.0
# Copyright © 2025 Rejeb Ben Rejeb
import pathlib
import struct
import time
from abc import abstractmethod, ABC
from typing import Optional, Union

import hid
import usb.core
import usb.util
from PIL import Image

from .config_loader import ConfigLoader
from .generator import DisplayGenerator
from ...common.logging_config import LoggerConfig


class DisplayDevice(hid.Device, ABC):
    _generator: DisplayGenerator = None

    def __init__(self, vid, pid, chunk_size, width, height, config_file: str, *args, **kwargs):
        super().__init__(vid, pid)
        self.vid = vid
        self.pid = pid
        self.chunk_size = chunk_size
        self.height = height
        self.width = width
        self.header = self.get_header()
        self.config_file = config_file
        self.last_modified = pathlib.Path(config_file).stat().st_mtime_ns
        self.logger = LoggerConfig.setup_service_logger()
        self._build_generator()
        self.logger.debug(f"DisplayDevice initialized with header: {self.header}")

    def _build_generator(self) -> DisplayGenerator:
        config_loader = ConfigLoader()
        config = config_loader.load_config(self.config_file)
        config.output_width = self.width
        config.output_height = self.height
        return DisplayGenerator(config)

    def _get_generator(self) -> DisplayGenerator:
        if self._generator is None:
            self.logger.info(f"No generator found, reloading from {self.config_file}")
            self._generator = self._build_generator()
            return self._generator
        elif pathlib.Path(self.config_file).stat().st_mtime_ns > self.last_modified:
            self.logger.info(f"Config file updated: {self.config_file}")
            self.last_modified = pathlib.Path(self.config_file).stat().st_mtime_ns
            self._generator = self._build_generator()
            self.logger.info(f"Display device generator reloaded from {self.config_file}")
            return self._generator
        else:
            return self._generator

    def _encode_image(self, img: Image) -> bytearray:
        width, height = img.size
        coords = [(x, y) for x in range(width) for y in range(height - 1, -1, -1)]
        out = bytearray()
        for i, (x, y) in enumerate(coords, start=1):
            if i % height == 0:
                out.extend((0x00, 0x00))
            else:
                r, g, b = img.getpixel((x, y))
                val565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                lo = val565 & 0xFF
                hi = (val565 >> 8) & 0xFF
                out.extend((lo, hi))
        return out

    @abstractmethod
    def get_header(self, *args, **kwargs):
        pass

    def reset(self):
        dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
        if dev is None:
            raise ValueError("Display device not found")
        dev.reset()
        self.logger.info("Display device reinitialised via USB reset")

    def _prepare_frame_packets(self, img_bytes: bytes):
        frame_packets = []
        for i in range(0, len(img_bytes), self.chunk_size):
            chunk = img_bytes[i:i + self.chunk_size]
            if len(chunk) < self.chunk_size:
                chunk += b"\x00" * (self.chunk_size - len(chunk))
            frame_packets.append(bytes([0x00]) + chunk)
        return frame_packets

    def run(self):
        self.logger.info("Display device running")
        while True:
            img, delay_time = self._get_generator().get_frame_with_duration()
            header = self.get_header()
            img_bytes = header + self._encode_image(img)
            frame_packets = self._prepare_frame_packets(img_bytes)
            for packet in frame_packets:
                self.write(packet)
            time.sleep(delay_time)


class USBDisplayDevice(ABC):
    def __init__(self, vid, pid, chunk_size, width, height, config_file: str, endpoint_out, endpoint_in, interface=0):
        self.vid = vid
        self.pid = pid
        self.chunk_size = chunk_size
        self.height = height
        self.width = width
        self.endpoint_out = endpoint_out
        self.endpoint_in = endpoint_in
        self.interface = interface
        self.config_file = config_file
        self.last_modified = pathlib.Path(config_file).stat().st_mtime_ns
        self.logger = LoggerConfig.setup_service_logger()
        self.dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
        if self.dev is None:
            raise ValueError("USB device not found")

        if self.dev.is_kernel_driver_active(self.interface):
            self.dev.detach_kernel_driver(self.interface)
        usb.util.claim_interface(self.dev, self.interface)
        self.logger.info(f"USB device {hex(self.vid)}:{hex(self.pid)} claimed on interface {self.interface}")

        self._generator = self._build_generator()

    def _build_generator(self) -> DisplayGenerator:
        config_loader = ConfigLoader()
        config = config_loader.load_config(self.config_file)
        config.output_width = self.width
        config.output_height = self.height
        return DisplayGenerator(config)

    def _get_generator(self) -> DisplayGenerator:
        if self._generator is None:
            self._generator = self._build_generator()
        elif pathlib.Path(self.config_file).stat().st_mtime_ns > self.last_modified:
            self.last_modified = pathlib.Path(self.config_file).stat().st_mtime_ns
            self._generator = self._build_generator()
        return self._generator

    def _encode_image(self, img: Image) -> bytearray:
        width, height = img.size
        coords = [(x, y) for x in range(width) for y in range(height - 1, -1, -1)]
        out = bytearray()
        for i, (x, y) in enumerate(coords, start=1):
            if i % height == 0:
                out.extend((0x00, 0x00))
            else:
                r, g, b = img.getpixel((x, y))
                val565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                lo = val565 & 0xFF
                hi = (val565 >> 8) & 0xFF
                out.extend((lo, hi))
        return out

    def get_header(self) -> bytes:
        return struct.pack('<BBHHH', 0x69, 0x88, self.width, self.height, 0)

    def _prepare_frame_packets(self, img_bytes: bytes):
        frame_packets = []
        for i in range(0, len(img_bytes), self.chunk_size):
            chunk = img_bytes[i:i + self.chunk_size]
            if len(chunk) < self.chunk_size:
                chunk += b"\x00" * (self.chunk_size - len(chunk))
            frame_packets.append(bytes([0x00]) + chunk)
        return frame_packets

    def send_init_sequence(self):
        init1 = bytes.fromhex("1b0010d09e27028effff000000000900000100020001034000000012345678000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000000")
        assert len(init1) == 91
        init2_raw = bytes.fromhex("1b0010907227028effff0000000009000101000200010300000000")
        assert len(init2_raw) == 27

        self.logger.info("Sending init sequence to ChiZhu panel")
        self.dev.write(self.endpoint_out, init1)
        self.dev.write(self.endpoint_out, init2_raw)

    def run(self):
        self.logger.info("USB display device running")
        while True:
            img, delay_time = self._get_generator().get_frame_with_duration()
            img_bytes = self.get_header() + self._encode_image(img)
            frame_packets = self._prepare_frame_packets(img_bytes)
            for packet in frame_packets:
                self.dev.write(self.endpoint_out, packet)
            time.sleep(delay_time)


class DisplayDevice04185303(DisplayDevice):
    def __init__(self, config_file: str):
        super().__init__(0x0418, 0x5303, 64, 320, 320, config_file)

    def get_header(self) -> bytes:
        return struct.pack('<BBHHH', 0x69, 0x88, 320, 320, 0)


class DisplayDevice04185304(DisplayDevice):
    def __init__(self, config_file: str):
        super().__init__(0x0418, 0x5304, 512, 480, 480, config_file)

    def get_header(self) -> bytes:
        return struct.pack('<BBHHH', 0x69, 0x88, 480, 480, 0)

class DisplayDevice04168001(DisplayDevice):
    def __init__(self, config_file: str):
        super().__init__(0x0416, 0x8001, 64, 480, 480, config_file)

    def get_header(self) -> bytes:
        prefix = bytes([0xDA, 0xDB, 0xDC, 0xDD])
        body = struct.pack('<6HIH', 2, 1, 480, 480, 2, 0, 460800, 0)
        return prefix + body


class DisplayDevice04165302(DisplayDevice):
    def __init__(self, config_file: str):
        super().__init__(0x0416, 0x5302, 512, 320, 240, config_file)

    def get_header(self) -> bytes:
        prefix = bytes([0xDA, 0xDB, 0xDC, 0xDD])
        body = struct.pack('<6HIH', 2, 1, 320, 240, 2, 0, 153600, 0)
        return prefix + body


class ChiZhuDisplay(USBDisplayDevice):
    def __init__(self, config_file: str):
        super().__init__(
            vid=0x87ad,
            pid=0x70db,
            chunk_size=512,
            width=480,
            height=480,
            config_file=config_file,
            endpoint_out=0x01,
            endpoint_in=0x81,
            interface=0
        )

    def get_header(self) -> bytes:
        return struct.pack('<BBHHH', 0x69, 0x88, 480, 480, 0)


def load_device(config_file: str) -> Optional[Union[DisplayDevice, USBDisplayDevice]]:
    try:
        for device in hid.enumerate():
            vid = device['vendor_id']
            pid = device['product_id']
            if vid == 0x0416:
                if pid == 0x5302:
                    return DisplayDevice04165302(config_file)
                elif pid == 0x8001:
                    return DisplayDevice04168001(config_file)
            elif vid == 0x0418:
                if pid == 0x5303:
                    return DisplayDevice04185303(config_file)
                elif pid == 0x5304:
                    return DisplayDevice04185304(config_file)

        # Fallback for USB-only ChiZhu panel
        dev = usb.core.find(idVendor=0x87ad, idProduct=0x70db)
        if dev is not None:
            return ChiZhuDisplay(config_file)

        raise Exception("No supported device found")
    except Exception as e:
        raise Exception(f"Device detection failed: {e}") from e


