"""PyCharm launcher for local face tracking with the Stack-chan camera."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ivisyx.face_tracking import main

if __name__ == "__main__":
    main()
