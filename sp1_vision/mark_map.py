"""The ball-mark map (ball_mark_map.json) as numpy arrays.

The JSON is the single source; its conventions block is authoritative. All
vectors are in the stencil (map) frame. Outlines are (east, north) in mm on the
plane tangent at the shell inner radius; the ink on the ball is that outline
projected centrally onto the ball, scale BALL_RADIUS_MM / shell radius.
"""

import json

import numpy as np

BALL_RADIUS_MM = 21.335
MAP_PATH = "sp1_vision/ball_marks/ball_mark_map.json"


def _polygon_area(poly):
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


class MarkMap(object):
    def __init__(self, data):
        sites = sorted(data["sites"], key=lambda s: s["id"])
        self.shell_radius_mm = data["shell"]["inner_diameter_mm"] / 2.0
        self.normals = np.array([s["normal"] for s in sites], dtype=float)
        self.north = np.array([s["north"] for s in sites], dtype=float)
        self.east = np.array([s["east"] for s in sites], dtype=float)
        self.shapes = [s["shape"] for s in sites]
        self.neighbours = [list(s["neighbours"]) for s in sites]
        self.outlines_mm = [np.array(s["outline_mm"], dtype=float) for s in sites]
        self.directions = np.zeros((len(sites), 3))
        for i, s in enumerate(sites):
            if s["shape"] == "cross":
                self.directions[i] = self.east[i]
            elif s["shape"] == "bar":
                n = self.normals[i]
                v = self.normals[s["bar_to"]]
                v = v - n * float(v @ n)
                self.directions[i] = v / np.linalg.norm(v)
        scale2 = (BALL_RADIUS_MM / self.shell_radius_mm) ** 2
        self.ink_area_mm2 = {}
        for shape in ("dot", "bar", "cross"):
            i = self.shapes.index(shape)
            self.ink_area_mm2[shape] = _polygon_area(self.outlines_mm[i]) * scale2
        angles = []
        for i, nb in enumerate(self.neighbours):
            for j in nb:
                c = float(np.clip(self.normals[i] @ self.normals[j], -1, 1))
                angles.append(np.degrees(np.arccos(c)))
        self.neighbour_angle_deg = float(np.mean(angles))


def load_map(path=MAP_PATH):
    with open(path) as fh:
        return MarkMap(json.load(fh))
