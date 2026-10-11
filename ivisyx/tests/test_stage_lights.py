from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class StageLightsTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "C++ compiler not installed")
    def test_firmware_stage_priority_and_colors(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            executable = str(Path(directory) / "stage_lights_check")
            subprocess.run([
                "c++", "-std=c++11", "-I", str(project / "arduino" / "StackChanIvisyx"),
                str(project / "tests" / "stage_lights_check.cpp"), "-o", executable,
            ], check=True, capture_output=True)
            subprocess.run([executable], check=True, capture_output=True)
