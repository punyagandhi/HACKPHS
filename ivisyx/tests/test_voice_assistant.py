import signal
import unittest
from unittest.mock import MagicMock, patch

from ivisyx.config import Settings
from ivisyx.voice_assistant import run_desktop_conversation


class ConversationTests(unittest.TestCase):
    @patch("ivisyx.cores3_audio.CoreS3AudioInterface")
    @patch("elevenlabs.conversational_ai.conversation.Conversation")
    @patch("elevenlabs.client.ElevenLabs")
    def test_session_callbacks_and_cleanup(self, client, conversation, audio):
        audio.return_value.error = None
        conversation.return_value.wait_for_session_end.return_value = "conversation_test"
        robot = MagicMock()
        previous_handler = signal.getsignal(signal.SIGINT)

        result = run_desktop_conversation(Settings("agent_test"), robot, user_id="demo")

        self.assertEqual(result, "conversation_test")
        self.assertEqual(conversation.call_args.kwargs["user_id"], "demo")
        self.assertFalse(conversation.call_args.kwargs["requires_auth"])
        audio.assert_called_once_with(robot)
        self.assertIs(conversation.call_args.kwargs["audio_interface"], audio.return_value)
        conversation.return_value.start_session.assert_called_once_with()
        callbacks = conversation.call_args.kwargs
        callbacks["callback_user_transcript"]("Hello")
        callbacks["callback_agent_response"]("Hello pilot")
        robot.think_started.assert_called_once()
        robot.speak_started.assert_called_once()
        callbacks["callback_agent_response_correction"]("Hello pilot", "Hello")
        robot.show_transcript.assert_not_called()
        robot.show_response.assert_not_called()
        robot.reset.assert_called_once()
        self.assertEqual(signal.getsignal(signal.SIGINT), previous_handler)

    @patch("ivisyx.cores3_audio.CoreS3AudioInterface")
    @patch("elevenlabs.conversational_ai.conversation.Conversation")
    @patch("elevenlabs.client.ElevenLabs")
    def test_startup_failure_resets_robot_and_signal(self, client, conversation, audio):
        audio.return_value.error = None
        conversation.return_value.start_session.side_effect = RuntimeError("Connection failed")
        robot = MagicMock()
        previous_handler = signal.getsignal(signal.SIGINT)
        with self.assertRaisesRegex(RuntimeError, "Connection failed"):
            run_desktop_conversation(Settings("agent_test"), robot)
        robot.reset.assert_called_once()
        self.assertEqual(signal.getsignal(signal.SIGINT), previous_handler)


if __name__ == "__main__":
    unittest.main()
