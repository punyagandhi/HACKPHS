"""Local face-point demonstration using only the CoreS3 camera."""

import argparse
from pathlib import Path
import time

from ivisyx.config import load_settings
from ivisyx.cores3_camera import connect_camera
from ivisyx.drowsiness import EYES, AgentAlert, EyelidMonitor, eye_ratios
from ivisyx.robot_display import RobotDisplay
from ivisyx.presentation import PresentationSequence

PROJECT = Path(__file__).resolve().parents[2]
MODEL = PROJECT / "models" / "face_landmarker.task"
WINDOW = "ivisyx | Stack-chan face tracking"


def decode_frame(jpeg):
    import cv2
    import numpy as np

    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape[:2] != (240, 320):
        raise RuntimeError("Expected a valid 320x240 image from the CoreS3 camera.")
    return frame


def draw_tracking(frame, result, fps, eyelids=None, agent_status=None):
    import cv2
    from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarksConnections

    canvas = cv2.resize(frame, (960, 720), interpolation=cv2.INTER_LINEAR)
    faces = result.face_landmarks
    if faces:
        points = [(round(point.x * 959), round(point.y * 719)) for point in faces[0]]
        visible = points if eyelids is None else [points[i] for eye in EYES for i in eye]
        for x, y in visible:
            if 0 <= x < 960 and 0 <= y < 720:
                cv2.circle(canvas, (x, y), 1, (80, 240, 160), -1, cv2.LINE_AA)
        for connection in FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYE + FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYE:
            cv2.line(canvas, points[connection.start], points[connection.end], (0, 220, 255), 2, cv2.LINE_AA)
        status = f"FACE TRACKED   {len(points)} points" if eyelids is None else eyelids.state
    else:
        status = "NO FACE DETECTED"
    cv2.rectangle(canvas, (0, 0), (960, 44), (24, 24, 24), -1)
    cv2.putText(canvas, status, (16, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 230, 230), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"{fps:.1f} FPS", (825, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1, cv2.LINE_AA)
    if eyelids is not None:
        cv2.rectangle(canvas, (0, 624), (960, 720), (24, 24, 24), -1)
        color = (80, 80, 255) if eyelids.reason else (230, 230, 230)
        cv2.putText(canvas, f"Closure {eyelids.closed_seconds:.1f}s   Closure-time proxy {eyelids.closure_fraction:.0%}   Coverage {eyelids.coverage:.0%}", (16, 653), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
        cv2.putText(canvas, f"EXPERIMENTAL   {agent_status or 'Agent off'}", (16, 691), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1, cv2.LINE_AA)
    return canvas


def robot_preview(frame, result):
    import cv2

    thumbnail = cv2.resize(frame, (144, 108), interpolation=cv2.INTER_AREA)
    if result.face_landmarks:
        for eye in EYES:
            for index in eye:
                point = result.face_landmarks[0][index]
                x, y = round(point.x * 143), round(point.y * 107)
                if 0 <= x < 144 and 0 <= y < 108:
                    cv2.circle(thumbnail, (x, y), 1, (0, 255, 80), -1)
    else:
        cv2.putText(thumbnail, "NO EYES", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, .35, (0, 220, 255), 1)
    success, jpeg = cv2.imencode(".jpg", thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 55])
    if not success:
        raise RuntimeError("Could not encode robot eye preview")
    return jpeg.tobytes()


def main() -> None:
    parser = argparse.ArgumentParser(description="CoreS3 camera face-point demonstration on the Mac")
    parser.add_argument("--seconds", type=float, default=0, help="Stop automatically after this duration")
    parser.add_argument("--headless", action="store_true", help="Check camera and inference without a window")
    parser.add_argument("--snapshot", type=Path, help="Optionally save the final annotated image locally")
    parser.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0)
    parser.add_argument("--drowsiness", action="store_true", help="Show only eyelid points and demonstration metrics")
    parser.add_argument("--agent", action="store_true", help="Use CoreS3 microphone/speaker for ElevenLabs and send sustained eyelid alerts")
    parser.add_argument("--presentation", action="store_true", help="Power-button tilt, one-question check-in and synthetic alert")
    args = parser.parse_args()
    if args.presentation:
        args.agent = args.drowsiness = True
    if args.seconds < 0 or (args.headless and args.seconds <= 0):
        parser.error("Headless checks require a positive --seconds duration")

    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    if not MODEL.is_file():
        raise RuntimeError(f"Face model missing: {MODEL}. See README camera setup.")
    options = vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    settings = load_settings()
    monitor = EyelidMonitor() if args.drowsiness and not args.presentation else None
    conversation = None
    robot_audio = None
    notifier = None
    agent_status = "Agent off"
    last_eyelid_state = None
    camera = None
    robot_display = None
    frames = tracked = 0
    canvas = None
    started = time.monotonic()
    timestamp = -1
    sequence = None
    conversation_started = False
    last_preview = -float("inf")
    last_button = 0
    try:
        with vision.FaceLandmarker.create_from_options(options) as landmarker:
            camera = connect_camera(settings.stackchan_port, settings.stackchan_baud)
            robot_display = RobotDisplay(camera)
            robot_display.start()
            if args.agent:
                import os
                import certifi
                from elevenlabs.client import ElevenLabs
                from elevenlabs.conversational_ai.conversation import Conversation
                from ivisyx.cores3_audio import CoreS3AudioInterface

                os.environ.setdefault("SSL_CERT_FILE", certifi.where())
                camera.stop_camera()
                robot_audio = CoreS3AudioInterface(camera)
                conversation = Conversation(
                    ElevenLabs(api_key=settings.elevenlabs_api_key), settings.agent_id,
                    requires_auth=settings.requires_auth, audio_interface=robot_audio,
                    callback_agent_response=robot_display.agent_response,
                    callback_user_transcript=robot_display.user_transcript,
                    client_tools=robot_display.client_tools(),
                )
                robot_audio.on_error = conversation.end_session
                if args.presentation:
                    last_button = camera.presentation_status()["presses"]
                    sequence = PresentationSequence(robot_display)
                    camera.arm_presentation(True)
                    robot_display.set_message("PRESENTATION: press power")
                    agent_status = "Waiting for power button"
                    print("Presentation ready: short-click the power button to tilt up and begin.", flush=True)
                else:
                    conversation.start_session()
                    conversation_started = True
                    notifier = AgentAlert(conversation)
                    agent_status = "Agent starting / Stack-chan audio"
            if monitor:
                print("Eyelid calibration: face the camera with both eyes naturally open for three seconds. Press C to recalibrate.", flush=True)
            if not args.headless:
                cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(WINDOW, 960, 720)
            print("CoreS3 face tracking started. Face the robot camera; close the window or press Escape to stop.", flush=True)
            while not args.seconds or time.monotonic() - started < args.seconds:
                if sequence is not None:
                    button = camera.presentation_status()
                    if button["presses"] != last_button and not sequence.started:
                        last_button = button["presses"]
                        if button["motion"] != "commanded":
                            print(f"Head tilt unavailable; continuing without movement. Servo diagnostics: {button}", flush=True)
                        sequence.begin()
                        conversation.start_session()
                        conversation_started = True
                        agent_status = "Presentation / Stack-chan audio"
                    sequence.update(conversation, robot_audio)
                    if conversation_started and not sequence.dialogue_complete:
                        if not args.headless and cv2.waitKey(1) & 0xFF in (27, ord("q")):
                            break
                        time.sleep(.05)
                        continue
                if args.presentation and time.monotonic() - last_preview < 1:
                    if not args.headless and cv2.waitKey(1) & 0xFF in (27, ord("q")):
                        break
                    time.sleep(.05)
                    continue
                if robot_audio is not None:
                    if robot_audio.error:
                        raise RuntimeError("Stack-chan audio failed; no Mac audio fallback.") from robot_audio.error
                    # Do not insert camera pauses into queued speech playback.
                    if not robot_audio.camera_window_available():
                        if not args.headless and cv2.waitKey(1) & 0xFF in (27, ord("q")):
                            break
                        time.sleep(0.05)
                        continue
                    frame = decode_frame(camera.frame_between_audio())
                else:
                    frame = decode_frame(camera.frame())
                if args.rotate:
                    rotations = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
                    frame = cv2.rotate(frame, rotations[args.rotate])
                # Video mode requires strictly increasing timestamps, including fast USB frames.
                timestamp = max(timestamp + 1, int((time.monotonic() - started) * 1000))
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp)
                if time.monotonic() - last_preview >= 1:
                    camera.show_preview(robot_preview(frame, result))
                    last_preview = time.monotonic()
                eyelids = None
                if monitor is not None:
                    ratios = eye_ratios(result.face_landmarks[0], frame.shape[1], frame.shape[0]) if result.face_landmarks else None
                    eyelids = monitor.update(time.monotonic(), ratios)
                    if eyelids.state != last_eyelid_state:
                        print(f"Eyelids: {eyelids.state}; continuous closure {eyelids.closed_seconds:.1f}s; closure-time proxy {eyelids.closure_fraction:.0%}", flush=True)
                        last_eyelid_state = eyelids.state
                if notifier is not None:
                    if agent_status.startswith("Agent starting"):
                        try:
                            conversation.send_contextual_update((PROJECT / "agent_prompt.txt").read_text())
                            agent_status = "Agent connected / Stack-chan audio"
                        except Exception:
                            pass
                    if eyelids is not None and notifier.update(time.monotonic(), eyelids):
                        agent_status = "Alert sent / Stack-chan audio"
                        robot_display.set_message("Demo: eye closure alert")
                frames += 1
                tracked += bool(result.face_landmarks)
                canvas = draw_tracking(frame, result, frames / max(time.monotonic() - started, 0.001), eyelids, agent_status)
                if not args.headless:
                    cv2.imshow(WINDOW, canvas)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        break
                    if key in (ord("c"), ord("C")) and monitor is not None:
                        monitor = EyelidMonitor()
                        print("Recalibrating: keep both eyes naturally open for three seconds.", flush=True)
                    if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                        break
            if args.snapshot and canvas is not None:
                args.snapshot.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(args.snapshot), canvas):
                    raise RuntimeError("Could not save the requested snapshot.")
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if conversation is not None and conversation_started:
                conversation.end_session()
                conversation_id = conversation.wait_for_session_end()
                print(f"Agent conversation: {conversation_id or 'not established; check network, robot USB audio, and agent configuration'}", flush=True)
        finally:
            try:
                if camera is not None:
                    try:
                        if args.presentation:
                            camera.arm_presentation(False)
                        camera.stop_camera()
                    finally:
                        camera.close()
            finally:
                if not args.headless:
                    cv2.destroyAllWindows()
                print(f"Tracking stopped: {frames} frames, face tracked in {tracked} frames.", flush=True)


if __name__ == "__main__":
    main()
