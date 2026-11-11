#!/bin/bash
# Flash a compiled firmware onto the Teensy 4.0 from the Jetson.
#   bash Hardware/teensy_strobe/flash_teensy.sh teensy_strobe.ino.hex
#
# The .hex is built on the Windows box (Arduino IDE / arduino-cli with
# Teensyduino; fqbn teensy:avr:teensy40) and copied over. -s asks the running
# firmware to reboot into the bootloader over USB; if that does not happen
# within the wait, press the button on the Teensy. Needs
# install_teensy_loader.sh once (udev rule).
#
# Ubuntu 20.04's teensy-loader-cli (2.1) predates the Teensy 4.0 and refuses
# --mcu=TEENSY40. PJRC's current source (github.com/PaulStoffregen/
# teensy_loader_cli, 2.3) is built in ~/tools/teensy_loader_cli with `make`
# (needs libusb-dev); TEENSY_LOADER overrides the path.
#
# After flashing the Teensy has lost its pulse configuration; pitrac_lm or
# the sp1_vision tools push it again on their next start.
set -euo pipefail
HEX="${1:?usage: flash_teensy.sh FIRMWARE.hex}"
LOADER="${TEENSY_LOADER:-$HOME/tools/teensy_loader_cli/teensy_loader_cli}"
"$LOADER" --mcu=TEENSY40 -w -s -v "$HEX"
