"""The detector, against real golf balls rather than synthetic discs.

Every detector change on 2026-08-10/11 was convincing against drawn circles
and behaved differently against a real ball - dimples, a printed logo, wood
grain, one-sided light. Twice a test passed before the function it was meant
to exercise had been wired in at all. Synthetic fixtures are still worth
having: they are the only place truth is known exactly. They are not
sufficient, and this module is the other half.

See fixtures/ball_pairs/README.md for what each pair is and what it cost to
learn.
"""

import os
import unittest

import cv2
import numpy as np

from sp1_vision import ball_pair, stereo_geometry

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "ball_pairs")


def load_pair(name):
    frames = []
    for camera in ("cam1", "cam2"):
        path = os.path.join(FIXTURES, name, camera + ".png")
        frame = cv2.imread(path)
        if frame is None:
            raise unittest.SkipTest("fixture not readable: " + path)
        frames.append(frame)
    return frames


def load_rig():
    return stereo_geometry.load_rig(
        os.path.join(REPO, "sp1_vision", "calibration_results",
                     "stereo_extrinsics.json"),
        os.path.join(REPO, "Software", "LMSourceCode", "ImageProcessing",
                     "golf_sim_config.json"))


class RealFrameTest(unittest.TestCase):
    def setUp(self):
        self.rig = load_rig()

    def _find(self, name):
        return ball_pair.find_ball_pair(self.rig, *load_pair(name))

    def test_the_ball_is_found_in_a_cluttered_room(self):
        # The positive control. A loudspeaker with a woofer, a tweeter and a
        # sphere on top of it are all in frame and all stronger circles than
        # the ball; on the run this came from, the detector of the day
        # returned the loudspeaker in 17 frames out of 24.
        pair, reason = self._find("cluttered_ball")
        self.assertIsNotNone(pair, reason)
        np.testing.assert_allclose(pair.xyz_m * 1000.0,
                                   [-37.0, 83.0, 475.0], atol=12.0)

    def test_nothing_a_resting_ball_could_not_be_is_ever_returned(self):
        # This pair once PASSED the 2 px reprojection gate at 1.96 px, with
        # both cameras locked onto the same loudspeaker 1295 mm away and
        # 27 mm ABOVE the optical axis. A small residual means the cameras
        # agree with each other, not that they are looking at a ball.
        #
        # Deliberately not asserting that this pair is rejected: a better
        # detector may well find the real ball in it, and that would be a
        # success. What must never happen is a confident answer that no ball
        # on a table could have produced.
        pair, _ = self._find("cluttered_decoy")
        if pair is None:
            return
        self.assertGreater(pair.xyz_m[1], 0.0,
                           "returned a point ABOVE the optical axis")
        self.assertLess(pair.xyz_m[2], ball_pair.MAX_DEPTH_M,
                        "returned a point beyond the measurement volume")

    @unittest.expectedFailure
    def test_a_ball_lit_from_one_side_is_found(self):
        # THE GOAL. This is a clean scene, a bare wall, and the ball is
        # plainly visible in both cameras - cam1 (504.5, 595.5) r 42.7,
        # cam2 (682.5, 608.5) r 35.0. Pairing those two triangulates to
        # (-59.2, +78.6, 409.2) mm, and +78.6 mm of height says it really is
        # the ball. It is rejected on a 2.71 px residual because Hough fits
        # the bright arc rather than the outline, and each camera sees the
        # shading from a different angle.
        #
        # 2.71 px is about 10 mm of depth. The budget is 1.8 mm. Until this
        # passes, no measurement taken with this detector is worth the floor
        # time - so it is marked as an expected failure rather than deleted
        # or quietly skipped, and turning it green is the definition of done.
        pair, reason = self._find("lit_from_one_side")
        self.assertIsNotNone(pair, reason)
        np.testing.assert_allclose(pair.xyz_m * 1000.0,
                                   [-59.2, 78.6, 409.2], atol=10.0)


if __name__ == "__main__":
    unittest.main()
