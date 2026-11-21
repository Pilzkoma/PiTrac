# 2026-11-21 offset trigger: acceptance of part 3

Part 3 of `docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md`
(decision 5): each camera its own trigger edge, cam2 1.0 ms after cam1, and its
own flash. Firmware v0.4 (`SEQ` / `SEQ_SHOT`), flashed 2026-11-21.

    python3 -m sp1_vision.trigger_sweep --out ~/strobe_raw/offset_sweep1 --offset-us 1000 \
        --exposure 5 --pulse-us 50 --min-us 0 --max-us 3000 --step-us 50 --repeats 5

One 50 us flash per shot, swept 0-3 ms after cam1's edge in 50 us steps, 5
repeats, each flash shot followed by a dark shot at the same delay (616 shots,
0.5 ms exposure, gamma 72; room lighting not recorded). Raw frames stay on the Jetson
(`~/strobe_raw/offset_sweep1/raw`); `capture.json` and `result.json` are here.

| | cam1 | cam2 |
|---|---|---|
| frames / shots matched | 619 / 616 | 619 / 614 |
| held-back shift | 0 | 0 |
| flash seen (delay after cam1's edge) | 0.80 - 1.40 ms | 1.80 - 2.40 ms |
| after its own edge | 0.80 - 1.40 ms | 0.80 - 1.40 ms |
| seen in all 5 repeats | every delay inside | every delay inside |
| seen outside the window | 0.75 ms in 2 of 5 (the flash's tail reaching the start) | 1.75 ms in 1 of 5 (same) |
| flash | +3.0 grey levels (frame mean) | +2.6 |

**Windows apart by 0.40 ms. Neither camera ever saw the flash inside the other's
window.** The width of 0.60 ms is the 0.5 ms exposure plus the 50 us pulse,
rounded up to the 50 us step. Exposure starts ~0.78 ms after a camera's own edge,
the same as with both cameras edged together (2026-11-12), and cam2's start
follows its own edge, not cam1's.

So the planned recording schedule `SEQ,0:E1,900:F100,1000:E2,1900:F100` puts
cam1's flash (0.90-1.00 ms) inside cam1's window and 0.80 ms before cam2's, and
cam2's flash (1.90-2.00 ms) inside cam2's window and 0.50 ms after cam1's has
closed. The 0.5 ms exposure leaves 0.4 ms between the windows. That is room for
the < 25 us jitter, or for moving the offset down to ~0.65 ms if a shorter
coarse interval is ever wanted.

Frame alignment is proven by the interleaved dark shots: held-back shift 0 in
both cameras (a frame one shot late would light the dark slots), median
no-flash level -0.1 / -0.0 grey levels.
