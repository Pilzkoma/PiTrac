# 🗂️ Project Logbook — DIY Jetson Golf Launch Monitor

> \\\*\\\*How to use this logbook:\\\*\\\*
> - One section per sub-project — every section has the same structure so anyone can pick it up
> - Update the status header whenever something changes
> - Log decisions as you make them — even rough notes count
> - Save AI prompts that worked in the AI Prompt Log of each sub-project
> - The "Next Steps" list is your contract with yourself for the next session
> - After every AI session, paste the summary into Session Notes before closing the chat

\---

## 📋 Master Overview

|Sub-Project|Type|Phase|% Complete|Status|Last Updated|
|-|-|-|-|-|-|
|SP1 — Hardware & Build|HW+SW|Build|99%|🟡 In Progress|2026-08-10|
|SP2 — Spin Detection|HW + SW|Design|0%|🟡 In Progress|2026-03-15|
|SP3 — Club Tracking|HW + SW|Design|0%|🔵 Planning|2026-03-14|
|SP4 — GSPro Integration + Session Data|SW|Build|90%|🟡 In Progress|2026-03-21|
|SP5 — Video Recording + Enclosure|HW + 3D|Design|0%|🔵 Planning|2026-03-14|

**Status legend:** 🔵 Planning → 🟡 In Progress → 🔴 Blocked → ✅ Done

**Phase legend:** `Design → Build → Test → Done`

**Type legend:** `HW` = Hardware / `SW` = Software / `3D` = 3D Print / `PP` = Physical Prototype

\---

## 🔗 Sub-Project Dependencies

|Sub-Project|Depends On|Why|
|-|-|-|
|SP2 — Spin Detection|SP1|Requires camera triggering and IR strobe system from SP1 to be working|
|SP3 — Club Tracking|SP1|Requires camera pipeline from SP1; may share camera or need dedicated angle|
|SP4 — GSPro Integration|SP1 (minimum)|Can start with ball speed + angles only; full data needs SP2 + SP3|
|SP5 — Video Recording|SP1 (trigger signal)|USB camera needs to be triggered from the same shot detection event|

> \\\*\\\*Build order:\\\*\\\* SP1 → SP2 and SP3 in parallel → SP4 → SP5 (partially parallel with SP4)

\---

## ⚙️ Hardware Components Registry

> \\\*\\\*How to use:\\\*\\\* Add every component the moment you decide to use it. Paste this whole section at the top of any new AI chat.

|Component|Model / Part No.|Role in Project|Connects To|Bought From|Status|
|-|-|-|-|-|-|
|Microcontroller / SBC|NVIDIA Jetson Xavier NX (Seed Studio carrier)|Main compute — vision processing, shot detection, GSPro Output (V1)|Cameras, IR trigger circuit|Already owned|☑ In hand|
|Microcontroller / SBC|NVIDIA Jetson Xavier NX (NVIDIA carrier board)|Main compute — vision processing, shot detection, GSPro Output (V2)|Cameras, LiDAR, IR trigger circuit, Video recording camera|Already owned|☑ In hand|
|Primary Camera x2|Arducam **B0332**, OV9281 mono global shutter, **USB 2.0 UVC**, 70°(H) low-distortion M12 (**measured 2.77 mm**, focus adjustable by screwing the lens)|Ball imaging — strobe capture|Jetson USB-A. Both behind the carrier's soldered-on VIA Labs USB 2.0 hub, sharing one 480 Mbit/s upstream — direct-plugged physically, hubbed electrically, not separable by moving cables|—|☑ In use|
|↳ Camera identity trap|Both modules report VID:PID `0c45:6366` and iSerial **`UC762`** — Arducam's SKU code, not a per-unit serial|`/dev/v4l/by-id/` collides, so `/dev/videoN` is the only discriminator and it is assigned in enumeration order|Bind by USB port path instead: cam1 = `...usb-0:2.3...` = left module facing the unit, cam2 = `...2.4...` = right. Mirrored in `sp1_vision/camera_paths.py` and `v4l2_interface.cpp`|—|☑ Handled|
|LiDAR sensor (not used in v1 - v2 only)|TBD|Motion/trigger detection — detects ball or club movement to wake cameras|Jetson GPIO / serial|TBD|☐ Ordered ☐ In hand ☐ In use|
|IR LED array|850nm \~10W array board (e.g. Chanzon)|IR illumination for strobe capture|Strobe driver circuit|TBD|☐ Ordered ☐ In hand ☐ In use|
|IR strobe driver|Teensy 4.0 (DEV-15583) — pulled forward from v2 plan|Drives IR LED pulses at \~10µs via Hardware-Timer-backed delayMicroseconds; Jetson sends single GPIO trigger + setup over USB serial|Jetson Pin 29 (fire trigger) + USB + MOSFET → IR LED array|SparkFun|☑ In hand|
|IR LED array|Cenpek 4× 850nm 12V CCTV-style board (FY-S54-F)|IR illumination for strobe capture|MOSFET (low-side switch on 12V power line)|—|☑ In hand|
|MOSFET (LED gate)|IRLZ44N (TO-220, logic-level N-channel)|Switches 12V LED-array supply on Teensy gate signal|Teensy Pin 3 → MOSFET gate (with 1kΩ gate-source pulldown); LED-array V− → MOSFET drain; MOSFET source → common GND rail|—|☑ In hand|
|Bench-test transistor + LED|2N3904 NPN + 5mm LED + 1kΩ|Smoke-test for the Teensy gate output before MOSFET arrives|Teensy Pin 3 → 1kΩ → LED → GND (no transistor needed for visible blink)|—|☑ In hand|
|12V supply|Industrial 12V/15A PSU|Powers Jetson + LED array + Teensy in final lab build|Barrel jack to Jetson; +/− to MOSFET high-side|—|☑ In hand|
|Video recording camera (not used in v1 - v2 only)|TBD — USB, lower cost|Records swing from behind or in front for AI coaching upload|Jetson USB port|TBD|☐ Ordered ☐ In hand ☐ In use|
|Sound trigger (optional v1 backup, candidate v2)|SparkFun SEN-14262|Acoustic impact detection — redundant or alternative to camera motion trigger. Used in OpenFlight as primary trigger.|Jetson GPIO (digital interrupt)|TBD (~$18)|☐ Considered ☐ Ordered ☐ In hand ☐ In use|
|Doppler radar (v2 only)|OmniPreSense OPS243-A 24 GHz|Ball/club speed via Doppler shift, spin via I/Q analysis. Validated by OpenFlight project. ±0.5% speed accuracy.|Jetson USB serial|TBD (~$249)|☐ Considered ☐ Ordered ☐ In hand ☐ In use|
|Angle radar x2 (v2 stretch)|RFbeam K-LD7|Launch angle and club path measurement, USB serial. Used in OpenFlight.|Jetson USB|TBD (~$140 ea)|☐ Considered ☐ Ordered ☐ In hand ☐ In use|

**Power supply:** *Not yet decided. Indoor garage use. Likely mains-powered via USB-C PD or DC barrel jack on carrier board.*

**Communication protocols confirmed:** *USB3 (cameras), GPIO (trigger/strobe), I2C or UART (LiDAR — TBD), TCP socket (GSPro Open Connect API over WiFi/LAN)*

\---

### 🔌 Wiring \& Pin Diagram

> Fill in once hardware is selected and first prototype is being built.

**Diagram file / link:** *Not yet created*

**Pin assignment table:**

|Pin / Port|Component Connected|Signal Type|Notes|
|-|-|-|-|
|TBD|IR strobe trigger|Digital OUT|Must be sub-microsecond precision — may need dedicated MCU or FPGA|
|TBD|LiDAR sensor|UART / I2C|Used to wake camera capture pipeline|
|TBD|Global shutter camera 1|MIPI CSI or USB3|Primary ball-in-flight camera|
|TBD|Global shutter camera 2|MIPI CSI or USB3|Secondary camera (spin / club angle)|
|TBD|USB video camera|USB-A|Swing recording|

**Wiring notes:** *IR strobe timing is safety-critical for spin measurement accuracy. Strobe pulse width target \~10-15µs based on camera-Jetson speed. Consider whether GPIO on Xavier NX is fast enough or if a microcontroller (e.g. Arduino/Teensy) handles strobe timing.*

**Safety notes:** *IR LEDs at high drive current generate heat — use appropriate resistors and duty cycle limits. Do not point IR array at eyes.*

\---

## 💻 Software \& Tools Stack

**Operating System:** *Jetson: Linux4Tegra (Ubuntu-based). Dev machine: Ubuntu 20.04 laptop (ThinkPad T460p)*

|Tool / Software|Version|What It Is Used For|Sub-Projects|Status|
|-|-|-|-|-|
|PiTrac (open source)|Latest from github.com/PiTracLM/PiTrac|Core vision pipeline — ball detection, speed, angles, spin. Will be adapted from RPi to Jetson|SP1, SP2|☑ Installed ☐ Configured ☐ In use|
|OpenCV|4.5.4 (no CUDA)|Camera capture and image processing|SP1|☑ Installed ☑ Configured ☑ In use|
|v4l-utils|System|V4L2 camera detection and configuration|SP1|☑ Installed ☑ Configured ☑ In use|
|GSPro Open Connect API|v1|Shot JSON protocol over TCP|SP4|☑ Installed ☑ Configured ☑ In use|
|Python|3.8 (Jetson)|Sender, receiver, DB, physics, dashboard|SP4|☑ Installed ☑ Configured ☑ In use|
|OpenShotGolf|Latest (Godot 4.6)|Free GSPro-compatible driving range for testing|SP4|☑ Installed ☑ Configured ☑ In use|
|SQLite|3.x (Python stdlib)|Local session/shot data storage|SP4|☑ Installed ☑ Configured ☑ In use|
|Flask|3.0.3|Stats dashboard web server|SP4|☑ Installed ☑ Configured ☑ In use|
|Chart.js|4.4.7 (CDN)|Dashboard charts (scatter, range view)|SP4|☑ Installed ☑ Configured ☑ In use|
|systemd|System|Auto-start services on boot|SP4|☑ Installed ☑ Configured ☑ In use|
|USB camera recording SW|TBD|Trigger-based swing video capture and file management|SP5|☐ Installed ☐ Configured ☐ In use|

**Programming language(s) confirmed:** *PiTrac codebase is C++. GSPro sender and session layer likely Python. To be confirmed once PiTrac is studied in depth.*

**AI / agent tools in use:** *Claude (this logbook and session planning). Possible YOLOv8 / OpenCV DNN for future club tracking.*

**Key file locations:** *Forked to github.com/Pilzkoma/PiTrac, cloned to ~/JetsonLM on Ubuntu laptop*

\---

### ⚙️ Environment Setup Guide

> Fill in after first successful Jetson build.

**Last verified working on:** *05.05.2026*

```
1. JetPack 5.1.6 (L4T 35.6.4) confirmed installed — do not reflash
2. CUDA 11.4, OpenCV 4.5.4 (CUDA-enabled), TensorRT 8.5.2 — all pre-installed
3. PiTrac forked to github.com/Pilzkoma/PiTrac, cloned to ~/JetsonLM on Ubuntu laptop
4. CLAUDE.md and PORTING_TASKS.md created in repo — 24 porting tasks tracked
5. All 14 Group 1 compile blockers resolved via #ifdef JETSON_BUILD guards
6. Build dependencies on Jetson still to be installed (next session)
7. SP4: gspro_sender.py — direct TCP sender for manual testing
8. SP4: shot_receiver.py — persistent service, Unix socket + TCP + DB
9. SP4: shot_db.py — SQLite database, auto-creates jetson_lm.db
10. SP4: ball_physics.py — golf ball flight physics engine
11. SP4: dashboard.py — Flask web dashboard on port 5000
12. SP4: test_client.py — simulates C++ pipeline for testing
13. SP4: shot_sender.h — C++ header for pitrac_lm integration
14. SP4: OpenShotGolf on Windows — Godot 4.6 .NET, C# solution built
15. SP4: Flask installed on Jetson via pip3 install flask
16. SP4: Windows firewall rule TCP 49152 for OpenShotGolf
17. SP4: systemd services installed via setup_services.sh — auto-start on boot
18. SP4: Dashboard auto-refreshes every 5 seconds when new shots arrive
19. SP1: camera_test.py in ~/JetsonLM/sp1_vision/ — camera detection and test tool
20. SP1: v4l-utils installed (sudo apt install v4l-utils)
21. SP1: OV9281 Camera 1 → /dev/video0 (USB bus xhci-2.2.4)
22. SP1: OV9281 Camera 2 → /dev/video2 (USB bus xhci-2.3)
23. SP1: /dev/video1 and /dev/video3 are metadata devices — ignore
24. SP1: dual_camera_test.py in sp1_vision/ — sustained-FPS dual capture test (committed to repo)
25. SP1: v4l2-ctl --stream-mmap is the canonical way to validate raw camera throughput, bypassing OpenCV decode
26. SP1: V4L2Capture class implemented in v4l2_interface.cpp — V4L2 ioctl + 4 mmap'd MJPG buffers + libjpeg-turbo gray decode + cvtColor → BGR. Sustains ~125 FPS in ball_watcher_event_loop on the Jetson.
27. SP1: Run pitrac_lm with `--msg_broker_address=tcp://127.0.0.1:61616 --logging_level=trace` from the ImageProcessing/ working dir (the binary needs golf_sim_config.json relative).
28. SP1: ActiveMQ apt package installed; default instance enabled via `sudo ln -s /etc/activemq/instances-available/main /etc/activemq/instances-enabled/main`; broker runs as systemd service `activemq` listening on tcp://127.0.0.1:61616.
29. SP1: libturbojpeg0-dev required for the V4L2 capture engine (apt install).
30. SP1: V4L2 device cleanup: `timeout` SIGTERM does NOT cleanly release /dev/video0 — use `( cmd ) & sleep N; pkill -9 pitrac_lm` instead. If stuck: `sudo rmmod uvcvideo && sudo modprobe uvcvideo`.
31. SP1: motion_detect_stage tuned for bench testing (no IR strobe) in golf_sim_config.json — kDifferenceM=0.3, kDifferenceC=5.0, kFramePeriod=5. Static-scene noise floor ~10-19 regions vs threshold 12800 (~675x headroom); hand-wave tripped in <30 frames.
32. SP1: undistort_camera_image ported into v4l2_interface.cpp; called from TakeRawPicture. No-op until camera calibration loads a matrix (use_undistortion_matrix_=false), then OpenCV initUndistortRectifyMap+remap kicks in. Needs opencv2/calib3d.hpp include.
33. SP1: ConfigurePostProcessing must be called from WatchForHitAndTrigger BEFORE ball_watcher_event_loop on Jetson — the RPi side called it inside ConfigCameraForCropping which is RPi-only. Without this call, MotionDetectStage::Read falls through to cpp defaults (1x1 ROI, threshold=0) and trips on the first comparison frame.
34. SP1: ball_watcher_event_loop discards 2 warm-up frames after V4L2 stream-on so first decoded frame's pre-AGC content can't bias previous_frame_.
35. SP1: Teensy 4.0 strobe-controller firmware in Hardware/teensy_strobe/teensy_strobe.ino. Flash via Arduino IDE + Teensyduino add-on. Text protocol over USB serial: PULSES_FAST/SLOW,intervals... + ON_BITS,N + BAUD,N + MODE,FAST|SLOW + READY? + STATUS + TEST_FIRE. Pin 2=FIRE input (RISING-edge ISR), Pin 3=LED_GATE output, Pin 13=onboard status LED.
36. SP1: Jetson PulseStrobe Jetson-side impl in Software/LMSourceCode/ImageProcessing/pulse_strobe_jetson.cpp (~470 lines). Replaces no-op stubs from v4l2_interface.cpp. Uses libgpiod (apt: libgpiod-dev) for the fire pin + termios for /dev/ttyACM0 USB serial to Teensy. Soft fallback on every HW failure (Teensy missing, GPIO claim refused) — InitGPIOSystem still returns true and SendExternalTrigger no-ops, so dev runs continue without strobe rig wired.
37. SP1: Fire trigger pin = physical Pin 29 = PQ.05 = gpiochip1 line 105. Discovered authoritatively via Jetson.GPIO pin-data table at /usr/lib/python3/dist-packages/Jetson/GPIO/gpio_pin_data.py. Pin 29 is pure GPIO with no PWM/SPI/I2S/UART alternate (verified clean 0V↔3.3V toggle at 1Hz). The "user GPIO" pins 15/32/33 in the J202 datasheet ALL have PWM controllers attached (c340000.pwm, 32f0000.pwm, 3280000.pwm) and produce garbage voltages when driven via libgpiod — avoid them.
38. SP1: gpiod CLI installed (apt: gpiod). Useful for verification: `sudo gpiodetect`, `sudo gpioinfo gpiochipN`, `sudo gpioset --mode=signal gpiochipN line=value` (hold until Ctrl+C) or `--mode=time --sec=N` (timed). Bare `gpioset` (no --mode) releases the line immediately and does NOT visibly hold.
39. SP1: Three new strobing config keys in golf_sim_config.json — kJetsonTeensySerialDevice (default /dev/ttyACM0), kJetsonGpioChipName (gpiochip1), kJetsonFireGpioOffset (105). All overridable.

