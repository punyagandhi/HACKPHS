"""PyCharm launcher using the robot's microphone and speaker."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ivisyx.voice_assistant import main

if __name__ == "__main__":
    sys.argv[1:1] = ["--audio", "cores3"]
    main()
