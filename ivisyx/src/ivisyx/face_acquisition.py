"""Bounded startup search; speech remains off until a face is acquired."""


class FaceAcquisition:
    OFFSETS = (4, 8, 12, 8, 4, 0, -4, -8, -12, -8, -4, 0)
    TIMEOUT = 14.0

    def __init__(self, robot, display):
        self.robot = robot
        self.display = display
        self.started_at = 0.0
        self.next_move = 0.0
        self.index = 0
        self.hits = 0
        self.found = False
        self.failed = False

    def begin(self, now):
        self.robot.start_face_search()
        self.started_at = now
        self.next_move = now + 1.5
        self.display.set_message("Looking for your face")

    def update(self, now, has_face):
        if self.found or self.failed:
            return
        if now - self.started_at >= self.TIMEOUT:
            self.robot.cancel_face_search()
            self.failed = True
            self.display.set_message("No face found: press power")
            return
        if now < self.started_at + 1.5:
            return
        self.hits = self.hits + 1 if has_face else 0
        if has_face:
            # Freeze the current position even before the confirmation frame.
            if self.hits == 1:
                self.robot.hold_face_search()
            if self.hits >= 2:
                self.found = True
                self.display.set_message("Face found")
            return
        if now >= self.next_move and self.index < len(self.OFFSETS):
            self.robot.search_yaw(self.OFFSETS[self.index])
            self.index += 1
            self.next_move = now + 0.6
