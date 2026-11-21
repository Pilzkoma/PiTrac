# Build the hand-turn fixture for the owner's 15-degree turntable disc
# (Hardware/ball_stencil/drehscheibe.step). Run under FreeCAD, from the repo root:
#     freecadcmd Hardware/turn_fixture/make_fixture.py
#
# Purpose: acceptance 2 of docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md
# needs a marked ball turned by known angles about three axes (vertical, horizontal
# towards the cameras, horizontal across them). The disc alone only turns about the
# vertical. This fixture holds the disc so that it can be used flat or upright:
#
#   plate  - square plate with a pocket the disc turns in (rim bearing); a hole in
#            the floor to push the disc out from behind.
#   cover  - square frame over the disc's rim, pinned to the plate with 1.75 mm
#            filament; it keeps the disc in the pocket when upright. A tongue cut
#            from it reaches over the tick ring: a fork at its tip straddles one
#            tick (the detent, 15 deg steps). The prongs' outer bottom edges are
#            bevelled, so a tick turning towards the fork climbs it and drops into
#            the slot; out of the slot only with the tongue lifted.
#   cup    - ball seat with a 45-degree spigot that self-centres in the disc's
#            central countersink; glue it to the disc. Ball held with a pea of
#            adhesive putty in the bowl.
#   stand  - base with a slot the plate's bottom edge stands in (disc axis
#            horizontal); turned 90 deg on the floor it gives the second
#            horizontal axis.
#
# Writes <part>.step (exact B-rep) and <part>.stl (< 10,000 triangles) next to
# this file. check_fixture.py checks the result against the disc's STEP.

import math
import os

import FreeCAD
import MeshPart
import Part

V = FreeCAD.Vector
OUT = os.path.join("Hardware", "turn_fixture")
DISC_STEP = os.path.join("Hardware", "ball_stencil", "drehscheibe.step")

# --- the owner's disc, measured from drehscheibe.step (2026-11-21) -------------
DISC_CENTRE_IN_STEP = (170.0, 0.0)   # disc axis in the STEP's coordinates
DISC_R = 50.0
DISC_T = 4.0             # base thickness; ticks and labels stand 1 mm on top
TICK_H = 1.0
TICK_R = (34.0, 46.0)    # radial extent of each tick (round ends, width 2)
TICK_W = 2.0
TICK_STEP_DEG = 15.0     # ticks at 0, 15, ... 345 deg (0 deg = +x of the STEP)
LABEL_R_MAX = 32.0       # raised labels at r 28-32, every 45 deg
RECESS_R = 3.0           # central countersink: r 3 from z 1 to 2, cone to r 5 at z 4
RECESS_FLOOR_Z = 1.0
RECESS_CONE_Z = 2.0

# --- plate ---------------------------------------------------------------------
PLATE = 136.0            # square side
FLOOR = 3.0
POCKET_DEPTH = DISC_T + 0.2
POCKET_R = DISC_R + 0.3  # rim bearing; 0.3 mm radial play
PLATE_T = FLOOR + POCKET_DEPTH
PUSH_HOLE_R = 10.0       # through the floor, to push the disc out

# --- cover ---------------------------------------------------------------------
COVER_T = 2.0
COVER_R_IN = 47.5        # clears the ticks (to r 46), holds the rim (r 47.5-50)
PIN_HOLE_D = 1.9         # 1.75 mm filament as pins
PINS = [(60.0, 60.0), (-60.0, 60.0), (60.0, -60.0), (-60.0, -60.0),
        (11.0, 60.0), (-11.0, 60.0)]

# Tongue along +y (the plate's top edge when upright); its fork straddles the
# tick at 90 deg.
TONGUE_W = 8.0
TONGUE_GAP = 1.0         # cut round the tongue on each side
TONGUE_TIP_Y = 37.0      # tip over the ticks, outside the labels (r <= 32)
TONGUE_ROOT_Y = 63.0
SLOT_W = TICK_W + 0.3    # 0.15 mm each side: about +-0.2 deg of play
SLOT_END_Y = 48.5        # slot runs from the tip past the tick's outer end
BEVEL = 1.1              # > tick engagement (0.8 mm)
NUB = (6.0, 3.0, 3.0)    # lift grip on the tongue: x, y size, height
NUB_Y = 49.0

