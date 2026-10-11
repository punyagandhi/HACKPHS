import queue
import threading
import unittest
from unittest.mock import MagicMock, patch

from ivisyx.cores3_audio import CHUNK_BYTES, PREBUFFER_BYTES, CoreS3AudioInterface, CoreS3Bridge
from ivisyx.stackchan import StackChanCommand


class SerialFixture:
    def __init__(self, replies=(), payload=b""):
        self.replies = list(replies)
        self.payload = payload
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def flush(self):
        pass

    def readline(self):
        return self.replies.pop(0) if self.replies else b""

    def read(self, size):
        # USB reads can return less than one complete packet.
        data, self.payload = self.payload[:min(23, size)], self.payload[min(23, size):]
        return data


class AudioProtocolTests(unittest.TestCase):
    def test_v2_firmware_uses_queued_playback(self):
        serial = SerialFixture([b"audio:pcm_16000:8000:v2\n", b"ready:playq\n", b"ok:playq\n"])
        bridge = CoreS3Bridge(serial)
        bridge.verify_audio()
        bridge.play(b"\0\0")
        self.assertEqual(serial.writes, [b"audio\n", b"playq:2\n", b"\0\0"])

    def test_queued_playback_tail_can_be_drained(self):
        serial = SerialFixture([b"audio:pcm_16000:8000:v2\n", b"ok:drain\n"])
        bridge = CoreS3Bridge(serial)
        bridge.verify_audio()
        bridge.drain_playback()
        self.assertEqual(serial.writes, [b"audio\n", b"drain\n"])

    def test_message_uses_compact_acknowledgement(self):
        serial = SerialFixture([b"ok:message\n"])
        CoreS3Bridge(serial).show_message("Put on glasses")
        self.assertEqual(serial.writes, [b"message:Put on glasses\n"])

    def test_expression_uses_full_acknowledgement(self):
        serial = SerialFixture([b"ok:expr:speaking\n"])
        CoreS3Bridge(serial).send(StackChanCommand("expr", "speaking"))
        self.assertEqual(serial.writes, [b"expr:speaking\n"])

    def test_status_only_display_reply(self):
        serial = SerialFixture([b"display:status audio:listening\n"])
        self.assertEqual(CoreS3Bridge(serial).status(), "display:status audio:listening")

    def test_capture_handles_fragmented_binary_with_newlines(self):
        payload = bytes(range(256)) * 31 + bytes(range(64))
        self.assertEqual(len(payload), CHUNK_BYTES)
        serial = SerialFixture([b"pcm:8000\n"], payload)
        self.assertEqual(CoreS3Bridge(serial).capture(), payload)

    def test_capture_rejects_unbounded_packet_size(self):
        serial = SerialFixture([b"pcm:999999999\n"])
        with self.assertRaisesRegex(RuntimeError, "Invalid microphone header"):
            CoreS3Bridge(serial).capture()

    def test_old_firmware_is_reported(self):
        serial = SerialFixture([b"unknown:audio\n"])
        with self.assertRaisesRegex(RuntimeError, "unknown:audio"):
            CoreS3Bridge(serial).verify_audio()

    def test_playback_waits_for_ready_and_acknowledgement(self):
        serial = SerialFixture([b"ready:play\n", b"ok:play\n"])
        CoreS3Bridge(serial).play(b"\x00\x0a\x00\x0d")
        self.assertEqual(serial.writes, [b"play:4\n", b"\x00\x0a\x00\x0d"])

    def test_rejects_invalid_pcm_before_writing(self):
        serial = SerialFixture()
        for pcm in (b"", b"x", bytes(CHUNK_BYTES + 2)):
            with self.assertRaises(ValueError):
                CoreS3Bridge(serial).play(pcm)
        self.assertEqual(serial.writes, [])

    def test_truncated_microphone_packet_times_out(self):
        serial = SerialFixture(payload=b"short")
        with patch("ivisyx.cores3_audio.time.monotonic", side_effect=[0, 0, 6]):
            with self.assertRaisesRegex(TimeoutError, "5/8000"):
                CoreS3Bridge(serial)._exact(CHUNK_BYTES)


