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

"""Finite FIFO queue model for one simulated transport link.

The transport abstraction in :mod:`simulation.continuity` adds only path
latency and serialization time, which is accurate while a link is lightly
loaded but optimistic once offered demand exceeds link capacity. External
cross-validation against ns-3 (``validation/scenario_s1.py`` and
``docs/external-validation.md``) showed the gap: in a handover scenario where
all traffic falls back to a slower path, the queue-free model over-reported
delivery by 6.5 percentage points and under-reported the 95th-percentile
one-way delay by a factor of 5.7.

This module supplies the corrected behaviour: a bounded drop-tail buffer with
one server, so overload builds backlog, raises delay and drops the excess.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

#: Default buffer depth in packets, matching a 100-packet drop-tail queue.
DEFAULT_QUEUE_LIMIT_PACKETS = 100


@dataclass(frozen=True)
class QueueOutcome:
    """Result of offering one packet to a link queue."""

    queue_delay_seconds: float
    service_seconds: float
    dropped: bool

    @property
    def total_seconds(self) -> float:
        return self.queue_delay_seconds + self.service_seconds


class DropTailQueue:
    """Single-server, finite-buffer, first-in-first-out link queue.

    Time is supplied by the caller (seconds), so the same model can be driven
    by an event-oriented simulator, a tick-based benchmark or a validation
    harness. Departure times are tracked instead of packets, which keeps the
    state small: a departure time later than the arrival time means the packet
    is still waiting in or being served by the queue.
    """

    def __init__(self, limit_packets: int = DEFAULT_QUEUE_LIMIT_PACKETS) -> None:
        if not isinstance(limit_packets, int) or isinstance(limit_packets, bool):
            raise TypeError("Queue limit must be an integer number of packets.")
        if limit_packets <= 0:
            raise ValueError("Queue limit must be positive.")
        self.limit_packets = limit_packets
        self._departures: deque[float] = deque()

    def _expire(self, now_seconds: float) -> None:
        while self._departures and self._departures[0] <= now_seconds:
            self._departures.popleft()

    @property
    def occupancy(self) -> int:
        """Packets currently waiting for or using the link."""
        return len(self._departures)

    def arrive(self, now_seconds: float, service_seconds: float) -> QueueOutcome:
        """Offer a packet at ``now_seconds`` needing ``service_seconds`` of link time."""
        if service_seconds <= 0:
            raise ValueError("Service time must be positive.")
        self._expire(now_seconds)
        if len(self._departures) >= self.limit_packets:
            # Drop-tail: the packet is discarded and consumes no link time.
            return QueueOutcome(0.0, 0.0, True)
        start_seconds = (
            now_seconds
            if not self._departures
            else max(now_seconds, self._departures[-1])
        )
        self._departures.append(start_seconds + service_seconds)
        return QueueOutcome(
            queue_delay_seconds=max(0.0, start_seconds - now_seconds),
            service_seconds=service_seconds,
            dropped=False,
        )
