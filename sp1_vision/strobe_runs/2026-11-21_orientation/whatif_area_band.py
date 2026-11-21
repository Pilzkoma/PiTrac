"""What-if, not the method: the roll check with mark_detect.AREA_BAND's
lower edge changed at run time (real marks measure 0.67-0.81 of the map's
ink area, see results.txt). The committed constants are unchanged.

    python sp1_vision/strobe_runs/2026-11-21_orientation/whatif_area_band.py LOW SHOTS_DIR
"""
import os
import sys

sys.path.insert(0, os.getcwd())
from sp1_vision import mark_detect, orientation_check  # noqa: E402

low, shots = float(sys.argv[1]), sys.argv[2]
mark_detect.AREA_BAND = (low, mark_detect.AREA_BAND[1])
print("AREA_BAND = %r (what-if)" % (mark_detect.AREA_BAND,))
fix = "sp1_vision/tests/fixtures/marked_ball/"
orientation_check.main(["static", fix + "static_cam1.png", fix + "static_cam2.png"])
for a, b in (("8.74", "9.05"), ("16.02", "16.42"), ("44.86", "45.13")):
    orientation_check.main(["roll", shots + "/cam1", shots + "/cam2", a, b])
