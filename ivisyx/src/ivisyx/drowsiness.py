"""Demonstration eyelid metrics. Not validated PERCLOS or a safety assessment."""

from collections import deque
from dataclasses import dataclass
import math
import statistics

EYES = ((33, 160, 158, 133, 153, 144), (362, 385, 387, 263, 373, 380))


def eye_ratios(landmarks, width, height):
    ratios = []
    widths = []
    for indices in EYES:
        points = [(landmarks[i].x * width, landmarks[i].y * height) for i in indices]
        if any(not math.isfinite(v) for point in points for v in point):
            return None
        if any(not (0 <= x < width and 0 <= y < height) for x, y in points):
            return None
        span = math.dist(points[0], points[3])
        if span < 6:
            return None
        ratio = (math.dist(points[1], points[5]) + math.dist(points[2], points[4])) / (2 * span)
        if not 0 <= ratio <= 0.8:
            return None
        ratios.append(ratio)
        widths.append(span)
    if max(widths) / min(widths) > 2:
        return None
    return tuple(ratios)


@dataclass(frozen=True)
class EyelidStatus:
    state: str
    closed_seconds: float = 0
    closure_fraction: float = 0
    valid_seconds: float = 0
    coverage: float = 0
    reason: str | None = None


class EyelidMonitor:
    window = 60.0
    max_gap = 0.5
    blink_cutoff = 0.5
    prolonged_threshold = 2.0
    fraction_threshold = 0.20
    min_valid_seconds = 30.0

    def __init__(self):
        self.calibration = []
        self.baseline = None
        self.previous = None
        self.closed_since = None
        self.intervals = deque()
        self.started = None
        self.last_time = None

    def update(self, now, ratios):
        if self.last_time is not None and now <= self.last_time:
            raise ValueError("Timestamps must increase")
        self.last_time = now
        if ratios is not None and (len(ratios) != 2 or any(not math.isfinite(v) or not 0 <= v <= 0.8 for v in ratios)):
            ratios = None
        if self.baseline is None:
            if ratios is None:
                self.calibration.clear()
                return EyelidStatus("TRACKING LOST")
            if self.calibration and now - self.calibration[-1][0] > self.max_gap:
                self.calibration.clear()
            self.calibration.append((now, ratios))
            if now - self.calibration[0][0] < 3 or len(self.calibration) < 15:
                return EyelidStatus("CALIBRATING")
            baseline = tuple(statistics.median(sorted(sample[1][eye] for sample in self.calibration)[len(self.calibration) // 2:]) for eye in range(2))
            if min(baseline) < 0.15:
                self.calibration.clear()
                return EyelidStatus("CALIBRATING")
            self.baseline = baseline
            self.started = now

        closed = None if ratios is None else all(value < base * 0.65 for value, base in zip(ratios, self.baseline))
        previous = self.previous
        connected = previous is not None and now - previous[0] <= self.max_gap and previous[1] is not None and closed is not None
        if connected:
            self.intervals.append((previous[0], now, previous[1], previous[2]))
        if closed:
            if not connected or not previous[1]:
                self.closed_since = now
        else:
            self.closed_since = None
        self.previous = (now, closed, self.closed_since)
        while self.intervals and self.intervals[0][1] <= now - self.window:
            self.intervals.popleft()
        valid = closed_time = 0.0
        for start, end, was_closed, run_start in self.intervals:
            start = max(start, now - self.window)
            valid += end - start
            # Exclude the first half-second of each closure, reducing ordinary blink contribution.
            if was_closed and run_start is not None:
                closed_time += max(0, end - max(start, run_start + self.blink_cutoff))
        fraction = closed_time / valid if valid else 0
        span = min(self.window, max(0, now - self.started))
        coverage = valid / span if span else 0
        duration = now - self.closed_since if self.closed_since is not None else 0
        reason = None
        if closed is not None:
            if duration >= self.prolonged_threshold:
                reason = "prolonged eyelid closure"
            elif valid >= self.min_valid_seconds and coverage >= 0.8 and fraction >= self.fraction_threshold:
                reason = "elevated closure-time proxy"
        state = "TRACKING LOST" if closed is None else "POSSIBLE DROWSINESS" if reason else "EYES CLOSED" if closed else "EYES OPEN"
        return EyelidStatus(state, duration, fraction, valid, coverage, reason)


class AgentAlert:
    def __init__(self, conversation, cooldown=60.0):
        self.conversation = conversation
        self.cooldown = cooldown
        self.last_sent = -math.inf
        self.next_attempt = -math.inf

    def update(self, now, status):
        if not status.reason or now - self.last_sent < self.cooldown or now < self.next_attempt:
            return False
        text = (
            "ivisyx simulation sensor event: POSSIBLE DROWSINESS, not a diagnosis. "
            f"Reason: {status.reason}; continuous closure {status.closed_seconds:.1f}s; "
            f"60s closure-time proxy {status.closure_fraction:.0%}; valid observation {status.valid_seconds:.1f}s; "
            f"coverage {status.coverage:.0%}. This is an unvalidated EAR-based demo, not PERCLOS80. "
            "Give a brief demonstration alert and ask whether the participant is okay. "
            "Do not assert actual fatigue or give operational flight instructions."
        )
        try:
            self.conversation.send_user_message(text)
        except Exception as exc:
            self.next_attempt = now + 5
            print(f"Agent alert not sent; will retry only while the condition persists: {exc}", flush=True)
            return False
        self.last_sent = now
        print("Drowsiness demo alert sent to ElevenLabs.", flush=True)
        return True
