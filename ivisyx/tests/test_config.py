from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ivisyx.config import DEFAULT_BAUD, load_settings


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        dotenv_patch = patch("ivisyx.config.load_dotenv_if_available")
        dotenv_patch.start()
        self.addCleanup(dotenv_patch.stop)

    def test_requires_agent_id(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "AGENT_ID"):
                load_settings()

    def test_loads_minimum_settings(self) -> None:
        with patch.dict(os.environ, {"AGENT_ID": "agent_123"}, clear=True):
            settings = load_settings()

        self.assertEqual(settings.agent_id, "agent_123")
        self.assertIsNone(settings.elevenlabs_api_key)
        self.assertFalse(settings.requires_auth)
        self.assertEqual(settings.stackchan_baud, DEFAULT_BAUD)

    def test_private_agent_requires_auth_when_api_key_is_set(self) -> None:
        with patch.dict(
            os.environ,
            {"AGENT_ID": "agent_123", "ELEVENLABS_API_KEY": "secret", "STACKCHAN_BAUD": "9600"},
            clear=True,
        ):
            settings = load_settings()

        self.assertTrue(settings.requires_auth)
        self.assertEqual(settings.stackchan_baud, 9600)


if __name__ == "__main__":
    unittest.main()