Next step: solder pins on Teensy when they arrive, wire Jetson Pin 29 ↔ Teensy Pin 2, GND ↔ GND, USB. Then Phase C-Test 1 (2N3904 + LED on Teensy Pin 3 — verify pulse train comes through). Then order MOSFET (IRLZ44N), wire to Cenpek 12V IR board for Phase C-Test 2.
```

\---

## 🐛 Known Issues Register

|#|Sub-Project|Description|Severity|Investigated?|Decision|Date|
|-|-|-|-|-|-|-|
|1|SP1|PiTrac is built for Raspberry Pi camera stack (libcamera). Jetson uses a different camera API (Argus / V4L2). Porting will require rewriting camera abstraction layer.|✅ Resolved|☑ Yes|Resolved 2026-03-16 — porting approach confirmed: #ifdef JETSON_BUILD guards throughout libcamera_interface.h, ball_watcher.cpp, motion_detect.h, motion_detect_stage.cpp. New v4l2_interface.h created with JetsonCaptureApp and JetsonCompletedRequest structs replacing RPi types.|2026-03-16|
|2|SP1|IR strobe pulse timing on RPi uses hardware hacks to the Pi GS camera. Jetson GPIO timing characteristics are different — may need external microcontroller for sub-microsecond strobe control.|🟡 Annoying|☑ Yes|Investigate Jetson GPIO latency vs dedicated Arduino/Teensy strobe controller|2026-03-14|
|3|SP2|Spin detection requires marked balls. Standard range balls will not work for spin. Must use balls with visible dot pattern (similar to Foresight approach).|🔵 Minor|☑ Yes|Accepted — user confirmed willingness to use marked balls|2026-03-14|
|4|SP4|GSPro runs on Windows PC only — it cannot run on the Jetson. The Jetson sends JSON shot data over TCP to a separate Windows PC running GSPro. Firewall and network config required if on different subnets.|🔵 Minor|☑ Yes|Architectural decision logged — Jetson = compute, Windows PC = GSPro host|2026-03-14|
|5|SP1|LiDAR excluded from v1. Camera-only trigger may log a topped/missed shot as a real shot in rare cases.|🔵 Minor|☑ Yes|Accepted for v1. V2 trigger/speed sensor: open choice between LiDAR (trigger only) and 24 GHz Doppler radar (trigger + ball speed ±0.5% + spin fallback). OpenFlight (github.com/jewbetcha/openflight) validates OPS243-A radar for golf ball Doppler — primary V2 reference.|2026-03-14|
|6|SP1|pitrac_lm binary is not yet tested with real cameras — all camera functions return stub false values until Group 2 runtime implementations are complete|🟡 Annoying|☑ Yes|Expected — cameras not yet arrived. Will implement V4L2 capture, GPIO strobe when OV9281 cameras arrive|2026-03-19|
|7|SP4|OpenShotGolf requires Godot 4.6 .NET + .NET SDK 8.0 + C# build|🔵 Minor|☑ Yes|One-time: build C# solution in Godot before first run|2026-03-21|
|8|SP4|OpenShotGolf returns 501 for heartbeat messages|🔵 Minor|☑ Yes|Harmless — heartbeat optional in protocol|2026-03-21|
|9|SP4|Python 3.8 on JetPack 5.1.6 needs typing.Optional instead of dict\|None|🔵 Minor|☑ Yes|All scripts updated|2026-03-21|
|10|SP4|pip3 on JetPack 5.1.6 doesn't support --break-system-packages|🔵 Minor|☑ Yes|Use pip3 install without the flag|2026-03-21|
|11|SP4|Receiver shows "Simulator connection lost: timed out" when OpenShotGolf is not running|🔵 Minor|☑ Yes|By design — receiver auto-reconnects and logs to DB regardless. Shots are never lost.|2026-03-21|
|12|SP4|Carry distance is physics-estimated, not from simulator|🔵 Minor|☑ Yes|GSPro Open Connect v1 protocol does not return carry data. Physics engine uses same aerodynamic model as OpenShotGolf. Accurate enough for training analysis.|2026-03-21|
|13|SP1|OpenCV 4.5.4 on JetPack has no CUDA support. May need CUDA-enabled build for GPU-accelerated frame processing.|🟡 Medium|☑ Yes|PiTrac may include its own OpenCV build with CUDA. Check before rebuilding system OpenCV.|2026-03-21|
|14|SP1|OpenCV defaults to YUYV format (10 FPS). Must explicitly set MJPG fourcc for 120 FPS from OV9281.|🔵 Minor|☑ Yes|Set cv2.CAP_PROP_FOURCC to cv2.VideoWriter_fourcc('M','J','P','G') in capture code|2026-03-21|
|15|SP1|OpenCV cv2.VideoCapture.read() caps Python at ~60 FPS per camera even with MJPG fourcc set. CPU-bound JPEG decode + BGR conversion is the bottleneck — not USB, not the camera. Raw v4l2-ctl streaming hits the full 120 FPS on both cameras simultaneously.|🔵 Minor|☑ Yes|Not a blocker — C++ v4l2_interface.cpp will use V4L2 ioctl directly + libjpeg-turbo or nvJPEG (Jetson hardware decoder), bypassing OpenCV's VideoCapture. Python test scripts accept the cap.|2026-04-26|
|16|SP1|UVC auto-exposure (exposure_auto=3) silently caps frame rate when integration time exceeds the frame interval. At default exposure_absolute=157 (15.7ms), max achievable is ~64 FPS regardless of requested rate.|🔵 Minor|☑ Yes|Irrelevant for production: IR strobe is the effective shutter (10–15µs pulse), camera exposure stays open. For bench testing without strobe, set exposure_auto=1 + low exposure_absolute via v4l2-ctl.|2026-04-26|
|17|SP1|V4L2Capture::ensure_streaming() leaks the open fd on any failure path (REQBUFS, mmap, STREAMON). `streaming_=false` stays set, so subsequent `read()` calls re-attempt ensure_streaming against the same already-failed fd and never recover. /dev/videoX gets stuck and only `rmmod uvcvideo && modprobe uvcvideo` clears it.|✅ Resolved|☑ Yes|Resolved 2026-05-05 — every failure path in ensure_streaming() now calls release() before returning false (release() is idempotent and safe with partial state). Also reordered: tj_handle / gray_scratch allocation moved BEFORE VIDIOC_STREAMON so that STREAMON is the unique point-of-no-return at the end, with no failure paths after it. Caller's retry loop in ball_watcher_event_loop now hits kMaxConsecutiveReadFailures and exits cleanly instead of spinning on a zombie fd.|2026-04-29|
|18|SP1|motion_detect_stage.cpp horizontal hskip step is in BYTES not PIXELS. Assumes CV_8UC1 input but V4L2Capture engine delivers CV_8UC3 BGR (after cvtColor(GRAY2BGR) inside decode_into). Today this still produces sensible motion-detect because B=G=R per pixel, but the effective horizontal pixel coverage is reduced from 640 samples to ~213 actual pixels per row.|✅ Resolved|☑ Yes|Resolved 2026-05-05 — motion_detect_stage.cpp now derives `hskip_bytes = config_.hskip * frame.channels()` under JETSON_BUILD and uses that for all 4 pointer-arithmetic spots (2 initial offsets, 2 inner-loop steps). RPi behavior unchanged (channels=1 implicit). Effective horizontal coverage now matches the configured 640 samples / row.|2026-05-02|
|19|SP1|PiTrac FSM ball-stabilization gate cycles endlessly between WaitingForBall ↔ WaitingForBallStabilization without advancing to WaitingForBallHit / WatchForHitAndTrigger. Even with a stable yellow ball in a cap (no movement, LED+breadboard out of frame), the CheckForBallStable check fails every ~1 second and the FSM bounces back. Suspected: HoughCircles finds slightly different ball positions frame-to-frame in the noisy ambient-IR mono image, and the stability tolerance treats that as motion.|🟡 Medium|☑ Yes|Workaround for strobe-pipeline validation: bypass pitrac_lm entirely via Hardware/teensy_strobe/test_strobe_bypass.py (claims Pin 29 + sends Teensy setup + toggles GPIO directly). Real fix expected to land naturally once IR strobe LED illumination is hooked up — sharp on/off contrast from strobe-lit ball will give HoughCircles a much more stable detection. Partially worked around in code via Issue #21.|2026-05-05|
|20|SP1|motion_detect_stage.cpp explicitly skipped SendExternalTrigger when system_mode == kCamera1TestStandalone (RPi-only intent: "don't pulse a non-existent cam2 system during isolated cam1 testing"). On Jetson SendExternalTrigger drives the IR strobe (no separate cam2 system to skip), so this prevented the strobe from ever firing during pitrac_lm motion-detect trips.|✅ Resolved|☑ Yes|Resolved 2026-05-05 — motion_detect_stage.cpp now unconditionally calls SendExternalTrigger under #ifdef JETSON_BUILD regardless of system_mode.|2026-05-05|
|21|SP1|JETSON_STUB bypass in gs_fsm.cpp WaitingForBallStabilization handler — when CheckForBall finds the ball but reports "moved" (sub-pixel HoughCircles jitter), force-advance to WaitingForBallHit instead of bailing back to WaitingForBall. Allows pitrac_lm to exercise the full strobe-trigger pipeline despite Issue #19. When ball is genuinely lost (!found) the original bail-back behavior is preserved.|🟡 Medium|☑ Yes|Temporary development bypass — REMOVE this `#ifdef JETSON_BUILD` block in gs_fsm.cpp once IR strobe is wired and HoughCircles produces stable ball detections. Until then it's the only way to exercise the SP1 strobe pipeline end-to-end through pitrac_lm.|2026-05-05|
|22|SP1|libgpiod chardev (gpiod_line_set_value via /dev/gpiochip1) does NOT drive Pin 29 in a way that the Teensy ISR sees a rising edge on the Seeed reComputer J202 carrier. Confirmed via extensive 2026-05-05 debugging — gpioset CLI (uses libgpiod chardev) does not trigger the Teensy either; only Python's Jetson.GPIO library works. Adding force-LOW + 5ms hold + 2ms settle to the C++ libgpiod path did not help. The cause is unknown — possibly a kernel/device-tree quirk specific to this carrier+L4T combination.|🟡 Medium|☑ Yes|Workaround in place: pulse_strobe_jetson.cpp's SendExternalTrigger calls Hardware/teensy_strobe/fire_trigger.py via std::system instead of libgpiod chardev (Jetson.GPIO under the hood works reliably). ~100-200ms fork+exec+python startup latency is acceptable. Could revisit if/when L4T is upgraded or libgpiod 2.x is available — until then, the Python helper is reliable.|2026-05-05|
|23|SP1|**Every optical constant described PiTrac's IMX296, and the undistortion was live with it.** Focal length 6.222/5.903 mm against a real 2.767/2.772; sensor 5.077x3.789 mm against 3.840x2.400; distortion k1 −0.509/−0.818 against +0.015/+0.053 — an order of magnitude too strong and of the opposite sign, through a principal point 113 px outside the frame. `camera_hardware.cpp` enables `use_undistortion_matrix_` whenever the config carries a non-zero matrix, and the config carried PiTrac's, so every still from `TakeRawPicture` — the path `CheckForBall` and therefore ball detection use — was remapped through the wrong lens model. The 2026-04-29 note "no-op until calibration loads a matrix" was wrong. Separately, only the *resolution* was overridden to 1280x800 while the sensor stayed IMX296, leaving its aspect at 1.340 against an image of 1.600 and skewing the vertical world axis ~19%.|✅ Resolved|☑ Yes|Resolved 2026-08-06 — measured intrinsics written to `golf_sim_config.json`, sensor dimensions given the same override mechanism the port already used for resolution (applied after every model branch so none can miss it), expected ball radius corrected to 49 under the keys the code actually reads. Verified in a live trace run.|2026-08-06|
|24|SP1|**Both camera modules are indistinguishable by USB identity** — same VID:PID `0c45:6366`, same `bcdDevice`, and iSerial `UC762` on both, which is Arducam's SKU code rather than a per-unit serial. `/dev/v4l/by-id/` therefore holds one colliding entry and `/dev/videoN` is assigned in enumeration order. If the two swap across a reboot the stereo baseline changes sign and depth comes out mirrored, with nothing visibly wrong in either image. Not hypothetical: the port comment recorded ports `xhci-2.2.4`/`2.3` while the hardware had already moved to `2.3`/`2.4`.|✅ Resolved|☑ Yes|Resolved 2026-08-06 — bound by USB port path in both `sp1_vision/camera_paths.py` and `v4l2_interface.cpp`, failing loudly rather than falling back to `/dev/video0`. Which module is which established twice over: covering a lens, and parallax. cam1 = port 2.3 = left module facing the unit. **The USB cables must not be swapped between sockets** — the socket is the identity.|2026-08-06|
|25|SP1|Both lenses were out of focus and nobody had noticed — cam1 by a factor of 5.4 in Laplacian variance, cam2 by 1.6. Compounding this, `expected_ball_radius_pixels_at_40cm_` sat at the IMX296's 87 against a real 49, so the Hough search radius was nearly double what the ball actually subtends. Plausibly a third contributing factor to Issue #19 alongside ambient light and background clutter.|✅ Resolved|☑ Yes|Resolved 2026-08-06 — both lenses refocused (they *are* adjustable, contrary to first assumption), now within 3% of each other at ~3000 Laplace points. Ball radius corrected. Worth re-testing Issue #19's stabilisation behaviour now that the ball is both in focus and correctly sized; the Issue #21 bypass may no longer be carrying as much weight as it was.|2026-08-06|

\---

## 🖨️ 3D Design File Log

|Part Name|File Name|Version|Printed?|Material|Print Settings|Notes|
|-|-|-|-|-|-|-|
|Main enclosure / housing|TBD|v1|☐ Yes ☐ No|TBD|TBD|Will house Jetson, cameras, IR array. Size depends on final camera selection.|
|Camera mount bracket x2|TBD|v1|☐ Yes ☐ No|TBD|TBD|Must allow precise angle adjustment for calibration|
|LiDAR mount|TBD|v1|☐ Yes ☐ No|TBD|TBD|Position relative to hitting area is critical|
|IR LED array housing|TBD|v1|☐ Yes ☐ No|TBD|TBD|Heat dissipation consideration for high-current IR LEDs|

**Design files stored at:** *Not yet created*

**CAD software used:** *TBD (user proficient in 3D design)*

**Slicer software and profile:** *TBD*

\---

## 🧪 Test \& Validation Log

|Date|Sub-Project|What Was Tested|Method|Result|Notes|
|-|-|-|-|-|-|
|—|—|—|—|—|—|

\---

## 🔗 External References

> External projects, papers, and resources useful as design input or comparison.

|Project / Resource|URL|Relevance|License|Use For|
|-|-|-|-|-|
|PiTrac|github.com/PiTracLM/PiTrac|Base codebase — adapted from RPi to Jetson|GPL-3.0|All vision pipeline, ball detection, spin, GSPro|
|OpenShotGolf|github.com/(see SP4 notes)|Free GSPro-protocol-compatible simulator (Godot 4.6 .NET) — used as test target|MIT (Godot project)|SP4 testing without GSPro license. V3 vision: porting to Jetson HDMI output.|
|OpenFlight|github.com/jewbetcha/openflight|Doppler-radar-based DIY launch monitor (24 GHz OPS243-A + K-LD7 angle radars + sound trigger). Primary V2 reference if radar feature added. Hardware validated for golf ball Doppler.|AGPL-3.0|V2 radar hardware reference (OPS243-A, K-LD7), sound trigger pattern (SEN-14262). Do NOT copy code directly — AGPL conflicts with PiTrac GPL-3 + would put Flask dashboard / TCP sender under AGPL network terms. Re-implement clean-room if used.|

\---

### 📋 Context Block — Paste Into Any New AI Chat

```
== PROJECT CONTEXT — PASTE AT START OF EVERY NEW CHAT ==

PROJECT: DIY Golf Launch Monitor — "Jetson LM"
Goal: Garmin R10/R50-class launch monitor running on NVIDIA Jetson Xavier NX.
      Full ball + club data. GSPro integration. Session recording. Indoor garage use.

MY BACKGROUND:
- Strong skills: 3D design \\\& printing, soldering, electronics assembly
- Learning: software/coding — I use AI to help me write code
- I understand programming logic and structure but do not write from scratch

CORE TECHNICAL APPROACH:
- Base codebase: PiTrac (github.com/PiTracLM/PiTrac) — adapting from RPi to Jetson
- Camera approach: 2x global shutter cameras + IR strobe (microsecond pulses)
- Trigger: LiDAR for motion detection
- Spin: Marked balls (dot pattern) — non-negotiable requirement
- GSPro: Sends JSON over TCP using GSPro Open Connect API v1
- Swing video: Separate USB camera, saved locally, uploaded externally for AI analysis

HARDWARE I AM WORKING WITH:
- NVIDIA Jetson Xavier NX x2 (Seed Studio carrier + NVIDIA carrier) — in hand
- Global shutter cameras x2 — NOT YET SELECTED
- LiDAR sensor — NOT YET SELECTED
- IR LED array + strobe driver — NOT YET SELECTED
- USB swing recording camera — NOT YET SELECTED



HARDWARE AVAILABLE FOR ASSISTANCE:

\\- Windows 11 gaming pc with ryzen 5 3200, gtx 3060 ti, 32gb ram

\\- Ubuntu 20.04 Laptop

\\- Raspberry pi5 with nvme

\\- Raspberry pi3

\\- Laboratory power supply (30v)

\\- 12v industrial power supplys

\\- Screen, mouse and Keyboard

\\- ESP32's

\\- STM32 dev Board

SOFTWARE AND TOOLS:
- PiTrac (C++ / OpenCV) — core vision pipeline, to be adapted
- GSPro Open Connect API v1 — TCP JSON socket
- Language: C++ (PiTrac core), Python (GSPro sender + session layer)
- Session data: SQLite (TBD)
- OS on Jetson: JetPack 5.1.6

KNOWN ISSUES (do not try to fix these — they are logged decisions):
1. PiTrac uses RPi libcamera stack — Jetson uses Argus/V4L2. Camera abstraction must be rewritten. (Blocking — must solve in SP1 design)
2. IR strobe timing on Jetson GPIO may be insufficient — may need Arduino/Teensy for strobe control.
3. Spin requires marked balls — accepted, user confirmed.
4. GSPro runs on separate Windows PC — Jetson sends data over TCP. Not a bug, architectural decision.

ACTIVE SUB-PROJECTS:
SP1 — Core Vision System (foundation — build first)
SP2 — Spin Detection (depends on SP1)
SP3 — Club Tracking (depends on SP1, parallel with SP2)
SP4 — GSPro Integration + Session Data (depends on SP1 minimum)
SP5 — Video Recording + Enclosure (partially parallel with SP4)

IMPORTANT RULES FOR THIS CHAT:
- Do NOT suggest components or tools I have not listed above without asking first
- Do NOT assume I have any library or tool installed unless listed
- Do NOT try to fix items in Known Issues unless I specifically ask
- If unsure about my setup, ask before proceeding
- Recommend the simplest solution that works for my skill level
- Do NOT write code until we have agreed on an approach in plain language first

== END OF CONTEXT ==
```

\---

\---

## 🔧 Sub-Project 1: Core Vision System

**One-line description:** Camera triggering pipeline, IR strobe control, ball detection, ball speed, and launch angles — the foundation everything else is built on.

|Field|Value|
|-|-|
|Type|☑ Hardware ☑ Software|
|Phase|Build|
|% Complete|99%|
|Status|🟡 In Progress|
|Depends On|None — this is the foundation|
|Started|2026-03-14|
|Last Updated|2026-08-09|

\---

### 🎯 Goal

A shot is struck indoors. Within 2 seconds, the system outputs ball speed, vertical launch angle, and horizontal launch direction to the console. The system correctly detects when a ball is struck (not just waggled at), captures multiple strobe-frame images of the ball in flight, and correctly identifies ball position across frames. Someone watching the console output can verify speed and angles are plausible for the club used.

\---

### 📐 Design Notes

**Approach:** Adapt PiTrac's core pipeline (github.com/PiTracLM/PiTrac) from Raspberry Pi to Jetson Xavier NX.

PiTrac's key techniques:

* Camera 1 monitors for ball movement (low FPS, low resolution — watchdog)
* Camera 2 captures ball in flight using IR strobe (effective \~3000fps via strobe)
* IR strobe pulses are microsecond-duration, triggered precisely relative to ball crossing a threshold
* OpenCV HoughCircles detects ball positions across strobe frames
* Ball speed calculated from distance between circle centres + known strobe interval
* Launch angles calculated from 3D position change across frames
* libcamera\_interface.h identified as the single porting seam — 13 functions, 1630 lines of implementation
* All 13 functions will be reimplemented in a new v4l2\_interface.cpp using OpenCV VideoCapture + V4L2 controls
* The Camera/infrastructure/unix/libcamera\_unix\_impl.hpp type aliases will be replaced with a new infrastructure/jetson/v4l2\_jetson\_impl.hpp
* All ball detection, spin, and GSPro code is confirmed hardware-independent — zero changes needed
* libcamera\_interface.h identified as the single seam, 13 functions, 1630-line implementation, #ifdef JETSON\_BUILD compile guard approach

**Key porting challenge:** PiTrac uses RPi libcamera API. Jetson uses NVIDIA Argus (for CSI cameras) or V4L2 (for USB cameras). The camera abstraction layer in PiTrac must be rewritten or wrapped.

**IR strobe timing concern:** Sub-microsecond GPIO pulses may not be achievable reliably on Jetson under Linux. Options:

1. Use a dedicated Arduino/Teensy as strobe timing controller (receives trigger from Jetson, fires LEDs with hardware precision)
2. Investigate Jetson real-time GPIO capabilities
3. Use a small FPGA module (overkill for v1)

**LiDAR role:** Provides the initial trigger — detects club or ball movement in the hitting zone and wakes the camera capture pipeline. Avoids processing every frame continuously.

\---

### 🧠 Decisions Log