# --- cup -------------------------------------------------------------------------
CUP_SPIGOT_R = RECESS_R - 0.15   # 45-deg cone parallel to the countersink
CUP_R = 10.0
CUP_TOP_Z = 16.0                 # in disc coordinates (disc bottom = 0)
CUP_SEAT_R = 20.5                # bowl radius < ball radius: the ball rests on the rim,
                                 # a gap for the putty underneath
BALL_R = 42.67 / 2
CUP_SEAT_DROP = 0.15             # how far the cup sinks before the cones touch

# --- stand -------------------------------------------------------------------------
STAND_X = 150.0
STAND_Y = 80.0
STAND_BASE_T = 4.0
STAND_SLOT_W = PLATE_T + COVER_T + 0.4   # plate and cover stand in it together
STAND_WALL_T = 5.0
STAND_WALL_H = 22.0              # above the base
STAND_GUSSET_T = 4.0
STAND_GUSSETS_X = (-62.0, 0.0, 62.0)

MAX_TRIANGLES = 9500


def _box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def _cyl(r, z0, z1, x=0.0, y=0.0):
    return Part.makeCylinder(r, z1 - z0, V(x, y, z0))


def _cone(r0, r1, z0, z1):
    return Part.makeCone(r0, r1, z1 - z0, V(0, 0, z0))


def _pin_holes(z0, z1):
    holes = [_cyl(PIN_HOLE_D / 2, z0 - 1, z1 + 1, x, y) for x, y in PINS]
    out = holes[0]
    for h in holes[1:]:
        out = out.fuse(h)
    return out


def build_plate():
    h = PLATE / 2
    body = _box(-h, h, -h, h, 0, PLATE_T)
    body = body.cut(_cyl(POCKET_R, FLOOR, PLATE_T + 1))
    body = body.cut(_cyl(PUSH_HOLE_R, -1, FLOOR + 1))
    body = body.cut(_pin_holes(0, PLATE_T))
    return body.removeSplitter()


def _bevel_prism(x_edge, sign, y0, y1, z0):
    """Wedge along y removing the bottom outer edge of a prong at x = x_edge;
    sign = +1 for the edge facing +x."""
    pts = [V(x_edge + sign * 0.01, y0, z0 - 0.01),
           V(x_edge - sign * BEVEL, y0, z0 - 0.01),
           V(x_edge + sign * 0.01, y0, z0 + BEVEL)]
    wire = Part.makePolygon(pts + [pts[0]])
    return Part.Face(wire).extrude(V(0, y1 - y0, 0))


def build_cover():
    """In plate coordinates: the cover lies on the plate, z = PLATE_T ... + COVER_T."""
    h = PLATE / 2
    z0, z1 = PLATE_T, PLATE_T + COVER_T
    body = _box(-h, h, -h, h, z0, z1)
    body = body.cut(_cyl(COVER_R_IN, z0 - 1, z1 + 1))
    half_gap = TONGUE_W / 2 + TONGUE_GAP
    body = body.cut(_box(-half_gap, half_gap, 0, TONGUE_ROOT_Y, z0 - 1, z1 + 1))
    tw = TONGUE_W / 2
    tongue = _box(-tw, tw, TONGUE_TIP_Y, TONGUE_ROOT_Y + 0.5, z0, z1)
    tongue = tongue.cut(_box(-SLOT_W / 2, SLOT_W / 2, TONGUE_TIP_Y - 1, SLOT_END_Y,
                             z0 - 1, z1 + 1))
    for sign in (1, -1):
        tongue = tongue.cut(_bevel_prism(sign * tw, sign, TONGUE_TIP_Y - 1,
                                         SLOT_END_Y, z0))
    nx, ny, nz = NUB
    tongue = tongue.fuse(_box(-nx / 2, nx / 2, NUB_Y, NUB_Y + ny, z1 - 0.01, z1 + nz))
    body = body.fuse(tongue)
    body = body.cut(_pin_holes(z0, z1))
    return body.removeSplitter()


