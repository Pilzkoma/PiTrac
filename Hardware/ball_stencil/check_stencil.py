# Check the generated ball stencil. Run under FreeCAD, from the repo root:
#     freecadcmd Hardware/ball_stencil/check_stencil.py
#
# Reads both STEP files back and asserts: valid solids; a cutout through the
# wall at every mark site of that half (the wall's mid-surface point at the
# site is empty) while the wall is solid at the dodecahedron's face centres
# (the points farthest from any mark); removed volume close to the cutout
# prisms; outer diameter = flange; both STLs under 10,000 triangles.
# Prints CHECK OK, else CHECK FAILED (freecadcmd does not pass an exit code
# on, so the printed verdict is the result).

import json
import math
import os
import sys

import FreeCAD
import Mesh
import Part

_print = print


def print(*a, **k):  # noqa: A001 - freecadcmd drops buffered output at exit
    _print(*a, flush=True, **k)


HERE = os.path.join("Hardware", "ball_stencil")
sys.path.insert(0, HERE)
os.environ["BALL_STENCIL_IMPORT_ONLY"] = "1"
import make_stencil as ms  # noqa: E402

MAP = os.path.join("sp1_vision", "ball_marks", "ball_mark_map.json")


def face_centres():
    """The 12 dodecahedron face centres = directions farthest from the 20 sites."""
    with open(MAP, encoding="utf-8") as f:
        sites = [s["normal"] for s in json.load(f)["sites"]]
    # brute force on a 2-degree grid: the directions whose nearest site is
    # farthest away, taking 12 that are well apart
    centres = []
    best = []
    for th in range(0, 180, 2):
        for ph in range(0, 360, 2):
            v = (math.sin(math.radians(th)) * math.cos(math.radians(ph)),
                 math.sin(math.radians(th)) * math.sin(math.radians(ph)),
                 math.cos(math.radians(th)))
            d = max(sum(p * q for p, q in zip(v, s)) for s in sites)
            best.append((d, v))
    best.sort()
    for d, v in best:
        if all(sum(p * q for p, q in zip(v, c)) < 0.9 for c in centres):
            centres.append(v)
        if len(centres) == 12:
            break
    return centres


def hole_azimuths(shape, radius, z):
    """Azimuths (deg) where the flange is empty on the pin circle at height z."""
    empty = [a for a in range(360)
             if not shape.isInside(FreeCAD.Vector(radius * math.cos(math.radians(a)),
                                                  radius * math.sin(math.radians(a)), z), 0.01, True)]
    groups, start, prev = [], None, None
    for a in empty + [None]:
        if a is not None and prev is not None and a == prev + 1:
            prev = a
            continue
        if start is not None:
            groups.append((start + prev) / 2.0)
        start, prev = a, a
    if len(groups) > 1 and empty and empty[0] == 0 and empty[-1] == 359:
        # one hole across 0 deg: merge the first and last group
        first, last = groups[0], groups[-1]
        groups = groups[1:-1] + [((first + last + 360) / 2.0) % 360]
    return sorted(groups)


def same_pattern(a, b, tol=3.0):
    return len(a) == len(b) and all(min(abs((x - y + 180) % 360 - 180) for y in b) < tol for x in a)


def skin_free(shape, site, r_in):
    """Probes just outside the inner surface near every outline vertex: empty?"""
    n, north, east = (FreeCAD.Vector(*site[k]) for k in ("normal", "north", "east"))
    bad = 0
    for e, nn in site["outline_mm"]:
        for f in (0.8, 0.9):
            d = n * r_in + east * (f * e) + north * (f * nn)
            d.normalize()
            if shape.isInside(d * (r_in + 0.1), 0.005, True):
                bad += 1
    return bad


def polygon_area(pts):
    return 0.5 * abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])))


def main():
    doc = ms.load_map(MAP)
    r_in = doc["shell"]["inner_diameter_mm"] / 2
    wall = doc["shell"]["wall_mm"]
    r_mid = r_in + wall / 2
    ok = True
    holes = {}
    centres = face_centres()
    for half in ("upper", "lower"):
        step = os.path.join(HERE, "stencil_%s.step" % half)
        stl = os.path.join(HERE, "stencil_%s.stl" % half)
        if not (os.path.exists(step) and os.path.exists(stl)):
            print("%s: missing %s or %s" % (half, step, stl))
            ok = False
            continue
        shape = Part.read(step)
        sites = [s for s in doc["sites"] if s["half"] == half]
        print("%s: valid %s, volume %.1f mm3" % (half, shape.isValid(), shape.Volume))
        ok &= shape.isValid()
        sign = 1 if half == "upper" else -1
        open_sites = sum(not shape.isInside(FreeCAD.Vector(*[c * r_mid for c in s["normal"]]), 0.01, True)
                         for s in sites)
        print("  cutouts open at %d of %d sites" % (open_sites, len(sites)))
        ok &= open_sites == len(sites) == 10
        solid = [c for c in centres if c[2] * sign > 0.05]
        filled = sum(shape.isInside(FreeCAD.Vector(*[x * r_mid for x in c]), 0.01, True) for c in solid)
        print("  wall solid at %d of %d face centres" % (filled, len(solid)))
        ok &= filled == len(solid) and len(solid) >= 5
        skins = sum(skin_free(shape, st, r_in) for st in sites)
        print("  probes near outline ends blocked: %d" % skins)
        ok &= skins == 0
        holes[half] = hole_azimuths(shape, ms.pin_circle_radius(doc),
                                    ms.FLANGE_THICK_MM / 2 if half == "upper" else -ms.FLANGE_THICK_MM / 2)
        print("  alignment holes at %s deg" % ", ".join("%.0f" % h for h in holes[half]))
        uncut = ms.build_half(doc, half, cutouts=False)
        removed = uncut.Volume - shape.Volume
        expected = sum(0.5 * (polygon_area(s["outline_mm"]) + polygon_area(s["outline_outer_mm"])) * wall
                       for s in sites)
        print("  removed %.1f mm3, expected about %.1f" % (removed, expected))
        ok &= 0.75 * expected <= removed <= 1.25 * expected
        bb = shape.BoundBox
        want = 2 * ms.flange_radius(doc)
        print("  outer diameter %.2f / %.2f mm (want %.2f)" % (bb.XLength, bb.YLength, want))
        ok &= abs(bb.XLength - want) < 0.1 and abs(bb.YLength - want) < 0.1
        facets = Mesh.Mesh(stl).CountFacets
        print("  STL %d triangles" % facets)
        ok &= facets < 10000
    if "upper" in holes and "lower" in holes:
        match = same_pattern(holes["upper"], holes["lower"])
        unique = not any(same_pattern([(h + rot) % 360 for h in holes["upper"]], holes["upper"])
                         for rot in (120, 240))
        print("holes match between halves: %s; only one way to close: %s" % (match, unique))
        ok &= match and unique
    print("CHECK OK" if ok else "CHECK FAILED")
    return ok


main()
