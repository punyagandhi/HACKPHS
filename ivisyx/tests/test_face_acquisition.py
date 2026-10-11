import unittest
from unittest.mock import MagicMock

from ivisyx.face_acquisition import FaceAcquisition
from ivisyx.cores3_audio import CoreS3Bridge


class FaceAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.robot = MagicMock()
        self.display = MagicMock()
        self.search = FaceAcquisition(self.robot, self.display)
        self.search.begin(10)

    def test_pitch_settles_before_search(self):
        self.search.update(11, True)
        self.robot.search_yaw.assert_not_called()
        self.robot.hold_face_search.assert_not_called()
        self.assertFalse(self.search.found)
        self.assertFalse(self.search.ready_for_conversation)

    def test_first_detection_freezes_and_second_acquires(self):
        self.search.update(12, True)
        self.robot.hold_face_search.assert_called_once()
        self.assertFalse(self.search.found)
        self.search.update(12.3, True)
        self.assertTrue(self.search.found)
        self.assertTrue(self.search.ready_for_conversation)
        self.search.update(13, False)
        self.robot.search_yaw.assert_not_called()

    def test_detection_gap_resets_confirmation(self):
        self.search.update(12, True)
        self.search.update(12.3, False)
        self.search.update(12.6, True)
        self.assertFalse(self.search.found)

    def test_timeout_does_not_report_face_found(self):
        self.search.update(24, True)
        self.assertTrue(self.search.failed)
        self.assertFalse(self.search.found)
        self.robot.cancel_face_search.assert_called_once()
        self.assertTrue(self.search.ready_for_conversation)
        self.display.set_message.assert_called_with("No face found: continuing")
        self.search.update(25, False)
        self.robot.search_yaw.assert_not_called()

    def test_sweep_is_small_and_rate_limited(self):
        self.search.update(12, False)
        self.search.update(12.2, False)
        self.robot.search_yaw.assert_called_once_with(4)
        for index in range(1, len(self.search.OFFSETS)):
            self.search.update(12 + index * .7, False)
        offsets = [call.args[0] for call in self.robot.search_yaw.call_args_list]
        self.assertEqual(offsets, list(self.search.OFFSETS))
        self.assertLessEqual(max(map(abs, offsets)), 12)

    def test_motor_error_does_not_report_success(self):
        self.robot.hold_face_search.side_effect = RuntimeError("No servo response")
        with self.assertRaises(RuntimeError):
            self.search.update(12, True)
        self.assertFalse(self.search.found)

    def test_yaw_rejects_unsafe_values_before_writing(self):
        bridge = CoreS3Bridge(MagicMock())
        for degrees in (-13, 13, True, 1.5):
            with self.assertRaises(ValueError):
                bridge.search_yaw(degrees)
        bridge._serial.write.assert_not_called()
