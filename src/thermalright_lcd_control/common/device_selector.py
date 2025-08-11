import usb.core
import usb.util
import yaml


def load_gui_config(config_path="./resources/gui_config.yaml"):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def find_supported_device(config):
    supported = config.get("supported_devices", [])
    connected = list(usb.core.find(find_all=True))

    for dev in connected:
        vid = f"0x{dev.idVendor:04x}"
        pid = f"0x{dev.idProduct:04x}"

        for entry in supported:
            if entry.get("vid") == vid and entry.get("pid") == pid:
                print(f"Matched device: {vid}:{pid}")
                return entry

    print("No supported device found")
    return None
