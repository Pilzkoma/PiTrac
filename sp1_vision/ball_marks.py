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

import numpy as np

PHI = (1.0 + 5.0 ** 0.5) / 2.0


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
