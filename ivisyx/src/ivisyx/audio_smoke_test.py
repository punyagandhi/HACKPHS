"""Capture one second on the robot and play a short tone without cloud calls."""

import math
import struct

from ivisyx.config import load_settings
from ivisyx.cores3_audio import CHUNK_BYTES, SAMPLE_RATE, connect_audio_bridge


def main() -> None:
    settings = load_settings()
    bridge = connect_audio_bridge(settings.stackchan_port, settings.stackchan_baud)
    try:
        print(bridge.status())
        print("Recording one second through CoreS3 microphones...")
        pcm = b"".join(bridge.capture() for _ in range(4))
        samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        print(f"Captured {len(samples)} samples; RMS={rms:.1f}; peak={max(map(abs, samples))}")
        if not any(samples):
            raise RuntimeError("Microphone returned only zeros.")
        status = bridge.status()
        print(status)
        if "display:status" not in status or "audio:listening" not in status:
            raise RuntimeError("Expected microphone-on status after capture.")
        print("Playing a half-second tone through CoreS3 speaker...")
        tone = b"".join(
            struct.pack("<h", round(4000 * math.sin(2 * math.pi * 440 * index / SAMPLE_RATE)))
            for index in range(SAMPLE_RATE // 2)
        )
        for offset in range(0, len(tone), CHUNK_BYTES):
            bridge.play(tone[offset:offset + CHUNK_BYTES])
        bridge.drain_playback()
        bridge.idle()
        status = bridge.status()
        print(status)
        if "audio:idle" not in status:
            raise RuntimeError("Expected microphone-off status after stopping audio.")
        print("Audio transport test passed. Confirm the tone was audible on the robot.")
    finally:
        try:
            bridge.idle()
        finally:
            bridge.close()


if __name__ == "__main__":
    main()
