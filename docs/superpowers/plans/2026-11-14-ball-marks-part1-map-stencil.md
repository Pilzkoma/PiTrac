# Ball Marks Part 1 — Mark Map and Stencil Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One committed mark-map file (20 dodecahedron sites, dot/bar/cross,
identifiable from any site plus two neighbours) and, generated from it, a
two-half-shell stencil as real STEP files (FreeCAD), plus a site table and a
drawing, so the owner can print the stencil and mark 5 balls.

**Architecture:** All geometry and the shape assignment live in pure-numpy
`sp1_vision/ball_marks.py` (unit-tested with the rest of `sp1_vision`). A CLI
writes the map JSON, a Markdown table and an SVG drawing. A thin FreeCAD
script reads only the JSON (site frames and cutout outlines precomputed in
mm) and builds, checks and exports the half-shells. Parts 2-4 of the spec
(detection/orientation, offset trigger, spin) get their own plans and read
the same JSON.

**Tech Stack:** Python 3.14 + numpy (Windows box), `unittest`; FreeCAD
(headless `FreeCADCmd`, owner-approved for the STEP) for the CAD.

**Spec:** `docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md`

## Global Constraints

- No new libraries beyond FreeCAD (approved 2026-11-14). numpy only in `ball_marks.py`.
- Real STEP from FreeCAD B-rep, **never** converted from an STL; any STL < 10,000 triangles per half.
- 20 sites = vertices of a regular dodecahedron, **vertex-up**: one site on +Z; heights ±1, ±0.745, ±0.333; 10 per half; seam = plane z = 0.
- Shapes: dot, bar, cross, drawn with a 3 mm marker; sizes: dot Ø 7.0 mm, bar 11.0 × 3.5 mm, cross arms 10.0 × 3.5 mm.
- Identification rule: every ordered V (site c plus two consecutive neighbours a, b, counter-clockwise seen from outside) has a unique signature (definition in Task 2).
- Shell: inner Ø 42.9 mm, wall 1.5 mm, cutouts chamfered outward by 1.0 mm (outline offset at the outer surface).
- The map JSON is the single source for the stencil and for the analysis of parts 2-4.
- Tests: `python -m unittest sp1_vision.tests.test_ball_marks` from the repo root (Windows: `python`, not `python3`).
- Jetson not needed for this plan.

## Review Focus

- A cutout that crosses the seam would be split between the halves → test: every outer outline point stays ≥ 1.0 mm from z = 0 (Task 3).
- Neighbouring cutouts merging or leaving a hair-thin bridge → test: ≥ 3.0 mm between outer outlines of any two sites, measured on the outer sphere (Task 3).
- Mirror confusion (CCW vs CW): a camera sees the outside of the ball, never a mirror → test: the mirrored map (x → −x) does not reproduce the same signatures site-for-site (Task 2).
- A slot the 3 mm marker cannot reach into → test: narrowest cutout width at the ball surface ≥ 3.5 mm (Task 3).
- STL too dense for Shapr3D → verification: triangle count per half < 10,000 printed by the FreeCAD check (Task 4).

---

### Task 1: Dodecahedron sites, neighbours, tangent frames

**Files:**
- Create: `sp1_vision/ball_marks.py`
- Test: `sp1_vision/tests/test_ball_marks.py`

**Interfaces:**
- Produces:
  - `dodecahedron_sites() -> np.ndarray` shape (20, 3), unit vectors, vertex-up (site 0 at +Z), sorted by descending z then by azimuth.
  - `neighbours(sites: np.ndarray) -> list[tuple[int, int, int]]` — the 3 neighbours of each site, **ordered counter-clockwise seen from outside** (looking along −n at the ball).
  - `tangent_frame(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]` — (north, east) unit vectors in the tangent plane at n; north = projection of +Z, or +X at the two poles (|n_z| > 0.999); east = north × n, so that east × north = n (right-handed, seen from outside: east to the right of north).

- [ ] **Step 1: Write the failing tests**

