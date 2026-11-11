#!/bin/bash
# One-time setup so the Teensy 4.0 can be flashed from the Jetson without root.
#   sudo bash Hardware/teensy_strobe/install_teensy_loader.sh
# then, as brain (no sudo):
#   git clone --depth 1 https://github.com/PaulStoffregen/teensy_loader_cli.git ~/tools/teensy_loader_cli
#   make -C ~/tools/teensy_loader_cli
#
# Ubuntu 20.04's own teensy-loader-cli package (2.1) predates the Teensy 4.0
# and refuses --mcu=TEENSY40, so PJRC's current source (2.3) is built
# instead; it needs the libusb-0.1 headers (libusb-dev). Also installs PJRC's
# udev rule for the Teensy vendor ID (16c0): world read/write on the Teensy's
# serial and bootloader (HID) interfaces, and ModemManager told to leave the
# serial port alone. Flashing: flash_teensy.sh.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo" >&2
    exit 1
fi

apt-get install -y libusb-dev

cat > /etc/udev/rules.d/00-teensy.rules <<'EOF'
# PJRC Teensy - https://www.pjrc.com/teensy/00-teensy.rules
ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="04[789B]?", ENV{ID_MM_DEVICE_IGNORE}="1", ENV{ID_MM_PORT_IGNORE}="1"
ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="04[789A]?", ENV{MTP_NO_PROBE}="1"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="04[789ABCD]?", MODE:="0666"
KERNEL=="ttyACM*", ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="04[789B]?", MODE:="0666"
KERNEL=="hidraw*", ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="04[789ABCD]?", MODE:="0666"
EOF

udevadm control --reload-rules
udevadm trigger
echo "libusb-dev installed, udev rule in place - now build the loader as brain (see header)"
