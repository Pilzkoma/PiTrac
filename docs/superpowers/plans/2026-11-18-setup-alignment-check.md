# Setup Alignment Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dashboard page "Aufbau" that, with one flash, measures where the ball on its rest spot sits relative to the target position (50 cm in front of the rear camera for the chosen handedness) and tells the owner how to move the unit.

**Architecture:** The flash capture is factored out of `sp1_vision/strobe_pair.py` into a reusable function; a pure geometry module computes the target and the offsets; a Flask blueprint in `sp4_gspro/` ties them together and renders the result with the target drawn into both images.

**Tech Stack:** Python 3, numpy, OpenCV, Flask (all already in use). No new libraries.

**Spec:** agreed with the owner in plain language on 2026-11-18 (no separate spec file):
- purpose: a check while setting up the unit, not per shot - "einmal hingestellt nicht wieder bewegen und der ball hat ja sein fenster";
- target: ball centre **50 cm** in front of the **rear** camera, the one the ball flies away from, chosen by handedness, "so dass möglichst viele Bilder vom Flug entstehen";
- measured **with the flash** (the ambient-lit ball detection is unreliable, CLAUDE.md issue #19/#21);
- shown on its own dashboard page with both camera images, target marker, offset in mm, arrows, green within ±10 mm.

## Global Constraints

- Target platform Jetson: Python 3.8.10, OpenCV 4.5.4, numpy 1.17.4 - no API newer than these (no walrus operator, no `math.dist`, no OpenCV 5 calls).
- Tests are `unittest`. sp1_vision: `python -m unittest sp1_vision.tests.<module>` from the repo root (Windows has numpy/OpenCV now) and on the Jetson with `.superpowers/sdd/2026-08-09-stereo-triangulation-block1/run-tests` (its `JET=` line still says `192.168.178.194`; the Jetson is `192.168.178.43` - fix that line first). sp4_gspro: `cd sp4_gspro && python3 -m unittest test_setup_page` on the Jetson (Flask lives there).
- Camera frame: OpenCV axes, X right, Y down, Z forward, metres; stereo convention `X2 = rig.r @ X1 + rig.t_m` (`stereo_geometry.StereoRig`). Camera 2 sits at negative x in camera 1's frame (`camera2_centre_in_camera1`, x ≈ −80 mm).
- Handedness: `"RH"` / `"LH"` as in `shot_db.players.handedness`. A right-handed golfer faces the unit and hits to their left, which is **+x** in the camera frame (the 2026-11-18 putts move towards +u). RH → flight sign +1, LH → −1.
- Flash capture settings unchanged from `strobe_pair`: 8 ms exposure (`exposure_units=80`), gamma 72, auto-exposure settle first, the saved image is flash minus ambient stretched to 220. Pulse for this page: **100 µs**.
- Any capture path must hand the cameras back: the dashboard's own `calibration_capture.SESSION` is released before the capture (in-process, not via HTTP to itself).
- UI text German, in the dashboard's existing look (`sp4_gspro/look.py`: `look.HEAD`, `look.header_html(...)`, `look.HEADER_SCRIPT`).
- `CLAUDE.md`: no libcamera, no LGPIO; commit per task; never `git stash` in this repo.

## Review Focus

1. **No ball, or a foot/club found instead** - the page must say why in German (the `find_ball_pair` reason) and show no offset numbers. Test in Task 3.
2. **Ball partly outside one image or within 40 px of an edge** - offsets may be right but the setup is not; must show a warning, not green. Test in Task 2 (`margin_ok`).
3. **Double click / second request while the flash is running** - must not open the cameras twice; the second request gets "Messung läuft bereits". Test in Task 3.
4. **Flash not seen in one camera** (`rise < strobe_capture.LIT_THRESHOLD`) - say "Blitz in Kamera N nicht gesehen", no numbers. Test in Task 1 (`unlit_cameras`) and Task 3.
5. **Handedness switched after a measurement** - the page must recompute target and text for the new handedness from the same measurement, not keep stale arrows. Test in Task 3 (the measure endpoint takes handedness; the page re-posts on toggle).

---

### Task 1: Reusable flash capture

**Files:**
- Create: `sp1_vision/flash_pair.py`
- Modify: `sp1_vision/strobe_pair.py` (`main` uses `flash_pair`; `lit_frame` moves to `flash_pair` and is re-exported from `strobe_pair` for existing callers)
- Test: `sp1_vision/tests/test_flash_pair.py`

**Interfaces:**
- Produces:
  - `lit_frame(frames, t_fire) -> (flash: np.ndarray uint8, ambient: np.ndarray uint8, rise: float)` - moved unchanged from `strobe_pair`.
  - `difference_image(flash, ambient) -> np.ndarray uint8` - `cv2.subtract`, then linear stretch so the 99.95th percentile sits at 220 (exactly what `strobe_pair.main` does today).
  - `unlit_cameras(rises: dict) -> list[int]` - camera numbers with `rise < strobe_capture.LIT_THRESHOLD`.
  - `class FlashPair` with attributes `diff: {1: img, 2: img}`, `flash`, `ambient`, `rises` (dicts keyed 1, 2), `pulse_us: int`.
  - `capture_flash_pair(pulse_us=100, exposure_units=80, gamma=strobe_capture.MEASURE_GAMMA, release=strobe_capture.release_dashboard) -> FlashPair` - the capture block of today's `strobe_pair.main` (Teensy, FirePin, open cameras, gamma, settle on auto, manual exposure, `single_pulse`, `one_run`, restore gamma/auto exposure in `finally`), then `lit_frame` + `difference_image` per camera. `release` is called first.

- [ ] **Step 1: Write the failing tests**

```python
class DifferenceImage(unittest.TestCase):
    def test_brightest_part_stretched_to_220(self):
        ambient = np.full((100, 100), 30, np.uint8)
        flash = ambient.copy(); flash[40:60, 40:60] = 90     # +60 on the ball
        d = flash_pair.difference_image(flash, ambient)
        self.assertEqual(int(d[50, 50]), 220)
        self.assertEqual(int(d[0, 0]), 0)

    def test_black_difference_does_not_divide_by_zero(self):
        a = np.full((10, 10), 50, np.uint8)
        self.assertEqual(int(flash_pair.difference_image(a, a).max()), 0)

class Unlit(unittest.TestCase):
    def test_threshold(self):
        t = strobe_capture.LIT_THRESHOLD
        self.assertEqual(flash_pair.unlit_cameras({1: t + 1, 2: t - 1}), [2])
        self.assertEqual(flash_pair.unlit_cameras({1: t, 2: t}), [])
```

Also move `strobe_pair`'s existing behaviour for `lit_frame` under test: frames list of 6 decoded-able fake MJPEG buffers is overkill - test `lit_frame` with `strobe_capture.decode` patched to identity (`mock.patch.object(strobe_capture, "decode", lambda b: b)`): 5 ambient frames of 30 before `t_fire`, then frames of 30 and 90 after; expect the 90 frame back, ambient 30, rise 60.

- [ ] **Step 2: Run, expect FAIL** - `python -m unittest sp1_vision.tests.test_flash_pair -v` → `ModuleNotFoundError: sp1_vision.flash_pair`.
- [ ] **Step 3: Implement `sp1_vision/flash_pair.py` and switch `strobe_pair.main` to `capture_flash_pair(args.pulse_us, args.exposure, args.gamma)`**; `strobe_pair` keeps its prints, manifest and return codes unchanged and uses `unlit_cameras` for its "NO FLASH" branch.
- [ ] **Step 4: Run, expect PASS** - same command; then the whole suite `python -m unittest discover -s sp1_vision/tests -t .` → no new failures (4 known failures in `test_real_frames` against the 2026-11-10 calibration are pre-existing, CLAUDE.md).
- [ ] **Step 5: Hardware check on the Jetson** - `python3 -m sp1_vision.strobe_pair --out /tmp/fp_check --tape 0 --series t --pulse-us 100` with a ball in place → prints `BALL at Z ...` as before.
- [ ] **Step 6: Commit** - `git add sp1_vision/flash_pair.py sp1_vision/strobe_pair.py sp1_vision/tests/test_flash_pair.py && git commit -m "flash_pair: strobe_pair's flash capture as a reusable function"`

### Task 2: Target and offsets

**Files:**
- Create: `sp1_vision/setup_check.py`
- Test: `sp1_vision/tests/test_setup_check.py`

**Interfaces:**
- Consumes: `stereo_geometry.load_rig`, `camera2_centre_in_camera1`, `ball_pair.BallPair` (`xyz_m`, `uv1`, `uv2`, `radius1_px`, `radius2_px`).
- Produces (all positions in camera 1's frame, metres):
  - `TARGET_DISTANCE_M = 0.50`, `TOLERANCE_MM = 10.0`, `EDGE_MARGIN_PX = 40`
  - `flight_sign(handedness: str) -> int` - `"RH"` → +1, `"LH"` → −1, anything else `ValueError`.
  - `camera_centres(rig) -> {1: np.zeros(3), 2: camera2_centre_in_camera1(rig)}`
  - `rear_camera(rig, handedness) -> int` - the camera whose centre has the smaller `x * flight_sign`.
  - `target_xyz_m(rig, handedness, ball_y_m) -> np.ndarray(3)` - x and z of the rear camera's centre with z + `TARGET_DISTANCE_M`; y = the measured ball's y (height is not checked).
  - `class Offsets` with `along_mm` (ball minus target along the flight direction, i.e. `(x_ball − x_t) * flight_sign * 1000`), `depth_mm` (`(z_ball − z_t) * 1000`, positive = ball too far), `ok: bool` (both `abs() <= TOLERANCE_MM`).
  - `offsets(ball_xyz_m, target_xyz_m, handedness) -> Offsets`
  - `margin_ok(ball, image_size=(1280, 800)) -> bool` - each circle at least `EDGE_MARGIN_PX` inside its image.
  - `advice(off: Offsets) -> list[str]` - German, how to move the **unit** (the ball's spot is fixed): `depth_mm > 0` → `"Einheit {n} mm näher zum Ball schieben"`, `< 0` → `"Einheit {n} mm vom Ball weg schieben"`; `along_mm > 0` → `"Einheit {n} mm in Schlagrichtung schieben"`, `< 0` → `"Einheit {n} mm gegen die Schlagrichtung schieben"`; `n` = rounded absolute mm; a component within tolerance gives no line; both within → `["Passt - innerhalb ±10 mm"]`.

- [ ] **Step 1: Write the failing tests** (rig from the repo: `stereo_geometry.load_rig()`)

```python
def test_rear_camera_by_handedness(self):
    rig = stereo_geometry.load_rig()
    self.assertEqual(setup_check.rear_camera(rig, "RH"), 2)   # cam2 at x = -80 mm
    self.assertEqual(setup_check.rear_camera(rig, "LH"), 1)

def test_target_is_50cm_in_front_of_rear_camera(self):
    rig = stereo_geometry.load_rig()
    c2 = stereo_geometry.camera2_centre_in_camera1(rig)
    t = setup_check.target_xyz_m(rig, "RH", ball_y_m=0.09)
    np.testing.assert_allclose(t, [c2[0], 0.09, c2[2] + 0.50], atol=1e-9)

def test_offset_signs(self):
    t = np.array([0.0, 0.09, 0.50])
    off = setup_check.offsets(np.array([0.008, 0.09, 0.512]), t, "RH")
    self.assertAlmostEqual(off.along_mm, 8.0); self.assertAlmostEqual(off.depth_mm, 12.0)
    self.assertFalse(off.ok)
    self.assertAlmostEqual(setup_check.offsets(np.array([0.008, 0.09, 0.5]), t, "LH").along_mm, -8.0)

def test_tolerance_boundary_and_advice(self):
    t = np.array([0.0, 0.09, 0.50])
    self.assertTrue(setup_check.offsets(np.array([0.010, 0.09, 0.490]), t, "RH").ok)
    off = setup_check.offsets(np.array([-0.0204, 0.09, 0.512]), t, "RH")
    self.assertEqual(setup_check.advice(off),
                     ["Einheit 12 mm näher zum Ball schieben",
                      "Einheit 20 mm gegen die Schlagrichtung schieben"])

def test_unknown_handedness(self):
    with self.assertRaises(ValueError):
        setup_check.flight_sign("rechts")
```

`margin_ok`: a `BallPair` with `uv1=(30, 400), radius1_px=45` → False; `(640, 400), 45` in both → True.

- [ ] **Step 2: Run, expect FAIL** - `python -m unittest sp1_vision.tests.test_setup_check -v` → module not found.
- [ ] **Step 3: Implement `sp1_vision/setup_check.py`** (pure functions, no I/O).
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** - `git commit -m "setup_check: target 50 cm in front of the rear camera, offsets and advice"`

### Task 3: Dashboard page "Aufbau"

**Files:**
- Create: `sp4_gspro/setup_page.py` (blueprint `setup_bp`, same structure as `calibration_page.py`, including its `sys.path` insert)
- Modify: `sp4_gspro/dashboard.py` (register `setup_bp` next to `calibration_bp`, line ~53); `sp4_gspro/look.py` (`header_html`: third nav entry `("setup", "/setup", "Aufbau")`, docstring lists the new key)
- Test: `sp4_gspro/test_setup_page.py`

**Interfaces:**
- Consumes: `flash_pair.capture_flash_pair`, `flash_pair.unlit_cameras`, `ball_pair.find_ball_pair`, `setup_check.*`, `stereo_geometry.load_rig`, `calibration_capture.SESSION.release`.
- Produces:
  - `GET /setup` - page: handedness toggle (RH/LH, remembered in `localStorage` key `lm-setup-hand`, try/catch around it, default RH), button "Messen", result area, the two annotated images side by side.
  - `POST /setup/measure` with JSON `{"handedness": "RH"|"LH"}` → JSON:
    `{"found": bool, "reason": str|null, "unlit": [int], "along_mm": float|null, "depth_mm": float|null, "ok": bool, "margin_ok": bool, "advice": [str], "xyz_mm": [x,y,z]|null, "rear_camera": int, "images": {"1": "<base64 jpeg>", "2": "<base64 jpeg>"}}`
  - `POST /setup/recompute` with `{"handedness"}` → the same JSON from the **last** measurement (kept in a module variable), without firing; `{"error": "noch keine Messung"}` if none (Review Focus 5).
  - Images: the stretched difference image, the found circle in green, the target projected (`cv2.projectPoints` with each camera's K/dist, cam2 via `rig.r`/`rig.t_m`) as a cross + circle of the expected radius in yellow, scaled to 640 px wide.
  - A module-level `threading.Lock`; if it is held, `/setup/measure` returns `{"error": "Messung läuft bereits"}` immediately (non-blocking `acquire(False)`).
  - The capture is a module attribute `_capture = flash_pair.capture_flash_pair`, called as `_capture(pulse_us=100, release=calibration_capture.SESSION.release)`, so tests replace it.

- [ ] **Step 1: Write the failing tests** (Flask test client, `_capture` replaced by a fake returning a `FlashPair` built from two images)

Fixture images: draw a white disc on black at the pixel positions where `ball_pair` would find a ball 0.50 m in front of camera 2 (project the 3D point with each camera's K/dist; radius from `ball_pair.apparent_radius_px`), so `find_ball_pair` succeeds without real frames.

```python
def test_measure_found(self):
    r = self.client.post("/setup/measure", json={"handedness": "RH"}).get_json()
    self.assertTrue(r["found"]); self.assertEqual(r["rear_camera"], 2)
    self.assertLess(abs(r["depth_mm"]), 10); self.assertLess(abs(r["along_mm"]), 10)
    self.assertTrue(r["ok"]); self.assertEqual(set(r["images"]), {"1", "2"})

def test_no_ball_gives_reason_and_no_numbers(self):     # Review Focus 1
    ...fake returns black images...
    r = self.client.post("/setup/measure", json={"handedness": "RH"}).get_json()
    self.assertFalse(r["found"]); self.assertIn("circle", r["reason"])
    self.assertIsNone(r["along_mm"]); self.assertFalse(r["ok"])

def test_unlit_camera(self):                            # Review Focus 4
    ...fake with rises {1: 50, 2: 1}...
    r = self.client.post("/setup/measure", json={"handedness": "RH"}).get_json()
    self.assertEqual(r["unlit"], [2]); self.assertFalse(r["found"]); self.assertIsNone(r["along_mm"])

def test_busy(self):                                    # Review Focus 3
    setup_page._lock.acquire()
    try:
        r = self.client.post("/setup/measure", json={"handedness": "RH"}).get_json()
        self.assertEqual(r["error"], "Messung läuft bereits")
    finally:
        setup_page._lock.release()

def test_recompute_switches_rear_camera(self):          # Review Focus 5
    self.client.post("/setup/measure", json={"handedness": "RH"})
    r = self.client.post("/setup/recompute", json={"handedness": "LH"}).get_json()
    self.assertEqual(r["rear_camera"], 1); self.assertFalse(r["ok"])   # ball is 80 mm off for LH

def test_page_and_nav(self):
    html = self.client.get("/setup").get_data(as_text=True)
    self.assertIn("Aufbau", html); self.assertIn('href="/setup"', html)
```

- [ ] **Step 2: Run on the Jetson, expect FAIL** - `cd sp4_gspro && python3 -m unittest test_setup_page -v` → `ModuleNotFoundError: setup_page`.
- [ ] **Step 3: Implement `setup_page.py`, register it, add the nav entry.** The `unlit` check comes before `find_ball_pair`; `find_ball_pair` gets the two difference images as BGR, as `strobe_pair` does.
- [ ] **Step 4: Run, expect PASS**; also `python3 -m unittest test_dashboard_api` still passes (nav change).
- [ ] **Step 5: Commit** - `git commit -m "Dashboard: Aufbau page - one flash, ball offset from the target, how to move the unit"`

### Task 4: On the device

**Files:**
- Modify: `sp1_vision/strobe_runs/README.md` (short entry), `CLAUDE.md` ("Current task": the page exists, target 50 cm / rear camera)

- [ ] **Step 1:** Deploy to the Jetson (push from Windows, pull on the Jetson as in memory `jetson_ssh_access`), `sudo systemctl restart jetson-lm-dashboard`.
- [ ] **Step 2:** Ball on the floor, tape from camera 2's lens front to the ball centre 50 cm minus the lens-to-optical-centre offset (record what was measured). Press "Messen" for RH: expect `|depth_mm|`, `|along_mm|` within ~10 mm of the tape. Move the ball 20 mm in flight direction: `along_mm` changes by +20 ± 3 and the advice says "in Schlagrichtung". LH: rear camera 1, the ball now ~80 mm off.
- [ ] **Step 3:** Repeat "Messen" three times without touching anything: spread of each offset ≤ 3 mm (else the tolerance is meaningless - report, do not tune).
- [ ] **Step 4:** Commit the README/CLAUDE.md notes with the measured numbers.
