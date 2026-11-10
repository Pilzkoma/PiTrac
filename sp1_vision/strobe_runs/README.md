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

**cam1 saturates on the shortest pulse; cam2 gets about half.** The right-hand
array is weaker or aimed differently. Real measurement runs must choose pulse
length (or gain) so neither camera clips.

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
