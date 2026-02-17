"""
Simple statistical anomaly detection for tenant cost metrics.

Uses a rolling-window approach (mean +/- k * std_dev) to flag values that
deviate significantly from recent history. Designed to catch billing spikes
early so tenants can be notified before costs escalate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class AnomalyResult:
    """Outcome of a single anomaly check."""

    is_anomaly: bool
    expected_min: float
    expected_max: float
    actual_value: float
    deviation_factor: float


class AnomalyDetector:
    """
    Stateless anomaly detector using the z-score method.

    The ``detect`` method compares *current_value* against the statistical
    profile of *historical_values*. A value is flagged as anomalous when it
    falls outside ``mean +/- threshold * std_dev``.
    """

    # Minimum number of historical data points required for a meaningful check.
    MIN_HISTORY_LENGTH: int = 3

    def detect(
        self,
        current_value: float,
        historical_values: Sequence[float],
        threshold: float = 2.5,
    ) -> AnomalyResult:
        """
        Determine whether *current_value* is anomalous relative to recent
        history.

        Parameters
        ----------
        current_value:
            The latest observed metric value.
        historical_values:
            A window of recent observations (ideally 7 days' worth).
        threshold:
            Number of standard deviations from the mean before a value is
            considered anomalous. Defaults to 2.5.

        Returns
        -------
        AnomalyResult
            Contains the anomaly flag, the expected range, the actual value,
            and the deviation factor (how many std-devs away the value is).
        """

        # -- Edge case: insufficient data ----------------------------------
        if len(historical_values) < self.MIN_HISTORY_LENGTH:
            return AnomalyResult(
                is_anomaly=False,
                expected_min=0.0,
                expected_max=0.0,
                actual_value=current_value,
                deviation_factor=0.0,
            )

        mean = self._mean(historical_values)
        std = self._std(historical_values, mean)

        # -- Edge case: flat / near-zero pattern ---------------------------
        if std < 1e-9:
            # All historical values are (nearly) identical.
            is_anomaly = abs(current_value - mean) > 1e-9
            deviation = float("inf") if is_anomaly else 0.0
            return AnomalyResult(
                is_anomaly=is_anomaly,
                expected_min=mean,
                expected_max=mean,
                actual_value=current_value,
                deviation_factor=deviation,
            )

        expected_min = mean - threshold * std
        expected_max = mean + threshold * std
        deviation_factor = abs(current_value - mean) / std
        is_anomaly = current_value < expected_min or current_value > expected_max

        return AnomalyResult(
            is_anomaly=is_anomaly,
            expected_min=expected_min,
            expected_max=expected_max,
            actual_value=current_value,
            deviation_factor=round(deviation_factor, 4),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mean(values: Sequence[float]) -> float:
        return sum(values) / len(values)

    @staticmethod
    def _std(values: Sequence[float], mean: float) -> float:
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)