def build_cup():
    """In disc coordinates (disc bottom = 0, axis = z), before the seating drop."""
    spigot = _cyl(CUP_SPIGOT_R, RECESS_FLOOR_Z + 0.25, RECESS_CONE_Z)
    cone_top = RECESS_CONE_Z + (CUP_R - CUP_SPIGOT_R)
    cone = _cone(CUP_SPIGOT_R, CUP_R, RECESS_CONE_Z, cone_top)
    column = _cyl(CUP_R, cone_top, CUP_TOP_Z)
    body = spigot.fuse(cone).fuse(column)
    seat_z = CUP_TOP_Z + math.sqrt(CUP_SEAT_R ** 2 - CUP_R ** 2)
    body = body.cut(Part.makeSphere(CUP_SEAT_R, V(0, 0, seat_z)))
    return body.removeSplitter()


def ball_centre_disc_z():
    """Ball centre above the disc bottom with the cup seated."""
    return CUP_TOP_Z - CUP_SEAT_DROP + math.sqrt(BALL_R ** 2 - CUP_R ** 2)


def build_stand():
    hx, hy = STAND_X / 2, STAND_Y / 2
    body = _box(-hx, hx, -hy, hy, 0, STAND_BASE_T)
    s = STAND_SLOT_W / 2
    top = STAND_BASE_T + STAND_WALL_H
    for sign in (1, -1):
        y0, y1 = sorted((sign * s, sign * (s + STAND_WALL_T)))
        body = body.fuse(_box(-hx, hx, y0, y1, STAND_BASE_T - 0.01, top))
        for gx in STAND_GUSSETS_X:
            yw = sign * (s + STAND_WALL_T - 0.01)
            yo = sign * (hy - 2.0)
            pts = [V(gx - STAND_GUSSET_T / 2, yw, STAND_BASE_T - 0.01),
                   V(gx - STAND_GUSSET_T / 2, yo, STAND_BASE_T - 0.01),
                   V(gx - STAND_GUSSET_T / 2, yw, top)]
            face = Part.Face(Part.makePolygon(pts + [pts[0]]))
            body = body.fuse(face.extrude(V(STAND_GUSSET_T, 0, 0)))
    return body.removeSplitter()


def load_disc():
    """The owner's disc in disc coordinates: axis = z through the origin, bottom z = 0."""
    disc = Part.read(DISC_STEP)
    cx, cy = DISC_CENTRE_IN_STEP
    disc.translate(V(-cx, -cy, 0))
    return disc


PARTS = {
    "plate": build_plate,
    "cover": build_cover,
    "cup": build_cup,
    "stand": build_stand,
}


def export(name, body, out=OUT):
    step = os.path.join(out, name + ".step")
    stl = os.path.join(out, name + ".stl")
    body.exportStep(step)
    deflection = 0.05
    while True:
        mesh = MeshPart.meshFromShape(Shape=body, LinearDeflection=deflection,
                                      AngularDeflection=0.3, Relative=False)
        if mesh.CountFacets <= MAX_TRIANGLES or deflection > 1.0:
            break
        deflection *= 1.5
    mesh.write(stl)
    print("%s: valid %s, volume %.0f mm3, %d triangles (deflection %.3f mm)"
          % (name, body.isValid(), body.Volume, mesh.CountFacets, deflection),
          flush=True)


def main():
    for name, build in PARTS.items():
        export(name, build())
    print("ball centre above the disc face: %.1f mm" % (ball_centre_disc_z() - DISC_T),
          flush=True)


if not os.environ.get("TURN_FIXTURE_IMPORT_ONLY"):
    main()
