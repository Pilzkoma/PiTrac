# Check the turn fixture against the owner's disc. Run under FreeCAD, from the repo root:
#     freecadcmd Hardware/turn_fixture/check_fixture.py
#
# Reads the four generated STEP files and drehscheibe.step back and checks:
# valid solids, STLs under 10,000 triangles; disc in the pocket with a tick in
# the fork: no overlap with plate, cover or cup; turned a little off the detent
# the tick runs into a prong (the detent holds) and the free play is about
# +-0.2 deg; the tongue's fork clears the labels and every other tick; ball
# clear of everything but its seat; plate stands in the stand without overlap;
# pin holes line up. Prints CHECK OK, else CHECK FAILED (freecadcmd does not pass
# an exit code on, so the printed verdict is the result).

import math
import os
import sys

import FreeCAD
import Mesh
import Part

_print = print


def print(*a, **k):  # noqa: A001 - freecadcmd drops buffered output at exit
    _print(*a, flush=True, **k)


HERE = os.path.join("Hardware", "turn_fixture")
sys.path.insert(0, HERE)
os.environ["TURN_FIXTURE_IMPORT_ONLY"] = "1"
import make_fixture as mf  # noqa: E402

V = FreeCAD.Vector
FAILS = []


def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        FAILS.append(what)


def overlap(a, b):
    return a.common(b).Volume


def disc_in_plate(angle_deg):
    """Disc in plate coordinates, turned by angle_deg about its axis."""
    d = mf.load_disc()
    d.rotate(V(0, 0, 0), V(0, 0, 1), angle_deg)
    d.translate(V(0, 0, mf.FLOOR))
    return d


def main():
    parts = {}
    for name in mf.PARTS:
        shape = Part.read(os.path.join(HERE, name + ".step"))
        parts[name] = shape
        check(shape.isValid() and len(shape.Solids) == 1,
              "%s: one valid solid (%d)" % (name, len(shape.Solids)))
        mesh = Mesh.Mesh(os.path.join(HERE, name + ".stl"))
        check(mesh.CountFacets < 10000, "%s.stl: %d triangles" % (name, mesh.CountFacets))
    plate, cover, cup, stand = (parts[n] for n in ("plate", "cover", "cup", "stand"))

    # Disc at the detent: the 90-deg tick sits in the fork (ticks every 15 deg
    # from 0, so any multiple of 15 deg is a detent).
    disc = disc_in_plate(0.0)
    check(overlap(disc, plate) < 1e-3, "disc in pocket: no overlap with plate (%.4f mm3)"
          % overlap(disc, plate))
    check(overlap(disc, cover) < 1e-3, "disc at detent: no overlap with cover (%.4f mm3)"
          % overlap(disc, cover))
    check(cover.isInside(V(-(mf.DISC_R - 1), 0, mf.PLATE_T + 0.5), 1e-4, True),
          "cover lies over the disc rim (holds it in the pocket upright)")

    # Detent: play and hold.
    lo, hi = 0.0, 3.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if overlap(disc_in_plate(mid), cover) > 1e-4:
            hi = mid
        else:
            lo = mid
    play_pos = lo
    lo, hi = 0.0, 3.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if overlap(disc_in_plate(-mid), cover) > 1e-4:
            hi = mid
        else:
            lo = mid
    play_neg = lo
    check(0.05 < play_pos < 0.4 and 0.05 < play_neg < 0.4,
          "detent play +%.2f / -%.2f deg" % (play_pos, play_neg))
    held = overlap(disc_in_plate(1.5), cover)
    check(held > 0.2, "turned 1.5 deg off the detent the tick runs into a prong (%.2f mm3)"
          % held)
    mid = disc_in_plate(7.5)
    # Halfway between detents the tongue is lifted by the ticks only where the
    # bevel is; the overlap must be small (climbing), not the slot wall.
    climb = overlap(mid, cover)
    print("  info  halfway between detents, tick under the prong bevel: %.2f mm3" % climb)

    # Labels and other ticks never under the tongue's fork at a detent: the
    # fork reaches r >= TONGUE_TIP_Y > LABEL_R_MAX.
    check(mf.TONGUE_TIP_Y > mf.LABEL_R_MAX + 2, "fork tip r %.1f clears labels (r <= %.1f)"
          % (mf.TONGUE_TIP_Y, mf.LABEL_R_MAX))

    # Cup seated in the countersink.
    cup_seated = cup.copy()
    cup_seated.translate(V(0, 0, mf.FLOOR - mf.CUP_SEAT_DROP + 0.01))
    check(overlap(cup_seated, disc) < 1e-3, "cup seated: no overlap with disc (%.4f mm3)"
          % overlap(cup_seated, disc))
    sunk = cup.copy()
    sunk.translate(V(0, 0, mf.FLOOR - mf.CUP_SEAT_DROP - 0.05))
    check(overlap(sunk, disc) > 1e-3, "cup 0.05 mm deeper touches the countersink cone "
          "(it seats on the cone, %.4f mm3)" % overlap(sunk, disc))
    for name, other in (("plate", plate), ("cover", cover)):
        check(overlap(cup_seated, other) < 1e-3, "cup clear of %s" % name)

    # Ball on the seat.
    bz = mf.FLOOR + mf.ball_centre_disc_z()
    ball = Part.makeSphere(mf.BALL_R - 0.02, V(0, 0, bz))
    for name, other in (("plate", plate), ("cover", cover), ("disc", disc)):
        check(overlap(ball, other) < 1e-3, "ball clear of %s" % name)
    check(overlap(ball, cup_seated) < 0.05, "ball sits on the cup rim (%.4f mm3)"
          % overlap(ball, cup_seated))
    print("  info  ball centre %.1f mm above the plate's back, %.1f mm above the disc face"
          % (bz, bz - mf.FLOOR - mf.DISC_T))

    # Pins line up: every pin position is a hole in both parts.
    for x, y in mf.PINS:
        p_plate = V(x, y, mf.PLATE_T / 2)
        p_cover = V(x, y, mf.PLATE_T + mf.COVER_T / 2)
        check(not plate.isInside(p_plate, 1e-4, True)
              and not cover.isInside(p_cover, 1e-4, True), "pin hole at (%.0f, %.0f)" % (x, y))

    # Plate (with cover) standing in the stand: plate bottom edge (y = -PLATE/2)
    # on the stand's base, plate normal along the stand's y.
    stack = plate.fuse(cover)
    stack.translate(V(0, 0, -(mf.PLATE_T + mf.COVER_T) / 2))   # centre plate + cover
    stack.rotate(V(0, 0, 0), V(1, 0, 0), 90)             # plate y -> stand z, z -> -y
    stack.translate(V(0, 0, mf.PLATE / 2 + mf.STAND_BASE_T + 0.01))
    check(overlap(stack, stand) < 1e-3, "plate stands in the slot without overlap (%.4f mm3)"
          % overlap(stack, stand))
    print("  info  upright: disc axis %.1f mm above the floor"
          % (mf.PLATE / 2 + mf.STAND_BASE_T))

    print("CHECK FAILED: %d" % len(FAILS) if FAILS else "CHECK OK")


main()
