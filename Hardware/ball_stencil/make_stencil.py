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
# FLANGE_THICK_MM thick; PIN_COUNT holes through the flange for alignment
# pins (pieces of 1.75 mm filament), so both halves print flange-down
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
PIN_COUNT = 3
PIN_HOLE_DIAMETER_MM = 1.9    # 1.75 mm filament as alignment pins
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


def _wire(site, outline_key, radius):
    """The site's outline as a closed wire on the plane tangent at radius."""
    n, north, east = (V(*site[k]) for k in ("normal", "north", "east"))
    pts = [n * radius + east * e + north * nn for e, nn in site[outline_key]]
    return Part.makePolygon(pts + [pts[0]])


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
    r_pin = (r_out + r_f) / 2
    for k in range(PIN_COUNT):
        a = 2 * math.pi * k / PIN_COUNT
        hole = Part.makeCylinder(PIN_HOLE_DIAMETER_MM / 2, FLANGE_THICK_MM + 2,
                                 V(r_pin * math.cos(a), r_pin * math.sin(a), fz - 1))
        body = body.cut(hole)
    if cutouts:
        for site in doc["sites"]:
            if site["half"] != half:
                continue
            loft = Part.makeLoft([_wire(site, "outline_mm", r_in - 0.5),
                                  _wire(site, "outline_outer_mm", r_out + 0.5)], True)
            body = body.cut(loft)
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
