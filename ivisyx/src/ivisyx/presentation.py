"""Explicitly synthetic presentation events, separate from camera measurements."""

import time

MODERATE_EVENT = (
    "ivisyx presentation sensor event: SYNTHETIC, NOT A CAMERA MEASUREMENT. "
    "The scripted drowsiness score is 50/100, MODERATE. Say exactly: "
    "Moderate drowsiness detected. Please put on your ivisyx glasses. "
    "Follow your approved fatigue procedures. "
    "Do not greet, ask for confirmation, or start a checklist. "
    "Set the display message to Put on ivisyx glasses. "
    "Do not say presentation test. The screen marks the score TEST. "
    "If asked, explain that the score is scripted, not a camera measurement. "
    "Never claim this score measures the pilot or that glasses treat fatigue."
)


class PresentationSequence:
    def __init__(self, display):
        self.display = display
        self.started = False
        self.alert_sent = False
        self._began_at = 0.0

    def begin(self):
        self.started = True
        self._began_at = time.monotonic()
        self.display.set_message("Pilot support ready")
        self.display.robot.send_score(50, synthetic=True)

    @property
    def tracking_paused(self):
        return self.started

    @property
    def dialogue_complete(self):
        return self.alert_sent and self.display.message in (
            "Put on ivisyx glasses", "Alert acknowledged"
        )

    def update(self, conversation, audio):
        if not self.started or self.alert_sent:
            return
        # The configured First Message already delivers the alert; do not repeat it.
        if self.display.message == "Put on ivisyx glasses":
            self.alert_sent = True
            return
        if audio.has_received_audio:
            if not audio.camera_window_available():
                return
        elif time.monotonic() - self._began_at < 5:
            return
        try:
            conversation.send_user_message(MODERATE_EVENT)
        except RuntimeError:
            return
        self.alert_sent = True
