# Offset Trigger (ball marks part 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each camera gets its own trigger edge and its own flash, cam2 ~1 ms after cam1, proven by a flash-delay sweep, and recordable for shots.

**Architecture:** Firmware v0.4 gets a per-period event schedule (`SEQ`), parsed and compiled into sorted pin transitions by a pure C++ header that is unit-tested on the host (g++ on the Jetson); the sketch plays the transitions on the cycle counter. Python builds schedule strings in one small module, used by `trigger_sweep --offset-us` (acceptance) and `strobe_shot --trigger --offset-us` (recording).

**Tech Stack:** Teensy 4.0 / Teensyduino (arduino-cli, fqbn `teensy:avr:teensy40`), C++11 header, Python 3.8 (Jetson) / 3.14 (Windows), unittest.

**Spec:** `docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md`, "Spin measurement (parts 3-4)", "How each part is accepted" 3, and "Owner decision (2026-11-21)" 5.

## Global Constraints

- Firmware command: `SEQ,<t_us>:<event>,...`; events `E1`, `E2` (rising trigger edge at t; line pulled low TRIG_LOW_US = 10 us before), `F<pulse_us>` (flash from t). `SEQ_SHOT` plays once, `SEQ_RUN,<period_us>[,max_ms]` repeats, `STOP` ends it. SHOT and TRIG_RUN unchanged.
- Guards as today: armed (TRIG_ARM) required; pulse <= SHOT_MAX_PULSE_US (1000); SEQ_SHOT spacing >= SHOT_MIN_SPACING_US (5000); SEQ_RUN period >= TRIG_RUN_MIN_PERIOD_US (5000); flash duty <= MAX_RUN_DUTY (0.25); schedule end + 200 us <= period; max_ms default 60 s, cap 10 min.
- Default timing: cam2 edge 1000 us after cam1's, each flash 900 us after its own camera's edge, 100 us.
- OpenCV / numpy APIs no newer than the Jetson's (4.5.4 / 1.17.4); Python 3.8 syntax.
- Do not add hardware or libraries.

## Review Focus

- Two flashes overlapping, or a flash running into the next period: refused with ERR, never fired as one long pulse.
- More than one edge per camera in one schedule: refused (a camera takes at most one frame per ~10 ms).
- A malformed SEQ (`900F100`, `x:E1`, empty, > 16 events, unsorted times): ERR, and the previously stored schedule stays valid.
- SEQ_SHOT / SEQ_RUN before any SEQ or while disarmed: ERR, no pin moves.
- STOP during SEQ_RUN leaves both trigger lines HIGH (armed idle) and the LED gate LOW.

---

### Task 1: Schedule parser/compiler as a host-tested header

**Files:**
- Create: `Hardware/teensy_strobe/seq_schedule.h`
- Create: `Hardware/teensy_strobe/test_seq_schedule.cpp`

**Interfaces:**
- Produces: `struct SeqTransition { uint32_t t_us; uint8_t line; uint8_t level; }` (`line`: 0 = cam1 trigger, 1 = cam2 trigger, 2 = LED gate); `struct SeqSchedule { SeqTransition tr[2 * SEQ_MAX_EVENTS]; uint8_t n; uint32_t end_us; uint32_t flash_us; }`; `const char* seq_parse(const char* args, SeqSchedule* out)` returning nullptr on success or an error string (out untouched on error). Times in the compiled schedule are shifted by TRIG_LOW_US so the first low transition can sit at 0; `end_us` = last transition; `flash_us` = sum of pulses (duty check).
- `SEQ_MAX_EVENTS = 16`, `SEQ_TRIG_LOW_US = 10`, `SEQ_MAX_PULSE_US = 1000`.

- [ ] **Step 1: Write the tests** (`test_seq_schedule.cpp`, plain asserts, prints `ALL OK`): default schedule `0:E1,900:F100,1000:E2,1900:F100` → 8 transitions sorted by time, cam1 low at 0 / high at 10, LED high at 910 / low at 1010, cam2 low at 1000 / high at 1010, LED 1910/2010, end 2010, flash 200; refusals with a message for: two `E1`; overlapping flashes (`0:F100,50:F100`); pulse 0 or 1001; unsorted times; bad token (`900F100`, `x:E1`, `0:E3`); empty; 17 events; on refusal `out` keeps its old content.
- [ ] **Step 2: Run on the Jetson, see it fail to compile** — `g++ -std=c++11 -Wall -o /tmp/tseq test_seq_schedule.cpp && /tmp/tseq`.
- [ ] **Step 3: Implement `seq_parse`** — `strtoul` per token, events stored then sorted (insertion sort), transitions generated and sorted stably by time; no Arduino headers, no heap.
- [ ] **Step 4: Run, expect `ALL OK`.**
- [ ] **Step 5: Commit.**

### Task 2: Firmware v0.4 commands SEQ / SEQ_SHOT / SEQ_RUN

**Files:**
- Modify: `Hardware/teensy_strobe/teensy_strobe.ino` (header comment, version string, handleLine, STATUS, stopRun, new `playSchedule`, `seqRunStep`)

**Interfaces:**
- Consumes: `seq_parse`, `SeqSchedule` (Task 1).
- Produces: serial protocol above; `STATUS` gains ` SEQ=<n events>`; `STOP` after SEQ_RUN replies `OK <periods played>`.

