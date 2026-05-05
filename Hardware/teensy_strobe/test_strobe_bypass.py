#!/usr/bin/env python3
# Standalone Jetson -> Teensy strobe-pipeline diagnostic.
# Bypasses pitrac_lm: opens /dev/ttyACM0, configures the Teensy with
# long visible pulses, then toggles the fire-trigger GPIO (Pin 29) a
# few times. The test LED on Teensy Pin 3 should flicker on each fire.
#
# Run as root (libgpiod + /dev/ttyACM0 access).
# Usage: sudo python3 test_strobe_bypass.py [fire_count]

import sys
import time
import serial
import Jetson.GPIO as GPIO

DEV = '/dev/ttyACM0'
BAUD = 115200
FIRE_PIN_BOARD = 29  # PQ.05, gpiochip1 line 105 — matches pulse_strobe_jetson.cpp

# Long-pulse config: ON_BITS=32 at BAUD=1000 = 32 ms ON pulse,
# 200 ms intervals between pulses, 7 pulses -> ~1.5 s visible flicker.
SETUP_CMDS = [
    'PULSES_FAST,200,200,200,200,200,200,0',
    'ON_BITS,32',
    'BAUD,1000',
    'MODE,FAST',
]


def send(ser, cmd):
    ser.write((cmd + '\n').encode())
    line = ser.readline().decode().strip()
    print(f"  {cmd:40s} -> {line}")
    return line


def main():
    fire_count = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    print(f"Connecting to Teensy on {DEV} at {BAUD} 8N1...")
    ser = serial.Serial(DEV, BAUD, timeout=2)
    time.sleep(2)
    ser.reset_input_buffer()

    print("Setup:")
    for cmd in SETUP_CMDS:
        if send(ser, cmd) != 'OK':
            print("  setup failed — aborting")
            ser.close()
            sys.exit(1)
    send(ser, 'STATUS')

    print(f"\nClaiming Jetson Pin {FIRE_PIN_BOARD}...")
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(FIRE_PIN_BOARD, GPIO.OUT, initial=GPIO.LOW)

    print(f"\nFiring {fire_count} times — Test-LED on Teensy Pin 3 should flicker each time:")
    for i in range(fire_count):
        print(f"  Fire {i+1}/{fire_count}")
        GPIO.output(FIRE_PIN_BOARD, GPIO.HIGH)
        time.sleep(0.0001)        # 100 us trigger pulse
        GPIO.output(FIRE_PIN_BOARD, GPIO.LOW)
        time.sleep(3)             # space the bursts so each is clearly visible

    GPIO.cleanup()
    ser.close()
    print("Done.")


if __name__ == '__main__':
    main()
