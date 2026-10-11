import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ivisyx.presentation import MODERATE_EVENT, PresentationSequence
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
        self.robot.send_score.assert_not_called()

    def test_tracking_stays_paused_after_start(self):
        self.assertFalse(self.sequence.tracking_paused)
        self.sequence.begin()
        self.assertTrue(self.sequence.tracking_paused)
        self.display.set_message("Put on ivisyx glasses")
        self.assertTrue(self.sequence.tracking_paused)

    def test_score_is_marked_synthetic_at_start(self):
        self.sequence.begin()
        self.robot.send_score.assert_called_once_with(50, synthetic=True)

    def test_correct_first_message_is_not_interrupted_or_repeated(self):
        self.sequence.begin()
        self.audio.camera_window_available.return_value = False
        self.display.agent_response("Moderate drowsiness detected. Are you feeling drowsy?")
        self.sequence.update(self.conversation, self.audio)
        self.sequence.update(self.conversation, self.audio)
        self.assertTrue(self.sequence.alert_sent)
        self.conversation.send_user_message.assert_not_called()
        self.robot.show_message.assert_called_with("Feeling drowsy?")

    def test_old_opening_finishes_before_fallback_alert(self):
        self.sequence.begin()
        self.audio.has_received_audio = True
        self.audio.camera_window_available.return_value = False
        self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_not_called()
        self.audio.camera_window_available.return_value = True
        self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_called_once_with(MODERATE_EVENT)

    def test_no_first_message_falls_back_after_five_seconds(self):
        self.audio.has_received_audio = False
        with patch("ivisyx.presentation.time.monotonic", return_value=10):
            self.sequence.begin()
            self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_not_called()
        with patch("ivisyx.presentation.time.monotonic", return_value=15):
            self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_called_once_with(MODERATE_EVENT)

    def test_fallback_alert_is_sent_once(self):
        self.sequence.begin()
        self.sequence.update(self.conversation, self.audio)
        self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_called_once_with(MODERATE_EVENT)

    def test_question_does_not_show_glasses_before_agent_affirmative_reply(self):
        self.display.agent_response("Moderate drowsiness detected. Are you feeling drowsy?")
        self.display.user_transcript("yes")
        self.robot.show_message.assert_called_once_with("Feeling drowsy?")
        self.display.agent_response("Please put on your ivisyx glasses. Follow your approved fatigue procedures.")
        self.robot.show_message.assert_called_with("Put on ivisyx glasses")

    def test_event_asks_question_and_waits_for_affirmative_answer(self):
        self.assertIn("Moderate drowsiness detected. Are you feeling drowsy?", MODERATE_EVENT)
        self.assertIn("Only if affirmative", MODERATE_EVENT)
        self.assertIn("If negative", MODERATE_EVENT)

    def test_negative_answer_leaves_glasses_reminder_off(self):
        self.display.agent_response("Moderate drowsiness detected. Are you feeling drowsy?")
        self.display.user_transcript("no")
        self.display.agent_response("Understood. Please stay attentive to how you feel.")
        self.robot.show_message.assert_called_with("Alert acknowledged")
        self.assertNotIn("Put on ivisyx glasses", [c.args[0] for c in self.robot.show_message.call_args_list])

    def test_fallback_retries_when_socket_not_ready(self):
        self.sequence.begin()
        self.conversation.send_user_message.side_effect = [RuntimeError("Not connected"), None]
        self.sequence.update(self.conversation, self.audio)
        self.assertFalse(self.sequence.alert_sent)
        self.sequence.update(self.conversation, self.audio)
        self.assertTrue(self.sequence.alert_sent)

    def test_dialogue_complete_after_glasses_suggestion(self):
        self.sequence.begin()
        self.display.agent_response("Please put on your ivisyx glasses.")
        self.sequence.update(self.conversation, self.audio)
        self.assertTrue(self.sequence.dialogue_complete)

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
