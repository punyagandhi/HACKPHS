"""On-demand JPEG frames over the existing, exclusively owned USB connection."""

from ivisyx.cores3_audio import CoreS3Bridge
from ivisyx.stackchan import StackChanCommand

MAX_JPEG_BYTES = 200000


class CoreS3Camera(CoreS3Bridge):
    def frame_between_audio(self) -> bytes:
        # Camera owns an I2S controller; release it before the next audio packet.
        with self._lock:
            self.start_camera()
            try:
                return self.frame()
            finally:
                self.stop_camera()

    def start_camera(self) -> None:
        self.send(StackChanCommand("camera", "on"))

    def stop_camera(self) -> None:
        self.send(StackChanCommand("camera", "off"))

    def frame(self) -> bytes:
        with self._lock:
            self._write(b"frame\n")
            header = self._reply("jpeg:")
            try:
                size = int(header.removeprefix("jpeg:"))
            except ValueError as exc:
                raise RuntimeError(f"Invalid JPEG header: {header!r}") from exc
            if not 1 <= size <= MAX_JPEG_BYTES:
                raise RuntimeError(f"Invalid JPEG size: {size}")
            data = self._exact(size)
            if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
                raise RuntimeError("CoreS3 returned an invalid JPEG frame.")
            return data


def connect_camera(port: str | None, baud: int) -> CoreS3Camera:
    import serial
    from ivisyx.stackchan import autodetect_stackchan_port

    port = port or autodetect_stackchan_port()
    if not port:
        raise RuntimeError("Connect the CoreS3 over USB before starting face tracking.")
    try:
        camera = CoreS3Camera(serial.Serial(port, baud, timeout=0.25, write_timeout=3, exclusive=True))
    except serial.SerialException as exc:
        raise RuntimeError("Cannot open CoreS3. Stop the voice assistant and Arduino serial monitor first.") from exc
    try:
        camera.start_camera()
    except Exception:
        camera.close()
        raise
    return camera
