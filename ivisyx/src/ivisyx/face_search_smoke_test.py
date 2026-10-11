"""Camera/servo startup check without opening an ElevenLabs conversation."""

import time

from ivisyx.config import load_settings
from ivisyx.cores3_camera import connect_camera
from ivisyx.face_acquisition import FaceAcquisition
from ivisyx.face_tracking import MODEL, decode_frame, robot_preview
from ivisyx.robot_display import RobotDisplay
from ivisyx.stackchan import StackChanCommand


def main():
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    settings = load_settings()
    options = vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO, num_faces=1,
    )
    camera = connect_camera(settings.stackchan_port, settings.stackchan_baud)
    try:
        camera.arm_presentation(True)
        camera.send(StackChanCommand("demo", "tilt"))
        print("Tilt status:", camera.presentation_status(), flush=True)
        search = FaceAcquisition(camera, RobotDisplay(camera))
        search.begin(time.monotonic())
        with vision.FaceLandmarker.create_from_options(options) as landmarker:
            timestamp = -1
            while not (search.found or search.failed):
                camera.presentation_status()
                frame = decode_frame(camera.frame())
                timestamp = max(timestamp + 1, int(time.monotonic() * 1000))
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                result = landmarker.detect_for_video(image, timestamp)
                camera.show_preview(robot_preview(frame, result))
                search.update(time.monotonic(), bool(result.face_landmarks))
                print(f"Face={bool(result.face_landmarks)} confirmations={search.hits} sweep_steps={search.index}", flush=True)
                time.sleep(.25)
        print("FACE ACQUIRED: search stopped; conversation would now start."
              if search.found else "NO FACE: stopped safely without starting speech.", flush=True)
    finally:
        try:
            camera.arm_presentation(False)
            camera.stop_camera()
        finally:
            camera.close()


if __name__ == "__main__":
    main()
