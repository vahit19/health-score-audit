"""A change alarm for an audit stream that runs for months.

verdict-gate's AuditMonitor answers "has accuracy been below target since we
started?". Its false-alarm guarantee holds however often you look, but after a
long stretch above target its wealth sits far below 1, and a sudden break has
to climb out of that hole first: in the drift experiment it never fires.

ChangeAlarm restarts the evidence instead (a CUSUM-style e-detector): for each
betting fraction the log-wealth is floored at zero after every audit, so the
alarm only looks at the evidence since the last time things looked fine. The
detectors for several fractions are averaged. Each is bounded by a
Shiryaev-Roberts e-detector, so the average is too, and an alarm level A gives
an average run length of at least A audits before a false alarm when accuracy
is at or above target (Shin, Ramdas and Rinaldo, "E-detectors", 2023).
"""

from __future__ import annotations

import numpy as np


class ChangeAlarm:
    def __init__(self, target_accuracy: float = 0.95, arl: float = 10_000.0):
        self.eps = 1.0 - target_accuracy
        self.level = arl
        cap = 1.0 / self.eps
        self.lambdas = np.array([cap * f for f in (0.05, 0.1, 0.2, 0.4, 0.6)])
        self.log_w = np.zeros_like(self.lambdas)
        self.audited = 0

    def update(self, correct: bool) -> bool:
        """Record one audited verdict; return True when the alarm is raised."""
        x = 0.0 if correct else 1.0
        self.audited += 1
        self.log_w = np.maximum(0.0, self.log_w + np.log1p(self.lambdas * (x - self.eps)))
        return self.alarm

    @property
    def statistic(self) -> float:
        return float(np.mean(np.exp(self.log_w)))

    @property
    def alarm(self) -> bool:
        return self.statistic >= self.level