- [ ] **Step 1: Implement** — `playSchedule(const SeqSchedule&)` spins on `ARM_DWT_CYCCNT` from c0 and applies each transition with `digitalWriteFast` (lines mapped to CAM1_TRIG, CAM2_TRIG, LED_GATE); ends with LED LOW and both trigger lines HIGH. SEQ_RUN shares State::RUNNING with RUN / TRIG_RUN (`seq_running` flag), checks period, duty (`flash_us / period`), `end_us + 200 <= period`, armed, schedule present.
- [ ] **Step 2: Compile** with arduino-cli (`--fqbn teensy:avr:teensy40`), expect no errors; copy the .hex to the Jetson, flash with `flash_teensy.sh`, expect `BOOT teensy_strobe firmware v0.4`.
- [ ] **Step 3: Serial smoke test on the Jetson** (pyserial, cameras not needed): `TRIG_ARM` OK; `SEQ_SHOT` before SEQ → ERR; `SEQ,0:E1,0:E1` → ERR; default SEQ → OK; `SEQ_SHOT` → OK; `SEQ_RUN,10000,500` → OK then after 0.5 s state READY again and `STOP` → `OK <n>` with n ≈ 50; `SEQ_RUN,2000` → ERR (period); old `TRIG_RUN,10000,900,100,300` still OK.
- [ ] **Step 4: Commit** (sketch + note of the smoke-test output in the commit message).

### Task 3: Python schedule builder + trigger_sweep --offset-us

**Files:**
- Create: `sp1_vision/trigger_seq.py`
- Create: `sp1_vision/tests/test_trigger_seq.py`
- Modify: `sp1_vision/trigger_sweep.py` (capture with `--offset-us`, analysis prints windows per own edge and the separation)
- Modify: `sp1_vision/tests/test_trigger_sweep.py`

**Interfaces:**
- Produces: `seq_command(events) -> str` (`events`: list of `(t_us, "E1"|"E2"|"F<us>")`, sorted output `SEQ,0:E1,...`); `offset_schedule(offset_us=1000, delay_us=900, pulse_us=100) -> list` (both cameras' edges and flashes; pulse 0 → no flash events); `sweep_schedule(offset_us, flash_at_us, pulse_us) -> list` (both edges, one flash at flash_at_us from cam1's edge, none if pulse 0); in trigger_sweep `windows_separation_us(w1, w2) -> float` (cam2 start − cam1 end, negative = overlap).

- [ ] **Step 1: Tests** — `seq_command([(1000,"E2"),(0,"E1")]) == "SEQ,0:E1,1000:E2"`; `offset_schedule()` gives `0:E1,900:F100,1000:E2,1900:F100`; `offset_schedule(pulse_us=0)` has no F; `sweep_schedule(1000, 1500, 50)` = `0:E1,1000:E2,1500:F50`; `windows_separation_us({"end_us":1280}, {"start_us":1780}) == 500`.
- [ ] **Step 2: Run them, expect failure** (`python -m unittest sp1_vision.tests.test_trigger_seq sp1_vision.tests.test_trigger_sweep`).
- [ ] **Step 3: Implement**; trigger_sweep with `--offset-us N` sends `SEQ,...` then `SEQ_SHOT` per shot (dark shots: schedule without F), default sweep then `--min-us 0 --max-us 3000 --step-us 50`; `capture.json` records `offset_us`; analysis prints each camera's window relative to cam1's edge and to its own edge, and "windows apart by X ms" or "OVERLAP".
- [ ] **Step 4: Tests pass** on Windows and on the Jetson (`run-tests`).
- [ ] **Step 5: Commit.**

### Task 4: Acceptance sweep on the hardware

- [ ] **Step 1:** Ball / scene in view, room light as usual; on the Jetson `python3 -m sp1_vision.trigger_sweep --out ~/strobe_raw/offset_sweep1 --offset-us 1000 --exposure 5 --pulse-us 50 --min-us 0 --max-us 3000 --step-us 50 --repeats 5`.
- [ ] **Step 2: Expected:** cam1 window ≈ 0.78–1.28 ms, cam2 ≈ 1.78–2.28 ms after cam1's edge (≈ 0.78 after its own), held-back shift 0, windows apart ≈ 0.5 ms. A camera seeing the flash outside its window fails the acceptance.
- [ ] **Step 3:** Copy `result.json` + brightest frames into `sp1_vision/strobe_runs/2026-11-21_offset_trigger/` with a README of the numbers; commit.

### Task 5: strobe_shot --offset-us recording

**Files:**
- Modify: `sp1_vision/strobe_shot.py`

**Interfaces:**
- Consumes: `offset_schedule` (Task 3).

- [ ] **Step 1: Implement** — with `--trigger --offset-us N`: `SEQ` from `offset_schedule(N, args.trigger_delay_us, args.pulse_us)` then `SEQ_RUN,<period>,<max_ms>` instead of TRIG_RUN; write `trigger.json` (period, offset, delay, pulse) next to `raw/` so part 4 knows each camera's exposure time.
- [ ] **Step 2: 3 s test recording** on the Jetson with a ball at rest: both cameras ~300 frames, contact sheet shows the ball lit in both.
- [ ] **Step 3: Commit;** update CLAUDE.md "Current task" and `sp1_vision/strobe_runs/README.md` with firmware v0.4 and the measured windows.
