# 7g-backhaul-simulation
# Copyright (C) 2026 MILAN NIKOLIC
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Tuple


@dataclass(frozen=True)
class TrendEstimate:
    value: float
    velocity: float
    acceleration: float
    forecast: float


class SecondOrderTrendEstimator:
    """Estimate a metric's first and second derivatives from equally spaced samples."""

    @staticmethod
    def estimate(
        current: float,
        previous: float,
        older: float,
        sample_interval: float,
        horizon: float,
    ) -> TrendEstimate:
        if sample_interval <= 0 or horizon < 0:
            raise ValueError("Sample interval must be positive and forecast horizon non-negative.")
        velocity = (current - previous) / sample_interval
        acceleration = (current - (2 * previous) + older) / (sample_interval**2)
        forecast = current + velocity * horizon + 0.5 * acceleration * horizon**2
        return TrendEstimate(current, velocity, acceleration, forecast)


class RequestDemandLearner:
    """Estimate request-rate acceleration from timestamped arrivals per region."""

    def __init__(self, window_seconds: float = 5.0, forecast_horizon_seconds: float = 5.0) -> None:
        if window_seconds <= 0 or forecast_horizon_seconds < 0:
            raise ValueError("Demand window must be positive and forecast horizon non-negative.")
        self.window_seconds = window_seconds
        self.forecast_horizon_seconds = forecast_horizon_seconds
        self._arrivals: Dict[str, Deque[float]] = defaultdict(deque)
        self._last_timestamp: Dict[str, float] = {}

    def observe(self, region: str, timestamp: float) -> TrendEstimate:
        if not region:
            raise ValueError("Region must not be empty.")
        if timestamp < self._last_timestamp.get(region, timestamp):
            raise ValueError("Request timestamps must be non-decreasing for each region.")

        arrivals = self._arrivals[region]
        arrivals.append(timestamp)
        self._last_timestamp[region] = timestamp
        window = self.window_seconds
        while arrivals and arrivals[0] < timestamp - 3 * window:
            arrivals.popleft()

        current = sum(timestamp - window < event <= timestamp for event in arrivals) / window
        previous = sum(timestamp - 2 * window < event <= timestamp - window for event in arrivals) / window
        older = sum(timestamp - 3 * window < event <= timestamp - 2 * window for event in arrivals) / window
        rate_trend = SecondOrderTrendEstimator.estimate(
            current,
            previous,
            older,
            window,
            self.forecast_horizon_seconds,
        )
        return TrendEstimate(
            value=current,
            velocity=rate_trend.velocity,
            acceleration=rate_trend.acceleration,
            forecast=max(0.0, rate_trend.forecast) * self.forecast_horizon_seconds,
        )