class AudioLifecycleTests(unittest.TestCase):
    def test_startup_combines_fragments_before_playback(self):
        audio = CoreS3AudioInterface(MagicMock())
        first = b"\x01\x00" * 100
        rest = b"\x02\x00" * ((PREBUFFER_BYTES - len(first)) // 2)
        audio.output(rest)
        generation, pcm = audio._collect_audio(0, first, startup=True)
        self.assertEqual(generation, 0)
        self.assertEqual(pcm, first + rest)

    def test_short_greeting_flushes_after_bounded_wait(self):
        audio = CoreS3AudioInterface(MagicMock())
        with patch.object(audio._queue, "get", side_effect=queue.Empty):
            self.assertEqual(audio._collect_audio(0, b"\x01\x00", startup=True),
                             (0, b"\x01\x00"))

    def test_prebuffer_is_sent_in_bounded_usb_packets_without_loss(self):
        bridge = MagicMock()
        audio = CoreS3AudioInterface(bridge)
        pcm = bytes(range(256)) * (PREBUFFER_BYTES // 256) + bytes(range(PREBUFFER_BYTES % 256))
        for offset in range(0, len(pcm), 200):
            audio.output(pcm[offset:offset + 200])
        callbacks = []

        def callback(data):
            callbacks.append(data)
            if len(callbacks) == 3:
                audio._stop.set()

        audio._run(callback)
        packets = [call.args[0] for call in bridge.play.call_args_list]
        self.assertEqual([len(packet) for packet in packets], [CHUNK_BYTES] * 3)
        self.assertEqual(b"".join(packets), pcm)
        bridge.capture.assert_not_called()

    def test_interruption_does_not_merge_old_and_new_speech(self):
        audio = CoreS3AudioInterface(MagicMock())
        audio.interrupt()
        audio.output(b"\x02\x00")
        self.assertEqual(audio._collect_audio(0, b"\x01\x00", startup=True),
                         (1, b"\x02\x00"))

    def test_camera_waits_while_buffered_audio_is_in_flight(self):
        audio = CoreS3AudioInterface(MagicMock())
        audio._playback_active = True
        self.assertFalse(audio.camera_window_available())

    def test_camera_pauses_during_reply_and_tail(self):
        audio = CoreS3AudioInterface(MagicMock())
        with patch("ivisyx.cores3_audio.time.monotonic", return_value=10):
            self.assertTrue(audio.camera_window_available())
            audio.output(b"\0\0")
            self.assertFalse(audio.camera_window_available())
            audio._queue.get_nowait()
            self.assertFalse(audio.camera_window_available())
        with patch("ivisyx.cores3_audio.time.monotonic", return_value=12):
            self.assertTrue(audio.camera_window_available())

    def test_reply_packet_gaps_send_silence_instead_of_opening_microphone(self):
        bridge = MagicMock()
        audio = CoreS3AudioInterface(bridge)
        callbacks = []

        def callback(pcm):
            callbacks.append(pcm)
            if len(callbacks) == 2:
                audio._stop.set()

        with patch("ivisyx.cores3_audio.time.monotonic", return_value=10):
            audio.output(b"\x01\x00")
            audio._run(callback)
        bridge.play.assert_called_once_with(b"\x01\x00")
        bridge.capture.assert_not_called()
        self.assertEqual(callbacks, [b"\x00\x00", bytes(CHUNK_BYTES)])

    def test_stop_is_safe_before_start_and_when_called_twice(self):
        bridge = MagicMock()
        audio = CoreS3AudioInterface(bridge)
        audio.stop()
        audio.stop()
        bridge.idle.assert_called_once()

    def test_interrupt_discards_queued_audio(self):
        audio = CoreS3AudioInterface(MagicMock())
        audio.output(bytes(CHUNK_BYTES + 10))
        audio.interrupt()
        self.assertTrue(audio._queue.empty())
        audio.output(b"\x01\x00")
        generation, pcm = audio._queue.get_nowait()
        self.assertEqual(generation, 1)
        self.assertEqual(pcm, b"\x01\x00")

    def test_stop_does_not_deliver_pending_microphone_packet(self):
        entered = threading.Event()
        release = threading.Event()
        bridge = MagicMock()

        def capture():
            entered.set()
            release.wait(timeout=2)
            return bytes(CHUNK_BYTES)

        bridge.capture.side_effect = capture
        callback = MagicMock()
        audio = CoreS3AudioInterface(bridge)
        audio.start(callback)
        self.assertTrue(entered.wait(timeout=2))
        audio._stop.set()
        release.set()
        audio.stop()
        callback.assert_not_called()
        bridge.idle.assert_called_once()

    def test_worker_failure_is_reported_to_session(self):
        bridge = MagicMock()
        bridge.capture.side_effect = RuntimeError("USB disconnected")
        audio = CoreS3AudioInterface(bridge)
        failed = threading.Event()
        audio.on_error = failed.set
        audio.start(MagicMock())
        self.assertTrue(failed.wait(timeout=2))
        audio.stop()
        self.assertIsInstance(audio.error, RuntimeError)


if __name__ == "__main__":
    unittest.main()
