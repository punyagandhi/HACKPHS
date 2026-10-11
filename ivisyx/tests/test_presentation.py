import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ivisyx.presentation import MODERATE_EVENT, START_EVENT, PresentationSequence
from ivisyx.robot_display import RobotDisplay
from ivisyx.cores3_audio import CoreS3Bridge
from ivisyx.face_tracking import robot_preview
from test_cores3_audio import SerialFixture


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.robot = MagicMock()
        self.display = RobotDisplay(self.robot)
        self.sequence = PresentationSequence(self.display)
        self.conversation = MagicMock()
        self.audio = MagicMock()

    def test_no_scripted_event_before_button(self):
        self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_not_called()

    def test_two_questions_before_synthetic_alert(self):
        self.sequence.begin()
        self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_called_once_with(START_EVENT)
        for question in ("Have you reviewed your aircraft's approved preflight checklist?",
                         "Are you feeling alert and ready?"):
            self.display.agent_response(question)
            self.sequence.update(self.conversation, self.audio)
        self.assertFalse(self.sequence.alert_sent)
        self.display.agent_response("Preflight check-in complete.")
        self.audio.camera_window_available.return_value = False
        self.sequence.update(self.conversation, self.audio)
        self.assertFalse(self.sequence.alert_sent)
        self.audio.camera_window_available.return_value = True
        self.sequence.update(self.conversation, self.audio)
        self.sequence.update(self.conversation, self.audio)
        self.assertEqual(self.conversation.send_user_message.call_count, 2)
        self.conversation.send_user_message.assert_called_with(MODERATE_EVENT)
        self.robot.send_score.assert_called_once_with(50, synthetic=True)
        self.robot.show_message.assert_called_with("Put on glasses")

    def test_retries_start_when_socket_not_ready(self):
        self.sequence.begin()
        self.conversation.send_user_message.side_effect = [RuntimeError("Not connected"), None]
        self.sequence.update(self.conversation, self.audio)
        self.assertFalse(self.sequence.start_sent)
        self.sequence.update(self.conversation, self.audio)
        self.assertTrue(self.sequence.start_sent)

    def test_real_scores_are_not_accepted_as_scripted(self):
        bridge = CoreS3Bridge(SerialFixture())
        for score, synthetic in ((50, False), (101, True), (True, True)):
            with self.assertRaises(ValueError):
                bridge.send_score(score, synthetic=synthetic)

    def test_binary_preview_protocol_and_size_validation(self):
        jpeg = b"\xff\xd8\xff\xd9"
        serial = SerialFixture([b"ready:preview\n", b"ok:preview\n"])
        bridge = CoreS3Bridge(serial)
        bridge.show_preview(jpeg)
        self.assertEqual(serial.writes, [b"preview:4\n", jpeg])
        for invalid in (b"bad", bytes(20001)):
            with self.assertRaises(ValueError):
                bridge.show_preview(invalid)

    def test_button_counter_is_polled_not_unsolicited(self):
        serial = SerialFixture([b"demo:presses=3 motion=commanded\n"])
        self.assertEqual(CoreS3Bridge(serial).presentation_status(),
                         {"presses": 3, "motion": "commanded"})

    def test_eye_thumbnail_dimensions_and_tracked_pixels(self):
        import cv2
        import numpy as np

        points = [SimpleNamespace(x=.5, y=.5) for _ in range(478)]
        jpeg = robot_preview(np.zeros((240, 320, 3), dtype=np.uint8),
                             SimpleNamespace(face_landmarks=[points]))
        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(image.shape[:2], (108, 144))
        self.assertGreater(int(image[54, 72, 1]), 80)

    def test_two_item_bounds(self):
        bridge = CoreS3Bridge(SerialFixture())
        with self.assertRaises(ValueError):
            bridge.show_checklist(3)
