"""The mark map for spin: where the marks sit on the ball and what they look like.

Spin is read from marks drawn on the ball, not from its dimples (CLAUDE.md,
known issues 1; spec docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md).
The marks sit at the 20 vertices of a regular dodecahedron, vertex-up in the
stencil frame (+Z = the stencil axis, the seam is the plane z = 0), so the
nearest marks are 19.5 deg from the seam and none is split between the two
half-shells.

This module is the single source of the geometry: the stencil generator and
the analysis both read the map file it writes, never their own copy.
"""

import json
from collections import Counter
from dataclasses import dataclass
from typing import Optional

import numpy as np

PHI = (1.0 + 5.0 ** 0.5) / 2.0
SHAPES = ("dot", "bar", "cross")
MIN_PER_SHAPE = 5

BALL_DIAMETER_MM = 42.67
SHELL_INNER_DIAMETER_MM = 42.9
SHELL_WALL_MM = 1.5
CHAMFER_MM = 1.5              # cutout outline grown by this at the outer surface
DOT_DIAMETER_MM = 7.0
BAR_MM = (11.0, 3.5)          # length, width
CROSS_MM = (10.0, 3.5)        # arm length, arm width


@dataclass(frozen=True)
class Mark:
    """One mark: its site, its shape, and for a bar the neighbour it points at.

    A bar is symmetric, so "aligned with the edge to a neighbour" is the only
    state it has; dots and crosses have none.
    """
    site: int
    shape: str
    bar_to: Optional[int] = None


def _rotation_to_z(v):
    """Rotation matrix taking the unit vector v onto +Z (Rodrigues)."""
    v = np.asarray(v, dtype=np.float64)
    v = v / np.linalg.norm(v)
    z = np.array([0.0, 0.0, 1.0])
    axis = np.cross(v, z)
    s = np.linalg.norm(axis)
    c = float(v @ z)
    if s < 1e-15:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    k = axis / s
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + s * kx + (1 - c) * (kx @ kx)


def dodecahedron_sites():
    """The 20 mark sites: unit vectors, vertex-up, site 0 at +Z.

    Sorted by descending height, then by azimuth, so the ids read from the
    top of the stencil down.
    """
    pts = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    for a in (-1, 1):
        for b in (-1, 1):
            pts += [(0, a / PHI, b * PHI), (a / PHI, b * PHI, 0), (a * PHI, 0, b / PHI)]
    p = np.array(pts, dtype=np.float64)
    p /= np.linalg.norm(p, axis=1, keepdims=True)
    p = p @ _rotation_to_z((1.0, 1.0, 1.0)).T
    az = np.arctan2(p[:, 1], p[:, 0])
    order = np.lexsort((np.round(az, 9), -np.round(p[:, 2], 9)))
    p = p[order]
    p[0] = (0.0, 0.0, 1.0)
    p[-1] = (0.0, 0.0, -1.0)
    return p


def tangent_frame(n):
    """(north, east) in the tangent plane at n; east x north = n.

    North is +Z projected into the plane, or +X at the two poles. Seen from
    outside the ball, east is to the right of north.
    """
    n = np.asarray(n, dtype=np.float64)
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[2]) > 0.999 else np.array([0.0, 0.0, 1.0])
    north = ref - (ref @ n) * n
    north /= np.linalg.norm(north)
    east = np.cross(north, n)
    return north, east


def neighbours(sites):
    """The 3 neighbours of every site, counter-clockwise seen from outside.

    A camera sees the outside of the ball, never a mirror image, so this
    order is observable in an image and part of how marks are identified.
    """
    sites = np.asarray(sites, dtype=np.float64)
    out = []
    for i, n in enumerate(sites):
        dots = sites @ n
        dots[i] = -2.0
        trio = np.argsort(-dots)[:3]
        north, east = tangent_frame(n)
        ang = [np.arctan2((sites[j] - n) @ north, (sites[j] - n) @ east) for j in trio]
        out.append(tuple(int(j) for _, j in sorted(zip(ang, trio))))
    return out


def relative_symbol(marks, nb, x, ref):
    """Mark x as seen from its neighbour ref: what a camera can tell apart.

    "dot" or "cross"; for a bar "bar0" (along the edge to ref), "bar+" (along
    the edge to the neighbour after ref, counter-clockwise from outside) or
    "bar-" (the remaining one).
    """
    m = marks[x]
    if m.shape != "bar":
        return m.shape
    order = nb[x]
    k = order.index(ref)
    if m.bar_to == ref:
        return "bar0"
    return "bar+" if m.bar_to == order[(k + 1) % 3] else "bar-"