```python
class Sites(unittest.TestCase):
    def test_twenty_unit_vectors_vertex_up(self):
        s = bm.dodecahedron_sites()
        self.assertEqual(s.shape, (20, 3))
        np.testing.assert_allclose(np.linalg.norm(s, axis=1), 1.0, atol=1e-12)
        np.testing.assert_allclose(s[0], [0, 0, 1], atol=1e-12)
        heights = np.round(np.abs(s[:, 2]), 3).tolist()
        self.assertEqual((heights.count(1.0), heights.count(0.745), heights.count(0.333)), (2, 6, 12))
        self.assertEqual(int((s[:, 2] > 0).sum()), 10)
        self.assertAlmostEqual(float(np.min(np.abs(s[:, 2]))), 1 / 3, places=6)

    def test_three_neighbours_at_the_edge_angle(self):
        s = bm.dodecahedron_sites()
        nb = bm.neighbours(s)
        edge = np.degrees(np.arccos(np.sqrt(5) / 3))      # 41.81 deg
        for i, trio in enumerate(nb):
            self.assertEqual(len(set(trio)), 3)
            for j in trio:
                self.assertAlmostEqual(np.degrees(np.arccos(s[i] @ s[j])), edge, places=6)
                self.assertIn(i, nb[j])

    def test_neighbours_run_counter_clockwise_from_outside(self):
        s = bm.dodecahedron_sites()
        for i, (a, b, c) in enumerate(bm.neighbours(s)):
            # (a - n) x (b - n) points outward for CCW seen from outside
            self.assertGreater(np.cross(s[a] - s[i], s[b] - s[i]) @ s[i], 0)

    def test_tangent_frame_is_right_handed_and_tangent(self):
        for n in bm.dodecahedron_sites():
            north, east = bm.tangent_frame(n)
            self.assertAlmostEqual(north @ n, 0, places=12)
            self.assertAlmostEqual(east @ n, 0, places=12)
            np.testing.assert_allclose(np.cross(east, north), n, atol=1e-12)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m unittest sp1_vision.tests.test_ball_marks -v`
Expected: ERROR, `module 'sp1_vision.ball_marks' has no attribute ...` / import error.

- [ ] **Step 3: Implement the three functions**

Vertices: the 20 points (±1, ±1, ±1), (0, ±1/φ, ±φ), (±1/φ, ±φ, 0), (±φ, 0, ±1/φ), normalised, then rotated so one vertex goes to +Z (Rodrigues rotation taking (1,1,1)/√3 to +Z). Neighbours: the three nearest by angle, then sorted by azimuth in the site's tangent frame so the order is CCW seen from outside.

- [ ] **Step 4: Run the tests to see them pass**

Run: `python -m unittest sp1_vision.tests.test_ball_marks -v`
Expected: 4 tests OK.

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/ball_marks.py sp1_vision/tests/test_ball_marks.py
git commit -m "ball_marks: dodecahedron sites, CCW neighbours, tangent frames"
```

---

### Task 2: Shape symbols, V signatures, shape assignment

**Files:**
- Modify: `sp1_vision/ball_marks.py`
- Test: `sp1_vision/tests/test_ball_marks.py`

**Interfaces:**
- Consumes: Task 1 functions.
- Produces:
  - `@dataclass(frozen=True) class Mark: site: int; shape: str  # "dot" | "bar" | "cross"; bar_to: int | None  # neighbour the bar is aligned with, bars only`
  - `relative_symbol(marks, nb, x: int, ref: int) -> str` — `"dot"`, `"cross"`, or for a bar `"bar0"` (aligned with the edge x→ref), `"bar+"` (aligned with the edge to the neighbour following ref CCW), `"bar-"` (the remaining neighbour).
  - `v_signature(marks, nb, c: int, a: int, b: int) -> tuple[str, str, str]` = `(relative_symbol(c, ref=a), relative_symbol(a, ref=c), relative_symbol(b, ref=c))`, for b following a CCW round c.
  - `all_v_signatures(marks, nb) -> list[tuple[int, int, int, tuple]]` — all 60 ordered V's (c, a, b, signature): for each c, the pairs (n1,n2), (n2,n3), (n3,n1).
  - `assign_marks(seed: int = 0) -> list[Mark]` — deterministic search (random restarts + local repair is fine) until all 60 signatures are distinct; at least 5 of each shape.

