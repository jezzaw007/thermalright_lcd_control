# src/thermalright_lcd_control/common/usb/hid_device.py

class HidDevice:
    def __init__(self, vid, pid, interface=0):
        print(f"HID backend selected for {vid:04x}:{pid:04x}")
        # Add actual HID logic here if needed

    def reset(self):
        print("HID reset called")

    def run(self):
        print("HID run called")