def v_signature(marks, nb, c, a, b):
    """What three visible marks in a V (centre c, neighbours a then b CCW) show."""
    return (relative_symbol(marks, nb, c, a),
            relative_symbol(marks, nb, a, c),
            relative_symbol(marks, nb, b, c))


def all_v_signatures(marks, nb):
    """All 60 ordered V's: (c, a, b, signature), b following a CCW round c."""
    out = []
    for c, (n1, n2, n3) in enumerate(nb):
        for a, b in ((n1, n2), (n2, n3), (n3, n1)):
            out.append((c, a, b, v_signature(marks, nb, c, a, b)))
    return out


def _options(nb, site):
    return ([Mark(site, "dot"), Mark(site, "cross")]
            + [Mark(site, "bar", j) for j in nb[site]])


def _cost(marks, nb):
    sigs = Counter(sig for _, _, _, sig in all_v_signatures(marks, nb))
    dup = sum(n - 1 for n in sigs.values())
    counts = Counter(m.shape for m in marks)
    short = sum(max(0, MIN_PER_SHAPE - counts[s]) for s in SHAPES)
    return dup + short


def assign_marks(seed=0, accept="stencil", max_restarts=200, max_steps=4000):
    """A shape for every site such that all 60 V signatures are distinct.

    Deterministic for a seed: random start, then repeatedly re-choose one
    site's mark to the option with the lowest cost (duplicate signatures,
    plus shortfall below MIN_PER_SHAPE of any shape), restarting when stuck.
    Only marks `accept(mark) -> bool` allows are ever chosen; the default,
    "stencil", is clears_seam: a bar pointing at a neighbour across the seam
    brings its outer cutout to ~1.0 mm of it.
    """
    sites = dodecahedron_sites()
    nb = neighbours(sites)
    if accept == "stencil":
        accept = lambda m: clears_seam(m, sites, nb)  # noqa: E731
    allowed = [[o for o in _options(nb, i) if accept is None or accept(o)] for i in range(20)]
    rng = np.random.default_rng(seed)
    for _ in range(max_restarts):
        marks = [opts[int(rng.integers(len(opts)))] for opts in allowed]
        cost = _cost(marks, nb)
        for _ in range(max_steps):
            if cost == 0:
                return marks
            i = int(rng.integers(20))
            best, best_cost = [], None
            for opt in allowed[i]:
                trial = marks[:i] + [opt] + marks[i + 1:]
                c = _cost(trial, nb)
                if best_cost is None or c < best_cost:
                    best, best_cost = [opt], c
                elif c == best_cost:
                    best.append(opt)
            marks[i] = best[int(rng.integers(len(best)))]
            cost = best_cost
    raise RuntimeError("no assignment with unique V signatures found")


def _rect(half_len, half_wid, angle):
    """Rectangle outline (4, 2) in (east, north), long axis at angle from east."""
    c, s_ = np.cos(angle), np.sin(angle)
    u, v = np.array([c, s_]), np.array([-s_, c])
    return np.array([half_len * u + half_wid * v, -half_len * u + half_wid * v,
                     -half_len * u - half_wid * v, half_len * u - half_wid * v])


def cutout_outline_mm(mark, sites, nb, offset_mm=0.0):
    """The mark's outline (k, 2) in its tangent frame (east, north), in mm.

    Dot: a 32-gon of DOT_DIAMETER_MM. Bar: BAR_MM along the great-circle
    direction to the neighbour it points at. Cross: two CROSS_MM arms along
    north and east. `offset_mm` grows the outline (the outward chamfer).
    """
    if mark.shape == "dot":
        r = DOT_DIAMETER_MM / 2 + offset_mm
        t = np.linspace(0, 2 * np.pi, 32, endpoint=False)
        return np.stack([r * np.cos(t), r * np.sin(t)], axis=1)
    if mark.shape == "bar":
        north, east = tangent_frame(sites[mark.site])
        d = sites[mark.bar_to] - sites[mark.site]
        angle = np.arctan2(d @ north, d @ east)
        return _rect(BAR_MM[0] / 2 + offset_mm, BAR_MM[1] / 2 + offset_mm, angle)
    a = CROSS_MM[0] / 2 + offset_mm
    w = CROSS_MM[1] / 2 + offset_mm
    return np.array([(w, w), (w, a), (-w, a), (-w, w), (-a, w), (-a, -w),
                     (-w, -w), (-w, -a), (w, -a), (w, -w), (a, -w), (a, w)], dtype=np.float64)


