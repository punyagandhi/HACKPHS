import unittest

from ivisyx.cores3_camera import CoreS3Camera
from test_cores3_audio import SerialFixture


class CameraProtocolTests(unittest.TestCase):
    def test_audio_interleaving_releases_camera_after_frame(self):
        jpeg = b"\xff\xd8\xff\xd9"
        serial = SerialFixture([b"ok:camera:on\n", b"jpeg:4\n", b"ok:camera:off\n"], jpeg)
        self.assertEqual(CoreS3Camera(serial).frame_between_audio(), jpeg)
        self.assertEqual(serial.writes, [b"camera:on\n", b"frame\n", b"camera:off\n"])

    def test_audio_interleaving_releases_camera_after_failure(self):
        serial = SerialFixture([b"ok:camera:on\n", b"jpeg:0\n", b"ok:camera:off\n"])
        with self.assertRaisesRegex(RuntimeError, "Invalid JPEG"):
            CoreS3Camera(serial).frame_between_audio()
        self.assertEqual(serial.writes[-1], b"camera:off\n")

    def test_fragmented_jpeg_contains_serial_newlines(self):
        jpeg = b"\xff\xd8" + bytes(range(256)) * 4 + b"\xff\xd9"
        serial = SerialFixture([f"jpeg:{len(jpeg)}\n".encode()], jpeg)
        self.assertEqual(CoreS3Camera(serial).frame(), jpeg)
        self.assertEqual(serial.writes, [b"frame\n"])

    def test_rejects_invalid_and_unbounded_lengths(self):
        for header in (b"jpeg:0\n", b"jpeg:200001\n", b"jpeg:-1\n", b"jpeg:no\n"):
            with self.subTest(header=header):
                with self.assertRaisesRegex(RuntimeError, "Invalid JPEG"):
                    CoreS3Camera(SerialFixture([header])).frame()

    def test_rejects_invalid_image_markers(self):
        with self.assertRaisesRegex(RuntimeError, "invalid JPEG frame"):
            CoreS3Camera(SerialFixture([b"jpeg:4\n"], b"oops")).frame()

    def test_start_and_stop_acknowledgements(self):
        serial = SerialFixture([b"ok:camera:on\n", b"ok:camera:off\n"])
        camera = CoreS3Camera(serial)
        camera.start_camera()
        camera.stop_camera()
        self.assertEqual(serial.writes, [b"camera:on\n", b"camera:off\n"])

    def test_firmware_camera_error_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, "camera frame unavailable"):
            CoreS3Camera(SerialFixture([b"ERR camera frame unavailable\n"])).frame()


if __name__ == "__main__":
    unittest.main()
