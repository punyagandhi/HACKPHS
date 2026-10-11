"""Explicitly synthetic presentation events, separate from camera measurements."""

START_EVENT = (
    "ivisyx presentation control: START. Begin a two-item pilot preflight check-in now. "
    "Ask exactly: Have you reviewed your aircraft's approved preflight checklist? "
    "Wait for confirmation, then ask exactly: Are you feeling alert and ready? "
    "Wait again, then say exactly: Preflight check-in complete. "
    "Do not add other checklist items. Keep each reply short."
)
MODERATE_EVENT = (
    "ivisyx presentation sensor event: SYNTHETIC, NOT A CAMERA MEASUREMENT. "
    "The scripted drowsiness score is 50/100, MODERATE. Say exactly: "
    "Presentation alert: moderate drowsiness score. Please put on your glasses. "
    "Never claim this score measures the pilot or that glasses treat fatigue."
)


class PresentationSequence:
    def __init__(self, display):
        self.display = display
        self.started = False
        self.start_sent = False
        self.alert_sent = False

    def begin(self):
        self.started = True
        self.display.update_tool({"checklist_step": -1, "message": "PRESENTATION MODE"})

    def update(self, conversation, audio):
        if not self.started:
            return
        if not self.start_sent:
            try:
                conversation.send_user_message(START_EVENT)
            except RuntimeError:
                return
            self.start_sent = True
        elif not self.alert_sent and self.display.step == 2 and audio.camera_window_available():
            conversation.send_user_message(MODERATE_EVENT)
            self.alert_sent = True
            self.display.set_message("Put on glasses")
            self.display.robot.send_score(50, synthetic=True)
