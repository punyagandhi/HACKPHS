"""Keep robot speech lights aligned with actual Mac audio playback."""

import queue
import threading
import time

from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface


class RobotDesktopAudio(DefaultAudioInterface):
    def __init__(self, robot):
        super().__init__()
        self.robot = robot
        self._lifecycle_lock = threading.Lock()
        self._started = False
        self._stopped = False
        self.error = None
        self._generation = 0

    def start(self, callback):
        with self._lifecycle_lock:
            try:
                super().start(callback)
                self._started = True
            except Exception:
                if hasattr(self, "should_stop"):
                    self.should_stop.set()
                if hasattr(self, "output_thread") and self.output_thread.is_alive():
                    self.output_thread.join()
                for name in ("in_stream", "out_stream"):
                    stream = getattr(self, name, None)
                    if stream is not None:
                        stream.close()
                if hasattr(self, "p"):
                    self.p.terminate()
                self._notify("off")
                raise

    def stop(self):
        with self._lifecycle_lock:
            if self._stopped:
                return
            self._stopped = True
            if self._started:
                super().stop()
            self._notify("off")

    def _notify(self, state):
        try:
            self.robot.show_activity(state)
        except Exception as exc:
            print(f"Robot activity update failed: {exc}", flush=True)

    def interrupt(self):
        self._generation += 1
        if hasattr(self, "output_queue"):
            super().interrupt()

    def _output_thread(self):
        state = None
        last_update = -float("inf")

        def update(new_state):
            nonlocal state, last_update
            now = time.monotonic()
            if state != new_state or now - last_update >= 1:
                self._notify(new_state)
                state, last_update = new_state, now

        try:
            update("macmic")
            while not self.should_stop.is_set():
                try:
                    audio = self.output_queue.get(timeout=0.25)
                except queue.Empty:
                    update("macmic")
                    continue
                generation = self._generation
                for offset in range(0, len(audio), 4000):
                    if self.should_stop.is_set() or generation != self._generation:
                        break
                    update("speaking")
                    self.out_stream.write(audio[offset:offset + 4000])
        except Exception as exc:
            self.error = exc
            print(f"Mac audio playback failed: {exc}", flush=True)
        finally:
            self._notify("off")
