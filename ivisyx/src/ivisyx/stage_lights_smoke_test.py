"""Cycle real firmware stages without ElevenLabs, saving no audio."""

import math
import struct
import time

from ivisyx.config import load_settings
from ivisyx.cores3_audio import CHUNK_BYTES, SAMPLE_RATE, connect_audio_bridge


def main():
    settings = load_settings()
    robot = connect_audio_bridge(settings.stackchan_port, settings.stackchan_baud)
    try:
        robot.show_checklist(-1)
        robot.show_message("Looking for your face")
        print("YELLOW / SEARCH:", robot.lights_status(), flush=True)
        time.sleep(4)
        robot.show_message("Pilot support ready")
        robot.capture()
        print("CYAN / MIC:", robot.lights_status(), flush=True)
        time.sleep(4)
        tone = b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE)))
                        for i in range(SAMPLE_RATE * 3))
        for offset in range(0, len(tone), CHUNK_BYTES):
            robot.play(tone[offset:offset + CHUNK_BYTES])
            if offset == CHUNK_BYTES:
                print("MAGENTA / TALK:", robot.lights_status(), flush=True)
        robot.drain_playback()
        robot.show_checklist(2)
        print("GREEN / COMPLETE:", robot.lights_status(), flush=True)
        time.sleep(4)
        robot.show_message("Put on ivisyx glasses")
        print("ORANGE / GLASSES:", robot.lights_status(), flush=True)
        time.sleep(4)
    finally:
        try:
            robot.idle()
            print("OFF:", robot.lights_status(), flush=True)
        finally:
            robot.close()


if __name__ == "__main__":
    main()
