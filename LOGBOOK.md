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
|SP1 — Core Vision System|HW + SW|Build|55%|🟡 In Progress|2026-03-16|
|SP2 — Spin Detection|HW + SW|Design|0%|🟡 In Progress|2026-03-15|
|SP3 — Club Tracking|HW + SW|Design|0%|🔵 Planning|2026-03-14|
|SP4 — GSPro Integration + Session Data|SW|Design|0%|🔵 Planning|2026-03-14|
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
|OpenCV|TBD (PiTrac dependency)|Computer vision — circle detection, strobe frame analysis, spin calculation|SP1, SP2, SP3|☐ Installed ☐ Configured ☐ In use|
|GSPro Open Connect API|v1|Receives shot JSON over TCP socket from Jetson|SP4|☐ Installed ☐ Configured ☐ In use|
|Python or C++|TBD|Glue code, GSPro sender, session data storage|SP4|☐ Installed ☐ Configured ☐ In use|
|SQLite or similar|TBD|Local session data storage — per player, per club, over time|SP4|☐ Installed ☐ Configured ☐ In use|
|Web app (lightweight)|TBD|Session stats dashboard, player profiles|SP4|☐ Installed ☐ Configured ☐ In use|
|USB camera recording SW|TBD|Trigger-based swing video capture and file management|SP5|☐ Installed ☐ Configured ☐ In use|

**Programming language(s) confirmed:** *PiTrac codebase is C++. GSPro sender and session layer likely Python. To be confirmed once PiTrac is studied in depth.*

**AI / agent tools in use:** *Claude (this logbook and session planning). Possible YOLOv8 / OpenCV DNN for future club tracking.*

**Key file locations:** *Forked to github.com/Pilzkoma/PiTrac, cloned to ~/JetsonLM on Ubuntu laptop*

\---

### ⚙️ Environment Setup Guide

> Fill in after first successful Jetson build.

**Last verified working on:** *14.03.2026*

```
1. JetPack 5.1.6 (L4T 35.6.4) confirmed installed — do not reflash
2. CUDA 11.4, OpenCV 4.5.4 (CUDA-enabled), TensorRT 8.5.2 — all pre-installed
3. PiTrac forked to github.com/Pilzkoma/PiTrac, cloned to ~/JetsonLM on Ubuntu laptop
4. CLAUDE.md and PORTING_TASKS.md created in repo — 24 porting tasks tracked
5. All 14 Group 1 compile blockers resolved via #ifdef JETSON_BUILD guards
6. Build dependencies on Jetson still to be installed (next session)

Next step: run meson setup -Djetson_build=true on Jetson to find remaining errors
```

\---

## 🐛 Known Issues Register

|#|Sub-Project|Description|Severity|Investigated?|Decision|Date|
|-|-|-|-|-|-|-|
|1|SP1|PiTrac is built for Raspberry Pi camera stack (libcamera). Jetson uses a different camera API (Argus / V4L2). Porting will require rewriting camera abstraction layer.|✅ Resolved|☑ Yes|Resolved 2026-03-16 — porting approach confirmed: #ifdef JETSON_BUILD guards throughout libcamera_interface.h, ball_watcher.cpp, motion_detect.h, motion_detect_stage.cpp. New v4l2_interface.h created with JetsonCaptureApp and JetsonCompletedRequest structs replacing RPi types.|2026-03-16|
|2|SP1|IR strobe pulse timing on RPi uses hardware hacks to the Pi GS camera. Jetson GPIO timing characteristics are different — may need external microcontroller for sub-microsecond strobe control.|🟡 Annoying|☑ Yes|Investigate Jetson GPIO latency vs dedicated Arduino/Teensy strobe controller|2026-03-14|
|3|SP2|Spin detection requires marked balls. Standard range balls will not work for spin. Must use balls with visible dot pattern (similar to Foresight approach).|🔵 Minor|☑ Yes|Accepted — user confirmed willingness to use marked balls|2026-03-14|
|4|SP4|GSPro runs on Windows PC only — it cannot run on the Jetson. The Jetson sends JSON shot data over TCP to a separate Windows PC running GSPro. Firewall and network config required if on different subnets.|🔵 Minor|☑ Yes|Architectural decision logged — Jetson = compute, Windows PC = GSPro host|2026-03-14|
|5|SP1|LiDAR excluded from v1. Camera-only trigger may log a topped/missed shot as a real shot in rare cases.|🔵 Minor|☑ Yes|Accepted for v1. LiDAR ball-launch confirmation planned for v2 second Jetson build.|2026-03-14|

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
|% Complete|55%|
|Status|🟡 In Progress|
|Depends On|None — this is the foundation|
|Started|2026-03-14|
|Last Updated|2026-03-16|

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

|Date|What Was Tested|Result|Notes|
|-|-|-|-|
|—|—|—|—|

\---

### ✅ Next Steps

* \[x] Complete Group 3 stubs (7 no-op functions) — SetLibCameraLoggingOff, ConfigurePostProcessing pipeline half, ConfigureLibCameraOptions, WatchForHitAndTrigger, SetLibcameraTuningFileEnvVariable, kGatherClubData=false, kUsePreImageSubtraction=false
* \[ ] Clone repo on Jetson: git clone https://github.com/Pilzkoma/PiTrac.git ~/JetsonLM
* \[ ] Install apt dependencies on Jetson: meson ninja-build libboost-all-dev libmsgpack-dev default-jdk maven v4l-utils libv4l-dev libgpiod-dev
* \[ ] Build ActiveMQ-CPP 3.9.5 from source on Jetson
* \[ ] Run: meson setup build_jetson -Djetson_build=true --wipe — paste output
* \[ ] Fix any meson configure errors
* \[ ] Begin Group 2 runtime implementations once cameras arrive
* \[ ] Order IR LED array 850nm ~10W (e.g. Chanzon) — not yet ordered

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
|Phase|Design|
|% Complete|0%|
|Status|🔵 Planning|
|Depends On|SP1 (minimum to start), SP2 + SP3 for full data|
|Started|2026-03-14|
|Last Updated|2026-03-14|

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

\---

### 🧠 Decisions Log

|Date|Decision|Why I Made It|Alternatives Considered|
|-|-|-|-|
|2026-03-14|GSPro runs on separate Windows PC, Jetson sends over TCP|GSPro is Windows-only. Jetson is the compute unit, not the simulator.|Run simulation on Jetson (not possible — GSPro is Windows only)|
|2026-03-14|Session data stored in SQLite on Jetson|Simple, file-based, no server required, easy to back up|PostgreSQL (overkill), cloud DB (unnecessary complexity for v1)|
|2026-03-14|Stats dashboard as local web app|Accessible from phone/tablet without installing anything. Works on local WiFi only.|Native app (too much development overhead for v1)|

\---

### ✅ Next Steps

* \[ ] Read GSPro Open Connect v1 full documentation (gsprogolf.com/GSProConnectV1.html)
* \[ ] Design JSON data flow: C++ vision pipeline → Python sender → GSPro
* \[ ] Design SQLite schema: shots table, players table, sessions table
* \[ ] Prototype a basic TCP sender that sends a dummy shot to GSPro to confirm connectivity
* \[ ] Do not start until SP1 produces at least ball speed + launch angles

\---

### 📝 Session Notes

**2026-03-14**

> Architecture designed at high level. Depends on SP1 for real data.
> Can prototype the GSPro TCP sender with dummy data independently of vision work.

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

*Last updated: 2026-03-16 | Logbook version: 1.0 | Project: DIY Jetson Golf Launch Monitor*

