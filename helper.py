import usb.core, usb.util

VID, PID = 0x87ad, 0x70db
IFACE, ALT   = 0, 0

dev = usb.core.find(idVendor=VID, idProduct=PID)
dev.set_configuration()
if dev.is_kernel_driver_active(IFACE):
    dev.detach_kernel_driver(IFACE)
cfg  = dev.get_active_configuration()
intf = usb.util.find_descriptor(cfg,
    bInterfaceNumber=IFACE,
    bAlternateSetting=ALT
)

print(f"Interface {IFACE} alt {ALT}:")
for ep in intf.endpoints():
    direction = "IN" if ep.bEndpointAddress & 0x80 else "OUT"
    kind      = {0:"Control",1:"Iso",2:"Bulk",3:"Interrupt"}[ep.bmAttributes & 0x3]
    print(f"  • 0x{ep.bEndpointAddress:02X}   {direction}  {kind}")
