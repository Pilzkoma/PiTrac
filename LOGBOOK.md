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
|SP1 — Hardware & Build|HW+SW|Build|97%|🟡 In Progress|2026-05-05|
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
|Primary Camera x2|Arducam OV9281 Monochrome USB3|Ball imaging — strobe capture|Jetson USB3 port|TBD|☐ Ordered ☐ In hand ☐ In use|
|LiDAR sensor (not used in v1 - v2 only)|TBD|Motion/trigger detection — detects ball or club movement to wake cameras|Jetson GPIO / serial|TBD|☐ Ordered ☐ In hand ☐ In use|
|IR LED array|850nm \~10W array board (e.g. Chanzon)|IR illumination for strobe capture|Strobe driver circuit|TBD|☐ Ordered ☐ In hand ☐ In use|
|IR strobe driver|Teensy 4.0 (DEV-15583) — pulled forward from v2 plan|Drives IR LED pulses at \~10µs via Hardware-Timer-backed delayMicroseconds; Jetson sends single GPIO trigger + setup over USB serial|Jetson Pin 29 (fire trigger) + USB + MOSFET → IR LED array|SparkFun|☑ In hand|
|IR LED array|Cenpek 4× 850nm 12V CCTV-style board (FY-S54-F)|IR illumination for strobe capture|MOSFET (low-side switch on 12V power line)|—|☑ In hand|
|MOSFET (LED gate)|IRLZ44N (or SparkFun PRT-12959 breakout) — TBD|Switches 12V LED-array supply on Teensy gate signal|Teensy Pin 3 → MOSFET gate; LED-array J1− → MOSFET drain|TBD|☐ Ordered|
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
|17|SP1|V4L2Capture::ensure_streaming() leaks the open fd on any failure path (REQBUFS, mmap, STREAMON). `streaming_=false` stays set, so subsequent `read()` calls re-attempt ensure_streaming against the same already-failed fd and never recover. /dev/videoX gets stuck and only `rmmod uvcvideo && modprobe uvcvideo` clears it.|🔵 Minor|☑ Yes|Fix: call release() on every ensure_streaming failure path, not just shutdown. Documented but not yet implemented — has not bitten in normal runs because the happy path works. ~1 hour of work.|2026-04-29|
|18|SP1|motion_detect_stage.cpp horizontal hskip step is in BYTES not PIXELS. Assumes CV_8UC1 input but V4L2Capture engine delivers CV_8UC3 BGR (after cvtColor(GRAY2BGR) inside decode_into). Today this still produces sensible motion-detect because B=G=R per pixel, but the effective horizontal pixel coverage is reduced from 640 samples to ~213 actual pixels per row.|✅ Resolved|☑ Yes|Resolved 2026-05-05 — motion_detect_stage.cpp now derives `hskip_bytes = config_.hskip * frame.channels()` under JETSON_BUILD and uses that for all 4 pointer-arithmetic spots (2 initial offsets, 2 inner-loop steps). RPi behavior unchanged (channels=1 implicit). Effective horizontal coverage now matches the configured 640 samples / row.|2026-05-02|
|19|SP1|PiTrac FSM ball-stabilization gate cycles endlessly between WaitingForBall ↔ WaitingForBallStabilization without advancing to WaitingForBallHit / WatchForHitAndTrigger. Even with a stable yellow ball in a cap (no movement, LED+breadboard out of frame), the CheckForBallStable check fails every ~1 second and the FSM bounces back. Suspected: HoughCircles finds slightly different ball positions frame-to-frame in the noisy ambient-IR mono image, and the stability tolerance treats that as motion.|🟡 Medium|☑ Yes|Workaround for strobe-pipeline validation: bypass pitrac_lm entirely via Hardware/teensy_strobe/test_strobe_bypass.py (claims Pin 29 + sends Teensy setup + toggles GPIO directly). Real fix expected to land naturally once IR strobe LED illumination is hooked up — sharp on/off contrast from strobe-lit ball will give HoughCircles a much more stable detection. Partially worked around in code via Issue #21.|2026-05-05|
|20|SP1|motion_detect_stage.cpp explicitly skipped SendExternalTrigger when system_mode == kCamera1TestStandalone (RPi-only intent: "don't pulse a non-existent cam2 system during isolated cam1 testing"). On Jetson SendExternalTrigger drives the IR strobe (no separate cam2 system to skip), so this prevented the strobe from ever firing during pitrac_lm motion-detect trips.|✅ Resolved|☑ Yes|Resolved 2026-05-05 — motion_detect_stage.cpp now unconditionally calls SendExternalTrigger under #ifdef JETSON_BUILD regardless of system_mode.|2026-05-05|
|21|SP1|JETSON_STUB bypass in gs_fsm.cpp WaitingForBallStabilization handler — when CheckForBall finds the ball but reports "moved" (sub-pixel HoughCircles jitter), force-advance to WaitingForBallHit instead of bailing back to WaitingForBall. Allows pitrac_lm to exercise the full strobe-trigger pipeline despite Issue #19. When ball is genuinely lost (!found) the original bail-back behavior is preserved.|🟡 Medium|☑ Yes|Temporary development bypass — REMOVE this `#ifdef JETSON_BUILD` block in gs_fsm.cpp once IR strobe is wired and HoughCircles produces stable ball detections. Until then it's the only way to exercise the SP1 strobe pipeline end-to-end through pitrac_lm.|2026-05-05|
|22|SP1|libgpiod chardev (gpiod_line_set_value via /dev/gpiochip1) does NOT drive Pin 29 in a way that the Teensy ISR sees a rising edge on the Seeed reComputer J202 carrier. Confirmed via extensive 2026-05-05 debugging — gpioset CLI (uses libgpiod chardev) does not trigger the Teensy either; only Python's Jetson.GPIO library works. Adding force-LOW + 5ms hold + 2ms settle to the C++ libgpiod path did not help. The cause is unknown — possibly a kernel/device-tree quirk specific to this carrier+L4T combination.|🟡 Medium|☑ Yes|Workaround in place: pulse_strobe_jetson.cpp's SendExternalTrigger calls Hardware/teensy_strobe/fire_trigger.py via std::system instead of libgpiod chardev (Jetson.GPIO under the hood works reliably). ~100-200ms fork+exec+python startup latency is acceptable. Could revisit if/when L4T is upgraded or libgpiod 2.x is available — until then, the Python helper is reliable.|2026-05-05|

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
|% Complete|75%|
|Status|🟡 In Progress|
|Depends On|None — this is the foundation|
|Started|2026-03-14|
|Last Updated|2026-04-26|

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
* ☐ Workaround for Issue #19 (FSM ball-stabilization too flaky without IR): use the bypass-test script for any strobe-pipeline iteration until IR illumination is wired. Real fix expected to land naturally once the IR LEDs are blasting the ball.
* ☐ Workaround for Issue #22 (libgpiod chardev doesn't drive Pin 29 on Seeed J202): pulse_strobe_jetson.cpp now shells out to fire_trigger.py via std::system. Could revisit when L4T upgrades or libgpiod 2.x available — until then, the Python helper is reliable.
* ☐ MOSFET (IRLZ44N oder SparkFun PRT-12959) bestellen für Phase C-Test 2 (12V Cenpek IR-Board switching)
* ☐ Phase C Test 2: MOSFET zwischen Teensy Pin 3 und Cenpek-12V-Rückleitung; Cenpek-LED-Array statt Test-LED; selber Bypass-Test sollte echte IR-Bursts produzieren (verifizierbar mit Smartphone-Kamera in Slowmo, da die meisten Smartphone-Sensoren 850nm IR sehen)
* ☐ Permanent fix für /dev/ttyACM0 Permissions: `sudo usermod -a -G dialout brain` + neu einloggen, statt jedem Boot `sudo chmod 666` zu machen
* ☐ V4L2Capture::ensure_streaming() failure-path fd leak — release() on failure so a retry can recover (see Issue #17)
* ☐ motion_detect_stage CV_8UC1/CV_8UC3 byte-step assumption (Issue #18) — works today only because cvtColor(GRAY→BGR) makes B=G=R; fix is `hskip * frame.channels()`
* ☐ Verify `undistort_camera_image` end-to-end during the calibration run (currently no-op since use_undistortion_matrix_=false)
* ☐ Mount cameras in enclosure at correct angles for stereo ball tracking
* ☐ Run PiTrac calibration procedure with both cameras
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

*Last updated: 2026-03-19 | Logbook version: 1.0 | Project: DIY Jetson Golf Launch Monitor*

