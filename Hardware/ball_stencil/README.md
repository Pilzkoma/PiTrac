# Ball-marking stencil

Two half-shells that close round a golf ball so its 20 spin marks can be
drawn through the cutouts in one go, at exactly the positions the spin
analysis expects. Design: `docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md`.

| File | What |
|---|---|
| `stencil_upper.step`, `stencil_lower.step` | the halves as exact CAD solids (edit these, e.g. in Shapr3D) |
| `stencil_upper.stl`, `stencil_lower.stl` | for printing, ~5,700 triangles each |
| `make_stencil.py` | generates all four from the mark map (chamfer defect, see below) |
| `check_stencil.py` | checks the generated files |
| `../../sp1_vision/ball_marks/marks_table.md`, `marks_drawing.svg` | where every mark sits, its shape and direction |

**Status 2026-11-18.** The map now asks for a 1.5 mm chamfer (the thick
marker did not reach everything at 1.0 mm). The STEP/STL files here are
still the 2026-11-14 generation with 1.0 mm, and `make_stencil.py` makes the
chamfer only about half as wide as asked on the outer surface (known defect,
written up in `_cutout`). The stencil actually printed and used is the
owner's own CAD edit of these files with wider chamfers; all mark positions
and the ink outlines are unchanged, so balls marked with either version
match the map.

Geometry: inner Ø 42.9 mm (ball 42.67 mm), wall 1.5 mm, cutouts chamfered
1.5 mm (map; see status) towards the outside, flange at the seam Ø 53.9 mm × 2 mm per half,
3 alignment holes Ø 1.9 mm through both flanges at **0°, 100°, 220°** — not
evenly spaced on purpose: the mark layout is 3-fold symmetric, so with even
spacing the halves would also close turned by 120° and the upper ten marks
would land in the wrong places. Now they close only one way. Each cutout is
cut as a cone from the ball centre through the mark outline, so the ink on
the ball is exactly the outline in the map (projected onto the ball). Marks: 5 dots (Ø 7 mm),
10 bars (11 × 3.5 mm, each along the edge to a neighbouring mark), 5 crosses
(arms 10 × 3.5 mm); 10 per half, none closer than 1.5 mm to the seam.

## Printing

- A hemispherical shell has overhangs beyond 45° in any orientation, so
  **supports are needed**. Recommended: each half **dome down** (apex on the
  bed, flange up) with tree supports — they then touch only the outside and
  the underside of the flange, and the inside, where the ball sits, stays
  clean. (Flange-down also works but puts supports inside the dome.) Not
  test-printed yet; check the fit with a ball before marking.
- Alignment pins: three ~4 mm pieces of **1.75 mm filament**, pushed into the
  holes of one half.

## Marking a ball

1. Ball into the lower half. Turn it so the **logos sit between cutouts**
   (print is dark at 850 nm too; a mark touching a logo is lost). The thin
   alignment line between the logos may run through cutouts: the analysis
   strips anything thinner than ~2 mm (tested 2026-11-18,
   `sp1_vision/strobe_runs/2026-11-18_thin_print/`).
2. Upper half on so all **three** pins go into holes (it only fits one way),
   a rubber band (or tape) round the flange so nothing moves.
3. Fill **every cutout completely** with the **3 mm Edeka permanent marker**
   (the only pen tested that stays dark at 850 nm). Go round the edges of
   each cutout, then fill.
4. Let it dry a few minutes before opening, so nothing smears.
5. Same stencil, same way, for all 5 balls.

## Regenerating

From the repo root, after changing the mark map
(`python -m sp1_vision.ball_marks_design`):

```
"C:\Users\lasse\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe" Hardware/ball_stencil/make_stencil.py
"C:\Users\lasse\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe" Hardware/ball_stencil/check_stencil.py
```

The check prints `CHECK OK` or `CHECK FAILED` — read that line; `freecadcmd`
returns exit code 0 either way. FreeCAD 1.1.4 (installed 2026-11-14 via
`winget install --id FreeCAD.FreeCAD`).