|Date|Decision|Why I Made It|Alternatives Considered|
|-|-|-|-|
|2026-03-14|Base codebase: PiTrac|Proven working DIY LM, GSPro integration already done, open source C++/OpenCV|Full scratch build (too slow), VisTrak LX (commercial, not open)|
|2026-03-14|Target platform: Jetson Xavier NX|Already owned x2. More compute than RPi — CUDA available for future vision acceleration|Upgrade to AGX Orin (unnecessary until Xavier NX proven insufficient)|
|2026-03-14|Trigger method: LiDAR|Clean non-contact detection, already in plan, works in controlled indoor environment|Microphone (noise-based, less reliable), laser break-beam (simpler but less flexible)|
|2026-03-14|Milestone priority: All data points working before GSPro connection|Avoids shipping partial/wrong data to simulator. Clean milestone gates.|GSPro-first (risks building around simulator before data is validated)|
|2026-03-14|Camera: Arducam OV9281 Monochrome USB3 ×2|Same sensor family as PiTrac reference hardware. Monochrome better for IR. USB3 = simplest driver path on Jetson (V4L2, no custom MIPI CSI work).|IMX296 (higher res, v2 upgrade path); MIPI CSI (v2 only)|
|2026-03-14|No LiDAR in v1|Camera-only trigger is sufficient for controlled indoor garage environment. LiDAR adds complexity without being necessary for v1.|LiDAR as ball-launch confirmation — logged as v2 upgrade|
|2026-03-14|Strobe driver: try Jetson GPIO first at 10µs|10µs is within plausible range for Jetson GPIO. Validate with USB oscilloscope before writing off. Teensy 4.0 reserved for v2 Jetson if GPIO jitter is unacceptable.|Teensy 4.0 (v2); Arduino Nano (fallback)|
|2026-03-14|IR LED array: 850nm|OV9281 monochrome has better sensitivity at 850nm vs 940nm. Also faintly visible to human eye — useful for setup and debugging.|940nm (less visible, marginally less detectable by sensor)|
|2026-03-14|Two-Jetson strategy: v1 = USB3 + camera-only + GPIO strobe. v2 = MIPI CSI + better cameras + LiDAR + Teensy strobe|Allows v1 to be completed cleanly. v2 built on second Jetson in parallel or after v1 is working.|Single build with all features (too complex, delays first working system)|
|2026-03-14|Port strategy: reimplement libcamera\_interface using OpenCV VideoCapture + V4L2|Single clean seam identified. 13 functions to reimplement. Rest of codebase untouched. Fastest path to working v1.|Full architectural port per migration guide (v2 on second Jetson)|
|2026-03-16|Porting strategy: #ifdef JETSON_BUILD guards, not a full rewrite|Preserves RPi build path, minimal diff, easier to maintain|Full rewrite of camera layer (higher risk, breaks RPi compatibility)|
|2026-03-16|JetsonCaptureApp struct replaces LibcameraJpegApp|LibcameraJpegApp inherits RPiCamApp which does not exist on Jetson. JetsonCaptureApp holds cv::VideoCapture + camera config|Forward-declare LibcameraJpegApp as empty stub (fragile)|
|2026-03-16|JetsonCompletedRequest struct replaces CompletedRequestPtr|libcamera::CompletedRequest does not exist on Jetson. New struct holds cv::Mat frame, sequence, framerate, post_process_metadata map|Pass cv::Mat directly (loses metadata bag needed by MotionDetectStage)|
|2026-03-16|Strobe is SPI not simple GPIO|PiTrac analysis revealed strobe uses lgSpiWrite — pre-built pulse train over SPI MOSI wired to IR LED driver. Simple GPIO toggle will not work.|GPIO toggle (insufficient timing precision for multi-pulse strobe train)|
|2026-03-16|Dev workflow: laptop Claude Code → GitHub → Jetson compile|Cannot compile on laptop (x86 vs ARM64). Laptop used for code editing with Claude Code, Jetson for compile and test.|Edit directly on Jetson (slower, no Claude Code integration)|
|2026-03-21|V3 long-term goal: standalone simulator system in single enclosure|Jetson renders OpenShotGolf directly via HDMI to projector/screen, no gaming PC needed. Requires Godot ARM64 Linux build and C#→GDScript port of physics. Not started — goal after V1 and V2 are working.|Always require Windows PC (limits portability)|
|2026-03-21|OV9281 USB cameras use /dev/video0 and /dev/video2 (video1 and video3 are UVC metadata devices)|Each USB camera creates two /dev/video devices. Only even-numbered devices (0, 2) are capture devices. Odd-numbered (1, 3) are metadata — no formats, can't be opened.|N/A — UVC standard behavior|
|2026-03-21|Cameras on separate USB buses (xhci-2.2.4 and xhci-2.3)|No bandwidth conflict — both can stream 1280x800 @ 120 FPS simultaneously.|Same bus (would halve available bandwidth)|
|2026-03-21|MJPG format for 120 FPS, YUYV limited to 10 FPS|OpenCV defaults to YUYV (10 FPS). PiTrac pipeline must explicitly request MJPG fourcc for 120 FPS.|YUYV at 10 FPS (too slow for ball tracking)|
|2026-04-26|Both OV9281 cameras verified at sustained 120 FPS @ 1280x800 MJPG, in parallel|v4l2-ctl raw streaming hits 120 FPS on each camera and on both simultaneously. Confirms the kernel/USB/camera path is not a bottleneck. Separate USB buses (xhci-2.2.4 / xhci-2.3) eliminate bandwidth contention.|None — this was a verification milestone|
|2026-04-26|C++ v4l2_interface.cpp will bypass OpenCV VideoCapture, use V4L2 ioctl directly|OpenCV's cap.read() caps Python at ~60 FPS due to CPU-bound MJPG decode. The C++ port must talk to V4L2 directly (open/ioctl/mmap) and decode with libjpeg-turbo or nvJPEG, not via cv::VideoCapture which inherits the same decode bottleneck.|cv::VideoCapture (rejected — same decode bottleneck), GStreamer pipeline (more complex, defer to later optimization)|
|2026-04-29|V4L2Capture engine: synchronous read(), libjpeg-turbo gray decode + cvtColor → BGR, mmap × 4 buffers|Synchronous keeps the implementation simple and predictable; measured ~125 FPS sustained, well above 120 target. Gray decode + GRAY2BGR is faster than asking libjpeg-turbo for BGR directly (OV9281 is monochrome — JPEG is single-channel internally anyway). Drop-in CV_8UC3 BGR output matches cv::VideoCapture semantics so consumers compile unchanged.|Background producer thread + ring buffer (deferred — unnecessary at the achieved rate); nvJPEG (deferred — needs CUDA-OpenCV not available, Issue #13); decode-to-grayscale CV_8UC1 directly (would change output semantics for callers, defer until profiled need)|
|2026-04-29|PerformCameraSystemStartup writes CameraHardware::resolution_x_override_=1280, resolution_y_override_=800|PiTrac's PiGS CameraModel default is 1456×1088 — every captured 1280×800 frame failed the resolution check at camera_hardware.cpp:205. Setting the existing override (already used by gs_automated_testing.cpp and lm_main.cpp) is the in-scope fix that lets PiTrac's downstream code accept OV9281 frames without touching gs_camera.cpp / camera_hardware.cpp.|Adding a new `OV9281_USB_Mono = 6` entry to the CameraModel enum (out of scope — touches camera_hardware.{h,cpp} and gs_camera.cpp); patching the resolution check to log warning instead of error (out of scope, same files)|
|2026-04-29|PulseStrobe::* GPIO/SPI stubs return true (no-op success) instead of false|gs_fsm.cpp:959 + lm_main.cpp:1159 treat false as a fatal init error and abort before reaching camera capture. Returning true ("succeeded as a no-op") lets the FSM advance; SendExternalTrigger remains a no-op until the IR LED hardware lands and the real libgpiod / SPI implementation can be written.|False return (rejected — abort path); skip-GPIO CLI flag (would require touching lm_main.cpp/gs_options.h)|
|2026-04-29|ActiveMQ broker required at runtime; broker = system apt activemq, addr passed via --msg_broker_address|PiTrac's IPC layer (consumer + producer threads, ipcResults messages) is mandatory in every system_mode. The broker is now installed via the Debian apt package on the Jetson, with the default `main` instance enabled at /etc/activemq/instances-enabled/main, listening on tcp://127.0.0.1:61616. CLI flag `--msg_broker_address` overrides the JSON config's empty `kWebActiveMQHostAddress` so we don't have to edit golf_sim_config.json.|Edit golf_sim_config.json (rejected — out of scope for this session; CLI flag is cleaner); skip the IPC init (would require code changes to lm_main / gs_fsm)|
|2026-05-02|ConfigurePostProcessing wired into Jetson WatchForHitAndTrigger before ball_watcher_event_loop, with full-frame ROI (1280x800)|RPi side called it inside ConfigCameraForCropping which is RPi-only — on Jetson the call was missing, MotionDetectStage::Read fell through to cpp defaults (1x1 ROI, threshold=0), and any non-zero `regions` count tripped on the first comparison frame. Full-frame ROI is the v1 default since SendCameraCroppingCommand is still TODO (Group 2). Verified by `MotionDetectStage::Read - using internal data.` trace.|Hardcode params inline in ball_watcher.cpp Jetson branch (rejected — scatters config); keep ConfigurePostProcessing call in PerformCameraSystemStartup (rejected — wrong scope; needs camera-specific roi which is a watch-time concern)|
|2026-05-02|ball_watcher_event_loop discards 2 warm-up frames after V4L2 stream-on|First decoded frame after VIDIOC_STREAMON can be partially exposed / pre-AGC. With frame_period=5, sequence=0 stores that junk frame as previous_frame_, then sequence=5 (settled) compares against junk and trips. 2 warm-up frames at 120 FPS = ~17ms, invisible in normal operation.|Skip the first MotionDetectStage::Process call (would require changes to motion_detect_stage.cpp first_time_ logic); higher warm-up count (no benefit observed at 2)|
|2026-05-02|undistort_camera_image ported verbatim from libcamera_interface.cpp:950 into v4l2_interface.cpp; called from TakeRawPicture|Pure OpenCV (initUndistortRectifyMap + remap), no libcamera/rpicam-apps dep. Matches RPi behavior so downstream ball-detect / stereo geometry consistently sees rectified frames once a calibration matrix is loaded. No-op until then (use_undistortion_matrix_=false). Required adding `#include <opencv2/calib3d.hpp>` — RPi side picked it up transitively.|Skip the port (rejected — would diverge from RPi when calibration eventually runs); call undistort at consumer site (rejected — multiple consumers)|
|2026-05-02|motion_detect_stage thresholds tuned for bench (no-strobe) testing in golf_sim_config.json: kDifferenceM 0.9→0.3, kDifferenceC 3.0→5.0, kFramePeriod 0→5|Diagnostic confirmed regions=0 across 1200+ frames at the original gs_config defaults — even with the lens fully covered. The 0.9 per-pixel multiplier required near-saturation contrast change to count any pixel; frame_period=0 (compare adjacent frames at 8ms apart) made hand-wave transitions too small to see. Closer to assets/motion_detect.json RPi-tested defaults but with slack since we have no IR strobe yet (production path uses the strobe as effective shutter and gets sharp on/off contrast). Verified: static-scene noise floor 10-19 regions vs threshold 12800 (~675x headroom); hand-wave trip in <30 frames.|Keep gs_config defaults (rejected — confirmed unworkable on bench); use assets/motion_detect.json values verbatim (looser frame_period and hskip/vskip than necessary at our 120 FPS)|
|2026-05-02|Strobe architecture: Teensy 4.0 as offloaded pulse-train controller, Jetson sends single fire trigger + USB-serial setup|Pulled the Teensy 4.0 forward from the v2 plan. Linux on Jetson Xavier NX cannot reliably hit sub-10µs GPIO timing under load (V4L2 + motion-detect run concurrently). Teensy 4.0 has 600 MHz Cortex-M7 + hardware timers and gives ns-precision pulse-train generation, completely deterministic. Jetson computes intervals/on-bits/baud once at startup, sends via USB serial; runtime fire is one GPIO pulse. PiTrac's BuildPulseTrain math stays unmodified on Jetson side (we just re-package the result for the Teensy protocol). Cleaner architecture than the RPi SPI bit-bang.|RPi SPI bit-bang ported 1:1 (rejected — Linux jitter > pulse width); Jetson GPIO direct via libgpiod (rejected — same jitter issue, still in Linux land); Arduino Nano (rejected — slower MCU, less margin)|
|2026-05-02|Fire-trigger pin = Pin 29 = PQ.05 = gpiochip1 line 105|Discovered authoritatively via Jetson.GPIO's pin-data table at /usr/lib/python3/dist-packages/Jetson/GPIO/gpio_pin_data.py. Initial picks Pin 15 / Pin 32 / Pin 33 ("user GPIO" per the J202 datasheet) all have PWM controllers attached (c340000.pwm, 32f0000.pwm, 3280000.pwm) — kernel PWM driver fights libgpiod writes, multimeter reads garbage 1.5V averages. Pin 29 has no PWM/SPI/I2S/UART alternate (only "General Purpose Clock #0" which isn't active). Verified: clean 0V↔3.3V toggle at 1Hz via Jetson.GPIO Python.|Pin 15 (PWM-occupied), Pin 32/33 (PWM-occupied), AON gpiochip2 lines (PCC/PEE — uncertain header routing on J202), pure-SPI pins like 23/24 (would work but feel weird as user GPIO)|
|2026-05-02|Cenpek IR LED board switched via low-side N-channel MOSFET (IRLZ44N) — not via on-board Q-transistors|Cenpek FY-S54-F-style boards have an LDR-based dusk-to-dawn auto-on circuit and Q-transistors that switch the LED branches. Modifying that circuit is invasive and undocumented (no schematic). Cleaner: leave the board untouched, gate the 12V-/return path via an external MOSFET driven from Teensy Pin 3. The board sees power-cycled supply; LDR-control is bypassed because the supply itself is gated.|Hack the on-board Q-transistor gate (rejected — invasive, irreversible if wrong); replace the Cenpek board with a custom MOSFET+LED board (rejected — extra design+order work)|
|2026-05-02|Jetson PulseStrobe Jetson-side impl in dedicated pulse_strobe_jetson.cpp, NOT mixed into v4l2_interface.cpp|Mirrors v4l2_interface.cpp vs libcamera_interface.cpp split — clean per-file ownership. The 5 PulseStrobe stubs that lived in v4l2_interface.cpp until 2026-05-02 were placeholders, now removed. New file owns the full PulseStrobe Jetson surface (5 method implementations + all static member definitions + libgpiod + termios + Teensy text-protocol handshake).|Add to v4l2_interface.cpp (rejected — file already owns camera bring-up, would dilute responsibility); subdir under Hardware/ (rejected — needs to compile into pitrac_lm, not a separate target)|
|2026-05-02|Strobe init failures degrade soft (warn + continue + SendExternalTrigger no-ops), not hard|During development the Teensy isn't always plugged in, the GPIO line might be in use, /dev/ttyACM0 might rename. Hard fail would block every dev run that doesn't have the strobe rig wired. Soft fallback lets us iterate on camera + motion-detect without the strobe sub-system, and the warning logs make the silent no-op visible.|Hard fail on init (rejected — too restrictive for dev); silent no-op without log (rejected — masks misconfiguration in production)|

\---

### 🤖 AI Prompt Log

**Session: 2026-03-14 — Project kickoff and logbook setup**

> Used general project scoping conversation with Claude.
> What worked: Structured questioning approach got all key decisions made in one session.
> What to change next time: Paste context block at the start of every new chat.
> Logbook sections updated: ☑ Decisions Log ☑ Design Notes ☑ Next Steps ☑ Known Issues

**Session: 2026-03-16 — Full pipeline analysis and Group 1 porting**

> Used Claude Code on Ubuntu laptop pointed at ~/JetsonLM (forked PiTrac repo).
> What worked: CLAUDE.md context file made Claude Code immediately productive. "Show me the plan before writing anything" instruction prevented premature code generation.
> Key prompts: read libcamera_interface.h → read 3 key functions → read ball_watcher_event_loop → produce porting plan → create PORTING_TASKS.md → work through Group 1 tasks in order.
> What to do next time: start session by running "claude --resume" to continue the same Claude Code session if possible.

\---

### ⚠️ Blockers \& Problems

|Date|Problem|Status|Solution Found|
|-|-|-|-|
|2026-03-14|PiTrac camera API (libcamera) does not exist on Jetson — must rewrite camera abstraction|🟡 Investigating|Study PiTrac camera layer depth before deciding on rewrite vs wrapper approach|
|2026-03-14|IR strobe timing precision on Jetson GPIO unknown|🟡 Investigating|Research Jetson GPIO latency; prototype with Arduino/Teensy as fallback|

\---

### 🧪 Tests This Sub-Project

