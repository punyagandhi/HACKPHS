from __future__ import annotations

import unittest

from ivisyx.stackchan import Expression, StackChan, StackChanCommand


class FakeSerial:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.flush_count = 0
        self.close_count = 0
        self.replies: list[bytes] = []

    def readline(self) -> bytes:
        return self.replies.pop(0) if self.replies else b""

    def write(self, data: bytes) -> object:
        self.writes.append(data)
        return len(data)

    def flush(self) -> object:
        self.flush_count += 1

    def close(self) -> object:
        self.close_count += 1


class StackChanTests(unittest.TestCase):
    def test_expression_verification_accepts_acknowledgement(self) -> None:
        serial = FakeSerial()
        serial.replies = [b"ivisyx Stack-chan bridge ready\n", b"ok:expr:happy\n"]
        StackChan(serial).check_expression(Expression.HAPPY)
        self.assertEqual(serial.writes, [b"expr:happy\n"])

    def test_expression_verification_rejects_incompatible_firmware(self) -> None:
        serial = FakeSerial()
        serial.replies = [b"ERR UNKNOWN expr:neutral\r\n"]
        with self.assertRaisesRegex(RuntimeError, "Firmware rejected"):
            StackChan(serial).check_expression(Expression.NEUTRAL)

    def test_command_encoding_without_value(self) -> None:
        self.assertEqual(StackChanCommand("ping").encode(), b"ping\n")

    def test_command_encoding_with_value(self) -> None:
        self.assertEqual(StackChanCommand("expr", "happy").encode(), b"expr:happy\n")

    def test_expression_writes_serial_command(self) -> None:
        serial = FakeSerial()
        stackchan = StackChan(serial)

        stackchan.set_expression(Expression.LISTENING)

        self.assertEqual(serial.writes, [b"expr:listening\n"])
        self.assertEqual(serial.flush_count, 1)

    def test_close_closes_serial_connection(self) -> None:
        serial = FakeSerial()
        stackchan = StackChan(serial)

        stackchan.close()

        self.assertEqual(serial.close_count, 1)
        self.assertFalse(stackchan.connected)


if __name__ == "__main__":
    unittest.main()
