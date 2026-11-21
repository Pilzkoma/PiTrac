"""Synthetic diagnosis: what each error of the ball-centre fit costs.

    python sp1_vision/strobe_runs/2026-11-21_centre/centre_diagnosis.py

Oversampled renders (exact silhouette, area-weighted edge) with cam1's K and
distortion, 0.40-0.48 m, 0-30 deg off the optical axis in 8 directions, plain
and marked (random pose), each clean and as the camera delivers it (JPEG q 85,
Gaussian noise sigma 2). Per refiner the error of the projected sphere centre
(the pixel where the ball's centre projects), split radial (along the line
from the principal point, + = outward) and tangential. 1 px ~ 1.7 deg of
orientation across the ray at 420 mm (2026-11-21_orientation/results.txt).
At 30 deg, 2 of the 8 directions put the ball outside the 1280 x 800 image
(vertical half field ~24 deg): those are the refusals there, for every refiner.
The renders are uniformly lit; the real limb is dimmer (IR beam from above).
"""

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sp1_vision import frame_analysis as fa  # noqa: E402
from sp1_vision import mark_map, sphere_fit, stereo_geometry  # noqa: E402
from sp1_vision.mark_map import BALL_RADIUS_MM  # noqa: E402
from sp1_vision.tests.render_ball import render_ball  # noqa: E402

R_M = BALL_RADIUS_MM / 1000.0


def quat_r(rs):
    q = rs.normal(size=4)
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def camera_like(img, rs):
    noisy = np.clip(img.astype(np.float64) + rs.normal(0, 2.0, img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", noisy, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)


def main():
    m = mark_map.load_map()
    rig = stereo_geometry.load_rig()
    k, d = rig.k1, rig.d1
    pp = np.array([k[0, 2], k[1, 2]])
    cone = sphere_fit.cone_refiner(k, d)
    refiners = [("circle (refine_ball)", fa.refine_ball),
                ("contrast (by_contrast)", fa.refine_ball_by_contrast),
                ("cone (sphere_fit)", cone)]
    rs = np.random.RandomState(11)
    rows = {}
    for deg in (0, 10, 20, 30):
        for az in range(0, 360, 45):
            for marked in (False, True):
                t, p = np.radians(deg), np.radians(az)
                z = rs.uniform(0.40, 0.48)
                c = np.array([np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)])
                c *= z / c[2]
                R = quat_r(rs)
                img = render_ball(m, k, d, c, R, ball_grey=200,
                                  ink_grey=40 if marked else 200, background=15, oversample=4)
                truth, _ = cv2.projectPoints(c.reshape(1, 1, 3), np.zeros(3), np.zeros(3), k, d)
                truth = truth.reshape(2)
                out = truth - pp
                radial = out / np.linalg.norm(out) if np.linalg.norm(out) > 1 else np.array([1.0, 0.0])
                seed = (truth[0] + rs.uniform(-2, 2), truth[1] + rs.uniform(-2, 2),
                        k[0, 0] * R_M / c[2] * rs.uniform(0.9, 1.1))
                for cond, im in (("clean", img), ("camera", camera_like(img, rs))):
                    for name, f in refiners:
                        fit = f(im, *seed)
                        key = (name, cond, marked, deg)
                        if fit is None:
                            rows.setdefault(key, []).append(None)
                            continue
                        e = np.array(fit[:2]) - truth
                        rows.setdefault(key, []).append((float(e @ radial),
                                                         float(e[0] * -radial[1] + e[1] * radial[0])))
    print(__doc__.split("\n\n")[0])
    print("8 directions per angle; median / 90th percentile of |error| in px, "
          "median radial (+ outward); refusals")
    for name, _ in refiners:
        print("\n" + name)
        print("  %-7s %-6s %5s   %-17s %-17s" % ("image", "marks", "deg", "|err| med/p90", "radial med  refused"))
        for cond in ("clean", "camera"):
            for marked in (False, True):
                for deg in (0, 10, 20, 30):
                    v = rows[(name, cond, marked, deg)]
                    ok = [x for x in v if x is not None]
                    if not ok:
                        print("  %-7s %-6s %5d   all refused" % (cond, "yes" if marked else "no", deg))
                        continue
                    mag = np.hypot(*np.array(ok).T)
                    print("  %-7s %-6s %5d   %5.2f / %5.2f     %+6.2f      %d of %d" % (
                        cond, "yes" if marked else "no", deg, np.median(mag),
                        np.percentile(mag, 90), np.median([x[0] for x in ok]),
                        len(v) - len(ok), len(v)))


if __name__ == "__main__":
    main()
