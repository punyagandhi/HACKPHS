from __future__ import annotations

import os
import signal
import argparse
from collections.abc import Callable

from ivisyx.config import Settings, load_settings
from ivisyx.stackchan import Expression, StackChan
from ivisyx.robot_display import RobotDisplay


def run_desktop_conversation(
    settings: Settings,
    stackchan: StackChan,
    user_id: str | None = None,
    audio_interface=None,
) -> str | None:
    import certifi

    # python.org macOS builds may lack a configured system certificate bundle.
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    from elevenlabs.client import ElevenLabs
    from elevenlabs.conversational_ai.conversation import Conversation
    from ivisyx.cores3_audio import CoreS3AudioInterface

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    display = RobotDisplay(stackchan)
    display.start()
    audio_interface = audio_interface if audio_interface is not None else CoreS3AudioInterface(stackchan)

    conversation = Conversation(
        client,
        settings.agent_id,
        user_id=user_id,
        requires_auth=settings.requires_auth,
        audio_interface=audio_interface,
        callback_user_transcript=_on_user_transcript(stackchan),
        callback_agent_response=_on_agent_response(stackchan, display),
        callback_agent_response_correction=_on_agent_response_correction(stackchan, display),
        client_tools=display.client_tools(),
    )
    if audio_interface is not None and hasattr(audio_interface, "on_error"):
        audio_interface.on_error = conversation.end_session

    def end_session(_sig: int, _frame: object) -> None:
        print("\nEnding ivisyx session...")
        conversation.end_session()

    previous_handler = signal.signal(signal.SIGINT, end_session)
    try:
        print("Connecting ivisyx. Say 'Hello ivisyx' to start. Press Ctrl+C to end.")
        stackchan.listen_started()
        conversation.start_session()
        conversation_id = conversation.wait_for_session_end()
        if audio_interface is not None and getattr(audio_interface, "error", None):
            raise RuntimeError("Voice audio connection failed.") from audio_interface.error
        if not conversation_id:
            raise RuntimeError(
                "No conversation was established. Check the error above, your network, "
                "and whether this agent needs ELEVENLABS_API_KEY in .env."
            )
        return conversation_id
    finally:
        signal.signal(signal.SIGINT, previous_handler)
        try:
            if audio_interface is not None:
                audio_interface.stop()
        finally:
            stackchan.reset()


def _on_user_transcript(stackchan: StackChan) -> Callable[[str], None]:
    def callback(transcript: str) -> None:
        print(f"You: {transcript}")
        stackchan.think_started()

    return callback


def _on_agent_response(stackchan: StackChan, display=None) -> Callable[[str], None]:
    def callback(response: str) -> None:
        if display is not None:
            display.agent_response(response)
        else:
            print(f"ivisyx: {response}")
        stackchan.speak_started()

    return callback


def _on_agent_response_correction(stackchan: StackChan, display=None) -> Callable[[str, str], None]:
    def callback(original: str, corrected: str) -> None:
        print(f"ivisyx corrected: {original} -> {corrected}")
        if display is not None:
            display.agent_response(corrected)
        stackchan.set_expression(Expression.SPEAKING)

    return callback


def main() -> None:
    parser = argparse.ArgumentParser(description="ivisyx conversational voice assistant")
    parser.add_argument("--audio", choices=("cores3",), default="cores3")
    args = parser.parse_args()
    settings = load_settings()
    audio_interface = None
    if args.audio == "cores3":
        from ivisyx.cores3_audio import CoreS3AudioInterface, connect_audio_bridge
        stackchan = connect_audio_bridge(settings.stackchan_port, settings.stackchan_baud)
        audio_interface = CoreS3AudioInterface(stackchan)
    try:
        conversation_id = run_desktop_conversation(settings, stackchan, audio_interface=audio_interface)
        print(f"Conversation ID: {conversation_id}")
    finally:
        stackchan.close()


if __name__ == "__main__":
    main()
