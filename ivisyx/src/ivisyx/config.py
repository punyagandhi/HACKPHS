from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BAUD = 115200


@dataclass(frozen=True)
class Settings:
    agent_id: str
    elevenlabs_api_key: str | None = None
    stackchan_port: str | None = None
    stackchan_baud: int = DEFAULT_BAUD

    @property
    def requires_auth(self) -> bool:
        return bool(self.elevenlabs_api_key)


def load_settings() -> Settings:
    load_dotenv_if_available()

    agent_id = _clean_env("AGENT_ID")
    if not agent_id:
        raise RuntimeError("AGENT_ID is required. Add it to .env or your PyCharm run configuration.")

    return Settings(
        agent_id=agent_id,
        elevenlabs_api_key=_clean_env("ELEVENLABS_API_KEY"),
        stackchan_port=_clean_env("STACKCHAN_PORT"),
        stackchan_baud=_read_int("STACKCHAN_BAUD", DEFAULT_BAUD),
    )


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _read_int(name: str, default: int) -> int:
    raw_value = _clean_env(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw_value!r}.") from exc
