# Jetson LM — DIY Golf Launch Monitor

## What this project is
Porting PiTrac (open source golf launch monitor) from Raspberry Pi to NVIDIA Jetson Xavier NX.
PiTrac uses strobe-lit cameras to measure golf ball speed, launch angles, and 3-axis spin.
This fork replaces the RPi-specific camera stack with a Jetson/V4L2 compatible implementation.

## Target hardware
- NVIDIA Jetson Xavier NX (JetPack 5.1.6, Ubuntu 20.04, CUDA 11.4, OpenCV 4.5.4)
- 2x Arducam OV9281 Monochrome USB3 global shutter cameras (not yet arrived)
- 850nm IR LED array + IR strobe via Jetson GPIO (~10-15µs pulse)
- No LiDAR in v1 — camera-only trigger
- GSPro running on separate Windows PC, Jetson sends shot JSON over TCP

## The single porting seam
**`Software/LMSourceCode/ImageProcessing/src/libcamera_interface.h`**
This is the ONLY file that touches RPi-specific camera code.
All other PiTrac code (ball detection, spin, GSPro) is hardware-independent — do not touch it.

The strategy:
1. Create `Software/LMSourceCode/ImageProcessing/src/v4l2_interface.h` — identical function signatures
2. Create `Software/LMSourceCode/ImageProcessing/src/v4l2_interface.cpp` — reimplemented using OpenCV VideoCapture + V4L2
3. Use `#ifdef JETSON_BUILD` compile guard to swap includes at build time
4. Stub out libcamera references in meson.build with `# JETSON_STUB` comments

## What NOT to do
- Do not modify any ball detection, spin calculation, or GSPro code
- Do not install or reference libcamera — it is RPi-only and does not exist on Jetson
- Do not install or reference LGPIO — it is RPi-only
- Do not write code until the approach has been agreed in plain language first
- Do not suggest hardware or libraries not listed here without asking first

## Build system
- Meson + Ninja
- Main build file: `Software/LMSourceCode/ImageProcessing/meson.build`
- Build command (on Jetson): `meson setup build_jetson --wipe && ninja -C build_jetson`
- PITRAC_ROOT = `Software/LMSourceCode`

## Key dependencies (all must work on JetPack 5.1.6 ARM64)
- OpenCV 4.5.4 with CUDA — already installed on Jetson
- Boost (log, thread, filesystem, system) — apt installable
- msgpack-c — apt installable  
- ActiveMQ-CPP 3.9.5 — must build from source
- Java OpenJDK + Maven — apt installable (for web GUI)
- V4L2 — built into Linux kernel, headers via libv4l-dev

## Known issues — do not try to fix these
1. libcamera does not exist on Jetson — camera abstraction must be rewritten (this is the active work)
2. IR strobe timing on Jetson GPIO unknown — validate with oscilloscope when cameras arrive
3. Spin requires marked balls — accepted, non-negotiable
4. GSPro is Windows-only — Jetson sends data over TCP, not a bug

## Current task
Reading libcamera_interface.h to map all 13 functions before writing any replacement code.
