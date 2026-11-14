# Ball-marking stencil

Two half-shells that close round a golf ball so its 20 spin marks can be
drawn through the cutouts in one go, at exactly the positions the spin
analysis expects. Design: `docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md`.

| File | What |
|---|---|
| `stencil_upper.step`, `stencil_lower.step` | the halves as exact CAD solids (edit these, e.g. in Shapr3D) |
| `stencil_upper.stl`, `stencil_lower.stl` | for printing, ~5,700 triangles each |
| `make_stencil.py` | generates all four from the mark map |
| `check_stencil.py` | checks the generated files |
| `../../sp1_vision/ball_marks/marks_table.md`, `marks_drawing.svg` | where every mark sits, its shape and direction |

Geometry: inner Ø 42.9 mm (ball 42.67 mm), wall 1.5 mm, cutouts chamfered
1.0 mm towards the outside, flange at the seam Ø 53.9 mm × 2 mm per half,
3 alignment holes Ø 1.9 mm through both flanges. Marks: 5 dots (Ø 7 mm),
10 bars (11 × 3.5 mm, each along the edge to a neighbouring mark), 5 crosses
(arms 10 × 3.5 mm); 10 per half, none closer than 1.5 mm to the seam.

## Printing

- Both halves **flange face down** on the bed (the lower half is modelled
  flange-up: flip it in the slicer). No supports needed for the flange; the
  dome prints as an overhang-free shell from the flange upwards.
- Alignment pins: three ~4 mm pieces of **1.75 mm filament**, pushed into the
  holes of one half.

## Marking a ball

1. Ball into the lower half. Turn it so the **factory print sits between
   cutouts** as far as possible (print is dark at 850 nm too; the analysis
   ignores dark blobs that do not fit the map, but a mark on top of a logo is
   lost).
2. Upper half on, pins in their holes, a rubber band (or tape) round the
   flange so nothing moves.
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
