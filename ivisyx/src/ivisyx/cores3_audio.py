"""Half-duplex 16 kHz PCM bridge over the CoreS3's native USB serial port."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

from elevenlabs.conversational_ai.conversation import AudioInterface

from ivisyx.stackchan import Expression, StackChan, StackChanCommand

SAMPLE_RATE = 16000
CHUNK_BYTES = 8000
PREBUFFER_BYTES = CHUNK_BYTES * 3
PREBUFFER_SECONDS = 0.75


class CoreS3Bridge(StackChan):
    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._lock = threading.RLock()
        self._queued_playback = False

    def _write(self, data: bytes) -> None:
        if self._serial is None:
            raise RuntimeError("CoreS3 serial connection is closed.")
        if self._serial.write(data) != len(data):
            raise RuntimeError("Incomplete USB serial write.")
        self._serial.flush()

    def _reply(self, expected: str, timeout: float = 5) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._serial is None:
                raise RuntimeError("CoreS3 serial connection is closed.")
            line = self._serial.readline().decode("utf-8", errors="replace").strip()
            if line.startswith(("ERR", "unknown:")):
                raise RuntimeError(f"CoreS3: {line}")
            if line.startswith(expected):
                return line
        raise TimeoutError(f"CoreS3 did not reply with {expected!r}.")

    def _exact(self, size: int) -> bytes:
        data = bytearray()
        deadline = time.monotonic() + 5
        while len(data) < size and time.monotonic() < deadline:
            data.extend(self._serial.read(size - len(data)))
        if len(data) != size:
            raise TimeoutError(f"Incomplete USB packet: {len(data)}/{size} bytes. Stop other robot programs and reconnect USB.")
        return bytes(data)

    def verify_audio(self) -> None:
        with self._lock:
            self._write(b"audio\n")
            reply = self._reply("audio:")
            if reply not in ("audio:pcm_16000:8000:v1", "audio:pcm_16000:8000:v2"):
                raise RuntimeError("Upload the ivisyx USB audio firmware first.")
            self._queued_playback = reply.endswith(":v2")

    def capture(self) -> bytes:
        with self._lock:
            self._write(b"mic\n")
            reply = self._reply("pcm:")
            if reply != f"pcm:{CHUNK_BYTES}":
                raise RuntimeError(f"Invalid microphone header: {reply!r}.")
            return self._exact(CHUNK_BYTES)

    def play(self, pcm: bytes) -> None:
        if not pcm or len(pcm) > CHUNK_BYTES or len(pcm) % 2:
            raise ValueError("Playback requires 2..8000 bytes of signed 16-bit PCM.")
        with self._lock:
            command = "playq" if self._queued_playback else "play"
            self._write(f"{command}:{len(pcm)}\n".encode())
            self._reply(f"ready:{command}")
            self._write(pcm)
            self._reply(f"ok:{command}")

    def send(self, command: StackChanCommand) -> None:
        with self._lock:
            encoded = command.encode()
            self._write(encoded)
            expected = "message" if command.name == "message" else encoded.decode().strip()
            self._reply("ok:" + expected)

    def check_expression(self, expression: Expression, timeout: float = 3.0) -> None:
        self.set_expression(expression)
        print(f"Firmware acknowledged {expression.value}")

    def idle(self) -> None:
        with self._lock:
            self._write(b"idle\n")
            self._reply("ok:idle")

    def drain_playback(self) -> None:
        if self._queued_playback:
            with self._lock:
                self._write(b"drain\n")
                self._reply("ok:drain")

    def status(self) -> str:
        with self._lock:
            self._write(b"status\n")
            return self._reply("display:")

    def show_preview(self, jpeg: bytes) -> None:
        if not 4 <= len(jpeg) <= 20000 or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
            raise ValueError("Preview requires a JPEG of at most 20000 bytes")
        with self._lock:
            self._write(f"preview:{len(jpeg)}\n".encode())
            self._reply("ready:preview")
            self._write(jpeg)
            self._reply("ok:preview")

    def presentation_status(self) -> dict:
        with self._lock:
            self._write(b"demo:status\n")
            reply = self._reply("demo:")
            values = dict(item.split("=", 1) for item in reply[5:].split())
            status = {"presses": int(values["presses"]), "motion": values["motion"]}
            status.update({key: int(values[key]) for key in ("current", "target", "limit", "torque", "write") if key in values})
            return status

    def arm_presentation(self, enabled: bool) -> None:
        self.send(StackChanCommand("demo", "arm" if enabled else "disarm"))

    def send_score(self, score: int, *, synthetic: bool) -> None:
        if not synthetic or isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            raise ValueError("Only explicitly synthetic presentation scores are supported")
        self.send(StackChanCommand("score", f"test:{score}"))

    def close(self) -> None:
        with self._lock:
            super().close()


def connect_audio_bridge(port: str | None, baud: int) -> CoreS3Bridge:
    import serial
    from ivisyx.stackchan import autodetect_stackchan_port

    port = port or autodetect_stackchan_port()
    if not port:
        raise RuntimeError("Connect the CoreS3 over USB and set STACKCHAN_PORT in .env.")
    bridge = CoreS3Bridge(serial.Serial(port, baud, timeout=0.25, write_timeout=3))
    try:
        bridge.verify_audio()
    except Exception:
        bridge.close()
        raise
    print(f"CoreS3 USB audio connected on {port} (16 kHz mono).")
    return bridge


class CoreS3AudioInterface(AudioInterface):
    def __init__(self, bridge: CoreS3Bridge) -> None:
        self.bridge = bridge
        self.on_error: Callable[[], None] | None = None
        self.error: Exception | None = None
        self._queue: queue.Queue[tuple[int, bytes]] = queue.Queue(maxsize=240)
        self._stop = threading.Event()
        self._generation = 0
        self._queue_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._stopping = False
        self._last_output = 0.0
        self._playback_active = False

    def start(self, input_callback: Callable[[bytes], None]) -> None:
        self.bridge.verify_audio()
        with self._state_lock:
            self._stopping = False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(input_callback,), name="cores3-audio", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        with self._state_lock:
            if self._stopping:
                return
            self._stopping = True
        self._stop.set()
        self.interrupt()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=12)
            if self._thread.is_alive():
                raise RuntimeError("CoreS3 audio worker did not stop.")
        self.bridge.idle()

    def output(self, audio: bytes) -> None:
        if len(audio) % 2:
            raise ValueError("ElevenLabs output must be signed 16-bit PCM.")
        with self._queue_lock:
            self._last_output = time.monotonic()
            for offset in range(0, len(audio), CHUNK_BYTES):
                self._queue.put_nowait((self._generation, audio[offset:offset + CHUNK_BYTES]))

    def interrupt(self) -> None:
        with self._queue_lock:
            self._generation += 1
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    return

    def camera_window_available(self) -> bool:
        with self._queue_lock:
            return (not self._playback_active and self._queue.empty()
                    and time.monotonic() - self._last_output >= 1.0)

    @property
    def has_received_audio(self) -> bool:
        with self._queue_lock:
            return self._last_output > 0

    def _collect_audio(self, generation: int, pcm: bytes, *, startup: bool) -> tuple[int, bytes]:
        # Accumulate network fragments before USB playback to absorb startup jitter.
        target = PREBUFFER_BYTES if startup else CHUNK_BYTES
        deadline = time.monotonic() + (PREBUFFER_SECONDS if startup else 0.12)
        buffered = bytearray(pcm)
        while len(buffered) < target and not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                next_generation, fragment = self._queue.get(timeout=remaining)
            except queue.Empty:
                break
            if next_generation != generation:
                return next_generation, fragment
            buffered.extend(fragment)
        return generation, bytes(buffered)

    def _run(self, callback: Callable[[bytes], None]) -> None:
        was_playing = False
        try:
            while not self._stop.is_set():
                try:
                    generation, pcm = self._queue.get(timeout=0.25 if was_playing else 0)
                except queue.Empty:
                    if was_playing and time.monotonic() - self._last_output < 1.0:
                        if not self._stop.is_set():
                            callback(bytes(CHUNK_BYTES))
                        continue
                    if was_playing:
                        self.bridge.drain_playback()
                    with self._queue_lock:
                        self._playback_active = False
                    pcm = self.bridge.capture()
                    if not self._stop.is_set():
                        callback(pcm)
                    was_playing = False
                    continue
                if generation != self._generation or self._stop.is_set():
                    continue
                with self._queue_lock:
                    self._playback_active = True
                generation, pcm = self._collect_audio(generation, pcm, startup=not was_playing)
                for offset in range(0, len(pcm), CHUNK_BYTES):
                    if generation != self._generation or self._stop.is_set():
                        break
                    packet = pcm[offset:offset + CHUNK_BYTES]
                    self.bridge.play(packet)
                    # Keep the service's input clock advancing without speaker echo.
                    if not self._stop.is_set():
                        callback(bytes(len(packet)))
                was_playing = True
        except Exception as exc:
            self.error = exc
            self._stop.set()
            print(f"CoreS3 audio failed: {exc}")
            if self.on_error:
                self.on_error()
