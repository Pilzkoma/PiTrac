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
|SP1 — Hardware & Build|HW+SW|Build|75%|🟡 In Progress|2026-04-26|
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
|IR strobe driver|Jetson GPIO (v1) — Teensy 4.0 reserved for v2|Drives IR LED pulses at \~10µs|Jetson GPIO + IR LED array|TBD|☐ Ordered ☐ In hand ☐ In use|
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

**Last verified working on:** *26.04.2026*

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

Next step: implement real V4L2 capture in Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp (currently 5 stub functions)
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

\---

### ✅ Next Steps

* ☑ OV9281 cameras arrived and detected on Jetson
* ☑ Test frames captured from both cameras
* ☑ Sustained 120 FPS @ 1280x800 MJPG verified on both cameras simultaneously (via v4l2-ctl raw stream)
* ☑ OpenCV cv2.VideoCapture decode benchmarked — caps at ~60 FPS due to CPU MJPG decode (Issue #15, not a blocker for C++ pipeline)
* ☐ Implement real V4L2 capture in Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp — replace 5 stub functions with V4L2 ioctl + libjpeg-turbo (or nvJPEG) decode
* ☐ Mount cameras in enclosure at correct angles for stereo ball tracking
* ☐ Configure PiTrac pitrac_lm to use /dev/video0 and /dev/video2
* ☐ Run PiTrac calibration procedure with both cameras
* ☐ First ball detection test with live camera feed

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

