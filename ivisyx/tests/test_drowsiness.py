import unittest
from unittest.mock import MagicMock

from ivisyx.drowsiness import EYES, AgentAlert, EyelidMonitor, EyelidStatus, eye_ratios
from types import SimpleNamespace


class MetricTests(unittest.TestCase):
    def test_eye_ratio_pixel_geometry(self):
        landmarks = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
        for eye in EYES:
            for index, (x, y) in zip(eye, ((0.3, 0.5), (0.4, 0.4), (0.6, 0.4), (0.7, 0.5), (0.6, 0.6), (0.4, 0.6))):
                landmarks[index] = SimpleNamespace(x=x, y=y)
        ratios = eye_ratios(landmarks, 320, 240)
        self.assertAlmostEqual(ratios[0], 0.375)
        self.assertAlmostEqual(ratios[1], 0.375)

    def test_tiny_eyes_are_unknown(self):
        landmarks = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
        self.assertIsNone(eye_ratios(landmarks, 320, 240))

    def monitor(self):
        monitor = EyelidMonitor()
        for i in range(31):
            monitor.update(i / 10, (0.3, 0.3))
        self.assertIsNotNone(monitor.baseline)
        return monitor

    def test_normal_blink_does_not_alert(self):
        monitor = self.monitor()
        for i in range(31, 41):
            status = monitor.update(i / 10, (0.05, 0.05) if i < 34 else (0.3, 0.3))
        self.assertIsNone(status.reason)
        self.assertEqual(status.closure_fraction, 0)

    def test_prolonged_closure_alerts(self):
        monitor = self.monitor()
        for i in range(31, 54):
            status = monitor.update(i / 10, (0.05, 0.05))
        self.assertEqual(status.reason, "prolonged eyelid closure")

    def test_wink_does_not_count_as_both_eyes_closed(self):
        monitor = self.monitor()
        for i in range(31, 70):
            status = monitor.update(i / 10, (0.05, 0.3))
        self.assertEqual(status.state, "EYES OPEN")

    def test_lost_tracking_breaks_continuous_closure(self):
        monitor = self.monitor()
        monitor.update(3.1, (0.05, 0.05))
        status = monitor.update(3.2, None)
        self.assertEqual(status.state, "TRACKING LOST")
        self.assertIsNone(status.reason)
        status = monitor.update(10, (0.05, 0.05))
        self.assertEqual(status.closed_seconds, 0)
        self.assertIsNone(status.reason)

    def test_regular_long_blinks_trigger_rolling_metric(self):
        monitor = self.monitor()
        for i in range(31, 400):
            status = monitor.update(i / 10, (0.05, 0.05) if i % 20 < 12 else (0.3, 0.3))
        self.assertGreater(status.valid_seconds, 30)
        self.assertEqual(status.reason, "elevated closure-time proxy")

    def test_gap_does_not_inflate_valid_observation(self):
        monitor = self.monitor()
        monitor.update(3.1, (0.3, 0.3))
        status = monitor.update(50, (0.3, 0.3))
        self.assertAlmostEqual(status.valid_seconds, 0.1)
        self.assertLess(status.coverage, 0.01)

    def test_invalid_values_are_unknown(self):
        monitor = self.monitor()
        self.assertEqual(monitor.update(3.1, (float("nan"), 0.3)).state, "TRACKING LOST")

    def test_calibration_gap_resets(self):
        monitor = EyelidMonitor()
        monitor.update(0, (0.3, 0.3))
        status = monitor.update(10, (0.3, 0.3))
        self.assertEqual(status.state, "CALIBRATING")
        self.assertEqual(len(monitor.calibration), 1)

    def test_window_expires_old_closures(self):
        monitor = self.monitor()
        for i in range(31, 54):
            monitor.update(i / 10, (0.05, 0.05))
        for i in range(54, 700):
            status = monitor.update(i / 10, (0.3, 0.3))
        self.assertEqual(status.closure_fraction, 0)
        self.assertIsNone(status.reason)


class AlertTests(unittest.TestCase):
    status = EyelidStatus("POSSIBLE DROWSINESS", 2.1, 0.3, 40, 1, "prolonged eyelid closure")

    def test_sends_derived_metric_with_cooldown(self):
        conversation = MagicMock()
        alert = AgentAlert(conversation)
        self.assertTrue(alert.update(10, self.status))
        self.assertFalse(alert.update(11, self.status))
        conversation.send_user_message.assert_called_once()
        message = conversation.send_user_message.call_args.args[0]
        self.assertTrue(message.startswith("ivisyx simulation sensor event:"))
        self.assertIn("not a diagnosis", message)
        self.assertIn("continuous closure 2.1s", message)
        self.assertTrue(alert.update(70, self.status))

    def test_unconnected_agent_retries_only_persistent_alerts(self):
        conversation = MagicMock()
        conversation.send_user_message.side_effect = RuntimeError("Not connected")
        alert = AgentAlert(conversation)
        self.assertFalse(alert.update(10, self.status))
        self.assertFalse(alert.update(11, self.status))
        conversation.send_user_message.assert_called_once()
        conversation.send_user_message.side_effect = None
        self.assertFalse(alert.update(16, EyelidStatus("EYES OPEN")))
        self.assertTrue(alert.update(17, self.status))