The camera sees the outside of the ball, so CCW order is observable and the
centre of a V is the mark adjacent to both others (42° vs 69° apart); a bar
is symmetric, so "aligned with an edge" is the only bar state.

- [ ] **Step 1: Write the failing tests**

```python
class Signatures(unittest.TestCase):
    def setUp(self):
        self.s = bm.dodecahedron_sites()
        self.nb = bm.neighbours(self.s)
        self.marks = bm.assign_marks(seed=0)

    def test_every_v_signature_is_unique(self):
        sigs = [sig for _, _, _, sig in bm.all_v_signatures(self.marks, self.nb)]
        self.assertEqual(len(sigs), 60)
        self.assertEqual(len(set(sigs)), 60)

    def test_shapes_are_balanced_and_bars_point_at_neighbours(self):
        shapes = [m.shape for m in self.marks]
        for kind in ("dot", "bar", "cross"):
            self.assertGreaterEqual(shapes.count(kind), 5)
        for m in self.marks:
            if m.shape == "bar":
                self.assertIn(m.bar_to, self.nb[m.site])
            else:
                self.assertIsNone(m.bar_to)

    def test_the_search_is_deterministic(self):
        self.assertEqual(bm.assign_marks(seed=0), self.marks)

    def test_a_mirrored_ball_does_not_read_the_same(self):
        # mirror x -> -x: neighbour order flips; at least one V must change
        mirrored = self.s * np.array([-1, 1, 1])
        nb_m = bm.neighbours(mirrored)
        sigs = {(c, a, b): sig for c, a, b, sig in bm.all_v_signatures(self.marks, self.nb)}
        sigs_m = {(c, a, b): sig for c, a, b, sig in bm.all_v_signatures(self.marks, nb_m)}
        self.assertNotEqual(set(sigs.values()), set(sigs_m.values()))
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m unittest sp1_vision.tests.test_ball_marks.Signatures -v`
Expected: ERROR, missing `assign_marks`.

- [ ] **Step 3: Implement `Mark`, `relative_symbol`, `v_signature`, `all_v_signatures`, `assign_marks`**

- [ ] **Step 4: Run all ball_marks tests**

