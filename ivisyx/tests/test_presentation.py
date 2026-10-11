import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

    def test_start_waits_for_greeting_to_finish(self):
        self.sequence.begin()
        self.audio.has_received_audio = True
        self.audio.camera_window_available.return_value = False
        self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_not_called()
        self.audio.camera_window_available.return_value = True
        self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_called_once_with(START_EVENT)

    def test_no_greeting_falls_back_after_five_seconds(self):
        self.audio.has_received_audio = False
        with patch("ivisyx.presentation.time.monotonic", return_value=10):
            self.sequence.begin()
            self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_not_called()
        with patch("ivisyx.presentation.time.monotonic", return_value=15):
            self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_called_once_with(START_EVENT)

    def test_one_question_before_synthetic_alert(self):
        self.sequence.begin()
        self.sequence.update(self.conversation, self.audio)
        self.conversation.send_user_message.assert_called_once_with(START_EVENT)
        for question in ("Have you reviewed your aircraft's approved preflight checklist?",):
            self.display.agent_response(question)
            self.sequence.update(self.conversation, self.audio)
        self.assertFalse(self.sequence.alert_sent)
        self.display.agent_response("Preflight checklist complete.")
        self.audio.camera_window_available.return_value = False
        self.sequence.update(self.conversation, self.audio)
        self.assertFalse(self.sequence.alert_sent)
        self.audio.camera_window_available.return_value = True
        self.sequence.update(self.conversation, self.audio)
        self.sequence.update(self.conversation, self.audio)
        self.assertEqual(self.conversation.send_user_message.call_count, 2)
        self.conversation.send_user_message.assert_called_with(MODERATE_EVENT)
        self.robot.send_score.assert_called_once_with(50, synthetic=True)
        self.robot.show_message.assert_called_with("Feeling drowsy?")

    def test_glasses_reminder_follows_agent_affirmative_branch(self):
        self.display.agent_response("Moderate drowsiness detected. Are you feeling drowsy?")
        self.display.user_transcript("yes")
        self.robot.show_message.assert_called_once_with("Feeling drowsy?")
        self.display.agent_response("Please put on your ivisyx glasses. Follow your approved fatigue procedures.")
        self.robot.show_message.assert_called_with("Put on ivisyx glasses")

    def test_negative_answer_does_not_show_glasses(self):
        self.display.agent_response("Moderate drowsiness detected. Are you feeling drowsy?")
        self.display.user_transcript("no")
        self.display.agent_response("Understood. Please stay attentive to how you feel.")
        self.robot.show_message.assert_called_with("Alert acknowledged")
        self.assertNotIn("Put on ivisyx glasses", [call.args[0] for call in self.robot.show_message.call_args_list])

    def test_event_instructs_agent_to_wait_for_answer(self):
        self.assertIn("Wait for the pilot's answer", MODERATE_EVENT)
        self.assertIn("Only if they affirm", MODERATE_EVENT)
        self.assertIn("If they deny", MODERATE_EVENT)

    def test_start_has_one_checklist_question_and_exact_completion(self):
        self.assertEqual(len(RobotDisplay.QUESTIONS), 1)
        self.assertNotIn("Are you feeling alert and ready", START_EVENT)
        self.assertIn("Preflight checklist complete.", START_EVENT)
        self.assertIn("Say exactly: Moderate drowsiness detected.", MODERATE_EVENT)

    def test_preview_waits_for_drowsiness_answer_acknowledgement(self):
        self.sequence.alert_sent = True
        self.display.set_message("Feeling drowsy?")
        self.assertFalse(self.sequence.dialogue_complete)
        for message in ("Put on ivisyx glasses", "Alert acknowledged"):
            self.display.set_message(message)
            self.assertTrue(self.sequence.dialogue_complete)

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
