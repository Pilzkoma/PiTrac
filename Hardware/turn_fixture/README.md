# Hand-turn fixture

Holds the owner's 15° turntable disc (`../ball_stencil/drehscheibe.step`) so a
marked ball can be turned by known angles about **three** axes. This is acceptance 2 of
`docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md`: known turns, both signs,
about different axes. The disc on its own only turns about the vertical, and that
leaves sign and axis errors in the two horizontal directions untested.

| File | What |
|---|---|
| `plate.step/.stl` | square plate 136 × 136 × 7.2 mm, pocket the disc turns in (Ø 100.6, rim bearing), push-out hole in the floor |
| `cover.step/.stl` | frame over the disc's rim (holds it in the pocket upright), detent tongue at the top edge |
| `cup.step/.stl` | ball seat; 45° spigot that self-centres in the disc's central countersink |
| `stand.step/.stl` | base with a slot the plate + cover stand in (disc axis horizontal, 72 mm above the floor) |
| `make_fixture.py` | generates all of them (FreeCAD, headless) |
| `check_fixture.py` | checks them against `drehscheibe.step` |

## Detent

The tongue's tip is a fork with a 2.3 mm slot that straddles one of the disc's 2 mm
ticks: **±0.19° of play** (checked). Turned 1.5° off the detent, the tick runs into the
prong. The prongs' outer bottom edges are bevelled, so a tick turned towards the fork
climbs it and drops into the slot by itself.
**To turn: lift the tongue by its nub, turn, let go. It clicks in at the next tick.**
Every click is 15°. The disc's labels (every 45°) next to the tongue show where you are.

If your printed ticks come out wider than ~2.2 mm and do not drop into the slot,
raise `SLOT_W` in `make_fixture.py` and regenerate. The same applies to the pocket
(`POCKET_R`) if the disc does not turn freely.

## Printing

No supports needed. Dark filament if possible: under the 850 nm flash a bright plate
behind the ball costs contrast.
- plate: back down
- cover: flat side down (the nub up)
- cup: spigot down, with a brim (the spigot is small)
- stand: base down
- pins: six ~8 mm pieces of **1.75 mm filament** through cover and plate
  (4 corners, 2 beside the tongue's root)

## Assembly

1. Disc into the pocket, ticks up. It must turn freely.
2. Cover on, tongue over the tick ring, pins in.
3. Cup into the disc's central countersink and **glue it** (a drop of superglue).
   It must not slip on the disc, or the angles are lost. Turn the disc by the cup or
   the ticks, never by the ball.
4. Ball into the bowl with a pea of adhesive putty (Patafix/Blu-Tack). The ball rests
   on the rim, and the putty sits in the gap underneath.

## The three positions

Ball about 44 cm in front of the cameras, as in the static run of 2026-11-21.

| Position | Disc axis | How |
|---|---|---|
| **flat** | vertical (hook/slice-like) | plate on the floor, tongue edge **away** from the cameras; ball centre ~38 mm above the floor |
| **facing** | horizontal, towards the cameras | plate in the stand, disc face towards the cameras; ball centre ~72 mm up |
| **side-on** | horizontal, across the line of sight | same, stand turned 90° on the floor |

**Side-on:** the plate must not stand between a camera and the ball. Put the ball in
front of the camera nearer the plate, with the plate on the side **away from the other
camera**. A camera more than ~29 mm to the plate's side of the ball looks at the plate's back.

Square the plate or stand against a line of tape. The axis direction is then good to
about ±2–3°, which is enough for the sign checks. The angles themselves come from the
detent.

## Regenerating

From the repo root:

```
"C:\Users\lasse\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe" Hardware/turn_fixture/make_fixture.py
"C:\Users\lasse\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe" Hardware/turn_fixture/check_fixture.py
```

Read the `CHECK OK` / `CHECK FAILED` line: `freecadcmd` returns exit code 0 either way.
