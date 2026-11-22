import os, sys, glob, math
import cv2, numpy as np
sys.path.insert(0, "/home/brain/turn_eval")
from sp1_vision import stereo_geometry, orientation_check as oc, ball_unwrap, mark_detect, mark_map, ball_orientation as bo
rig = stereo_geometry.load_rig(); mmap = mark_map.load_map()
S = os.path.expanduser("~/recordings/2026-11-22_turn_vertical")
def frame(pos, cam):
    fs = sorted(glob.glob(os.path.join(S, pos, "raw", cam, "t*.jpg")))
    return cv2.imread([f for f in fs if float(os.path.basename(f)[1:-4]) > 0.6][0], 0)
ball, _ = oc.find_ball(rig, frame("pos_000", "cam1"), frame("pos_000", "cam2"))
c1 = ball.xyz_m; c2 = rig.r @ c1 + rig.t_m
down = -np.asarray(oc.UP_CAM)
for cam, K, d, c in (("cam1", rig.k1, rig.d1, c1), ("cam2", rig.k2, rig.d2, c2)):
    for a, b in (("pos_000","pos_015"), ("pos_015","pos_030"), ("pos_240","pos_255"), ("pos_300","pos_315")):
        na = np.array([m.normal for m in mark_detect.detect_marks(ball_unwrap.unwrap(frame(a, cam), K, d, c), mmap) if m.area_mm2 > 15])
        nb = np.array([m.normal for m in mark_detect.detect_marks(ball_unwrap.unwrap(frame(b, cam), K, d, c), mmap) if m.area_mm2 > 15])
        if len(na) < 3 or len(nb) < 3: print(cam, a, b, "too few blobs"); continue
        pairs = []
        for i, n in enumerate(na):
            ang = np.degrees(np.arccos(np.clip(nb @ n, -1, 1))); j = int(np.argmin(ang))
            if 1.0 < ang[j] < 25.0: pairs.append((n, nb[j]))
        if len(pairs) < 3: print(cam, a, b, "too few matches"); continue
        A = np.array([p[0] for p in pairs]); B = np.array([p[1] for p in pairs])
        Q = bo.kabsch(A, B)
        if cam == "cam2": Q = rig.r.T @ Q @ rig.r      # into cam1's frame
        rv, _ = cv2.Rodrigues(Q); rv = rv.ravel(); th = np.degrees(np.linalg.norm(rv))
        print("%s %s->%s: %d blob matches, turn %.1f deg, axis . down = %+.2f  (+ = clockwise from above)" % (cam, a, b, len(pairs), th, rv @ down / np.linalg.norm(rv)))
