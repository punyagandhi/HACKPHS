from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Expression(str, Enum):
    NEUTRAL = "neutral"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    HAPPY = "happy"
    ALERT = "alert"
    ERROR = "error"


class SerialLike(Protocol):
    def readline(self) -> bytes:
        ...

    def write(self, data: bytes) -> object:
        ...

    def flush(self) -> object:
        ...

    def close(self) -> object:
        ...


@dataclass(frozen=True)
class StackChanCommand:
    name: str
    value: str | None = None

    def encode(self) -> bytes:
        if self.value is None:
            return f"{self.name}\n".encode("utf-8")
        return f"{self.name}:{self.value}\n".encode("utf-8")


class StackChan:
    def __init__(self, serial_connection: SerialLike | None = None) -> None:
        self._serial = serial_connection

    @property
    def connected(self) -> bool:
        return self._serial is not None

    def send(self, command: StackChanCommand) -> None:
        if self._serial is None:
            print(f"[stackchan dry-run] {command.encode().decode().strip()}")
            return

        self._serial.write(command.encode())
        self._serial.flush()

    def set_expression(self, expression: Expression | str) -> None:
        value = expression.value if isinstance(expression, Expression) else expression
        self.send(StackChanCommand("expr", value))

    def speak_started(self) -> None:
        self.set_expression(Expression.SPEAKING)

    def show_checklist(self, step: int) -> None:
        if isinstance(step, bool) or not isinstance(step, int) or not -1 <= step <= 2:
            raise ValueError("Checklist step must be -1..2")
        self.send(StackChanCommand("checklist", str(step)))

    def show_message(self, text: str) -> None:
        cleaned = " ".join("".join(char if 32 <= ord(char) < 127 else " " for char in text).split())
        self.send(StackChanCommand("message", cleaned[:120]))

    def show_activity(self, state: str) -> None:
        if state not in ("speaking", "macmic", "off"):
            raise ValueError("Invalid display activity")
        self.send(StackChanCommand("activity", state))

    def check_expression(self, expression: Expression, timeout: float = 3.0) -> None:
        if self._serial is None:
            raise RuntimeError("Expression verification requires a connected robot.")
        self.set_expression(expression)
        expected = f"ok:expr:{expression.value}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            reply = self._serial.readline().decode("utf-8", errors="replace").strip()
            if reply == expected:
                print(f"Firmware acknowledged {expression.value}")
                return
            if reply:
                print(f"Firmware: {reply}")
            if reply.startswith(("ERR", "unknown:")):
                raise RuntimeError(f"Firmware rejected expression command: {reply}")
        raise RuntimeError(f"No acknowledgement for expr:{expression.value}.")

    def listen_started(self) -> None:
        self.set_expression(Expression.LISTENING)

    def think_started(self) -> None:
        self.set_expression(Expression.THINKING)

    def reset(self) -> None:
        self.set_expression(Expression.NEUTRAL)

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None


def connect_stackchan(port: str | None, baud: int) -> StackChan:
    if not port:
        port = autodetect_stackchan_port()

    if not port:
        print("Stack-chan serial port not found. Continuing in dry-run mode.")
        return StackChan()

    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("pyserial is required for USB control. Install dependencies first.") from exc

    connection = serial.Serial(port=port, baudrate=baud, timeout=1)
    time.sleep(2.0)
    print(f"Connected to Stack-chan on {port} at {baud} baud.")
    return StackChan(connection)


def autodetect_stackchan_port() -> str | None:
    try:
        from serial.tools import list_ports
    except ImportError:
        return None

    preferred_markers = ("usbmodem", "wchusbserial", "usbserial", "m5stack", "esp32")
    ports = list(list_ports.comports())

    for port_info in ports:
        haystack = " ".join(
            str(part).lower()
            for part in (port_info.device, port_info.description, port_info.manufacturer)
            if part
        )
        if any(marker in haystack for marker in preferred_markers):
            return port_info.device

    return ports[0].device if len(ports) == 1 else None
