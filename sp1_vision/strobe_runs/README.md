# Strobe-lit captures

Measured with `sp1_vision/strobe_capture.py`: both cameras stream at 120 fps,
the Teensy fires one pulse from Pin 29 mid-stream, and every frame is logged
with its arrival time after the fire and how far it rose above the run's
ambient baseline. Raw output goes to `/tmp/strobe_<time>/` on the Jetson; only
what a conclusion rests on is kept here.

## 2026-11-10 — first flash, `2026-11-10_first_flash/`

Room light on, ball on the floor in front of the unit, nobody in view, the
arrays' photocells covered. 24 runs: exposure 8 / 4 / 1 ms × single pulse
0.5 / 2 ms × 4 repeats. `frames.csv` holds every frame; the PNGs are run 02
(8 ms exposure, 0.5 ms flash, both cameras) and run 22 (1 ms, 2 ms, cam1).

### The flash swamps room light

Ball centre, mean grey level (sensor black level ≈ 22):

| exposure | flash | cam1 | cam2 |
|---|---|---|---|
| 1 ms, room light only | — | 24 | 22 |
| 8 ms, room light only | — | 36 | 25 |
| 8 ms | 0.5 ms | 237 (saturated) | 118 |
| 8 ms | 2 ms | 244 (saturated) | 234 |
| 1 ms | 2 ms | 244 (saturated) | 131 |

Per unit time the flash puts roughly 50–100× more light on the ball than the
room lamps: a 0.5 ms pulse adds ~95 grey levels at cam2, a whole millisecond of
room light ~2. At 1 ms exposure the room is near black and the ball white.
Even at 8 ms exposure the flash is ~8× the ambient on the ball. Direct sun in
the garage is still untested.

**cam1 saturates on the shortest pulse; cam2 gets about half** — in this run.
It was not the arrays: the right-hand board's photocell was still dimming it
through the tape. With the photocells removed the two cameras agree to 1–2 %
(next section).

### Where the flash lands

- Fire → frame arrival in Python: **11–20 ms**. The 8 ms spread is the frame
  period; the offset is readout + USB + decode.
- **8 ms exposure catches every flash** (16/16), once split across two frames.
- Short exposures catch it by chance, about (exposure + pulse) / 8.33 ms:
  1 ms + 0.5 ms hit 1 of 8 camera-runs.
- **The two cameras are not in phase.** At short exposure one camera often saw
  the flash and the other did not. Triangulation needs both to see the same
  flash, so either the exposure stays long (~8 ms, flash still dominant) or the
  strobe fires a train covering a whole frame period. This is the input for
  `WaitForCam2Trigger`.

### Capture details learned on the way

- Continuous reading needs `CAP_PROP_BUFFERSIZE 2`: with 1 the stream halves to
  ~68 fps, because the frame arriving during a fetch has nowhere to go. The
  held-back-frame defect (CLAUDE.md) only concerns on-demand reads.
- `CAP_PROP_POS_MSEC` (V4L2 buffer timestamp) is unusable here: 4 ms steps and
  occasional jumps of hundreds of ms. Arrival time runs at a steady 8.0 ms.
- Frames are kept as raw MJPEG while streaming (`CAP_PROP_CONVERT_RGB 0`) and
  decoded afterwards; decoding two 120 fps streams in Python drops frames.

### Hardware faults found the same evening

All three made the flash look absent or random before this run:

1. **Two-pole connector on the LED supply** had an intermittent contact —
   replaced with two separate crimps.
2. **Photocells on the Cenpek boards** dim or cut the LEDs in room light (the
   source of the earlier "one array much weaker" and flicker). Covered for
   this run; to be removed for good, since tape will not hold against garage
   daylight.
3. **Trigger line Pin 29 → Teensy Pin 2** dropped out twice and came back while
   probing. To be re-soldered or clamped. Jetson Pin 29 itself was verified
   switching 0 ↔ 3.3 V on the header.

A flash that comes back from a hand or the calibration board held near the
lens reads up to +85 grey levels on the whole frame, so judge strobe
brightness only with an empty scene.

## 2026-11-11 — after the fixes

