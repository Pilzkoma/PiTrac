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

from collections import Counter
from dataclasses import dataclass
from typing import Optional

import numpy as np

PHI = (1.0 + 5.0 ** 0.5) / 2.0
SHAPES = ("dot", "bar", "cross")
MIN_PER_SHAPE = 5


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


def _cost(marks, nb, accept=None):
    sigs = Counter(sig for _, _, _, sig in all_v_signatures(marks, nb))
    dup = sum(n - 1 for n in sigs.values())
    counts = Counter(m.shape for m in marks)
    short = sum(max(0, MIN_PER_SHAPE - counts[s]) for s in SHAPES)
    bad = 0 if accept is None else sum(1 for m in marks if not accept(m))
    return dup + short + bad


def assign_marks(seed=0, accept=None, max_restarts=200, max_steps=4000):
    """A shape for every site such that all 60 V signatures are distinct.

    Deterministic for a seed: random start, then repeatedly re-choose one
    site's mark to the option with the lowest cost (duplicate signatures,
    plus shortfall below MIN_PER_SHAPE of any shape, plus marks `accept`
    refuses), restarting when stuck. `accept(mark) -> bool` lets the caller
    add per-mark constraints (stencil geometry).
    """
    sites = dodecahedron_sites()
    nb = neighbours(sites)
    rng = np.random.default_rng(seed)
    for _ in range(max_restarts):
        marks = [_options(nb, i)[rng.integers(5)] for i in range(20)]
        cost = _cost(marks, nb, accept)
        for _ in range(max_steps):
            if cost == 0:
                return marks
            i = int(rng.integers(20))
            best, best_cost = [], None
            for opt in _options(nb, i):
                trial = marks[:i] + [opt] + marks[i + 1:]
                c = _cost(trial, nb, accept)
                if best_cost is None or c < best_cost:
                    best, best_cost = [opt], c
                elif c == best_cost:
                    best.append(opt)
            marks[i] = best[int(rng.integers(len(best)))]
            cost = best_cost
    raise RuntimeError("no assignment with unique V signatures found")
