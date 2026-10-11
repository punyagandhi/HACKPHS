import queue
import threading
import unittest
from unittest.mock import MagicMock, patch

from ivisyx.desktop_audio import RobotDesktopAudio
from ivisyx.robot_display import RobotDisplay
from ivisyx.stackchan import StackChan


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.robot = MagicMock()
        self.display = RobotDisplay(self.robot)

    def test_start_shows_reminder_and_unstarted_checklist(self):
        self.display.start()
        self.robot.show_checklist.assert_called_once_with(-1)
        self.robot.show_message.assert_called_once_with("Pilot support ready")

    def test_preset_questions_and_completion_update_display(self):
        for step, question in enumerate(RobotDisplay.QUESTIONS):
            self.display.agent_response(question.upper() + "?")
            self.assertEqual(self.display.step, step)
        self.display.agent_response("Preflight check-in complete.")
        self.robot.show_checklist.assert_called_with(2)

    def test_user_confirmation_does_not_guess_checklist_state(self):
        self.display.user_transcript("yes")
        self.display.agent_response("Understood.")
        self.robot.show_checklist.assert_not_called()

    def test_repeated_question_does_not_resend(self):
        for _ in range(2):
            self.display.agent_response("Have you reviewed your aircraft's approved preflight checklist?")
        self.robot.show_checklist.assert_called_once_with(0)

    def test_tool_validates_every_field_before_changing_screen(self):
        for values in ({"checklist_step": 2, "message": 42},
                       {"checklist_step": True}, {"checklist_step": 6}):
            with self.assertRaises(ValueError):
                self.display.update_tool(values)
        self.robot.show_checklist.assert_not_called()
        self.robot.show_message.assert_not_called()

    def test_tool_updates_checklist_and_message(self):
        result = self.display.update_tool({"checklist_step": 1, "message": "Put on glasses"})
        self.assertEqual(result, {"checklist_step": 1, "message": "Put on glasses"})

    def test_message_is_single_line_ascii_and_bounded(self):
        robot = StackChan(MagicMock())
        robot.show_message("Put\non\rglasses " + "x" * 200)
        payload = robot._serial.write.call_args.args[0]
        self.assertEqual(payload.count(b"\n"), 1)
        self.assertEqual(len(payload), len(b"message:") + 120 + 1)

    def test_activity_rejects_unknown_state(self):
        with self.assertRaises(ValueError):
            StackChan().show_activity("dancing")


class DesktopActivityTests(unittest.TestCase):
    def setUp(self):
        self.robot = MagicMock()
        self.audio = RobotDesktopAudio(self.robot)
        self.audio.should_stop = threading.Event()
        self.audio.output_queue = queue.Queue()
        self.audio.out_stream = MagicMock()

    def test_speaking_only_during_playback_and_off_on_exit(self):
        self.audio.output_queue.put(b"\0" * 8000)
        writes = []

        def write(data):
            writes.append(data)
            self.robot.show_activity.assert_called_with("speaking")
            if len(writes) == 2:
                self.audio.should_stop.set()

        self.audio.out_stream.write.side_effect = write
        self.audio._output_thread()
        self.assertEqual([len(data) for data in writes], [4000, 4000])
        self.assertEqual([call.args[0] for call in self.robot.show_activity.call_args_list],
                         ["macmic", "speaking", "off"])

    def test_interrupt_drops_remaining_audio(self):
        self.audio.output_queue.put(b"\0" * 8000)

        def write(data):
            self.audio.interrupt()

        self.audio.out_stream.write.side_effect = write
        original_get = self.audio.output_queue.get

        def get(**kwargs):
            if self.audio.out_stream.write.called:
                self.audio.should_stop.set()
                raise queue.Empty
            return original_get(**kwargs)

        self.audio.output_queue.get = get
        self.audio._output_thread()
        self.audio.out_stream.write.assert_called_once()
        self.robot.show_activity.assert_called_with("off")

    def test_playback_failure_exposes_error_and_turns_lights_off(self):
        self.audio.output_queue.put(b"\0" * 4000)
        self.audio.out_stream.write.side_effect = OSError("speaker unavailable")
        self.audio._output_thread()
        self.assertIsInstance(self.audio.error, OSError)
        self.robot.show_activity.assert_called_with("off")

    def test_stop_is_idempotent(self):
        self.audio._started = True
        with patch("ivisyx.desktop_audio.DefaultAudioInterface.stop") as stop:
            self.audio.stop()
            self.audio.stop()
        stop.assert_called_once()
        self.robot.show_activity.assert_called_once_with("off")

    def test_start_failure_cleans_up_partial_audio_devices(self):
        self.audio.in_stream = MagicMock()
        self.audio.p = MagicMock()
        with patch("ivisyx.desktop_audio.DefaultAudioInterface.start", side_effect=OSError):
            with self.assertRaises(OSError):
                self.audio.start(lambda data: None)
        self.audio.in_stream.close.assert_called_once()
        self.audio.out_stream.close.assert_called_once()
        self.audio.p.terminate.assert_called_once()
        self.robot.show_activity.assert_called_with("off")