Run: `python -m unittest sp1_vision.tests.test_ball_marks -v`
Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/ball_marks.py sp1_vision/tests/test_ball_marks.py
git commit -m "ball_marks: dot/bar/cross assignment, unique V signatures"
```

---

### Task 3: Cutout outlines, geometry checks, map file, table and drawing

**Files:**
- Modify: `sp1_vision/ball_marks.py`
- Create: `sp1_vision/ball_marks_design.py` (CLI), `sp1_vision/ball_marks/ball_mark_map.json`, `sp1_vision/ball_marks/marks_table.md`, `sp1_vision/ball_marks/marks_drawing.svg` (all three generated, committed)
- Test: `sp1_vision/tests/test_ball_marks.py`

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces:
  - Constants: `BALL_DIAMETER_MM = 42.67`, `SHELL_INNER_DIAMETER_MM = 42.9`, `SHELL_WALL_MM = 1.5`, `CHAMFER_MM = 1.0`, `DOT_DIAMETER_MM = 7.0`, `BAR_MM = (11.0, 3.5)`, `CROSS_MM = (10.0, 3.5)`.
  - `cutout_outline_mm(mark: Mark, sites, nb, offset_mm: float = 0.0) -> np.ndarray` — closed polygon (k, 2) in the site's tangent frame (columns east, north), at the surface, grown by `offset_mm`; bars along the great-circle direction to `bar_to`; cross arms along north/east; dot as a 32-gon.
  - `outline_3d(mark, sites, nb, radius_mm: float, offset_mm: float = 0.0) -> np.ndarray` — (k, 3) points on the plane tangent at `radius_mm` (n·radius + e·east + n_·north).
  - `write_map(path, marks, sites, nb) -> None`, `read_map(path) -> dict`. JSON: `{"version": 1, "frame": "stencil, +Z = vertex-up axis, seam z=0", "ball_diameter_mm", "shell": {inner_diameter_mm, wall_mm, chamfer_mm}, "sites": [{"id", "normal": [x,y,z], "azimuth_deg", "elevation_deg", "half": "upper"|"lower", "shape", "bar_to", "bar_angle_deg" (from north toward east, bars only), "north": [..], "east": [..], "outline_mm": [[e,n],...], "outline_outer_mm": [[e,n],...] }]}`.
  - CLI: `python -m sp1_vision.ball_marks_design [--seed 0] [--out sp1_vision/ball_marks]` writes the JSON, a Markdown table (id, half, azimuth, elevation, shape, bar angle, neighbours) and an SVG with two orthographic views (upper half seen from +Z, lower from −Z), each site drawn at its outline and labelled with its id.

- [ ] **Step 1: Write the failing tests**

```python
class Geometry(unittest.TestCase):
    def setUp(self):
        self.s = bm.dodecahedron_sites()
        self.nb = bm.neighbours(self.s)
        self.marks = bm.assign_marks(seed=0)
        self.r_out = bm.SHELL_INNER_DIAMETER_MM / 2 + bm.SHELL_WALL_MM

    def test_no_cutout_reaches_the_seam(self):
        for m in self.marks:
            pts = bm.outline_3d(m, self.s, self.nb, self.r_out, bm.CHAMFER_MM)
            self.assertGreaterEqual(float(np.min(np.abs(pts[:, 2]))), 1.0, m)

    def test_cutouts_keep_three_mm_apart(self):
        outer = {m.site: bm.outline_3d(m, self.s, self.nb, self.r_out, bm.CHAMFER_MM)
                 for m in self.marks}
        for i in range(20):
            for j in self.nb[i]:
                d = np.linalg.norm(outer[i][:, None, :] - outer[j][None, :, :], axis=2)
                self.assertGreaterEqual(float(d.min()), 3.0, (i, j))

    def test_the_marker_fits_every_cutout(self):
        for m in self.marks:
            poly = bm.cutout_outline_mm(m, self.s, self.nb)
            width = min(np.ptp(poly @ np.array([np.cos(a), np.sin(a)]))
                        for a in np.linspace(0, np.pi, 180, endpoint=False))
            self.assertGreaterEqual(width, 3.5 - 1e-6, m)

    def test_map_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "map.json")
            bm.write_map(p, self.marks, self.s, self.nb)
            m = bm.read_map(p)
        self.assertEqual(len(m["sites"]), 20)
        self.assertEqual(sum(x["half"] == "upper" for x in m["sites"]), 10)
        self.assertEqual([x["shape"] for x in m["sites"]], [k.shape for k in self.marks])

    def test_the_cli_writes_all_three_files(self):
        with tempfile.TemporaryDirectory() as d:
            ball_marks_design.main(["--out", d])
            for name in ("ball_mark_map.json", "marks_table.md", "marks_drawing.svg"):
                self.assertTrue(os.path.getsize(os.path.join(d, name)) > 0, name)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m unittest sp1_vision.tests.test_ball_marks.Geometry -v`
Expected: ERROR, missing `outline_3d` / module `ball_marks_design`.

- [ ] **Step 3: Implement the constants, outlines, map I/O and the CLI**

If `test_cutouts_keep_three_mm_apart` or the seam test fails for the seed-0 assignment, make `assign_marks` also reject assignments whose outlines violate them (same search), rather than shrinking the shapes.

- [ ] **Step 4: Run all ball_marks tests**

Run: `python -m unittest sp1_vision.tests.test_ball_marks -v`
Expected: all OK.

- [ ] **Step 5: Generate the committed map, table and drawing; look at the SVG**

Run: `python -m sp1_vision.ball_marks_design --seed 0 --out sp1_vision/ball_marks`
Expected: three files written; the SVG shows 10 marks per view, none touching the rim circle, all labelled.

- [ ] **Step 6: Commit**

```bash
git add sp1_vision/ball_marks.py sp1_vision/ball_marks_design.py sp1_vision/ball_marks sp1_vision/tests/test_ball_marks.py
git commit -m "ball_marks: cutout outlines, geometry checks, map JSON, table and drawing"
```

---

### Task 4: FreeCAD half-shell stencil as STEP (and light STL), marking instructions

**Files:**
- Create: `Hardware/ball_stencil/make_stencil.py` (runs under `FreeCADCmd`), `Hardware/ball_stencil/check_stencil.py` (runs under `FreeCADCmd`), `Hardware/ball_stencil/README.md`
- Create (generated, committed): `Hardware/ball_stencil/stencil_upper.step`, `stencil_lower.step`, `stencil_upper.stl`, `stencil_lower.stl`
- Modify: `LOGBOOK.md` (session notes), `CLAUDE.md` (Next list, item 4)

**Interfaces:**
- Consumes: `sp1_vision/ball_marks/ball_mark_map.json` (Task 3) — only the JSON; no import of `sp1_vision`.

Geometry (values pinned): shell = sphere R 21.45 + 1.5 minus sphere R 21.45, split at z = 0; a flange ring at the seam on each half (outer radius R_out + 4 mm, 2 mm thick); 3 pins Ø 3.0 × 3.0 mm on the lower flange at azimuth 0/120/240°, matching holes Ø 3.3 in the upper flange; one cutout per site of that half = loft from `outline_mm` placed on the tangent plane at R 21.45 − 0.5 to `outline_outer_mm` on the plane at R 22.95 + 0.5, subtracted. Band notches or a lip: builder's call, keep it printable without supports on the flange face.

- [ ] **Step 1: Install FreeCAD (owner-approved)**

Run: `winget install --id FreeCAD.FreeCAD -e --accept-package-agreements --accept-source-agreements`
Expected: installed; locate `FreeCADCmd.exe` (record its path in the README).

- [ ] **Step 2: Write `check_stencil.py`**

Reads both STEP files back and the JSON, prints and asserts: each shape `isValid()`; volume of each half within ±15 % of (shell half + flange − Σ cutout prism volumes) computed from the JSON outlines; bounding box diameter = 2·(R_out + 4) ± 0.1 mm; each STL < 10,000 triangles. Exit code ≠ 0 on any failure.

- [ ] **Step 3: Run the check before the generator exists**

Run: `"<FreeCADCmd.exe>" Hardware/ball_stencil/check_stencil.py`
Expected: FAIL (STEP files missing).

- [ ] **Step 4: Write `make_stencil.py`**

Builds both halves as above with `Part` (sphere, cut, loft via `Part.makeLoft([wire_in, wire_out], True)`), exports `exportStep` per half, and meshes with `MeshPart.meshFromShape(shape, LinearDeflection=…, AngularDeflection=…)` choosing the deflection so each STL stays < 10,000 triangles.

- [ ] **Step 5: Generate and check**

Run: `"<FreeCADCmd.exe>" Hardware/ball_stencil/make_stencil.py` then `"<FreeCADCmd.exe>" Hardware/ball_stencil/check_stencil.py`
Expected: four files written; check prints valid shapes, volumes within tolerance, triangle counts < 10,000, exit 0.

- [ ] **Step 6: README with marking instructions**

How to regenerate (both commands), print notes (flange face down), and marking: ball into the lower half with the factory print between cutouts where possible, upper half on, pins in, band round; fill each cutout completely with the 3 mm Edeka permanent marker; let dry before opening; the same stencil for all 5 balls.

- [ ] **Step 7: Docs and commit**

LOGBOOK session entry and CLAUDE.md "Next" item 4 updated (part 1 done, files, what the owner does next).

```bash
git add Hardware/ball_stencil LOGBOOK.md CLAUDE.md
git commit -m "Ball stencil: FreeCAD half-shells as STEP + light STL from the mark map"
```

---

## After this plan

Owner prints the stencil and marks 5 balls. Part 2 (mark detection and ball
orientation, validated by hand turns incl. sign checks) gets its own plan and
reads `sp1_vision/ball_marks/ball_mark_map.json`.
