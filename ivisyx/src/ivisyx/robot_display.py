"""Map agent reminders to the robot display; legacy checklist commands remain compatible."""

import re
import threading


class RobotDisplay:
    def __init__(self, robot):
        self.robot = robot
        self._lock = threading.RLock()
        self.step = -1
        self.message = "Pilot support ready"

    def start(self):
        with self._lock:
            self.robot.show_checklist(self.step)
            self.robot.show_message(self.message)

    def agent_response(self, text):
        print(f"ivisyx: {text}", flush=True)
        normalized = " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())
        with self._lock:
            if "put on" in normalized and "glasses" in normalized:
                self.set_message("Put on ivisyx glasses")
            elif "are you feeling drowsy" in normalized:
                self.set_message("Feeling drowsy?")
            elif "please stay attentive to how you feel" in normalized:
                self.set_message("Alert acknowledged")

    def set_message(self, message):
        with self._lock:
            if message != self.message:
                self.robot.show_message(message)
                self.message = message

    def update_tool(self, parameters):
        with self._lock:
            step = parameters.get("checklist_step")
            message = parameters.get("message")
            if step is not None and (
                isinstance(step, bool) or not isinstance(step, int) or not -1 <= step <= 2
            ):
                raise ValueError("Checklist step must be -1..2")
            if message is not None and not isinstance(message, str):
                raise ValueError("message must be text")
            if step is not None:
                self.robot.show_checklist(step)
                self.step = step
            if message is not None:
                self.set_message(message)
            return {"checklist_step": self.step, "message": self.message}

    def user_transcript(self, text):
        print(f"You: {text}", flush=True)

    def client_tools(self):
        from elevenlabs.conversational_ai.conversation import ClientTools

        tools = ClientTools()
        tools.register("update_robot_display", self.update_tool)
        return tools
