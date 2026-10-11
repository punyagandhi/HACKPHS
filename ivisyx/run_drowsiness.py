"""CoreS3 eyelid monitoring and robot-only conversational audio."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ivisyx.face_tracking import main

if __name__ == "__main__":
    sys.argv[1:1] = ["--drowsiness", "--agent"]
    main()
