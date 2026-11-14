# Build the two half-shells of the ball-marking stencil from the mark map.
# Run under FreeCAD, from the repo root:
#     freecadcmd Hardware/ball_stencil/make_stencil.py
#
# Reads only sp1_vision/ball_marks/ball_mark_map.json (written by
# python -m sp1_vision.ball_marks_design) and writes, next to this file,
# stencil_upper.step / stencil_lower.step (exact B-rep, editable in CAD) and
# stencil_upper.stl / stencil_lower.stl (for printing, < 10,000 triangles).
#
# Each half: a spherical shell (inner diameter and wall from the map), cut at
# the seam plane z = 0; a flange ring at the seam, FLANGE_WIDTH_MM wide and
# FLANGE_THICK_MM thick; holes at PIN_AZIMUTHS_DEG through the flange for
# alignment pins (pieces of 1.75 mm filament), so both halves print flange-down
# without supports; and one cutout per mark site of that half, lofted from
# the mark outline at the inner surface to the chamfered outline outside.

import json
import math
import os

import FreeCAD
import MeshPart
import Part

MAP = os.path.join("sp1_vision", "ball_marks", "ball_mark_map.json")
OUT = os.path.join("Hardware", "ball_stencil")

FLANGE_WIDTH_MM = 4.0
FLANGE_THICK_MM = 2.0
# Not 120 deg apart: the vertex-up mark sites are 3-fold symmetric about Z,
# so evenly spaced holes would let the halves close three ways and only one
# matches the map (final review 2026-11-14).
PIN_AZIMUTHS_DEG = (0.0, 100.0, 220.0)
PIN_HOLE_DIAMETER_MM = 1.9    # 1.75 mm filament as alignment pins
DEEP_MM = 18.0               # inner end of the central-projection cut
MAX_TRIANGLES = 9500          # under the owner's 10,000 limit with margin

V = FreeCAD.Vector


def load_map(path=MAP):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def radii(doc):
    r_in = doc["shell"]["inner_diameter_mm"] / 2
    return r_in, r_in + doc["shell"]["wall_mm"]


def flange_radius(doc):
    return radii(doc)[1] + FLANGE_WIDTH_MM


def pin_circle_radius(doc):
    return (radii(doc)[1] + flange_radius(doc)) / 2


def _wire(site, outline_key, radius, scale=1.0):
    """The site's outline as a closed wire on the plane tangent at radius,
    its in-plane coordinates multiplied by scale."""
    n, north, east = (V(*site[k]) for k in ("normal", "north", "east"))
    pts = [n * radius + east * (e * scale) + north * (nn * scale) for e, nn in site[outline_key]]
    return Part.makePolygon(pts + [pts[0]])


def _cutout(site, r_in, r_out):
    """Through-cut for one mark: a central-projection frustum, then the chamfer.

    Inner part: the outline on the plane tangent at r_in, and the same outline
    scaled by DEEP_MM / r_in on the plane at DEEP_MM - i.e. the cone from the
    ball centre through the outline. It cuts through the inner surface
    everywhere (a flat start at r_in - 0.5 left a skin at the bar ends, where
    the sphere dips 0.7 mm below that plane), and the opening on the inner
    surface - and the ink on the ball - is the outline projected from the
    ball centre. Outer part: lofted from the outline at r_in to the chamfered
    outline on the plane 0.5 mm outside the shell.
    """
    deep = Part.makeLoft([_wire(site, "outline_mm", DEEP_MM, DEEP_MM / r_in),
                          _wire(site, "outline_mm", r_in)], True)
    chamfer = Part.makeLoft([_wire(site, "outline_mm", r_in),
                             _wire(site, "outline_outer_mm", r_out + 0.5)], True)
    return deep.fuse(chamfer)


def build_half(doc, half, cutouts=True):
    r_in, r_out = radii(doc)
    r_f = flange_radius(doc)
    up = half == "upper"
    z0 = 0.0 if up else -50.0
    keep = Part.makeBox(100, 100, 50, V(-50, -50, z0))
    shell = Part.makeSphere(r_out).cut(Part.makeSphere(r_in)).common(keep)
    fz = 0.0 if up else -FLANGE_THICK_MM
    flange = Part.makeCylinder(r_f, FLANGE_THICK_MM, V(0, 0, fz)).cut(Part.makeSphere(r_in))
    body = shell.fuse(flange)
    r_pin = pin_circle_radius(doc)
    for deg in PIN_AZIMUTHS_DEG:
        a = math.radians(deg)
        hole = Part.makeCylinder(PIN_HOLE_DIAMETER_MM / 2, FLANGE_THICK_MM + 2,
                                 V(r_pin * math.cos(a), r_pin * math.sin(a), fz - 1))
        body = body.cut(hole)
    if cutouts:
        for site in doc["sites"]:
            if site["half"] != half:
                continue
            body = body.cut(_cutout(site, r_in, r_out))
    return body.removeSplitter()


def export(doc, half, out=OUT):
    body = build_half(doc, half)
    step = os.path.join(out, "stencil_%s.step" % half)
    stl = os.path.join(out, "stencil_%s.stl" % half)
    body.exportStep(step)
    deflection = 0.05
    while True:
        mesh = MeshPart.meshFromShape(Shape=body, LinearDeflection=deflection,
                                      AngularDeflection=0.35, Relative=False)
        if mesh.CountFacets <= MAX_TRIANGLES:
            break
        deflection *= 1.4
    mesh.write(stl)
    print("%s: valid %s, volume %.1f mm3, STL %d triangles (deflection %.3f mm)" % (
        half, body.isValid(), body.Volume, mesh.CountFacets, deflection))


def main():
    doc = load_map()
    for half in ("upper", "lower"):
        export(doc, half)


# freecadcmd runs a script with __name__ set to its file name, the same name
# an import gets, so check_stencil.py says "import only" through the
# environment.
if not os.environ.get("BALL_STENCIL_IMPORT_ONLY"):
    main()