Photocells desoldered from both boards, trigger line re-soldered. Same scene,
8 ms exposure, 12 runs (raw data only on the Jetson, `/tmp/strobe_run3`).
Both cameras run identical V4L2 settings (gain 0, gamma 100, contrast 32).

- **Trigger: 12/12 flashes arrived, in both cameras.**
- Ball centre (dark level ≈ 24):

  | flash | cam1 | cam2 |
  |---|---|---|
  | 0.1 ms | 140 | 138–139 |
  | 0.3 ms | 238–239 | 237 (once 141) |
  | 0.5 ms | 244 (saturated) | 244 (saturated) |

- **The cameras agree to 1–2 %**; the arrays need no balancing.
- **0.1 ms is already enough** — mid-range on the ball; 0.3 ms clips. Short
  is what a moving ball needs anyway (6 mm of travel per 0.1 ms at 60 m/s).
- The one 141 at 0.3 ms is a flash straddling the ~0.33 ms gap between an
  8.0 ms exposure and the 8.33 ms frame period — about one flash in twenty
  loses part of its light that way.

## 2026-11-11 — the cameras' own processing changes what they report

Brighter room lamps (one lighting the ball from the right, one from above),
same flash, ball in the same place to 5 px. The flash's **contribution** on the
ball — flash frame minus ambient frame, which more ambient light must not
change — dropped:

| 0.1 ms flash, 8 ms exposure | cam1 | cam2 |
|---|---|---|
| dim room (above) | +116 | +114 |
| both lamps on | +53 | +19 |
| lamps off again | +110 | +18 |
| right lamp only | +61 | +19 |
| top lamp only | +93 | +18 |
| after the dashboard ran the cameras on auto exposure | **+108** | **+115** |

Not the arrays (photocells desoldered, both look equal on a phone camera),
not backlight compensation (on/off: no change), not cabling or focus
(re-plugging cam2 did not help). cam2 meanwhile showed a **fixed, soft, round
dark patch over the image centre**, near black in the middle — static over 9 s,
so no insect. It vanished within seconds of the dashboard opening the camera
with auto exposure, and the contribution came back to +115.

Two different things were mixed up in this table, and the first reading
("the processor keeps adapting") was only half right:

1. **cam2's dark patch was a stuck state** in the module's image processor —
   static, with every visible V4L2 control identical to cam1, cleared by one
   auto-exposure pass. Cause unknown.
2. **The lamp effect is a fixed, compressive tone curve, not adaptation.**
   Even after an auto-exposure reset, all lamps on gave +72 / +57 against
   +120 / +118 in the dim room. A gamma sweep under the lamps shows why
   (cam1, 8 ms exposure, ball centre; cam2 alike):

   | gamma | ambient on ball | 0.1 ms flash | 0.2 ms flash | ratio (linear = 2.0) |
   |---|---|---|---|---|
   | **72** (minimum) | 43 | +61 | +107 | **1.75** |
   | 100 (default) | 72 | +62 | +103 | 1.65 |
   | 200 | 138 | +49 | +75 | 1.53 |
   | 500 | 202 | +26 | +39 | 1.47 |

   The higher the ambient puts the ball on the curve, the fewer grey levels
   the same flash adds. Raising `gain` shows the same compression (gain
   0 → 32: ambient above black ×1.8, flash contribution ×1.46).

Consequences, now built into `strobe_capture.py`:
- **Settle on auto exposure before every switch to manual** (against 1).
- **Measure at gamma 72**, the straightest curve the control offers; 100 is
  restored afterwards. With all lamps on: 0.1 ms +65, 0.2 ms +115.
- Grey-level differences are not proportional to light. Comparing flash
  energy across runs needs the same ambient level, or an inverse of the curve
  measured with a pulse series. Detection only needs the ball to stand out,
  which it does.
- Production capture (`V4L2Capture` in `pitrac_lm`) does not set gamma and so
  runs at 100. Worth switching to 72 there too when strobe frames go into
  the C++ path.
- Vendor controls: the modules are Sonix bridges (`0c45:6366`) with two UVC
  extension units, one of them Sonix's undocumented register interface. Not
  touched — nothing above needs it, and writing blind registers can brick a
  module.