def outline_3d(mark, sites, nb, radius_mm, offset_mm=0.0):
    """The outline as 3D points (k, 3) on the plane tangent at radius_mm."""
    n = sites[mark.site]
    north, east = tangent_frame(n)
    poly = cutout_outline_mm(mark, sites, nb, offset_mm)
    return n * radius_mm + poly[:, :1] * east + poly[:, 1:] * north


def write_map(path, marks, sites, nb):
    """The map file read by the stencil generator and the analysis."""
    out = []
    for m in marks:
        n = sites[m.site]
        north, east = tangent_frame(n)
        entry = {
            "id": m.site,
            "normal": n.tolist(),
            "azimuth_deg": float(np.degrees(np.arctan2(n[1], n[0]))),
            "elevation_deg": float(np.degrees(np.arcsin(np.clip(n[2], -1, 1)))),
            "half": "upper" if n[2] > 0 else "lower",
            "shape": m.shape,
            "bar_to": m.bar_to,
            "bar_angle_deg": None,
            "neighbours": list(nb[m.site]),
            "north": north.tolist(),
            "east": east.tolist(),
            "outline_mm": cutout_outline_mm(m, sites, nb).tolist(),
            "outline_outer_mm": cutout_outline_mm(m, sites, nb, CHAMFER_MM).tolist(),
        }
        if m.shape == "bar":
            d = sites[m.bar_to] - n
            entry["bar_angle_deg"] = float(np.degrees(np.arctan2(d @ east, d @ north)))
        out.append(entry)
    doc = {
        "version": 1,
        "frame": "stencil frame: +Z = vertex-up axis, seam = plane z = 0; "
                 "outlines in (east, north) mm on the tangent plane",
        "conventions": {
            "frame": "Stencil frame, right-handed: +Z = the stencil axis through site 0 "
                     "(vertex-up), seam = plane z = 0; 'upper' sites have z > 0. "
                     "Alignment holes at 0/100/220 deg azimuth fix the one way the halves close.",
            "north_east": "Per site: north = +Z projected into the tangent plane (+X at the "
                          "two poles), east = north x normal, so east x north = normal and, "
                          "seen from outside, east is to the right of north.",
            "outline_mm": "Polygon (east, north) in mm on the plane tangent to the sphere of "
                          "radius shell.inner_diameter_mm/2 at the site; outline_outer_mm is "
                          "the same grown by shell.chamfer_mm (opening at the outer surface).",
            "bar_angle_deg": "Bars only: direction of the bar from north towards east "
                             "(clockwise seen from outside); a bar is symmetric, +180 deg is "
                             "the same bar. bar_to is the neighbour it is aligned with.",
            "neighbours": "The three neighbouring site ids, counter-clockwise seen from "
                          "outside the ball.",
            "inked_mark": "The stencil cuts each mark as the cone from the ball centre "
                          "through outline_mm, so the ink on the ball is outline_mm projected "
                          "centrally onto the ball surface (scale ball radius / shell inner "
                          "radius = 0.995). Ink may bleed a little at the edges.",
        },
        "ball_diameter_mm": BALL_DIAMETER_MM,
        "shell": {"inner_diameter_mm": SHELL_INNER_DIAMETER_MM,
                  "wall_mm": SHELL_WALL_MM, "chamfer_mm": CHAMFER_MM},
        "shapes_mm": {"dot_diameter": DOT_DIAMETER_MM, "bar": list(BAR_MM),
                      "cross": list(CROSS_MM)},
        "sites": out,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)


def read_map(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


SEAM_CLEARANCE_MM = 1.5       # outer cutout edge to the seam, on the cutting plane


def clears_seam(mark, sites, nb):
    """True if the mark's outer cutout stays SEAM_CLEARANCE_MM off the seam.

    Measured on the plane the stencil generator cuts through, 0.5 mm outside
    the shell's outer surface, with the chamfer.
    """
    r = SHELL_INNER_DIAMETER_MM / 2 + SHELL_WALL_MM + 0.5
    pts = outline_3d(mark, sites, nb, r, CHAMFER_MM)
    return float(np.min(np.abs(pts[:, 2]))) >= SEAM_CLEARANCE_MM
