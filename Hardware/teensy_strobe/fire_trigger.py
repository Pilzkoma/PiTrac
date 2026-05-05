#!/usr/bin/env python3
# Fire-trigger helper invoked from pulse_strobe_jetson.cpp via std::system().
# Pulses the configured fire-pin HIGH for ~5ms via Jetson.GPIO — the path
# proven to drive Pin 29 on the Seeed Xavier NX carrier where libgpiod
# chardev (gpiod_line_set_value) does not.
#
# Latency budget: ~100-200ms for fork+exec+Python startup. Acceptable
# vs the FSM/IPC latency already in the trigger path.

import sys
import time
import Jetson.GPIO as GPIO

PIN = 29  # BOARD pin number — must match kJetsonFireGpioOffset (= PQ.05 = gpiochip1 line 105)

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(PIN, GPIO.OUT, initial=GPIO.LOW)
time.sleep(0.001)            # settle LOW
GPIO.output(PIN, GPIO.HIGH)  # rising edge — Teensy ISR catches this
time.sleep(0.005)            # 5ms hold (well above any scheduler coalescing)
GPIO.output(PIN, GPIO.LOW)
GPIO.cleanup()
sys.exit(0)
