"""Explicitly synthetic presentation events, separate from camera measurements."""

import time

START_EVENT = (
    "ivisyx presentation control: START. Begin a one-question preflight check-in now. "
    "Ask exactly: Have you reviewed your aircraft's approved preflight checklist? "
    "Wait for confirmation, then say exactly: Preflight checklist complete. "
    "Do not add other checklist items. Keep each reply short."
)
MODERATE_EVENT = (
    "ivisyx presentation sensor event: SYNTHETIC, NOT A CAMERA MEASUREMENT. "
    "The scripted drowsiness score is 50/100, MODERATE. Say exactly: "
    "Moderate drowsiness detected. Are you feeling drowsy? "
    "Wait for the pilot's answer. Only if they affirm feeling drowsy, say exactly: "
    "Please put on your ivisyx glasses. Follow your approved fatigue procedures. "
    "If they deny drowsiness, say: Understood. Please stay attentive to how you feel. "
    "If their answer is unclear, ask: Are you feeling drowsy? "
    "Do not say presentation test. The screen marks the score TEST. "
    "If asked, explain that the score is scripted, not a camera measurement. "
    "Never claim this score measures the pilot or that glasses treat fatigue."
)


class PresentationSequence:
    def __init__(self, display):
        self.display = display
        self.started = False
        self.start_sent = False
        self.alert_sent = False
        self._began_at = 0.0

    def begin(self):
        self.started = True
        self._began_at = time.monotonic()
        self.display.update_tool({"checklist_step": -1, "message": "PRESENTATION MODE"})

    @property
    def tracking_paused(self):
        return self.started

    @property
    def dialogue_complete(self):
        return self.alert_sent and self.display.message in (
            "Put on ivisyx glasses", "Alert acknowledged"
        )

    def update(self, conversation, audio):
        if not self.started:
            return
        if not self.start_sent:
            # A START user-message can interrupt the agent's automatic greeting.
            if audio.has_received_audio:
                if not audio.camera_window_available():
                    return
            elif time.monotonic() - self._began_at < 5:
                return
            try:
                conversation.send_user_message(START_EVENT)
            except RuntimeError:
                return
            self.start_sent = True
        elif not self.alert_sent and self.display.step == 2 and audio.camera_window_available():
            conversation.send_user_message(MODERATE_EVENT)
            self.alert_sent = True
            self.display.set_message("Feeling drowsy?")
            self.display.robot.send_score(50, synthetic=True)
