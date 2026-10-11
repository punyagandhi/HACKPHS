"""Exercise glasses-triggered return without a cloud conversation."""

import time

from ivisyx.config import load_settings
from ivisyx.cores3_audio import connect_audio_bridge
from ivisyx.stackchan import StackChanCommand


def main():
    settings = load_settings()
    robot = connect_audio_bridge(settings.stackchan_port, settings.stackchan_baud)
    try:
        robot.arm_presentation(True)
        robot.send(StackChanCommand("demo", "tilt"))
        robot.start_face_search()
        robot.search_yaw(8)
        time.sleep(2.5)
        before = robot.home_status()
        print("Before glasses:", before, flush=True)
        robot.show_message("Feeling drowsy?")
        if robot.home_status()["return"] != "idle":
            raise RuntimeError("Head returned before glasses were requested")
        robot.show_message("Put on ivisyx glasses")
        time.sleep(3)
        after = robot.home_status()
        print("After glasses:", after, flush=True)
        print("Lights:", robot.lights_status(), flush=True)
        if after["return"] != "commanded" or any(
            abs(after[axis] - after["start_" + axis]) > 12 for axis in ("yaw", "pitch")
        ):
            raise RuntimeError("Servo feedback does not confirm return to starting pose")
        print("Both servos returned within 12 position units (3.75 degrees) of their saved start.", flush=True)
        time.sleep(3)
    finally:
        try:
            robot.arm_presentation(False)
            robot.idle()
        finally:
            robot.close()


if __name__ == "__main__":
    main()
