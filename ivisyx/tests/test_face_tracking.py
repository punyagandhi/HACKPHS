import importlib.util
from types import SimpleNamespace
import unittest

from ivisyx.face_tracking import decode_frame, draw_tracking


VISION_AVAILABLE = all(importlib.util.find_spec(name) for name in ("cv2", "numpy", "mediapipe"))


@unittest.skipUnless(VISION_AVAILABLE, "Optional vision dependencies are not installed")
class FaceOverlayTests(unittest.TestCase):
    def test_missing_face_has_no_stale_points(self):
        import numpy as np

        canvas = draw_tracking(np.zeros((240, 320, 3), dtype=np.uint8), SimpleNamespace(face_landmarks=[]), 10)
        self.assertEqual(canvas.shape, (720, 960, 3))
        self.assertTrue(canvas[:44].any())
        self.assertFalse(canvas[45:].any())

    def test_points_and_eye_contours_render(self):
        import numpy as np

        points = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
        canvas = draw_tracking(np.zeros((240, 320, 3), dtype=np.uint8), SimpleNamespace(face_landmarks=[points]), 10)
        self.assertTrue(canvas[350:370, 470:490].any())

    def test_decoder_rejects_non_image(self):
        with self.assertRaisesRegex(RuntimeError, "valid 320x240"):
            decode_frame(b"not a jpeg")


if __name__ == "__main__":
    unittest.main()