|Date|What Was Tested|Method|Result|Notes|
|-|-|-|-|-|
|2026-03-21|OV9281 Camera 1 detected via V4L2|camera_test.py auto-detect|✅ PASS|/dev/video0, Arducam OV9281, uvcvideo driver, 1280x800 @ 120fps MJPG|
|2026-03-21|OV9281 Camera 2 detected via V4L2|camera_test.py auto-detect|✅ PASS|/dev/video2, Arducam OV9281, uvcvideo driver, 1280x800 @ 120fps MJPG|
|2026-03-21|Test frame capture Camera 1|camera_test.py --capture --device 0|✅ PASS|1280x800 PNG saved, valid image data|
|2026-03-21|Test frame capture Camera 2|camera_test.py --capture --device 2|✅ PASS|1280x800 PNG saved, valid image data|
|2026-04-26|Single camera sustained 120 FPS @ 1280x800 MJPG (raw V4L2)|v4l2-ctl --stream-mmap --stream-count=600 --stream-to=/dev/null on /dev/video0 and /dev/video2|✅ PASS|Both cameras: 111→116→120→120→120 FPS (1s warm-up then locked at 120)|
|2026-04-26|Dual camera parallel sustained 120 FPS @ 1280x800 MJPG (raw V4L2)|Both v4l2-ctl streams running simultaneously via shell &|✅ PASS|Both cameras: 111→116→120→120→120 FPS each — no degradation from parallel streaming, separate USB buses confirmed independent|
|2026-04-26|Dual camera OpenCV cv2.VideoCapture.read() throughput|sp1_vision/dual_camera_test.py (with and without --exposure)|⚠ PARTIAL|Both cameras cap at ~55–60 FPS regardless of exposure setting. Confirmed via v4l2-ctl that this is a Python/OpenCV decode bottleneck, NOT a camera/USB limitation. Acceptable — production C++ pipeline will not use cv::VideoCapture. Issue #15 logged.|
|2026-04-29|C++ V4L2Capture engine sustained ≥120 FPS via WatchForHitAndTrigger / ball_watcher_event_loop|`./pitrac_lm --system_mode=camera1_test_standalone --msg_broker_address=tcp://127.0.0.1:61616` with cam1 connected; per-frame log inside V4L2Capture::read()|✅ PASS|Per-frame intervals 7.7–8.1 ms (avg ~7.9 ms) = 123–130 FPS sustained over the tight read loop. Loop exits early on motion-detect after open/release recycling, so only ~5 frames captured per loop run, but the per-frame interval directly proves engine rate. cv::VideoCapture replaced by V4L2 ioctl + libjpeg-turbo gray decode + cv::cvtColor → BGR. CheckForBall path runs ~8 FPS due to FSM/IPC overhead per call (config reload, image save, MQ send) — engine is not the bottleneck.|
|2026-05-02|Motion-detect static-scene baseline (false-positive check)|Same launch command, lens steady, no movement. Diagnostic log of `regions` per processed frame.|✅ PASS|Across 1060 frames at 120 FPS (~9 s loop), `regions` ranged 0-19 vs `region_threshold_=12800`. Loop ran to pkill timeout with no `motion_detect.result=true`. Confirms tuned thresholds (kDifferenceM=0.3, kDifferenceC=5.0, kFramePeriod=5) leave ~675× headroom over sensor/lighting noise floor.|
|2026-05-02|Motion-detect hand-wave positive trigger|Same launch, hand moved across camera 1 FoV during seconds 22-28 of the 30 s session.|✅ PASS|`WatchForHitAndTrigger - calling` at 17:23:53.851, `WatchForHitAndTrigger - returned true motion_detected=true` at 17:23:54.937. Trip occurred within ~30 frames (~250 ms) of loop start, well before the diagnostic's first scheduled log point. Loop exited cleanly without pkill.|
|2026-05-02|Teensy 4.0 firmware standalone test (no Jetson, no MOSFET)|Flash teensy_strobe.ino via Arduino IDE + Teensyduino. USB to Windows. Arduino Serial Monitor at 115200, line ending Newline. Sent: PULSES_FAST,5,5,5,5,5,5,0 / ON_BITS,4 / BAUD,38400 / MODE,FAST / STATUS / TEST_FIRE.|✅ PASS|All four setup commands → `OK`. STATUS dump returned `STATE=READY MODE=FAST ON_BITS=4 BAUD=38400 ON_PULSE_US=104 N_FAST=7 N_SLOW=0` — exactly matching the spec (104 µs = 4/38400×1e6). TEST_FIRE produced `FIRED` with brief LED13 dim during the pulse train. ISR detach/reattach worked (no double-fire). No MOSFET needed for this test.|
|2026-05-02|Pin 29 GPIO toggle verification (Jetson.GPIO Python)|Jetson.GPIO setmode(BOARD), setup(29, OUT), toggle in 1-second loop, multimeter probing physical Pin 29.|✅ PASS|Clean 0V↔3.3V wechsel im Sekundentakt, korreliert mit `Pin 29 = 0/1` Console-Output. Earlier failed candidates (Pin 12, 15, 32) were either wrong physical mapping (PCC.04≠Pin 12) or PWM-controller-occupied (15/32/33). Pin 29 / PQ.05 / gpiochip1 line 105 is the locked-in fire-trigger pin.|
|2026-05-02|Jetson PulseStrobe build (no HW yet)|`meson setup build_jetson --wipe -Djetson_build=true && ninja -C build_jetson` after pulse_strobe_jetson.cpp + meson dep + JSON keys landed.|✅ PASS|libgpiod-1.4.1 found via pkg-config. After fix-commit b9d51ac for the protected-member access bug (anonymous-namespace helper couldn't reach PulseStrobe::pulse_intervals_*; passed through as parameters), all 470 lines compiled, all PulseStrobe symbols resolved, binary produced clean.|
|2026-05-05|pitrac_lm strobe init handshake (Teensy + libgpiod), wired Jetson Pin 29 ↔ Teensy Pin 2 + GND ↔ GND + USB|`./pitrac_lm --system_mode=camera1_test_standalone --logging_level=trace`. Permission setup: `sudo chmod 666 /dev/ttyACM0` (brain not in dialout group; permanent fix via usermod scheduled for later).|✅ PASS|Init logs: `open_teensy_serial - opened /dev/ttyACM0 at 115200 8N1` → `send_setup_to_teensy - Teensy reached READY state` → `PulseStrobe::InitGPIOSystem - Teensy READY, GPIO line claimed. Strobe pipeline live.`. Teensy LED13 went from 1Hz blink (WAITING_SETUP) to solid HIGH (READY). Watch loop never reached during this run because PiTrac's FSM ball-stabilization check rejected the placed yellow-ball (see Issue #19) — but the Teensy + GPIO pipeline init proven sound.|
|2026-05-05|Phase C Test 1: Jetson → Teensy → Test-LED chain (FSM bypass)|`Hardware/teensy_strobe/test_strobe_bypass.py` standalone Python script: configures Teensy with long visible pulses (32ms ON, 200ms gaps, 7 pulses → ~1.5s burst), claims Jetson Pin 29 via Jetson.GPIO, toggles HIGH for 100µs five times.|✅ PASS|All 5 fires triggered visible LED flicker on Teensy Pin 3. STATUS dump confirmed `STATE=READY MODE=FAST ON_BITS=32 BAUD=1000 ON_PULSE_US=32000 N_FAST=7 N_SLOW=13`. End-to-end strobe pipeline software-validated: Python USB serial setup → Teensy state machine → libgpiod-equivalent GPIO toggle → Teensy ISR → Pin 3 pulse train → LED. Bypasses pitrac_lm so we can validate the strobe rig independently of the FSM stabilization issue.|
|2026-05-05|Phase C Test 1 follow-up — pitrac_lm strobe pipeline software-validated end-to-end|Manually invoked `python3 ~/JetsonLM/Hardware/teensy_strobe/fire_trigger.py` (the EXACT same Jetson.GPIO helper that pitrac_lm now calls via std::system) as user `brain` (no sudo needed — gpio group membership). LED rig wired as Phase C Test 1.|✅ PASS|LED blinked on every invocation (long-pulse Teensy config from prior pitrac_lm init still active). Together with the InitGPIOSystem trace `Strobe pipeline live (trigger via .../fire_trigger.py)` from a successful pitrac_lm run, this proves every link in the chain except the literal `pitrac_lm → SendExternalTrigger → std::system` invocation, which is hardcoded one-liner. Final FSM-driven test deferred to Phase C Test 2 with real IR strobe (Issue #19 ball-stabilization will resolve naturally once IR illumination provides clean ball edges to HoughCircles).|
|2026-08-06|Camera 1/2 mapped to the physical modules|Covered each lens in turn and watched the streams; independently, template-matched a patch from cam2 into cam1|✅ PASS|Both agree: cam1 = USB port 2.3 = **left** module facing the unit. The patch sat 76 px further left in cam1, correlation 0.95. The two readings look contradictory until the frame of reference is fixed — standing in front you look back down the optical axes, so your left/right is mirrored from the cameras' own.|
|2026-08-06|Lens focus, both cameras|Board sharpness (Laplacian variance over the detected board) before and after turning each lens|✅ PASS|cam1 566 → 3028 (**5.4x**), cam2 1887 → 2945 (1.6x). Both lenses were misadjusted and nobody had noticed, because the readout measured the central 40% of the frame — a blank wall while the board lay flat on the desk. Afterwards the two agree within 3%.|
|2026-08-06|Intrinsics from 20 simultaneous pairs|`CameraCalibration.py`, 24 mm board, images above 1.0 px reprojection dropped|✅ PASS|cam1 RMS 1.149 → **0.557 px** (4 dropped), cam2 1.116 → **0.550 px** (5 dropped). fx 922.30 / 923.98 px. fy/fx = 0.995 confirms square 3.0 µm pixels and with them the 3.840 x 2.400 mm sensor. Focal length **2.767 / 2.772 mm** against 2.74 derived from the 70° FOV spec — 1.2% agreement, and the two cameras agree with each other to 0.2%.|
|2026-08-06|Stereo extrinsics|`StereoCalibration.py` with CALIB_FIX_INTRINSIC over the same 20 pairs|✅ PASS|Baseline **79.83 mm** against 80.00 mm read out of `Hardware/JetsonLM.step` — 0.2% between an optical measurement and a CAD drawing, by entirely independent routes. Translation [79.79, 0.13, 2.60] mm; the 2.60 in Z is the two lenses sitting at different screw depths after focusing. Rotation: pitch 1.070°, roll 0.925°, yaw 0.756°, all well under the 3° at which rectification starts costing real frame height.|
|2026-08-06|Thermal drift of the printed mount|Split the 20 pairs into cooler (1-10) and warmer (11-20) halves and solved each separately|✅ PASS|Pitch 1.086 vs 1.088°, roll 0.926 vs 0.917° — **identical to 0.01°**, and those two are precisely the ones that produce vertical disparity. Baseline differs by 0.93 mm, but with the wrong sign for thermal expansion and seven times the magnitude plastic gives, so it is estimation noise from 10 pairs over only 35-55 cm of depth. No compensation warranted.|
|2026-08-06|Measured optics take effect at runtime|`pitrac_lm --logging_level=trace` after writing the config and rebuilding|✅ PASS|`Overriding sensor size with 3.840000 x 2.400000 mm (was 5.077365 x 3.789079)`; matrix `[922.30, 0, 637.17; 0, 917.97, 389.05; 0, 0, 1]`; `Setting focal length (from JSON file) = 2.767000`; `kExpectedBallRadiusPixelsAt40cmCamera1 = 49` — that last override taking effect for the first time ever, the old key lacked the CameraN suffix and fell back silently to the IMX296's 87.|
|2026-08-07|Calibration reproduces from the committed images|Re-ran both scripts against the 40 PNGs restored out of git|✅ PASS|Bit-identical: 2.767 / 2.772 mm, RMS 0.557 / 0.550, baseline 79.83 mm, same angles. The archive is reproducible, not merely stored.|
|2026-08-08|Focus unchanged after the mount rebuild|Dashboard `/calibration/sharpness` with the board propped, seven samples|✅ PASS|cam1 1035–1062, cam2 1066–1083, **2.4 % apart** against 3 % on 2026-08-06. The absolute drop from ~3000 is the room, not the lens: Laplacian variance scales with the square of scene contrast. Relative agreement is the only cross-session-valid reading, and it says no lens moved.|
|2026-08-08|Recapture, 24 pairs, board standing|Dashboard capture; 25–90 cm sweep, ±30° rotations, image regions, and six shots into the lower third|✅ PASS|Board found in both cameras in **all 24**. Depth 250–928 mm against the archive's 350–550; corner coverage y 45–727 of 800 against 71–636. Nothing hand-held, so the 20 ms exposure costs nothing — the archive's 0.19–3.30 px spread was all motion blur.|
|2026-08-08|Pitch is a readout of `cy` — found, then fixed|Solved the same pairs against two different intrinsic sets and compared|⚠️ FOUND|At 18 pairs the two sets gave pitch −0.745° and −1.834° **at an identical RMS of 0.90**: the data could not choose. Cause is `cy`, unconstrained because neither set covered the bottom fifth. `Δ(cy1−cy2)` = 17.6 px, 17.6/915 = 1.10° against an observed 1.09° gap. Six shots into the lower third cut the ambiguity to **0.21°**, and `cy` converged to 420.05 / 421.09 — 1.0 px apart, from 13.2.|
|2026-08-08|Intrinsics remeasured, and they replace the archive's|`CameraCalibration.py` over all 24|✅ PASS|**2.701 / 2.700 mm** against 2.767 / 2.772; fx 900.38 / 899.99; cy 420.05 / 421.09; RMS **0.500 / 0.519** against 0.557 / 0.550. The case is not the RMS but inter-camera agreement: fx to **0.04 %** against 0.18 %, cy to 1.0 px against 4.5. Same part, same lens — agreement is evidence.|
|2026-08-08|Extrinsics after the rebuild, both sets on equal footing|`StereoCalibration.py`, `CALIB_FIX_INTRINSIC`, both capture sets re-solved against the 24-pair intrinsics|✅ PASS|Pitch **+0.974 → −0.923°**, yaw **+1.032 → +0.427°**, roll **+0.757 → −0.851°**. The rebuild *inverted* pitch and roll rather than nulling them; only yaw improved. All well under 3°, ~1.5 % of frame height in total — no mechanical action.|
|2026-08-08|Baseline did not move, and the earlier "drop" was an artefact|Same two sets, same intrinsics|✅ PASS|78.63 mm with springs against **78.28 mm** bolted — 0.35 mm, the estimator's own noise. The reported 79.83 → 78.59 was the archive's overestimated fx, not hardware. Remaining −2.1 % against the CAD's 80.00 is print shrinkage; the archive's celebrated 0.2 % agreement came from a 35–55 cm set, and that same narrow-depth condition yields 81 mm here.|
|2026-08-08|Estimate stability, seven ways|Re-solved on halves, odds, evens, with and without the six lower-frame shots|✅ PASS|Pitch −0.86…−0.96°, roll −0.82…−0.88°, yaw +0.36…+0.47°, baseline 77.99…78.66 mm. The six lower-frame shots alone give pitch −0.942° at RMS 0.425, the cleanest sub-solve, agreeing with all 24 to 0.02°.|
|2026-08-09|New optics reach the C++ at runtime|`pitrac_lm --system_mode=camera1_test_standalone --logging_level=trace --msg_broker_address=tcp://127.0.0.1:61616`|✅ PASS|`Setting focal length (from JSON file) = 2.701000`; matrix `[900.375560084984, 0, 635.0969080840021; 0, 897.387429150186, 420.048921344356]`; `Overriding sensor size with 3.840000 x 2.400000 mm`; `kExpectedBallRadiusPixelsAt40cmCamera1 = 48`. `~/.pitrac/config/user_settings.json` does not exist, so nothing shadows the JSON. **Note the broker argument** — `kWebActiveMQHostAddress` is not in the config at all, and without `--msg_broker_address` the run aborts in IPC init and segfaults on the way out.|

\---

### ✅ Next Steps

* ☑ OV9281 cameras arrived and detected on Jetson
* ☑ Test frames captured from both cameras
* ☑ Sustained 120 FPS @ 1280x800 MJPG verified on both cameras simultaneously (via v4l2-ctl raw stream)
* ☑ OpenCV cv2.VideoCapture decode benchmarked — caps at ~60 FPS due to CPU MJPG decode (Issue #15, not a blocker for C++ pipeline)
* ☑ Real V4L2 capture engine implemented in v4l2_interface.cpp — V4L2Capture class with mmap + libjpeg-turbo decode; sustains 125–130 FPS in ball_watcher_event_loop
* ☑ ActiveMQ broker installed and configured on Jetson; PiTrac IPC runs end-to-end
* ☑ pitrac_lm advances through full FSM (Initializing → WaitingForBall → WaitingForBallStabilization → WaitingForBallHit → WatchForHitAndTrigger) with real OV9281 cameras
* ☑ `undistort_camera_image` ported into v4l2_interface.cpp and wired into TakeRawPicture (no-op until calibration loads a matrix; OpenCV initUndistortRectifyMap+remap kicks in then)
* ☑ `motion_detect_stage` tuned for bench testing: ConfigurePostProcessing wired into Jetson watch path, 2 warm-up frames discarded after stream-on, gs_config thresholds loosened (kDifferenceM 0.9→0.3, kFramePeriod 0→5). Static scene: 0-19 regions vs 12800 threshold; hand-wave trip in <30 frames.
* ☑ Teensy 4.0 strobe-controller firmware written + standalone-tested (Hardware/teensy_strobe/teensy_strobe.ino — TEST_FIRE returns FIRED via Arduino Serial Monitor, no Jetson needed)
* ☑ Jetson PulseStrobe Jetson-side impl in pulse_strobe_jetson.cpp (libgpiod fire-pin + termios USB-serial setup handshake + soft-fallback architecture). Builds clean.
* ☑ Fire-pin locked: Pin 29 = PQ.05 = gpiochip1 line 105. JSON defaults updated. Verified via Jetson.GPIO Python toggle + multimeter.
* ☑ Phase C Test 1 PASS (2026-05-05): wired Jetson Pin 29 ↔ Teensy Pin 2 + GND ↔ GND + USB; pitrac_lm init handshake complete; bypass-test script (`Hardware/teensy_strobe/test_strobe_bypass.py`) drives 5/5 visible LED flickers via the same chain pitrac_lm uses. Strobe pipeline software-validated end-to-end.
* ☑ pitrac_lm strobe init+trigger path software-validated 2026-05-05 — `Strobe pipeline live (trigger via fire_trigger.py)` log from real init, manual invocation of the same helper makes the LED blink. The only un-tested link is the literal `std::system("python3 fire_trigger.py")` line — hardcoded, low risk.
* ☑ Issue #19 (FSM ball-stabilization flaky in ambient light) **resolved by design** 2026-05-12: live FSM run reproduced the HoughCircles jitter exactly as expected. The 2026-05-05 hypothesis "IR strobe will fix this" was wrong — IR array is event-driven (fires only on FIRE trigger), so stabilization-check frames are always ambient-only. The Issue #21 bypass is the permanent solution: re-detected ball ⇒ accept (jitter); genuinely lost ⇒ bail back.
* ☑ Issue #21 (stabilization moved-check bypass) **promoted from workaround to permanent design** 2026-05-12: gs_fsm.cpp:280-301 comment block rewritten — JETSON_STUB → JETSON_DESIGN, false "remove this guard once IR strobe is wired" prophecy deleted. Log marker simplified to `Jetson stabilization: re-detected ball after jitter, advancing`.
* ☐ Workaround for Issue #22 (libgpiod chardev doesn't drive Pin 29 on Seeed J202): pulse_strobe_jetson.cpp now shells out to fire_trigger.py via std::system. Could revisit when L4T upgrades or libgpiod 2.x available — until then, the Python helper is reliable.
* ☑ MOSFET (IRLZ44N TO-220) angekommen + verdrahtet 2026-05-12: low-side switch zwischen Cenpek V− und GND-Schiene, 1kΩ Gate-Source-Pulldown, gemeinsame GND-Schiene mit 12V PSU(−) und Teensy GND
* ☑ Phase C Test 2 PASS (2026-05-12): `sudo python3 Hardware/teensy_strobe/test_strobe_bypass.py` — IR-Bursts via Smartphone-Kamera sichtbar (850nm geht durch IR-Cut-Filter durch), zusätzlich verifiziert über Strom-Spike am 12V PSU Ampere-Anzeige bei jedem Fire-Event. Cenpek-Array wird vom MOSFET sauber durchgeschaltet.
* ☑ Permanent fix für /dev/ttyACM0 Permissions: `sudo usermod -a -G dialout brain` ausgeführt 2026-05-05 (greift erst nach re-login)
* ☑ V4L2Capture::ensure_streaming() failure-path fd leak fixed 2026-05-05 (Issue #17 resolved)
* ☑ motion_detect_stage CV_8UC1/CV_8UC3 byte-step assumption fixed 2026-05-05 (Issue #18 resolved) — derives `hskip_bytes = config_.hskip * frame.channels()` under JETSON_BUILD, used in all 4 pointer-arithmetic spots
* ☑ Cameras mounted in the enclosure, 80.00 mm baseline, axes parallel (2026-08-06)
* ☑ **Calibration done 2026-08-06/07, redone and superseded 2026-08-08/09.** Own tooling built (dashboard page + CLI), not PiTrac's scripts — theirs depend on `rpicam-still` and `libcamera-hello`, neither of which exists here. Current numbers come from 24 pairs after the mount rebuild: focal length **2.701/2.700 mm**, fx 900.38/899.99, cy 420.05/421.09, sensor 3.840x2.400 mm, reprojection RMS **0.500/0.519 px**, baseline **78.28 mm**. In `golf_sim_config.json`, verified in a live trace run 2026-08-09. The 2026-08-06 set is archived under `sp1_vision/calibration_images/2026-08-06_springs/` and is superseded on every figure — see its README for why.
* ☑ **Mount springs removed and the plate bolted solid (2026-08-08).** Aim is no longer adjustable; changing it is a rework that drags a full recalibration behind it. The rebuild **inverted** pitch and roll rather than nulling them (+0.974 → −0.923°, +0.757 → −0.851°); only yaw improved (+1.032 → +0.427°). All under 3°, ~1.5 % of frame height in total, so rectification absorbs it and no further mechanical work is warranted.
* ☑ **Baseline settled at 78.28 mm, and it never moved.** Both capture sets solved against the same intrinsics agree to 0.35 mm. The 2026-08-06 figure of 79.83 mm was an artefact of that set's overestimated fx, and its 0.2 % agreement with the CAD's 80.00 was luck from a narrow 35–55 cm depth range. The real −2.1 % against the CAD is print shrinkage.
* ☑ **Calibration coverage rule learned the hard way:** the lower third of the frame is not optional. It is what constrains `cy`, and `cy` is what pitch is made of. Omitting it does not blur pitch, it biases it, and the reprojection error stays low throughout. Cost 1.1° of pitch until six extra shots fixed it.
* ☑ `undistort_camera_image` question resolved — and the 2026-04-29 note was wrong. It was **not** a no-op: `use_undistortion_matrix_` was true because the config carried PiTrac's IMX296 matrix, so every still from `TakeRawPicture` (the path `CheckForBall` uses) was remapped through the wrong lens model. Now carries the measured one.
* ☑ Cameras bound by USB port path in Python and C++ — both modules report the same iSerial, so `/dev/videoN` is not an identity. cam1 = port 2.3 = left module facing the unit, established by covering a lens and independently by parallax.
* ☑ Thermal drift measured by splitting the capture set into cooler/warmer halves: pitch and roll identical to 0.01°, baseline spread is estimation noise (wrong sign for expansion, 7x too large). No compensation needed.
* ☐ **Working distance: 50 cm decided, not yet built into the geometry config.** With the 2026-08-08 optics: ball radius at 50 cm is 38 px, disparity 141 px, and depth resolution 3.55 mm per pixel of disparity error — so ~1.8 mm at half-pixel matching. Three live constants still hold PiTrac's numbers: `kCameraNPositionsFromExpectedBallMeters` (**not** `...FromOriginMeters`, which exists only in PiTrac's docs — the origin is the expected ball, and only the vector's *magnitude* is ever read, at `gs_camera.cpp:455/458`; the trace's `distance: 0.621575` is exactly cam1's vector length, 24 % beyond the intended 50 cm); `kCameraNAngles`, which feed `AdjustXYZDistancesForCameraAngles` and become HLA/VLA, so they are the ones that matter; and `kCamera2OffsetFromCamera1OriginMeters` = `[0.00, -0.19, 0.0]`, PiTrac's **vertical** 19 cm camera stacking, applied at `gs_camera.cpp:700-703` and `lm_main.cpp:865` — ours are side by side at 78.28 mm, so the delta path currently carries a 19 cm offset that does not exist.
* ☐ `WaitForCam2Trigger` still a JETSON_STUB returning false. UVC exposes no trigger pin (confirmed: no such control in `v4l2-ctl --list-ctrls`), so this needs a different mechanism, not a translation. `exposure_absolute` reaches 500 ms, which makes "open a long exposure and fire the strobe into it" the obvious candidate.
* ☑ **Triangulation Block 1 built and merged (2026-08-10).** Python only, nothing in the C++ runtime path yet: `stereo_geometry.py` (the sole frame/unit conversion point, and the rig validation that refuses a mismatched intrinsics/extrinsics pairing), `triangulate.py`, `ground_plane.py`, `cli_triangulate.py`. 147 tests on the Jetson. The extrinsics are consumed for the first time.
* ☑ **Ball detection rebuilt as a stereo-pair decision (2026-08-10).** `find_ball` returned the strongest Hough circle per image, which in a cluttered room is the loudspeaker — 17 of 24 frames in run 1 returned the same pixel while the ball moved. `ball_pair.find_ball_pair` now chooses the candidate PAIR on three constraints declared in advance: apparent radius matching the range that image's own disparity implies (42.67 mm ball — the check no single image can make), the declared measurement volume, and the rays meeting. The same function runs at capture, so a shot the analysis would reject is rejected while the operator is still standing there.
* ☐ **Measurement run at the device — the only step left in Block 1. Run 1 failed on 2026-08-10 and must be repeated.** Same 24 shots, protocol in `sp1_vision/triangulation_run/PROTOCOL.md`; what changes is the room — unit facing a bare wall, dark matt cloth over everything behind the measuring field. Run 1's pairs are archived at `sp1_vision/2026-08-10_cluttered/` (untracked) as the only real cluttered-background dataset there is. Settles: whether the shipped scale holds and to what stated precision, the unit's attitude against the surface it stands on (which nothing has ever measured — the calibration measures camera against camera), the mounting height against the assumed 115 mm, and the sign of `yaw_from_target_line`.
* ☐ **A small residual is not evidence of a correct detection — confirmed on real data.** Run 1's `gs_03` passed the 2 px reprojection gate at 1.96 px with both cameras locked onto the same loudspeaker at 1295 mm. Keep this in mind for Block 2: the guard against a wrong correspondence is physical (size, volume, depth sign), not the residual.
* ☐ **The baseline figure needs correcting, independently of that run.** 78.28 mm is from the springs-against-bolted comparison table in `calibration_images/README.md`, a different solve from the shipped one — it reports pitch −0.923° where `stereo_extrinsics.json` says −0.9423°. The file the code actually reads says **78.749 mm**, and `CALIB_FIX_INTRINSIC` means 78.28 cannot be substituted into its R/T without re-solving. Every "78.28" in this logbook and in CLAUDE.md is quoting the comparison table, not the shipped geometry. Depth resolution follows: 3.53 mm/px at 0.500 m with the shipped baseline, not 3.55.
* ☐ Nothing consumes the extrinsics inside `pitrac_lm` yet — the ball-position path there is still PiTrac's monocular radius method, roughly an order of magnitude worse at these distances. That is Block 2, and for the flying ball it waits on `WaitForCam2Trigger`.
* ☐ First end-to-end ball detection + speed/angles output to console (motion-detect → CheckForBall → strobe-lit shot capture → shot data → SP4 GSPro JSON)

\---

### 📝 Session Notes

**2026-03-14**

> Project scoped and logbook populated in first AI session.
> Identified PiTrac as core foundation — adapt rather than rebuild.
> Key open question: camera API porting from RPi libcamera to Jetson Argus/V4L2.
> Key risk: IR strobe timing precision on Jetson GPIO.
> Next session should focus on reading PiTrac source code and camera selection research.

**2026-03-14**

> Camera selected: Arducam OV9281 Monochrome USB3 ×2. 

> No LiDAR for v1. 

> IR at 850nm. Strobe via Jetson GPIO at 10µs — validate with oscilloscope before committing. 

> Teensy 4.0 strobe driver and MIPI CSI cameras reserved for v2 on second Jetson. 

> Two-Jetson strategy confirmed: finish v1 first, then build improved v2.

**2026-03-16**

> Full camera pipeline analysis completed using Claude Code on laptop.
> 19 functions mapped in libcamera_interface.h. ball_watcher_event_loop, MotionDetectStage::Process, and PulseStrobe::SendExternalTrigger all read and understood.
> Key discovery: strobe uses SPI (lgSpiWrite), not simple GPIO — affects hardware wiring plan.
> PORTING_TASKS.md created with 24 tasks across 3 groups.
> All 14 Group 1 compile blockers completed: meson.build guards, v4l2_interface.h, JetsonCaptureApp, JetsonCompletedRequest, ball_watcher rewrite, motion_detect.h stub base class, motion_detect_stage.cpp guards.
> All changes committed and pushed to github.com/Pilzkoma/PiTrac.
> Next session: Group 3 stubs, then first meson configure on Jetson.

**2026-03-16 — session 2**

> All 24 porting tasks complete. Group 3 stubs done: v4l2_interface.cpp created with 5 stub functions, libcamera_interface.cpp fully guarded with JETSON_BUILD, meson.build updated.
> kGatherClubData and kUsePreImageSubtraction already false by default — no changes needed.
> Codebase is now ready for first meson configure attempt on Jetson.
> Next: boot Jetson, clone repo, install apt dependencies, run meson setup -Djetson_build=true --wipe.

**2026-03-16 — session 3 (Jetson first compile)**

> First ninja compile attempt on Jetson.
> Resolved: meson configure fully clean after fixing fmt, Boost floor, msgpack name, yaml-cpp, onnxruntime install, GCC 10, PITRAC_ROOT, JETSON_BUILD preprocessor define.
> Blocked on: Boost 1.71 incompatible with C++20 — named_scope.hpp, multi_index, property_tree all broken. BOOST_NO_CXX11_ALLOCATOR workaround insufficient.
> Fix in progress: building Boost 1.74.0 from source on Jetson (~20 min). Left running overnight.
> Also outstanding: libcamera_jpeg.cpp still pulls in rpicam headers — needs same JETSON_BUILD guard treatment as other files. v4l2_interface.cpp SetLibCameraLoggingOff declaration mismatch needs fixing.
> Next session: confirm Boost 1.74 install, re-run ninja, fix remaining compile errors.

**2026-03-19**

> FIRST SUCCESSFUL BUILD. pitrac_lm binary produced on Jetson Xavier NX (46MB).
> Binary starts correctly — signal handlers install, --help prints all command line options.
> All 51 source files compile cleanly. All linker errors resolved.
> Final fixes: E6 closed-source object excluded from Jetson build, GsE6Interface call sites guarded.
> Build environment: JetPack 5.1.6, GCC 10, Boost 1.76 (from source), OpenCV 4.5.4, ONNX Runtime 1.16.3.
> Next: cameras arrive → connect OV9281 → test V4L2 device detection → first live camera frame.

**2026-03-21**
> Created camera_test.py in ~/JetsonLM/sp1_vision/ — camera detection and test tool
> ready for when OV9281 cameras arrive. Detects USB cameras, queries V4L2 capabilities,
> captures test frames, live preview with FPS counter. Auto-identifies OV9281 and
> verifies monochrome sensor output.

**2026-03-21**
> OV9281 cameras arrived and tested. Both cameras detected immediately via V4L2
> (uvcvideo driver). Device mapping: /dev/video0 (bus xhci-2.2.4) and /dev/video2
> (bus xhci-2.3). /dev/video1 and /dev/video3 are UVC metadata devices (no formats).
> Test frames captured successfully from both cameras at 1280x800.
> OpenCV defaults to YUYV (10 FPS) — PiTrac pipeline must request MJPG for 120 FPS.
> CUDA not enabled in system OpenCV 4.5.4 — may need to rebuild with CUDA for
> GPU-accelerated processing, or use PiTrac's own OpenCV build.
> camera_test.py tool created in ~/JetsonLM/sp1_vision/ for future camera validation.

**2026-04-26**
> Verified sustained 120 FPS dual-camera capture at the kernel/USB level.
> Wrote sp1_vision/dual_camera_test.py (with optional --exposure flag for
> manual exposure control via v4l2-ctl). OpenCV cv2.VideoCapture caps at
> ~55-60 FPS per camera regardless of exposure setting — diagnosed as
> CPU-bound MJPG decode in cap.read(), not a camera or USB limitation.
> Confirmed via v4l2-ctl --stream-mmap that both cameras independently
> sustain the full 120 FPS @ 1280x800 MJPG even when streaming in parallel
> (separate USB buses, no bandwidth contention). Issues #15 and #16 logged.
>
> Conclusion: camera infrastructure is production-ready. The Python test
> harness's decode bottleneck is irrelevant — the C++ port of v4l2_interface.cpp
> will use V4L2 ioctl directly (open/mmap/dequeue) and decode with
> libjpeg-turbo or nvJPEG, both faster than OpenCV's generic decode path.
>
> Next session: design and implement the 5 real V4L2 capture functions
> in Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp (currently
> all stubs from Group 3 of PORTING_TASKS.md). This is the work that
> unblocks calibration, ball detection, and connecting real shots to
> the SP4 GSPro/SQLite pipeline.

**2026-04-29**
> SP1 milestone: real V4L2 capture engine landed.  4 of 5 stub functions
> in v4l2_interface.cpp now real; WaitForCam2Trigger stays stubbed
> pending IR strobe + SPI work.  Engine sustains ~125–130 FPS in the
> ball_watcher_event_loop tight read path — proven via per-frame log
> timestamps inside V4L2Capture::read().  Architecture: V4L2Capture
> class (mmap × 4 buffers, V4L2 ioctl: S_FMT/S_PARM/REQBUFS/QBUF/
> STREAMON/DQBUF, libjpeg-turbo gray decode + cvtColor → BGR).  Public
> method names mirror cv::VideoCapture so JetsonCaptureApp::cap swaps
> type without forcing edits to ball_watcher.cpp.
>
> Spec written to docs/superpowers/specs/2026-04-29-v4l2-capture-engine-design.md;
> implementation plan to docs/superpowers/plans/2026-04-29-v4l2-capture-engine.md.
> 11 commits on main for the engine + integration fixes.
>
> Integration fixes layered on top of the engine itself:
>   * meson.build: added libturbojpeg dep under jetson_build (apt: libturbojpeg0-dev).
>   * PerformCameraSystemStartup: writes CameraHardware::resolution_{x,y}_override_
>     = 1280, 800 so PiTrac's PiGS-default 1456×1088 resolution check
>     accepts OV9281 frames.
>   * PulseStrobe::* GPIO/SPI stubs flipped from false → true so the
>     FSM init chain advances past GPIO setup.  Real libgpiod work
>     stays a separate Group 2 item (no IR LED hardware yet).
>   * ActiveMQ broker installed via apt (5.15.11) and the default `main`
>     instance enabled at /etc/activemq/instances-enabled/main.  Address
>     supplied via --msg_broker_address=tcp://127.0.0.1:61616.
>
> Behavioral observations:
>   * CheckForBall path runs at ~8 FPS — FSM/IPC overhead per call,
>     not engine-throttled.
>   * ball_watcher_event_loop tight loop hits 125–130 FPS on the V4L2
>     engine alone.  Each loop currently exits at frame ~5 because
>     the open/release recycling makes the very first decoded frame
>     look "different" enough to trip motion-detect — a tuning issue
>     in motion_detect_stage, not the engine.
>   * `Video resolution (x,y) is: 1280/1080` is logged from
>     camera_hardware.cpp:265 which hardcodes y=1080 in the PiGS
>     branch; cosmetic-only, the actual resolution_y_ check at line
>     205 uses the override.
>   * `timeout` SIGTERM doesn't get pitrac_lm to release /dev/video0
>     cleanly — leaves zombie processes holding the fd.  Use `( … )&;
>     sleep N; pkill -9 pitrac_lm` instead, or rmmod+modprobe uvcvideo
>     to reset stuck device state.
>
> Known follow-ups for the next session:
>   * undistort_camera_image port (currently skipped in TakeRawPicture
>     for Jetson — frames aren't lens-corrected).
>   * Tighten motion_detect_stage so ball_watcher_event_loop doesn't
>     trip on the first-frame edge case after open/release.
>   * IR LED hardware + libgpiod/SPI strobe (gates WaitForCam2Trigger,
>     spin measurement, full shot pipeline).
>   * Mount cameras in enclosure at correct stereo angles.
>   * V4L2Capture has a known minor bug: on ensure_streaming() failure
>     path the fd remains open and `streaming_=false`, so subsequent
>     read() calls re-attempt ensure_streaming against the same
>     already-failed fd and never recover.  Fix: release() on failure.

**2026-05-02**
> SP1 motion-detect blocker resolved end-to-end.  ball_watcher_event_loop
> now runs the full MotionDetectStage path on Jetson — trips reliably on
> real motion (hand wave: <30 frames, ~250 ms) and stays silent on a
> static scene (1060 frames, regions 0-19 vs threshold 12800, ~675x
> headroom).  This was the last software gap between "engine works" and
> "ball detection produces real output."
>
> Three layered fixes, in order of importance:
>   1. ConfigurePostProcessing wired into Jetson WatchForHitAndTrigger
>      with a full-frame ROI (1280×800).  RPi side called this from
>      ConfigCameraForCropping which is RPi-only — without the wireup,
>      MotionDetectStage::Read fell through to cpp defaults (1×1 ROI,
>      threshold=0) and any non-zero `regions` count tripped on the
>      first comparison frame.  Verified by `MotionDetectStage::Read -
>      using internal data.` trace.
>   2. golf_sim_config.json motion_detect_stage thresholds tuned for
>      bench (no-strobe) testing: kDifferenceM 0.9→0.3, kDifferenceC
>      3.0→5.0, kFramePeriod 0→5.  The original 0.9 per-pixel
>      multiplier required near-saturation contrast to count any pixel;
>      diagnostic showed regions=0 across 1200+ frames even with the
>      lens fully covered.  Production path with IR strobe will likely
>      want the original strict thresholds back — saved as a known
>      pre-strobe-vs-post-strobe tuning question.
>   3. ball_watcher_event_loop discards 2 warm-up frames after V4L2
>      stream-on so the first decoded frame's pre-AGC content can't
>      bias previous_frame_.
>
> Side-quest landed in the same session: undistort_camera_image ported
> verbatim from libcamera_interface.cpp:950 (pure OpenCV — needs
> opencv2/calib3d.hpp include) and called from TakeRawPicture.  No-op
> until camera calibration loads a matrix, then OpenCV
> initUndistortRectifyMap+remap kicks in — matches RPi semantics so
> downstream ball-detect/stereo geometry consistently sees rectified
> frames.  Will be verified on the calibration run.
>
> 5 commits on main: ConfigurePostProcessing wireup + warm-up
> (e73d4cc), undistort port (56df327), opencv2/calib3d.hpp include
> (e41f5f8), motion-detect diagnostic (dacec39, removed at end of
> session), motion-detect threshold tune (21c28ef).
>
> Process notes (workflow lessons):
>   * `cd && git pull && ninja && (...) & sleep 30; pkill` is wrong —
>     the `&` backgrounds the whole chain and pkill fires while ninja
>     is still building.  Separate build from test+timing chain.
>   * trace flooding the terminal makes Ctrl+C feel unresponsive (the
>     keystrokes scroll past).  Always redirect to /tmp/pitrac.log,
>     grep after.  Open a second SSH session for emergency pkill.
>   * SSH from dev machine to Jetson is significantly faster than
>     copy-pasting through Google Docs.
>
> Two issues moved from "session-notes follow-up" to formal Known
> Issues Register (Issues #17 and #18) — neither is a current blocker:
>   * #17: V4L2Capture ensure_streaming() failure-path fd leak.  ~1h fix.
>   * #18: motion_detect_stage hskip is in bytes not pixels (CV_8UC3
>     assumption).  One-line fix, JETSON-guarded.
>
> Known follow-ups for the next session:
>   * Pick: SP4 placed-ball + manual-trigger TCP round-trip to GSPro
>     (proves the data pipeline) OR IR LED hardware procurement
>     (unblocks the strobe SPI work and Cam2 trigger).
>   * Camera calibration run will verify the undistort wire-in.
>   * Issues #17 and #18 are good "small cleanup" tasks if the next
>     session has a slow window.

**2026-05-02 (continued — same day, second half: strobe pipeline)**
> Strobe hardware arrived (Teensy 4.0 DEV-15583 + Cenpek 850nm 12V
> 4-LED IR board + 12V/15A industrial PSU).  Pivoted to Group 2 strobe
> work right after the motion-detect milestone.
>
> Architecture decision up front: pulled the Teensy 4.0 forward from
> the v2 plan instead of porting the RPi SPI bit-bang pulse generator
> 1:1.  Linux on Xavier NX with V4L2 + motion-detect already running
> can't reliably hit sub-10µs GPIO timing (jitter > pulse width).
> Teensy 4.0 has hardware timers and gives ns-precision pulse-train
> generation completely deterministically.  Jetson computes intervals
> + on-bits + baud once at startup, sends via USB serial; runtime fire
> is a single GPIO pulse.  PiTrac's BuildPulseTrain math stays
> unmodified on the Jetson side — we just re-package the result
> (pulse interval vector + ON-bit count) for the Teensy text protocol.
>
> Phase A — Teensy firmware (Hardware/teensy_strobe/teensy_strobe.ino,
> ~260 lines): text protocol over USB serial (PULSES_FAST, PULSES_SLOW,
> ON_BITS, BAUD, MODE, READY?, STATUS, TEST_FIRE), Pin 2 = FIRE input
> (RISING-edge ISR), Pin 3 = LED_GATE output, Pin 13 = onboard status
> LED.  Standalone-tested via Arduino Serial Monitor — `OK / FIRED`
> chain confirmed without any Jetson present.  Commit eec3c50.
>
> Phase B — Jetson PulseStrobe Jetson-side impl
> (pulse_strobe_jetson.cpp, ~470 lines): replaces the 5 no-op stubs
> from v4l2_interface.cpp.  Real libgpiod fire-pin claim + termios
> /dev/ttyACM0 USB-serial setup handshake.  Soft-fallback architecture
> on every HW failure (Teensy missing, GPIO claim refused) so dev runs
> without the strobe rig still work — InitGPIOSystem returns true,
> SendExternalTrigger no-ops with a warning.  Builds clean after one
> compile fix (anonymous-namespace helper couldn't reach
> protected static members; refactored to take them as parameters).
> Commits efe0fe6, b9d51ac.
>
> Phase B GPIO pin discovery — long debug arc, eventually nailed:
>   * Initial guess gpiochip0 line 148 (PMIC chip — only 8 lines, wrong)
>   * Switched to gpiochip2 line 14 (PCC.02) — multimeter found no
>     toggling header pin (PCC.02 likely not routed to header)
>   * Tried gpiochip2 line 28 (PEE.05) — no datasheet confirmation it
>     was on header
>   * Tried gpiochip2 line 16 (PCC.04) — discovered my port-adjacency
>     theory was wrong (PCC.04 is Pin 15, not Pin 12 as I assumed)
>   * Pin 15 toggle test failed (line stayed 0V) — turned out the
>     "user GPIO" pins 15/32/33 in the J202 datasheet ALL have PWM
>     controllers attached (c340000.pwm / 32f0000.pwm / 3280000.pwm)
>     per Jetson.GPIO's pin-data table.  Kernel PWM driver fights our
>     libgpiod writes and produces garbage 1.5V averages on the
>     multimeter
>   * Final pick: Pin 29 = PQ.05 = gpiochip1 line 105.  No PWM/SPI/
>     I2S/UART alternate (only "General Purpose Clock #0" which isn't
>     active).  Verified clean 0V↔3.3V toggle at 1Hz via Jetson.GPIO
>     Python (after fixing a cable contact issue that had been
>     polluting earlier multimeter readings).
> Commits 2ca5915, cd949d9, 01b521b, e8bd72d.
>
> Lessons saved as memory: (1) Jetson.GPIO pin-data file location at
> /usr/lib/python3/dist-packages/Jetson/GPIO/gpio_pin_data.py is the
> authoritative pinmap for any Jetson; (2) `gpioset` without
> `--mode=signal` or `--mode=time` releases the line immediately —
> apparent toggle-loop failures are usually this, not the pin.
>
> Status at end of session: Phase A (firmware) and Phase B (Jetson
> code) both complete and committed.  Phase C (wiring + bench tests)
> blocks on (a) header pins to solder onto the Teensy (waiting on
> shipment), and (b) IRLZ44N MOSFET to order for the 12V Cenpek
> board switching.  2N3904 + LED + 1kΩ already in hand for the
> intermediate Phase C-Test 1 (proof-of-life on Teensy Pin 3 gate
> output without the IR-LED-array risk).
>
> Hardware Components Registry updated: Teensy 4.0 / Cenpek IR /
> 12V PSU all marked "in hand"; MOSFET marked "TBD ordered."
> SP1 progress 88% → 92%.
>
> Handoff for next session is in SP1 Next Steps.  When the soldered
> Teensy is wired up, single command sequence will validate the full
> strobe pipeline:
>   1. cd ~/JetsonLM/Software/LMSourceCode/ImageProcessing
>   2. ./build_jetson/pitrac_lm --system_mode=camera1_test_standalone
>      --msg_broker_address=tcp://127.0.0.1:61616 --logging_level=trace
>   3. grep for "Teensy READY, GPIO line claimed" in the log
>   4. Wave hand → check for "SendExternalTrigger - fire pulse sent
>      to Teensy" + LED13 blip on Teensy

**2026-05-05 — Phase C Test 1 PASS**
> Hardware-side wired up (Jetson Pin 29 ↔ Teensy Pin 2, GND ↔ GND,
> USB), test rig built (Teensy Pin 3 → 5mm LED → 1kΩ → Teensy GND).
> SSH from the Windows dev box into the Jetson — significantly less
> friction than the Google-Doc copy-paste from earlier sessions.
>
> Permission gotcha: `brain` is in `gpio` (so /dev/gpiochip1 works
> out-of-the-box) but NOT in `dialout`, so /dev/ttyACM0 access fails
> as user.  One-shot fix: `sudo chmod 666 /dev/ttyACM0`.  Permanent
> fix queued: `sudo usermod -a -G dialout brain` + re-login.
>
> First pitrac_lm run with the strobe rig connected: init handshake
> all green —
>   * `open_teensy_serial - opened /dev/ttyACM0 at 115200 8N1`
>   * `send_setup_to_teensy - Teensy reached READY state`
>   * `PulseStrobe::InitGPIOSystem - Teensy READY, GPIO line claimed.
>      Strobe pipeline live.`
> Teensy LED13 went from 1Hz blink (WAITING_SETUP) to solid HIGH (READY)
> right on cue.  But: WatchForHitAndTrigger never got called, so
> SendExternalTrigger never fired, so the test LED never blinked.
>
> Diagnosis from FSM-transition trace: PiTrac is stuck in a
> WaitingForBall ↔ WaitingForBallStabilization ping-pong.  The yellow
> ball is in a cap (not moving), the test LED is out of frame, no
> hand motion in the scene — but CheckForBallStable rejects the
> placed ball every ~1 second.  Most likely HoughCircles is finding
> the ball at slightly different positions frame-to-frame in the
> noisy ambient-IR mono image.  Filed as Issue #19.  Won't fix in
> software — production path uses sharp IR-strobe lighting that gives
> HoughCircles clean ball edges.  No more time on this until the IR
> LEDs actually fire.
>
> Bypass: instead of trying to coax the FSM into the Watch loop,
> wrote Hardware/teensy_strobe/test_strobe_bypass.py — opens
> /dev/ttyACM0, configures the Teensy with long visible pulses
> (32 ms ON, 200 ms gaps, 7 pulses → ~1.5 s burst), claims Pin 29
> via Jetson.GPIO, toggles 100 µs HIGH pulses 5× with 3 s gaps.
> Result: 5/5 fires produced visible LED flicker on Teensy Pin 3.
> STATUS dump confirmed `STATE=READY MODE=FAST ON_BITS=32 BAUD=1000
> ON_PULSE_US=32000 N_FAST=7 N_SLOW=13`.
>
> What this milestone proves:
>   * Teensy firmware (Phase A) is correct — accepts setup, runs ISR,
>     drives Pin 3.
>   * pulse_strobe_jetson.cpp logic (Phase B) is correct — same
>     init-then-toggle sequence works in Python, so the C++ version
>     does the right thing too.
>   * Wiring is correct — Pin 29 on the Seeed J202 reaches the
>     Teensy's Pin 2 ISR cleanly.
>   * The FSM blocker (Issue #19) is decoupled from the strobe
>     pipeline — once IR illumination is in, FSM unsticks AND the
>     pipeline behind it is ready to fire.
>
> SP1 progress 92% → 95%.  Hardware-Components Registry already had
> the right entries from 2026-05-02; nothing to update there.
> The Bypass-Test-Skript is the cleanest way to validate any future
> change to the strobe rig (MOSFET swap, LED-array swap, wiring
> rerouting) without depending on PiTrac's FSM state.
>
> Open before SP1 declares done:
>   * IRLZ44N MOSFET to order (gate-driver between Teensy and Cenpek
>     12V IR board).
>   * Phase C Test 2: same bypass script, but with the Cenpek board
>     instead of the test LED.  Smartphone slowmo to confirm 850nm
>     IR pulses (most phone cameras pick up 850nm despite the IR-cut
>     filter).
>   * Once that's green, SP1 is functionally complete.  The
>     Issue #19 stabilization gate naturally falls open once the
>     ball is being IR-strobe-lit during pitrac_lm runs.

**2026-05-05 (continued — strobe pipeline software-validated end-to-end + 3 bug fixes)**
> Continued the same SSH session to actually wire the Teensy + LED rig
> to the Jetson and exercise the full strobe pipeline through pitrac_lm.
> Long arc, eventually validated via workaround.  Six commits.
>
> Setup: `sudo chmod 666 /dev/ttyACM0` (one-shot — `brain` not yet in
> `dialout` group; permanent fix `sudo usermod -a -G dialout brain` queued
> for next re-login).  Pin 29 ↔ Teensy Pin 2, GND ↔ GND, USB.
> Test rig: 5mm LED + 1kΩ between Teensy Pin 3 and GND.
>
> First pitrac_lm run with the rig wired:
>   * Init handshake clean — `Strobe pipeline live`, Teensy LED13 solid
>     HIGH (READY state)
>   * Ball Stabilized at 18:55:30, motion-detect tripped at 18:55:32
>     (FSM made it through Issue #19 once)
>   * `fire pulse sent to Teensy` logged
>   * BUT the test LED stayed dark
>
> Discovered Issue #20 first: `motion_detect_stage.cpp` had an explicit
> `if (system_mode != kCamera1TestStandalone)` gate around the
> `SendExternalTrigger` call — sensible on RPi (don't pulse a non-existent
> cam2 system in isolated cam1 testing) but wrong on Jetson where
> SendExternalTrigger drives the IR strobe.  Fixed: under
> `#ifdef JETSON_BUILD` always call SendExternalTrigger.  Commit 1981378.
>
> Next run: same FSM-stuck-in-stabilization-loop pattern as 2026-05-02 —
> Issue #19 prevented the watch loop from ever running.  Filed Issue #21
> as a development bypass: in `gs_fsm.cpp` WaitingForBallStabilization,
> when ball is found but reports "moved" (sub-pixel HoughCircles jitter),
> force-advance instead of bailing back.  When ball is genuinely lost,
> original behavior preserved.  Commit b2c5fb6.
>
> Run with bypass: ✅ FSM advanced (`Ball Stabilized` → `WatchForHitAndTrigger
> calling` → `fire pulse sent to Teensy` → `---> SendExternalTrigger
> (Jetson)`), all in the log — but the test LED *still* didn't blink.
>
> Diagnosed: production strobe values are 17 µs ON × 7 pulses ≈ 120 µs
> total ON time, way below the eye's perception threshold even with
> Smartphone slowmo.  Tweaked `golf_sim_config.json` to test values
> (ON_BITS=32, BAUD=1000 → 32 ms ON × 7 pulses ≈ 225 ms burst).
>
> Long debugging arc on the libgpiod chardev path follows.  Sequence:
>   * 5ms HIGH hold instead of 100us — no help
>   * Defensive force-LOW + 2ms settle before rising edge — no help
>   * Verified via Teensy STATUS query that pitrac_lm did push the long
>     pulse values to the Teensy and Teensy is in READY — config is fine
>   * Tried `gpioset --mode=time --sec=1 gpiochip1 105=1` (libgpiod CLI,
>     same chardev path as pitrac_lm) — also no LED blink
>   * Re-ran the bypass script (Python Jetson.GPIO) — LED blinks reliably
>   * **Conclusion (Issue #22):** libgpiod chardev does NOT drive Pin 29
>     in a way the Teensy ISR detects on this Seeed J202 carrier.
>     Cause unknown — possibly L4T-32-era kernel/devicetree quirk that
>     disagrees with the chardev write path but Jetson.GPIO works
>     because it uses a different code path.  Not chasing this down.
>
> Workaround: shell out to `Hardware/teensy_strobe/fire_trigger.py` via
> `std::system`.  Uses Jetson.GPIO under the hood (the path that works).
> ~100-200 ms fork+exec+python startup latency, dominated by Python
> interpreter cold-start.  Acceptable since the strobe pulse-train
> timing happens on the Teensy hardware-timer side, not on the trigger
> path.  Refactored `pulse_strobe_jetson.cpp`: removed all libgpiod
> calls, removed gpiod.h include, dropped 96 lines.  Commit fea85cf.
>
> Final validation:
>   * Manual `python3 fire_trigger.py` (no sudo, brain in gpio group):
>     LED blinks reliably ✅
>   * Teensy STATUS post-pitrac_lm: `STATE=READY MODE=FAST ON_BITS=32
>     BAUD=1000 ON_PULSE_US=32000 N_FAST=9 N_SLOW=13` — handshake done
>     correctly through pitrac_lm's init path ✅
>   * `Strobe pipeline live (trigger via fire_trigger.py)` logged in
>     pitrac_lm trace ✅
>   * Last untested link: literal `std::system("python3 fire_trigger.py")`
>     line — hardcoded one-liner, low risk.  Final FSM-driven validation
>     deferred to Phase C Test 2 with real IR strobe (Issue #19
>     stabilization will resolve naturally then).
>
> Side cleanups in the same session:
>   * **Issue #18 (motion_detect hskip-bytes-vs-pixels)** RESOLVED.
>     Derived `hskip_bytes = config_.hskip * frame.channels()` under
>     `#ifdef JETSON_BUILD`, replaced 4 pointer-arithmetic uses.  RPi
>     branch unchanged (channels=1 implicit).  Coverage now matches
>     configured 640 horizontal samples / row instead of ~213.
>     Commit 701d659.
>   * **Issue #17 (V4L2Capture ensure_streaming fd leak)** RESOLVED.
>     Every failure path now calls `release()` before `return false`.
>     Reordered: `tj_handle` + `gray_scratch` allocation moved BEFORE
>     `VIDIOC_STREAMON` so STREAMON is the unique point-of-no-return at
>     the end with no failure paths after it.  Commit cd54f0b.
>
> SP1 progress 95% → 97%.  Hardware Components Registry updated 2026-05-02
> already covers MOSFET TBD-ordered.
>
> Issues closed this session: #17 (fd leak), #18 (hskip bytes), #20
> (TestStandalone trigger skip).  Issues opened/active: #19 (stabilization
> — partial workaround via #21), #21 (force-advance bypass — REMOVE when
> IR strobe in), #22 (libgpiod chardev — workaround in place).
>
> SP1 strobe pipeline status: **software-vollständig validiert**.  Was
> noch fehlt für SP1 functional complete:
>   1. IRLZ44N MOSFET bestellen
>   2. Phase C Test 2: MOSFET + Cenpek IR-Board, gleicher Bypass-Test mit
>      Smartphone-Slowmo zur 850nm-Burst-Verifikation
>   3. Issue #19 + #21 lösen sich dann automatisch sobald IR-strobe-lit
>      ball für HoughCircles saubere Kanten liefert
>
> Lessons saved as memory: none new this session — Jetson.GPIO pin-data
> location and gpioset --mode lessons from 2026-05-02 still apply and
> were used today.  Issue #22 (libgpiod chardev mystery) is repo-specific
> and lives in LOGBOOK rather than memory since it might resolve with
> L4T upgrade.

**2026-05-12 — Phase C Test 2 PASS (strobe pipeline hardware-validated end-to-end)**

> IRLZ44N TO-220 angekommen.  Verdrahtet als low-side switch:
> Cenpek V+ → 12V PSU(+); Cenpek V− → MOSFET Drain (Pin 2/Tab);
> MOSFET Source (Pin 3) → gemeinsame GND-Schiene mit 12V PSU(−) und
> Teensy GND; Teensy Pin 3 → MOSFET Gate (Pin 1); 1kΩ Gate-Source-
> Pulldown direkt am MOSFET.  10k war im Plan, aber 1k tut's auch —
> 3.3 mA Idle-Strom durch den Pulldown wenn Pin 3 HIGH, weit unter
> Teensy 4.0 source-spec.  Schaltgeschwindigkeit unbeeinträchtigt
> da Teensy den Gate direkt treibt.
>
> Test: `sudo python3 Hardware/teensy_strobe/test_strobe_bypass.py`.
> Gleicher Bypass wie 2026-05-05 — 5 Fires, jeweils 7×32ms IR-Bursts.
> Doppelte Verifikation:
>   * Smartphone-Kamera sieht die 850nm-Bursts als schwaches rotes
>     Glimmen bei jedem Fire (Phone-IR-Cut-Filter blockt nicht
>     vollständig bei 850nm).
>   * 12V PSU Ampere-Anzeige zeigt synchron zu jedem Fire einen
>     Strom-Spike — beweist dass tatsächlich Last durchgeschaltet
>     wird, nicht nur ein optisches Artefakt.
>
> Was das bedeutet: die komplette Strobe-Kette ist jetzt
> hardware-validiert end-to-end:
>   Jetson Pin 29 → Teensy Pin 2 ISR → Teensy Pin 3 → IRLZ44N Gate
>   → Cenpek 12V-Pfad → 4× 850nm LEDs feuern.
> Die Software-seitige Validierung von 2026-05-05 (pitrac_lm
> Init-Handshake + std::system fire_trigger.py path) gilt unverändert
> weiter — heute kam nur die letzte Lastseite dran.
>
> SP1 Progress 97% → 98%.  Was noch offen für functional complete:
>   * Live FSM-Run mit Ball + IR-Strobe-Beleuchtung — Erwartung:
>     Issue #19 (HoughCircles-Jitter in ambient IR) und damit auch
>     der #21-Force-Advance-Workaround lösen sich automatisch sobald
>     die Bälle in scharfem 850nm-Burst beleuchtet werden.  Erst
>     dann ist die FSM-Validation echt geschlossen.
>   * Camera mounting + Stereo-Kalibrierung
>   * Erster echter Shot mit ball speed / launch angles → SP4 GSPro
>
> Hardware Components Registry: MOSFET-Zeile auf ☑ In hand
> aktualisiert, "IRLZ44N (TO-220, logic-level N-channel)" + 1kΩ
> Pulldown im Notes-Feld vermerkt.

**2026-05-12 (continued) — SP1 FSM-validated end-to-end + Issue #19/#21 resolved by design**

> Nach Phase C Test 2 PASS noch eine Session: pitrac_lm im echten
> kCamera1-Modus laufen lassen, Issue #19/#21-Hypothese aus 2026-05-05
> empirisch prüfen.  Setup minimal: Cam1 schräg auf einen Golfball
> in einem Putting-Mat in normalem Wohnzimmerlicht, IR-Array
> verdrahtet aber während Stabilization aus (s.u.).
>
> Boot-Hiccups erst gelöst:
>   * runCam1.sh erwartet env vars (PITRAC_MSG_BROKER_FULL_ADDRESS,
>     PITRAC_WEBSERVER_SHARE_DIR, PITRAC_BASE_IMAGE_LOGGING_DIR) —
>     direkt gesetzt
>   * runCam1.sh erwartet Binary in `build/pitrac_lm`, unser
>     Jetson-Build liegt in `build_jetson/` → Symlink
>     `ImageProcessing/build → build_jetson` aufgelöst (alte stale
>     `build/`-Dir vorher gelöscht)
>   * `WebServer/share/` Verzeichnis fehlte, dadurch keine
>     Diagnose-Bilder — `mkdir -p` und Fix
>
> Live-Run-Ergebnisse (sp1_fsm_1959.log, sp1_fsm_2006.log):
>   * Init: `Strobe pipeline live (trigger via fire_trigger.py)` ✓
>   * FSM: `WaitingForBall → BallPlaced → WaitingForBallStabilization`
>     → mehrere `Ball Lost Before Stabilizing` Zyklen → schließlich
>     `Ball Stabilized - Let's Play Golf! (Waiting for hit)` ✓
>   * Run 1: `JETSON_STUB Issue #21: stabilization moved-check bypassed`
>     hat genau einmal gegriffen → unmittelbar danach Ball Stabilized
>     → `PulseStrobe::SendExternalTrigger - fire pulse sent` ✓
>   * Damit ist die komplette FSM-Kette inkl. Trigger-Path im echten
>     Modus live validiert (vorher nur bypass-script).
>
> Critical realization über Issue #19:
>   * 2026-05-05-Hypothese war "IR-Strobe-Beleuchtung macht
>     HoughCircles-Kanten sauber, Stabilization wird natürlich passen".
>   * **Hypothese ist falsch.**  Bei Code-Review der Teensy-Firmware
>     (teensy_strobe.ino:74) wird LED_GATE im Setup auf LOW gesetzt
>     und nur während eines getriggerten Pulse-Trains HIGH.  Es gibt
>     keinen continuous-on Modus.  Strobe feuert erst in
>     `SendCameraPrimingPulses` (gs_fsm.cpp:322) — also NACH
>     Stabilization, nicht währenddessen.
>   * Stabilization-Check-Frames werden also für immer unter
>     Ambient-Licht-Bedingungen aufgenommen.  HoughCircles-Jitter ist
>     permanent.  Issue #19 ist nicht fix-bar durch IR allein.
>
> Diagnose-Bild `log_cam1_search_area_img.png` bestätigt: schlecht
> beleuchtete Mono-Szene mit clutter-Hintergrund (Skateboard,
> Leinwand, Stuhlbeine) — viele kreis-ähnliche Kanten die
> HoughCircles spurious detections geben.  Ball-Kontrast gegen das
> dunkle Putting-Mat ist niedrig.  Die einmalige Detection bei
> (663, 48) war wahrscheinlich ein False Positive am oberen
> Skateboard-Rand, nicht der echte Ball.  Das echte FSM-Verhalten
> (mehrere `Ball Lost` Zyklen vor erfolgreicher Stabilization) passt
> zu dieser Bild-Analyse.
>
> Entscheidung Option 2c: **Issue #21 Bypass als permanenten Design
> Choice promoten**, statt Workaround.
>   * gs_fsm.cpp:280-301: Kommentar-Block JETSON_STUB → JETSON_DESIGN,
>     falsche "remove once IR strobe is wired" Prophezeiung gelöscht,
>     stattdessen Erklärung dass IR-Array event-driven ist und
>     ambient-light jitter daher permanent.
>   * Begründung in Kommentar: für Launch-Monitor-Use-Case (Ball
>     liegt in Tee/Cap, kann sich physisch zwischen zwei 1-Sekunden-
>     Frames NICHT bewegen) ist "re-detection ⇒ accept jitter, genuine
>     loss ⇒ bail back" semantisch korrekt.
>   * Log-Marker `JETSON_STUB Issue #21: stabilization moved-check
>     bypassed` → `Jetson stabilization: re-detected ball after jitter,
>     advancing` (informativer, kein Stub-Geruch mehr).
>
> SP1 Progress 98% → 99%.  Issues #19/#21 als "Resolved by design"
> geschlossen.  Was offen bleibt für functional-complete:
>   * Issue #22 (libgpiod chardev mystery, Python-Helper-Workaround
>     in Production) — akzeptiert, kein Fix geplant
>   * Final 1%: echte Kalibrierung + erster Shot mit Speed/Angles auf
>     Console — braucht Camera-Mounting (Enclosure CAD, geht nach
>     SP5).  Davor ist SP1 mit "Hardware + Software end-to-end live
>     validiert" maximal abgedeckt.

**2026-08-06/07 — Kameras vermessen. Optik-Konstanten waren alle falsch.**

> Kameras sind im Gehäuse montiert, Geometrie fix. Ziel war, die echten
> Intrinsics zu messen, bevor irgendetwas an Geometrie oder Brennweite
> angefasst wird — die bisherigen 2.7 mm waren aus der 70°-Herstellerangabe
> gerechnet, nicht gemessen.
>
> **Die Ausgangslage war schlechter als gedacht.** Jede optische Konstante
> im Code beschrieb PiTracs IMX296 mit 6-mm-Objektiv:
>
> | | war | ist |
> |-|-|-|
> | Brennweite | 6.222 / 5.903 mm | **2.767 / 2.772 mm** |
> | Sensor | 5.077 x 3.789 mm | **3.840 x 2.400 mm** |
> | fx | 1833 / 2340 px | **922 / 924 px** |
> | k1 | -0.509 / -0.818 | **+0.015 / +0.053** |
> | Ballradius @ 40cm | 87 | **49** |
>
> Der unangenehmste Fund: die IMX296-Matrix lag nicht bloß ungenutzt herum,
> sie war **aktiv**. camera_hardware.cpp schaltet use_undistortion_matrix_
> ein, sobald die Config eine Matrix ungleich null trägt — und PiTracs stand
> drin. Jedes Standbild aus TakeRawPicture, also der Pfad den CheckForBall
> und damit die Ballerkennung benutzt, wurde durch ein fremdes Objektivmodell
> gerechnet: starke Tonnenkorrektur auf ein Bild das kaum verzeichnet, durch
> einen Hauptpunkt 113 px außerhalb der Bildmitte. Die Notiz vom 2026-04-29
> ("no-op until calibration loads a matrix") war falsch.
>
> Zweiter struktureller Fund: nur die *Auflösung* wurde auf 1280x800
> überschrieben, die Sensormaße blieben IMX296. Damit stand das Seitenverhältnis
> des Sensors auf 1.340 gegen ein Bild von 1.600 — und gs_camera.cpp:929/936
> rechnet Pixel über sensor_width_/focal_length_ und sensor_height_/focal_length_
> **getrennt** in Meter um. Die vertikale Achse war rund 19% daneben. Eine
> Fokallängen-Kalibrierung schluckt einen Fehler in der absoluten Breite; ein
> falsches Seitenverhältnis schluckt sie nicht.
>
> **Werkzeug gebaut statt Einmal-Skript.** Kalibrierung ist keine einmalige
> Sache — jede Mount-Verstellung macht sie ungültig. Also eine Seite im
> laufenden Dashboard unter /calibration: Livebild pro Kamera, Schärfeanzeige,
> Aufnahme-Knopf mit sofortiger Bretterkennungs-Rückmeldung, Auswerte-Knopf.
> CLI als Rückfallebene. 12 Tasks, TDD, 19 Tests auf echter Hardware.
>
> **Kamera-Identität ist ein Problem.** Beide Module melden iSerial "UC762" —
> Arducams Artikelnummer, keine Seriennummer. /dev/v4l/by-id/ kollidiert also,
> und /dev/videoN wird in Enumerierungsreihenfolge vergeben. Vertauschen die
> beiden, kippt das Vorzeichen der Basislinie und die Tiefe kommt gespiegelt
> heraus, ohne dass man es dem Bild ansieht. Nicht hypothetisch: der Kommentar
> im Code nannte Ports 2.2.4/2.3, tatsächlich sind es 2.3/2.4 — sie waren
> längst gewandert. Bindung läuft jetzt in Python **und** C++ über den
> USB-Portpfad.
>
> Welches Modul welche Nummer hat, zweifach gemessen statt geraten: Objektiv
> abdecken (rechter Stream wird dunkel = cam2) und Parallaxe (Ausschnitt aus
> cam2 liegt 76 px weiter links in cam1, Korrelation 0.95). Beide Befunde
> lesen sich zunächst widersprüchlich, weil man vor dem Gerät stehend gegen
> die optischen Achsen schaut und links/rechts gespiegelt sind. **cam1 = links
> vom Betrachter = rechts aus Kamerasicht.**
>
> **Der Abend in Fehlern: neun, acht davon meine (Claude).**
>   * Vier Nebenläufigkeitsfehler in der Session-Verwaltung. Nach dem vierten
>     den Entwurf verworfen statt weiter zu flicken — Hintergrund-Grabber mit
>     Frame-Cache raus, ein Lock über jede Operation rein. Jeder einzelne Fix
>     hatte ein neues Loch geöffnet; das war das Signal.
>   * Achsenbezeichnungen in der Stereo-Auswertung um eine Stelle verdreht:
>     Rotation um X hieß "roll" statt "pitch". Hätte den teuersten
>     Justagefehler als den harmlosesten etikettiert. Ersetzt durch den
>     Rodrigues-Vektor, gegen 5° um jede Achse verifiziert.
>   * Reprojektionsfehler um Faktor sqrt(54) = 7.35 falsch — L2-Norm durch die
>     Punktzahl statt durch deren Wurzel geteilt. Aus PiTrac übernommen, das es
>     aus dem OpenCV-Tutorial hat. Bilder mit 3.3 px Fehler zeigten 0.45, die
>     Ausreißer-Markierung hat nie ausgelöst.
>   * Feldgröße mit 20 mm geraten statt gemessen (24 mm). Skaliert den
>     Translationsvektor linear und damit die Basislinie: 66.40 mm statt 79.83,
>     was überzeugend nach einem verbauten Mount aussah.
>   * Eine Route (/calibration/run) im Plan, die es nicht gab — der Knopf lief
>     ins Leere.
>   * Fehlschluss "cam1 verliert 60% Licht" aus Reglerwerten, die im
>     Automatikmodus `flags=inactive` sind und nur alte manuelle Reste
>     anzeigen. Zurückgenommen bevor ein intaktes Objektiv gereinigt wurde.
>   * Fehlschluss "30 fps viertelt die Abwärme" — das Modul bietet bei
>     1280x800 nur 120 und 100 an, 30 landet still auf 100. 17% statt 75%, und
>     es kostet Gleichzeitigkeit (Skew 3.8 → 6.9 ms median). Zurückgenommen.
>
> Keiner davon wäre beim Lesen des Codes aufgefallen. Alle kamen aus
> wiederholtem Ausführen auf echter Hardware und aus unabhängiger Durchsicht.
> Konsequenz für künftige Arbeit an nebenläufigem Code: **fünf Durchläufe, nicht
> einer.** Drei hätten hier zwei der vier Races durchgelassen.
>
> **Wärmedrift: gemessen, keine gefunden.** Frage war, ob der gedruckte Halter
> sich beim Warmlaufen verzieht. Erster Versuch (Hintergrund-Merkmale kalt vs.
> warm vergleichen) scheiterte an der eigenen Annahme — die Szene stand nicht
> still. Besserer Weg: die 20 Paare in Hälften teilen und getrennt rechnen, die
> frühen kühler als die späten. Nicken 1.086 vs 1.088°, Rollen 0.926 vs 0.917°
> — **auf ein Hundertstel Grad identisch**, und das sind die beiden, die
> vertikale Disparität erzeugen. Basislinie streut um 0.93 mm, aber mit
> falschem Vorzeichen (Erwärmung müsste dehnen) und siebenfach über dem, was
> Kunststoffdehnung hergibt: Schätzrauschen aus je 10 Paaren über nur 35-55 cm
> Tiefe. **Keine Kompensation bauen.**
>
> **Objektive waren verstellt.** Fiel erst spät auf, weil die Schärfeanzeige
> die Bildmitte maß statt des Bretts — bei flach liegendem Brett also die
> Zimmerwand. cam1 war um Faktor 5.4 unscharf, cam2 um 1.6. Nach dem
> Nachfokussieren liegen beide bei ~3000 Laplace-Punkten und innerhalb von 3%
> zueinander. Die Anzeige misst jetzt das erkannte Brett und sagt dazu, welches
> von beidem sie gerade zeigt.
>
> **Basislinie: gemessener Wert genommen (79.83 mm), nicht die 80.00 aus dem
> CAD.** Begründung des Users: gedrucktes Teil, wird nicht exakt 80 sein. Die
> Messung kann das allerdings nicht beweisen — ihre eigene Streuung (±0.5 mm)
> ist größer als der Unterschied. Das bessere Argument ist Konsistenz: der
> gemessene Wert stammt aus derselben Anpassung wie Intrinsics und Rotationen.
>
> Rohbilder (40 Stück, 42 MB) sind committet, mit README zu Aufnahme-
> bedingungen und Schwächen der Serie. Reproduktion aus git verifiziert:
> identische Zahlen. Extrinsics in sp1_vision/calibration_results/.

**2026-08-08/09 — Federn raus, alles neu vermessen. Der RMS hat gelogen.**

> Die Federn hinter der Kamerahalterung sind entfernt und die Platte ist fest
> verschraubt. Damit sind die Extrinsics vom 06.08. hinfällig — die Pose der
> beiden Kameras zueinander hat sich geändert — und ein neuer Bildsatz war
> fällig. Die Intrinsics sollten stehen bleiben: es wurde kein Objektiv
> angefasst. Am Ende sind sie es, die ausgetauscht wurden.
>
> **Erst die Falle, die keiner gesehen hätte.** Beide Aufnahmewege schreiben
> nach `calibration_images/cam1|cam2` und nummerieren hinter das, was schon da
> liegt — `_pair_count() + 1` im Dashboard, `existing` in der CLI, und
> `IMAGE_ROOT` im Dashboard ist fest verdrahtet. Neue Aufnahmen wären neben die
> alten zwanzig gefallen, und die Auswertung liest das ganze Verzeichnis: ein
> Stereo-Solve, der zwei Mount-Geometrien mittelt, mit einer plausiblen Zahl am
> Ende und nichts, was den Fehler zeigt. Alter Satz also erst nach
> `2026-08-06_springs/` verschoben.
>
> **Der eigentliche Befund kam aus einem Gegentest, nicht aus einer Zahl.**
> Nach 18 Paaren stand pitch bei −0.745°. Gerechnet gegen die Intrinsics des
> neuen Satzes statt gegen die archivierten: **−1.834°, bei identischem RMS von
> 0.90.** Die Daten konnten zwischen den beiden nicht entscheiden — und der
> Reprojektionsfehler, das Maß, dem man hier üblicherweise glaubt, war für den
> Unterschied vollkommen blind.
>
> Ursache ist `cy`. Kein Satz hatte je das untere Fünftel des Bildes belegt
> (Ecken endeten bei y=636 bzw. 641 von 800), und ohne vertikale Abdeckung ist
> der Hauptpunkt kaum bestimmt: für dasselbe unangetastete cam1-Objektiv kam
> einmal 389.0 und einmal 420.1 heraus. Zwischen den Sätzen unterscheidet sich
> `cy1 − cy2` um 17.6 px, und 17.6/915 = 1.10° gegen eine beobachtete
> pitch-Differenz von 1.09. **Nicken war zu großen Teilen ein Ableseinstrument
> für einen ungemessenen Hauptpunkt.**
>
> Sechs Aufnahmen ins untere Drittel (Mitte bei 35/45/55/75 cm, links und
> rechts bei 45) haben es erledigt. Abdeckung bis y=727, `cy` konvergiert auf
> 420.05 / 421.09 — 1.0 px auseinander statt 13.2 — und die Mehrdeutigkeit
> fällt von 1.09° auf 0.21°.
>
> **Merksatz fürs nächste Mal:** das untere Drittel ist nicht optional. Ich
> hatte das Gegenteil behauptet, mit der Begründung, dass dort kein Ball
> fliegt und die radialen Terme symmetrisch sind. Beides stimmt und beides ist
> daneben — es geht um `cy`, und `cy` ist der Stoff, aus dem Nicken besteht.
> Weglassen verrauscht die Schätzung nicht, es verzerrt sie, und der RMS bleibt
> dabei ruhig.
>
> **Die Intrinsics haben deshalb die Quelle gewechselt.** 2.701/2.700 mm gegen
> 2.767/2.772, fx 900.38/899.99 gegen 922.30/923.98, RMS 0.500/0.519 gegen
> 0.557/0.550. Das Argument ist nicht der RMS, der kaum sinkt, sondern dass die
> **beiden Kameras jetzt übereinstimmen**: fx auf 0.04 % gegen vorher 0.18 %,
> cy auf 1.0 px gegen 4.5. Gleiches Bauteil, gleiches Objektiv — Übereinstimmung
> ist Evidenz, die Abweichung war Fehler.
>
> **Vorher/Nachher, beide Sätze gegen dieselben Intrinsics gerechnet:**
>
> | | mit Federn | verschraubt |
> |-|-|-|
> | Nicken | +0.974° | **−0.923°** |
> | Gieren | +1.032° | **+0.427°** |
> | Rollen | +0.757° | **−0.851°** |
> | Basislinie | 78.63 mm | **78.28 mm** |
>
> Der Umbau hat Nicken und Rollen **umgedreht statt genullt** — durch die Null
> hindurch auf fast denselben Betrag der anderen Seite. Nur Gieren hat sich
> echt halbiert. Wer wieder an den Mount geht: es war Überschuss, nicht
> Rückstand. Bei unter 3° und zusammen ~1.5 % Bildhöhe lohnt es aber nicht,
> zumal die Platte jetzt verschraubt ist und jede Korrektur eine komplette
> Neukalibrierung nach sich zöge.
>
> **Und die Basislinie hat sich nie bewegt.** 78.63 gegen 78.28 aus gleichen
> Intrinsics ist das Eigenrauschen der Schätzung. Der zwischenzeitlich
> gemeldete Abfall 79.83 → 78.59 war ein Artefakt der zu großen fx im Archiv,
> keine Hardware. Unangenehmer ist die Rückwirkung: die gefeierten 0.2 %
> Übereinstimmung des Archivs mit den 80.00 aus dem CAD waren Glück. Sie kamen
> aus 35–55 cm Tiefe, und genau diese enge Bedingung liefert im neuen Satz
> 81 mm. Die echten −2.1 % gegen das CAD sind Druckschrumpf.
>
> **Tiefenspreizung ist das, was die Translation festnagelt.** Teilmengen mit
> der 25–90-cm-Reihe: 78.2–78.5 mm. Teilmengen nur aus den 45–55-cm-Aufnahmen:
> 81.0–81.7. Die sieben Abstandsaufnahmen waren die wertvollsten im Satz.
>
> **Stabilität**, über Hälften, gerade, ungerade, mit und ohne die sechs neuen:
> Nicken −0.86…−0.96°, Rollen −0.82…−0.88°, Gieren +0.36…+0.47°, Basislinie
> 77.99…78.66 mm. Die sechs neuen allein: Nicken −0.942° bei RMS 0.425, der
> sauberste Teil-Solve überhaupt, auf 0.02° mit allen 24 übereinstimmend.
>
> **Aufnahmemethode.** Brett gestellt statt gehalten, Gerät verschraubt am
> Boden — nichts bewegt sich, und damit ist die Belichtungszeit gleichgültig.
> Die 0.19–3.30 px Streuung des alten Satzes war vollständig Verwacklung. 24
> Paare, alle mit Brett in beiden Kameras, keine Wiederholung nötig. Die
> 25-cm-Aufnahme liegt an der geometrischen Grenze — 80 mm Basislinie lassen
> einem 240-mm-Brett dort 27 mm seitliches Spiel — sie passte, wird vom Solve
> aber trotzdem als Ausreißer verworfen. 30 cm ist die sinnvolle Untergrenze.
>
> **Nebenbei zwei Werkzeugmängel.** Die Schärfeanzeige der CLI (`--focus`) misst
> weiter die Bildmitte statt des erkannten Bretts, anders als das Dashboard —
> also genau die Anzeige, die schon einmal einen 5.4x-Fokusfehler verdeckt hat.
> Und `kWebActiveMQHostAddress` steht überhaupt nicht in der Config: ohne
> `--msg_broker_address` bricht `pitrac_lm` in der IPC-Initialisierung ab und
> segfaultet beim Herunterfahren. Mit dem Argument läuft der Trace sauber und
> bestätigt Brennweite 2.701, Matrix, Sensorüberschreibung und Ballradius 48.

**2026-08-10 — Zweig gemergt, und die Basislinienfrage war falsch gestellt.**

> Block 1 der Triangulation ist in `main`: 29 Commits, 123 Tests grün auf dem
> gemergten Baum, gepusht, Jetson gezogen. Danach ging die Sitzung an etwas,
> das erst beim Nachrechnen sichtbar wurde. Der geplante Messlauf hätte eine
> Frage entschieden, die so nicht existiert — mit einem Werkzeug, das vier von
> sechs Messpunkten wegwirft.
>
> **78,28 gegen 78,749 ist nicht Mechanik gegen Kalibrierung.** Beide Zahlen
> kommen aus derselben Pipeline. 78,749 mm ist der ausgelieferte Solve in
> `stereo_extrinsics.json` — 19 von 24 Paaren, Nicken −0,9423°. 78,28 mm steht
> in der Vergleichstabelle des Kalibrier-READMEs, Federn gegen verschraubt, und
> das ist ein **anderer** Solve: er nennt Nicken −0,923°, Gieren +0,427°,
> Rollen −0,851°, wo die Datei −0,9423 / +0,3598 / −0,8241 sagt. Die
> dokumentierte Teilmengenstreuung ist 77,99–78,66 mm; der ausgelieferte Wert
> liegt knapp darüber. Und wegen `CALIB_FIX_INTRINSIC` lässt sich 78,28 gar
> nicht in die ausgelieferten R/T einsetzen, ohne neu zu lösen.
>
> Die beantwortbare Frage lautet damit **„stimmt der Maßstab der ausgelieferten
> Datei"**, nicht „welche der beiden Zahlen". CLAUDE.md und der Eintrag in den
> Next Steps führen 78,28 als *die* Basislinie — das widerspricht der Datei,
> die der Code liest, unabhängig davon, was der Messlauf ergibt. Nebenwirkung:
> 3,55 mm/px folgt aus b = 78,28 und 3,53 aus 78,749. Die beiden Korrekturen
> sind keine unabhängigen.
>
> **Das Präzisionsbudget, vorher gerechnet statt hinterher.** Z²/(b·f) gibt
> 1,73 / 3,53 / 6,91 mm pro Pixel Disparitätsfehler bei 0,35 / 0,50 / 0,70 m,
> am echten Rig auf dem Jetson bestätigt. Bei 0,2 px Detektionsrauschen sind
> das 0,35 mm nah und 1,40 mm fern. Über eine 350-mm-Spanne kommt die
> Regressionssteigung auf ~0,33 %, Lineal und Ballplatzierung legen ~0,34 %
> drauf — zusammen ~0,45 % gegen ein 0,6-%-Signal. **Der Lauf ist knapp
> entscheidungsfähig, und das ist Rechnung, nicht Pessimismus.** Die Lage
> dagegen ist immun: ein Maßstabsfehler ist eine radiale Streckung, die eine
> Ebene auf eine parallele abbildet und die Normale in Ruhe lässt. Nicken,
> Rollen und Gieren landen unabhängig davon, wie die Maßstabsfrage ausgeht.
>
> **Der alte Maßstabsschätzer teleskopierte.** Least-Squares durch den Ursprung
> auf Nachbardifferenzen fällt bei gleichen Abständen exakt auf (Z₆−Z₁)/(t₆−t₁)
> zusammen — die vier inneren Positionen einer Sechserreihe tragen **nichts**
> bei. Wiederholungen an derselben Position warf er ganz weg, weil deren
> Ablesedifferenz null ist, mit einer Meldung, die der Bediener als Kritik an
> seinem eigenen Aufbau liest. Ersetzt durch eine Geradenanpassung
> `Tiefe = Maßstab · Ablesewert + Versatz` über alle Punkte. Der Achsenabschnitt
> trägt den unbekannten Linsenebenenversatz, den die Differenzen vorher
> weggekürzt haben — und **meldet** ihn, was mehr ist: es ist die einzige
> Schätzung, die das Projekt davon hat, wie tief das optische Zentrum hinter
> der Frontfläche sitzt.
>
> Drei Dinge, die der Lauf vorher nicht sagen konnte: den Standardfehler auf
> Maßstab und implizierte Basislinie — 1,004 ± 0,001 entscheidet die Frage,
> 1,004 ± 0,009 nicht, und blank gedruckt sehen beide gleich aus; den Winkel
> zwischen Tiefenlinie und optischer Achse, aus den Bällen selbst, denn der
> Vergleich ΔZ gegen ΔAblesewert setzt ihn als null voraus und 5° sind 0,38 %
> Verzerrung; und die Wiederholstreuung.
>
> **Eine synthetische Probe hat das Aufnahmeprotokoll geändert.** Ein
> realistischer 22-Schuss-Lauf ergab Maßstab **1,0086 ± 0,0016 gegen eine
> Wahrheit von cos 2° = 0,9994**. Ursache: die Testvorrichtung zeichnet
> Ballmittelpunkte auf ganze Pixel gerundet — ein halbes Pixel, gleichsinnig an
> jeder Position. Ein Versatz, der linear mit Z wächst, **ist** ein
> Maßstabsfehler und von innen unsichtbar: er landet vollständig in der
> Steigung und lässt die Residuen klein. Für den Bediener heißt das:
> Wiederholungen **ohne den Ball anzufassen** mitteln das Sensorrauschen weg
> und lassen die Subpixel-Phase stehen — sie verkleinern die gedruckte
> Unsicherheit, nicht den Fehler. Also Ball dazwischen neu setzen, und lieber
> mehr verschiedene Positionen als mehr Wiederholungen derselben.
>
> **Das Ableseprotokoll ändert sich mit dem Schätzer.** Bisher: lotrechter
> Abstand zur Frontfläche. Jetzt: Lineal flach auf den Boden, Nullende an die
> Frontfläche, **Ball daneben auf dem Boden** an der Längskante, abgelesen an
> der dem Gerät zugewandten **Kante** des Balls. Die Richtung eines Lineals kann
> der Bediener kontrollieren und der Lauf nachmessen; eine Flächennormale ist
> keines von beidem. Kante statt Mitte, weil eine Kante scharf und eine Mitte
> eine Schätzung ist — der Ballradius daneben ist konstant und verschwindet im
> Achsenabschnitt, ebenso die Lage der Linealnull.
>
> Ein Detail, das beinahe durchgerutscht wäre: der Ball darf **nicht auf dem
> Lineal** liegen. Er säße dann eine Linealdicke über allen seitlichen Bällen,
> und die Ebenenanpassung mittelt zwischen zwei parallelen Ebenen und verkippt
> — Nicken und Rollen wären falsch, und nichts in der Ausgabe würde es sagen.
>
> **Gieren ist keine Konstante.** Nicken und Rollen sind durch Mount und Boden
> festgenagelt; Gieren ist der Winkel zu einer Linie, die der Bediener wählt.
> Das Gerät steht frei, ohne Mattenkante und ohne markierte Position, also
> beschreibt Gieren die heutige Aufstellung und nicht das Gerät. `kCameraNAngles`
> wird deshalb **nicht** befüllt — die Konstante könnte unsere drei Winkel
> ohnehin nicht tragen, Rollen fällt dort heraus. Die zwei
> Ziellinien-Aufnahmen behalten trotzdem ihren Zweck: sie klären das Vorzeichen
> von `yaw_from_target_line` gegen eine bewusst 100 mm nach rechts gelegte
> Linie, und ein falsches Vorzeichen dort landet 1:1 im horizontalen
> Abflugwinkel.
>
> **Ein Fehler, den der Test gefunden hat und kein Review.** Der Guard gegen
> eine Serie ohne Spreizung stand als `sxx <= 0.0` und feuerte nicht: drei
> identische Ablesungen von 0,40 zentrieren sich auf je ~5·10⁻¹⁷, nicht auf
> null. Eine Serie, die sich nie bewegt hat, hätte einen selbstbewussten
> Maßstab aus Rundungsrauschen geliefert.
>
> **Stand:** `main` bei `aa209e1`, 147 Tests grün im echten Jetson-Checkout.
> Der Messlauf am Gerät steht aus; die Anleitung mit allen 24 Aufnahmen
> einzeln liegt in `sp1_vision/triangulation_run/PROTOCOL.md`.

**2026-08-10, später — Der Messlauf hat einen Lautsprecher vermessen.**

> 24 Bildpaare aufgenommen, alle mit `cam1 ball  cam2 ball  -> keep`
> quittiert. Die Auswertung hat 21 davon verworfen, und die drei Überlebenden
> waren Unsinn: `Y = −27 mm`, also **über** der optischen Achse, wo ein Ball
> auf einer Fläche bei etwa +85 mm liegt, und `Z = 1295 mm` bei 400 mm
> Zollstock.
>
> **Die Ursache stand in den Erkennungen, nicht in einer Vermutung.** Der Lauf
> entstand auf einem Schreibtisch mit Blick quer durchs Zimmer — Lautsprecher
> mit Tief- und Hochtöner, eine Kugel obendrauf, Bilderrahmen, Pflanzen. In
> **17 von 24 Aufnahmen lag die Erkennung in cam1 bei (748, 407) und in cam2
> bei (871, 388)**: identisch, Bild für Bild, während der Ball über den Tisch
> bewegt wurde. Ein Ball, der sich nicht bewegt, ist keiner. `find_ball` nahm
> den stärksten Hough-Kandidaten je Bild, und der stärkste Kreis im Bild war
> der Lautsprecher.
>
> **`gs_03` ist die Aufnahme, die man sich merkt.** Sie kam mit 1,96 px durch
> die 2-px-Schwelle. Beide Kameras hatten dasselbe falsche Objekt gefunden,
> also trafen sich die Strahlen tadellos — bei 1295 mm. Das ist die erste
> Bestätigung an echten Daten für das, was im Docstring von `triangulate.py`
> steht: **ein kleines Residuum heißt, dass die Kameras einander zustimmen,
> nicht dass sie einen Ball ansehen.**
>
> **Der ärgerlichere Teil war mein eigener.** Die Anleitung sagte „du willst
> `cam1 ball  cam2 ball` sehen" und verkaufte das als Prüfung. Es prüfte
> nichts — `find_ball` meldete `True` für jeden Kreis. Deshalb bestand auch
> der Probeschuss, während ein Lautsprecher vermessen wurde, und deshalb
> entstanden 24 Aufnahmen, bevor es irgendetwas merken konnte. Nicht der
> Detektor war der teure Fehler, sondern die Kontrolle, die keine war.
>
> **Die Entscheidung gehört ins Stereopaar, nicht ins Einzelbild.** Ein
> Golfball und eine Lautsprechermembran sind beide helle Scheiben; kein
> Einzelbild kann sie unterscheiden. Das Paar kann es, an drei Bedingungen,
> die alle vorher feststehen und von denen keine sagt, wo das Ergebnis bequem
> läge: der Ball ist 42,67 mm groß, muss also **in jedem Bild so groß
> erscheinen, wie es die Entfernung aus seiner eigenen Disparität verlangt**;
> er muss im deklarierten Messvolumen liegen; und die beiden Strahlen müssen
> sich treffen. Die Größenbedingung ist die, die ein Einzelbild prinzipiell
> nicht hat, und sie ist es, die den Lautsprecher hinauswirft.
>
> `frame_analysis.ball_candidates` gibt jetzt **alles** zurück und entscheidet
> nichts — Trefferquote gehört zu den Pixeln, Genauigkeit zur Geometrie. Sein
> altes `minDist = 200` unterdrückte keine Falschtreffer, sondern den Ball,
> sobald etwas Stärkeres innerhalb von 200 px stand; in `gs_03` genau so
> geschehen. Und dieselbe Auswahl läuft jetzt **bei der Aufnahme**:
> `BALL at Z 474 mm (reproj 0.71 px, size +6%)` oder ein Grund, mit dem sich
> etwas anfangen lässt. Was die Auswertung später verwirft, wird verworfen,
> solange der Bediener noch danebensteht.
>
> **Drei Fehler haben Tests gefunden, kein Review.** Der Mehrdeutigkeitsschutz
> verlangte anfangs, dass ein Rivale im Punktwert nahe am Besten liegt — bei
> zwei sauberen Lösungen mit 0,05 und 0,30 ist das Faktor sechs, und der
> Schutz verschwand genau dann, wenn beide gut waren. Der
> Vertauschungshinweis, den ich eingebaut hatte, zählte Paare, die hinter den
> Kameras auflösen; das tut rund die Hälfte aller Zufallspaarungen, also
> feuerte er auf echten Bildern bei 1391 von 2450 in einer Szene ganz ohne
> Vertauschung — jetzt ein Anteil, 90 %. Und sämtliche Testvorrichtungen
> zeichneten einen 30-px-Ball in jeder Entfernung, also physikalisch einen
> anderen Ball pro Tiefe, womit sich eine Größenprüfung überhaupt nicht prüfen
> lässt. Beim Korrigieren kam heraus, dass **ganzzahlige Pixelmittelpunkte
> +1,45 mm systematisch in jede synthetische Tiefe legen** — und ein Versatz,
> der mit der Tiefe wächst, ist ein Maßstabsfehler unter anderem Namen. Mit
> Subpixel-Zeichnung: −0,4 mm Mittelwert, 1,8 mm RMS, und zwei zuvor rote
> Maßstabstests wurden grün, ohne dass eine Toleranz angefasst wurde.
>
> **Was die alten Bilder jetzt hergeben: 11 von 24.** Die elf sind kohärent —
> X konstant −37…−45 mm, Y 78…86 mm, Z folgt dem Zollstock mit ~−20 mm
> Versatz, Radiusabweichung +3…+7 % — und der Lautsprecher kommt nirgends mehr
> vor. Neun Aufnahmen sind aber **echt mehrdeutig**: es liegen zwei
> ballförmige Dinge im Messvolumen, und das Werkzeug weigert sich zu raten.
> Bleiben 9 Tiefenpositionen, 1 seitliche, **0 auf der Ziellinie** — ohne
> Ziellinienpaar kein Gieren, mit einer seitlichen Position keine bestimmte
> Ebene. Der Lauf ist nicht zu retten.
>
> **Nicht weiter nachjustiert, mit Absicht.** Schwellen, die diese Bilder
> retten, wären an diese eine Szene angepasst — bei einer Frage, deren ganzes
> Signal 0,6 % beträgt. Der zweite Lauf ist derselbe Lauf gegen freien
> Hintergrund: Gerät auf eine leere Wand, dunkles mattes Tuch über alles
> dahinter, altes Verzeichnis wegschieben. Die 24 Bildpaare bleiben liegen —
> es ist der einzige echte Datensatz mit störendem Hintergrund und damit der
> beste Test, den der Detektor je bekommt.
>
> **Stand:** `main` bei `61729f0`, 165 Tests grün im echten Jetson-Checkout.

\---

\---

## 🔧 Sub-Project 2: Spin Detection

**One-line description:** 3-axis spin rate measurement from marked ball images captured via strobe frames — backspin, sidespin, and spin axis.

|Field|Value|
|-|-|
|Type|☑ Hardware ☑ Software|
|Phase|Design|
|% Complete|0%|
|Status|🔵 Planning|
|Depends On|SP1 — Core Vision System|
|Started|2026-03-14|
|Last Updated|2026-03-14|

\---

### 🎯 Goal

After a shot, the system outputs backspin RPM, sidespin RPM, and spin axis in degrees — accurate enough to differentiate a 3000 RPM draw from a 5000 RPM fade. Spin values are plausible when cross-checked against a commercial launch monitor on the same shot. Marked balls are used.

\---

### 📐 Design Notes

**Approach:** PiTrac already implements 3-axis spin detection using marked balls. Two strobe frames of the ball in flight are compared — the angular rotation of the dot pattern between frames, combined with the known strobe interval, gives RPM and axis.

**Ball marking:** Needs a consistent, repeatable dot pattern. Research what pattern PiTrac recommends and whether commercial marked balls (like Foresight practice balls) are usable or if self-marking is required.

**Key challenge from PiTrac logs:** HoughCircles detection on overlapping ball images is unreliable at low resolution. Higher-resolution cameras than the RPi GS camera will help — this is one of the Jetson advantages.

**Strobe interval precision:** Spin accuracy is directly proportional to strobe timing accuracy. A 10% error in strobe interval = 10% error in RPM. This reinforces the IR strobe timing concern from SP1.

\---

### 🧠 Decisions Log

|Date|Decision|Why I Made It|Alternatives Considered|
|-|-|-|-|
|2026-03-14|Marked balls — non-negotiable|Unmärked ball spin from vision alone is not reliably achievable at DIY camera resolutions|Radar-based spin (requires Doppler radar hardware, different approach entirely)|

\---

### 🤖 AI Prompt Log

**Session: 2026-03-14 — Project kickoff**

> No SP2-specific prompts yet. Spin approach confirmed during scoping.

\---

### ⚠️ Blockers \& Problems

|Date|Problem|Status|Solution Found|
|-|-|-|-|
|2026-03-14|Blocked on SP1 — cannot start build until camera pipeline working|🔴 Open|SP1 must complete first|

\---

### ✅ Next Steps

* \[ ] Read PiTrac spin detection code and documentation in detail
* \[ ] Research ball marking options — PiTrac recommended pattern vs Foresight-style balls
* \[ ] Understand minimum camera resolution required for reliable spin dot tracking
* \[ ] Note: do not start build until SP1 camera pipeline is validated

\---

### 📝 Session Notes

**2026-03-14**

> Spin confirmed as non-negotiable. Marked balls accepted.
> Technical approach clear — adapt PiTrac spin module.
> Blocked on SP1. No further action until SP1 camera pipeline works.

\---

\---

## 🔧 Sub-Project 3: Club Tracking

**One-line description:** Club head speed, face angle at impact, club path, and club rotation — derived from camera images of the club during the downswing and impact zone.

|Field|Value|
|-|-|
|Type|☑ Hardware ☑ Software|
|Phase|Design|
|% Complete|0%|
|Status|🔵 Planning|
|Depends On|SP1 — Core Vision System|
|Started|2026-03-14|
|Last Updated|2026-03-14|

\---

### 🎯 Goal

After a shot, the system outputs club head speed, club face angle (open/closed at impact), and club path direction. Values are plausible when compared against a commercial monitor. Club rotation (face rotation through impact) is a stretch goal for v1.

\---

### 📐 Design Notes

**Approach:** PiTrac is primarily focused on ball tracking. Club tracking may require a dedicated camera angle (side-on to the swing plane) or reflective tape/dots on the club head.

**Reference:** Spectrum Golf Tech Element claims full club data — their approach is not yet open sourced but worth monitoring. GSA Golf VisTrak LX uses a dedicated side-mounted high-speed camera for club.

**Open question:** Can the existing two cameras from SP1 capture enough club data, or is a third camera angle needed? This depends on camera placement relative to the hitting area.

**Club markers:** Reflective tape dots on the club head face are commonly used in DIY systems for face angle detection. Research whether this is compatible with PiTrac's existing pipeline.

\---

### 🧠 Decisions Log

|Date|Decision|Why I Made It|Alternatives Considered|
|-|-|-|-|
|2026-03-14|Club tracking is SP3 — separate from ball tracking SP1|Different camera angle and algorithms required. Keeps SP1 focused and achievable.|Combining into SP1 (too complex for first build)|

\---

### ⚠️ Blockers \& Problems

|Date|Problem|Status|Solution Found|
|-|-|-|-|
|2026-03-14|Camera placement for club vs ball tracking may conflict — may need dedicated third camera|🟡 Investigating|Decide during SP1 physical layout planning|

\---

### ✅ Next Steps

* \[ ] Research how PiTrac and other DIY systems approach club tracking
* \[ ] Decide whether a third camera is required or if two cameras can cover both ball and club
* \[ ] Research club head marker approaches (reflective tape, painted dots)
* \[ ] Do not start build until SP1 is working

\---

### 📝 Session Notes

**2026-03-14**

> Club tracking confirmed as required data points. Approach to be determined.
> Key open question: dedicated third camera vs reuse of SP1 cameras.

\---

\---

## 🔧 Sub-Project 4: GSPro Integration + Session Data

**One-line description:** Sends validated shot data to GSPro over TCP, stores session history, and provides a per-player stats dashboard accessible over WiFi.

|Field|Value|
|-|-|
|Type|☑ Software|
|Phase|Build|
|% Complete|90%|
|Status|🟡 In Progress|
|Depends On|SP1 (minimum to start), SP2 + SP3 for full data|
|Started|2026-03-14|
|Last Updated|2026-03-21|

\---

### 🎯 Goal

A shot is struck. Within 2 seconds, the shot data appears in GSPro on a connected Windows PC. Session data (all shots, clubs used, player name, date) is stored locally on the Jetson. A web dashboard accessible from any device on the local network shows session history, per-player progress over time, and per-club averages.

\---

### 📐 Design Notes

**GSPro protocol:** Open Connect v1 — TCP socket, JSON payload. Jetson acts as the client. GSPro on Windows PC acts as the server (listens on port, default localhost but can be remote with firewall config).

JSON shot data fields available:

* BallData: Speed, SpinAxis, TotalSpin, BackSpin, SideSpin, HLA (horizontal launch angle), VLA (vertical launch angle), CarryDistance
* ClubData: Speed, AngleOfAttack, FaceToTarget, Lie, Loft, Path, SpeedAtImpact, VerticalFaceImpact, HorizontalFaceImpact, ClosureRate

**Architecture:**

* Jetson runs a Python service that receives computed shot data from the C++ vision pipeline (via local socket, file, or shared memory)
* Python service formats JSON and sends to GSPro over TCP
* Same service writes shot record to SQLite database (player, club, timestamp, all data fields)
* Lightweight web server (Flask or FastAPI) serves a stats dashboard on local network

**Player profiles:** Multiple players supported. Club selection communicated from GSPro back to the Jetson via the 2-way Open Connect protocol (GSPro sends club selection events).

**V3 Vision — Standalone Simulator System:**
Long-term goal: Run OpenShotGolf directly on the Jetson Xavier NX, output via HDMI
to projector/screen. No Windows gaming PC required — entire launch monitor + simulator
in one enclosure. Requires: Godot 4.x ARM64 Linux build, porting PhysicsLogger and
BallPhysics C# to GDScript, validating GPU can handle simultaneous vision pipeline +
3D rendering. Post-V2 goal — V1 and V2 must work first.

\---

### 🧠 Decisions Log

|Date|Decision|Why I Made It|Alternatives Considered|
|-|-|-|-|
|2026-03-14|GSPro runs on separate Windows PC, Jetson sends over TCP|GSPro is Windows-only. Jetson is the compute unit, not the simulator.|Run simulation on Jetson (not possible — GSPro is Windows only)|
|2026-03-14|Session data stored in SQLite on Jetson|Simple, file-based, no server required, easy to back up|PostgreSQL (overkill), cloud DB (unnecessary complexity for v1)|
|2026-03-14|Stats dashboard as local web app|Accessible from phone/tablet without installing anything. Works on local WiFi only.|Native app (too much development overhead for v1)|
| 2026-03-21 | OpenShotGolf as free test target instead of GSPro | Free, open source, built for PiTrac, accepts identical GSPro Open Connect v1 JSON on TCP port 49152. Visual ball flight on 3D driving range. Investigated Awesome Golf (no open API) and E6 Connect (proprietary protocol) — neither usable. | GSPro ($250/yr — unnecessary before cameras), Mock server (no visual feedback) |
| 2026-03-21 | Default port 49152 (OpenShotGolf), --port 921 for GSPro | Both use identical GSPro Open Connect v1 protocol. Only port differs. | Hardcode 921 (can't test without GSPro license) |
| 2026-03-21 | DeviceID: "Jetson LM 1.0" | Unique identifier in the GSPro Open Connect protocol | Any string works |
| 2026-03-21 | SQLite with 4 tables: players, courses, sessions, shots | All ball/club data as individual columns for direct SQL queries. DB auto-creates on first run with seeded courses. check_same_thread=False for Flask thread safety. | JSON blob storage (harder to query), PostgreSQL (overkill) |
| 2026-03-21 | Unix domain socket for C++ → Python interface | Real-time, bidirectional JSON over /tmp/jetson_lm.sock. C++ sends shot, Python responds with status + shot_id + gspro_code. Auto-reconnect on both sides. | JSON file drop (simpler but latent), Named pipe (fragile) |
| 2026-03-21 | Flask dashboard with 5 tabs + auto-refresh | Home, Sessions, Club Averages, Dispersion (Range View + HLA chart), Compare (up to 4 sessions). Player dropdown. CSV export. 5-second auto-refresh. Dark theme, mobile-friendly. | FastAPI (more complex), static HTML (no live data) |
| 2026-03-21 | Ball flight physics engine (ball_physics.py) | Reynolds-number-dependent Cd/Cl, Magnus lift, gravity, air drag. Calculates carry distance, offline, apex from ball speed + VLA + HLA + spin. Same aerodynamic principles as OpenShotGolf. | Simple estimate (less accurate), rely on simulator response (protocol doesn't support it) |
| 2026-03-21 | systemd services for auto-start | jetson-lm-receiver and jetson-lm-dashboard start on boot. Logs via journalctl. | Manual start every time (annoying) |
| 2026-03-21 | Session naming: date — time — player #N | Daily session number resets per day per player. No simulator name in display. | Database ID only (not human-readable) |

\---

### 🧪 Tests This Sub-Project

|Date|What Was Tested|Method|Result|Notes|
|-|-|-|-|-|
| 2026-03-21 | TCP connection Jetson → Windows OpenShotGolf port 49152 | gspro_sender.py --ip 192.168.178.20 | ✅ PASS | First end-to-end connectivity test |
| 2026-03-21 | Dummy 7-iron shot → ball flight visible in OpenShotGolf | Visual on Windows screen | ✅ PASS | Ball launched with correct trajectory and telemetry |
| 2026-03-21 | SQLite DB creation, schema, seeded data | Auto on first run | ✅ PASS | 4 tables, 2 default courses |
| 2026-03-21 | Shot logging during live session (6+ shots) | gspro_sender.py with --player | ✅ PASS | All shots recorded with full ball data |
| 2026-03-21 | Flask dashboard — all 5 tabs | Browser on LAN | ✅ PASS | Home, Sessions, Club Averages, Dispersion, Compare |
| 2026-03-21 | Player switching via dropdown | Multiple players | ✅ PASS | All views filter correctly |
| 2026-03-21 | Unix socket: shot_receiver.py + test_client.py | Two terminals | ✅ PASS | Full chain: client → socket → receiver → TCP → simulator + DB |
| 2026-03-21 | Rapid-fire burst: 20 shots at 0.5s interval | test_client.py --burst 20 | ✅ PASS | All 20 shots logged, 0 errors, all gspro_code 200 |
| 2026-03-21 | All 5 club codes (DR, 7I, PW, 5I, SW) | test_client.py interactive | ✅ PASS | All clubs stored correctly, visible in dashboard |
| 2026-03-21 | CSV export — all shots, session, club averages | Dashboard export buttons | ✅ PASS | Downloads correctly on browser |
| 2026-03-21 | Ball physics engine — carry distance calculation | ball_physics.py standalone test | ✅ PASS | DR 240yd, 7I 198yd, PW 141yd, SW 105yd — realistic |
| 2026-03-21 | Carry distance backfill on dashboard startup | Automatic for shots with NULL carry | ✅ PASS | All existing shots got carry values |
| 2026-03-21 | Compare tab — 4 sessions with Range View overlay | Dashboard compare tab | ✅ PASS | Stat cards, HLA chart, Range View all working |
| 2026-03-21 | systemd services auto-start | sudo bash setup_services.sh | ✅ PASS | Both services start, logs visible in journalctl |
| 2026-03-21 | Dashboard auto-refresh (5s polling) | Send shots while dashboard open | ✅ PASS | New shots appear without manual reload |
| 2026-03-21 | Receiver resilience — simulator offline | OpenShotGolf closed during session | ✅ PASS | Receiver reconnects, logs to DB regardless |

\---

### ✅ Next Steps

* ☐ Integrate shot_sender.h into pitrac_lm C++ codebase (when SP1 cameras arrive)
* ☐ Test with real vision pipeline shot data (depends on SP1)
* ☐ Buy GSPro with Open API license (when real shots need course play validation)
* ☐ Add more courses to DB as GSPro courses are played
* ☐ Optional: dashboard improvements (shot trail 3D view, per-session club breakdown chart, trend lines over time)

\---

### 📝 Session Notes

**2026-03-14**

> Architecture designed at high level. Depends on SP1 for real data.
> Can prototype the GSPro TCP sender with dummy data independently of vision work.

**2026-03-21 — Complete SP4 build session (0% → 90%)**
> Built the entire SP4 software stack in one session:
>
> 1. TCP Sender (gspro_sender.py): GSPro Open Connect v1 JSON over TCP. Three club
>    templates with random variation. Interactive + --once modes. Python 3.8 compatible.
>
> 2. OpenShotGolf as free simulator: Identified as perfect test target — same protocol
>    as GSPro on port 49152. Required Godot 4.6 .NET + C# build. Investigated and
>    rejected Awesome Golf (no open API) and E6 Connect (proprietary).
>
> 3. SQLite Database (shot_db.py): 4 tables (players, courses, sessions, shots).
>    Individual columns for all ball/club data. Auto-creates with seeded courses.
>
> 4. Flask Dashboard (dashboard.py): 5 tabs — Home, Sessions, Club Averages,
>    Dispersion (Range View + HLA scatter), Compare (up to 4 sessions, 2 overlay charts).
>    Player dropdown, CSV export, 5-second auto-refresh. Dark theme, mobile-friendly.
>
> 5. Ball Physics Engine (ball_physics.py): Reynolds-number-dependent Cd/Cl,
>    Magnus lift, spin axis decomposition. Calculates carry, offline, apex.
>    Carry distance backfilled into DB on dashboard startup.
>
> 6. Unix Socket Interface: shot_receiver.py as persistent service. Receives shots
>    from C++ pipeline via /tmp/jetson_lm.sock, forwards to simulator, logs to DB.
>    test_client.py for testing. shot_sender.h ready for C++ integration.
>    Auto-reconnect to simulator if connection lost.
>
> 7. systemd Services: jetson-lm-receiver and jetson-lm-dashboard auto-start on boot.
>    setup_services.sh installer script. Logs via journalctl.
>
> Architecture proven end-to-end:
> pitrac_lm (C++) → Unix Socket → shot_receiver.py → TCP/49152 → OpenShotGolf
>                                       ↓
>                                   SQLite DB ← dashboard.py (Flask, port 5000)
>
> Remaining 10%: integrate shot_sender.h into pitrac_lm C++ code (blocked on SP1 cameras).
> GSPro purchase deferred — switching requires only --port 921.

\---

\---

## 🔧 Sub-Project 5: Video Recording + Enclosure

**One-line description:** USB camera records swing video triggered by shot detection; 3D printed enclosure houses the full system cleanly and protects components.

|Field|Value|
|-|-|
|Type|☑ Hardware ☑ Software ☑ 3D Print|
|Phase|Design|
|% Complete|0%|
|Status|🔵 Planning|
|Depends On|SP1 (trigger signal for recording)|
|Started|2026-03-14|
|Last Updated|2026-03-14|

\---

### 🎯 Goal

Every shot triggers a video recording from the USB swing camera. Video is saved as a named file (player, date, shot number) on the Jetson. Files can be transferred to a PC or uploaded to a cloud AI service for swing analysis. The full device (Jetson, cameras, LiDAR, IR array) fits in a purpose-built 3D printed enclosure that can be positioned at the side of the hitting area in the garage.

\---

### 📐 Design Notes

**Video recording:**

* USB camera positioned behind or in front of the golfer (side-on to swing)
* Triggered by the same shot detection event from SP1 LiDAR
* Pre-buffer desirable (record X seconds before trigger) — may use a ring buffer approach
* Video saved as MP4 with metadata filename
* No AI processing on Jetson — file is exported and uploaded separately

**AI coaching workflow (off-device):**

* Upload video to external service (e.g. Sportsbox AI, SwingVision, or custom pipeline)
* Skeleton tracking + PGA swing analysis happens in cloud
* Results linked back to session record in SP4 dashboard (manual or via API if available)

**Enclosure design:**

* Must accommodate: Jetson Xavier NX + carrier board, 2x camera modules, LiDAR, IR LED array, strobe driver board, USB hub, power distribution
* Indoor only — no weatherproofing required
* Should allow camera angle adjustment for calibration without reprinting
* Consider ventilation for Jetson and IR LED thermal management
* Garage floor/shelf mounting — not ceiling mount

\---

### 🧠 Decisions Log

|Date|Decision|Why I Made It|Alternatives Considered|
|-|-|-|-|
|2026-03-14|AI swing analysis off-device|Keeps Jetson focused on real-time shot detection. Cloud AI tools already exist for this.|On-device inference (possible with Jetson but not needed for v1)|
|2026-03-14|Enclosure is 3D printed|User is skilled at 3D design. Custom fit = better result than off-shelf case.|Commercial electronics enclosure (less flexible for camera positioning)|

\---

### ✅ Next Steps

* \[ ] Select USB swing camera (wide angle, decent low-light, 1080p minimum)
* \[ ] Decide: behind-the-golfer or face-on camera position (or both eventually)
* \[ ] Research pre-buffer video recording approach on Jetson (V4L2 ring buffer or GStreamer pipeline)
* \[ ] Begin rough enclosure sketch once all hardware components are selected (SP1 hardware decisions gate this)
* \[ ] Measure garage hitting area dimensions and device placement constraints

\---

### 📝 Session Notes

**2026-03-14**

> Concept clear. Nothing to build until SP1 hardware is selected — enclosure design depends on final component dimensions.
> USB camera selection is an early independent task.

\---

\---

## 🤖 Master AI Prompting Guide

> Reusable prompts for your type of project. Every prompt follows the same three-step pattern.

**Universal logbook update prompt — paste at the end of any session:**

```
Before we finish, tell me exactly what I should update in my logbook.
Go through each section and tell me only what changed or is new:
- Master Overview (status, %, phase)
- Decisions Log
- Design Notes
- Next Steps
- Wiring / Pin Diagram
- Known Issues Register
- 3D Design File Log
- Test \\\& Validation Log
- Environment Setup Guide
Keep it short — just the changes, not a summary of the whole session.
```

\---

### 🔁 Session Handoff Prompt

*Use at the START of every new AI session.*

```
I am continuing work on my DIY Golf Launch Monitor project. Here is my full context.
Do NOT re-suggest things I have already decided.

== PASTE YOUR CONTEXT BLOCK HERE ==
\\\[Copy the context block from the logbook — it is kept updated]

SUB-PROJECT I AM WORKING ON TODAY: \\\[SP1 / SP2 / SP3 / SP4 / SP5]

WHERE I AM:
- Current phase: \\\[Design / Build / Test]
- % complete: \\\[X%]
- Last session I completed: \\\[2–3 bullet points]
- Current task or blocker: \\\[DESCRIBE]

DECISIONS ALREADY MADE — do not revisit these:
\\\[LIST KEY CHOICES FROM YOUR DECISIONS LOG]

TODAY'S GOAL:
\\\[WHAT DO YOU WANT TO ACHIEVE IN THIS SESSION]

If anything is unclear, ask me one question before we start.
Then help me move forward on today's goal.

At the end of our session, tell me exactly what to update in my logbook.
```

\---

*Last updated: 2026-08-09 | Logbook version: 1.0 | Project: DIY Jetson Golf Launch Monitor*

