#!/usr/bin/env python3
"""Write the ball mark map, a site table and a drawing.

    python -m sp1_vision.ball_marks_design [--seed 0] [--out sp1_vision/ball_marks]

The map (ball_mark_map.json) is the single source for the stencil
(Hardware/ball_stencil/make_stencil.py) and for the spin analysis. The table
(marks_table.md) and the drawing (marks_drawing.svg: the upper half seen
from +Z, the lower half seen from -Z, both from outside) are for people.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import ball_marks as bm  # noqa: E402

PX_PER_MM = 6.0


def write_table(path, doc):
    lines = ["# Ball mark sites", "",
             "Stencil frame: +Z = vertex-up axis, seam = plane z = 0. Bar angle from "
             "the site's north (towards +Z on the ball) clockwise to east, seen from outside.", "",
             "| id | half | azimuth ° | elevation ° | shape | bar to | bar angle ° | neighbours (CCW) |",
             "|---|---|---|---|---|---|---|---|"]
    for s in doc["sites"]:
        bar_angle = "" if s["bar_angle_deg"] is None else "%.1f" % s["bar_angle_deg"]
        bar_to = "" if s["bar_to"] is None else str(s["bar_to"])
        lines.append("| %d | %s | %.1f | %.1f | %s | %s | %s | %s |" % (
            s["id"], s["half"], s["azimuth_deg"], s["elevation_deg"], s["shape"],
            bar_to, bar_angle, ", ".join(str(n) for n in s["neighbours"])))
    shapes = [s["shape"] for s in doc["sites"]]
    lines += ["", "Shapes: %d dots, %d bars, %d crosses. Sizes: dot Ø %.1f mm, bar %.1f × %.1f mm, "
              "cross arms %.1f × %.1f mm; cutouts grow %.1f mm towards the outside (chamfer)." % (
                  shapes.count("dot"), shapes.count("bar"), shapes.count("cross"),
                  bm.DOT_DIAMETER_MM, *bm.BAR_MM, *bm.CROSS_MM, bm.CHAMFER_MM)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_svg(path, marks, sites, nb):
    r = bm.SHELL_INNER_DIAMETER_MM / 2 + bm.SHELL_WALL_MM
    size = 2 * r * PX_PER_MM + 60
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'font-family="sans-serif">' % (2 * size, size + 30),
             '<rect width="100%" height="100%" fill="white"/>']
    for k, (half, sign, title) in enumerate((("upper", 1, "upper half, seen from +Z"),
                                            ("lower", -1, "lower half, seen from -Z"))):
        cx, cy = k * size + size / 2, size / 2 + 20
        parts.append('<text x="%.1f" y="16" text-anchor="middle" font-size="14">%s</text>'
                     % (cx, title))
        parts.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="#888"/>'
                     % (cx, cy, r * PX_PER_MM))
        for m in marks:
            if (sites[m.site][2] > 0) != (sign > 0):
                continue
            pts = bm.outline_3d(m, sites, nb, r)
            # seen from outside: from -Z the x axis is mirrored
            xs = cx + sign * pts[:, 0] * PX_PER_MM
            ys = cy - pts[:, 1] * PX_PER_MM
            parts.append('<polygon points="%s" fill="#222"/>' % " ".join(
                "%.1f,%.1f" % (x, y) for x, y in zip(xs, ys)))
            c = sites[m.site] * r
            parts.append('<text x="%.1f" y="%.1f" font-size="12" fill="#c00">%d</text>' % (
                cx + sign * c[0] * PX_PER_MM + 8, cy - c[1] * PX_PER_MM - 8, m.site))
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "ball_marks"))
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    sites = bm.dodecahedron_sites()
    nb = bm.neighbours(sites)
    marks = bm.assign_marks(seed=args.seed)
    map_path = os.path.join(args.out, "ball_mark_map.json")
    bm.write_map(map_path, marks, sites, nb)
    write_table(os.path.join(args.out, "marks_table.md"), bm.read_map(map_path))
    write_svg(os.path.join(args.out, "marks_drawing.svg"), marks, sites, nb)
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
