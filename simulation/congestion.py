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

import math
from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

from .environment import TransportMedium


class AIMDCongestionController:
    """TCP-Reno-inspired congestion window and pacing model for one simulated link."""

    def __init__(
        self,
        medium: TransportMedium,
        initial_window_segments: int = 10,
        minimum_window_segments: int = 2,
    ) -> None:
        if initial_window_segments < minimum_window_segments or minimum_window_segments < 1:
            raise ValueError("Initial window must be at least the positive minimum window.")
        self.medium = medium
        self.minimum_window_segments = minimum_window_segments
        self.smoothed_rtt_ms = max(1.0, medium.base_latency * (1.0 + medium.current_load))
        segment_size = max(1, medium.max_payload_bytes)
        self.congestion_window_bytes = float(segment_size * initial_window_segments)
        self._update_window_limit()
        self.congestion_window_bytes = min(self.congestion_window_bytes, self.window_limit_bytes)

    def _update_window_limit(self) -> None:
        capacity_mbps = self.medium.base_bandwidth * max(0.01, 1.0 - self.medium.current_load)
        rtt_seconds = max(0.001, self.smoothed_rtt_ms / 1000.0)
        bandwidth_delay_product = capacity_mbps * 1_000_000 / 8 * rtt_seconds
        self.window_limit_bytes = max(
            float(self.medium.max_payload_bytes * self.minimum_window_segments),
            bandwidth_delay_product,
        )

    @property
    def pacing_rate_mbps(self) -> float:
        if not self.medium.available:
            return 0.0
        self._update_window_limit()
        window_rate_mbps = self.congestion_window_bytes * 8 / (self.smoothed_rtt_ms * 1000)
        physical_rate_mbps = self.medium.base_bandwidth * max(0.01, 1.0 - self.medium.current_load)
        return min(physical_rate_mbps, window_rate_mbps)

    def on_ack(self, acknowledged_bytes: int, rtt_ms: float) -> None:
        if acknowledged_bytes <= 0 or rtt_ms <= 0:
            raise ValueError("Acknowledged bytes and measured RTT must be positive.")
        self.smoothed_rtt_ms = 0.875 * self.smoothed_rtt_ms + 0.125 * rtt_ms
        self.congestion_window_bytes += (acknowledged_bytes**2) / max(1.0, self.congestion_window_bytes)
        self._update_window_limit()
        self.congestion_window_bytes = min(self.congestion_window_bytes, self.window_limit_bytes)

    def on_loss(self) -> None:
        minimum_window = float(self.medium.max_payload_bytes * self.minimum_window_segments)
        self.congestion_window_bytes = max(minimum_window, self.congestion_window_bytes * 0.5)


COUPLED_ALGORITHMS = ("reno", "lia", "olia")


@dataclass
class _SubflowState:
    """Congestion state for one subflow of a coupled multipath flow."""

    name: str
    mss_bytes: int
    rtt_ms: float | None
    congestion_window_bytes: float
    bytes_since_loss: float = 0.0
    bytes_previous_interval: float = 0.0
    acknowledgements: int = 0
    window_increases: int = 0


class CoupledCongestionGroup:
    """Coupled congestion control for one multipath flow over several paths.

    Three congestion-avoidance algorithms are available:

    ``"reno"``
        Uncoupled per-path AIMD. Each path runs an independent Reno window.
        The per-ACK increase is ``acknowledged_bytes * MSS_i / cwnd_i``
        (RFC 5681 appropriate byte counting). This is the baseline the
        coupled algorithms are compared against.

    ``"lia"``
        Linked Increases, RFC 6356. The per-ACK byte increase on path ``i`` is
        the RFC's equation (1)::

            min(alpha * acknowledged_bytes * MSS_i / cwnd_total,
                acknowledged_bytes * MSS_i / cwnd_i)

        with the RFC's equation (2) alpha::

            alpha = cwnd_total * max_i(cwnd_i / rtt_i**2)
                    / (sum_i(cwnd_i / rtt_i))**2

        computed from the current windows and RTT estimates on every ACK.
        Expressed in segments (``W_i = cwnd_i / MSS_i``,
        ``W_total = cwnd_total / MSS``), for one MSS acknowledged, equation
        (1) is ``min(alpha / W_total, 1 / W_i)`` per ACK, equivalently
        ``min(alpha * W_i / W_total, 1)`` segments per round trip. The RFC
        formula is kept in its byte-counted form so that the increase
        remains bounded by the TCP increase for arbitrary
        ``acknowledged_bytes`` values.

        On a loss only the subflow that saw the loss halves its window; the
        other subflows are left untouched. RFC 6356 requires TCP's
        multiplicative decrease per subflow and only couples the increase
        function. This is the MPTCP-like "only the affected subflow backs
        off" behaviour, not full resource pooling; the RFC explicitly notes
        that pooling the decrease as well would introduce flappiness.

    ``"olia"``
        Opportunistic Linked Increases, Khalili, Gast, Popovic and Le Boudec,
        "MPTCP is not Pareto-optimal: Performance issues and a possible
        solution" (ACM CoNEXT 2012; IEEE/ACM Transactions on Networking,
        2013) and ``draft-khalili-mptcp-congestion-control-00`` (February
        2013), Section 3 equation (1). For each ACK on path ``r``::

            ( w_r / rtt_r**2 / (sum_p w_p / rtt_p)**2 + alpha_r / w_r )
            * MSS_r * acknowledged_bytes

        All quantities are in bytes and seconds. ``alpha_r`` is the signed
        term of Section 3::

            alpha_r =  1 / (number_of_paths * |collected_paths|)
                        if r is in collected_paths,
                      -1 / (number_of_paths * |max_w_paths|)
                        if r is in max_w_paths and collected_paths is non-empty,
                      0 otherwise.

        The path sets follow the draft: ``best_paths`` are the paths with the
        largest ``l_r**2 / rtt_r``, where ``l_r = max(l1_r, l2_r)``;
        ``l1_r`` is the bytes sent between the previous two losses and
        ``l2_r`` the bytes sent since the last loss. ``max_w_paths`` are the
        paths with the largest window and ``collected_paths`` is
        ``best_paths - max_w_paths``. A negative ``alpha_r`` lets OLIA shrink
        a maximum-window path on an ACK when another best path has been
        collected, re-forwarding traffic to the latter.

        Simplifications made by this implementation: the caller supplies the
        (smoothed) RTT estimate per ACK rather than this class running a TCP
        RTT filter; the sets and ``alpha_r`` are recomputed on every ACK
        instead of once per RTT or drop (the draft permits both, and per-ACK
        recomputation is more precise); and slow start / ssthresh are out of
        scope for this module, which only models congestion-avoidance
        increase and multiplicative decrease. No term of the published
        increase equation is approximated or omitted. The window is floored
        at ``minimum_window_segments`` MSS, as in the existing per-link model.

    Both coupled algorithms use the same multiplicative decrease on loss:
    the affected subflow's window is halved (down to the configured
    minimum), while other subflows keep their windows.
    """

    def __init__(
        self,
        algorithm: str,
        paths: Sequence[Tuple[str, int] | Tuple[str, int, float]],
        *,
        initial_window_segments: int | Mapping[str, int] = 10,
        minimum_window_segments: int = 2,
        capacity_mbps: Mapping[str, float] | None = None,
    ) -> None:
        if not isinstance(algorithm, str) or algorithm.strip().lower() not in COUPLED_ALGORITHMS:
            raise ValueError(
                f"Unknown congestion-control algorithm {algorithm!r}; "
                f"expected one of {COUPLED_ALGORITHMS}."
            )
        self.algorithm = algorithm.strip().lower()
        if not isinstance(minimum_window_segments, int) or minimum_window_segments < 1:
            raise ValueError("Minimum window must be a positive integer number of segments.")

        entries = list(paths)
        if not entries:
            raise ValueError("At least one path is required.")

        initial_windows = self._resolve_initial_windows(initial_window_segments, entries)
        self.minimum_window_segments = minimum_window_segments
        self._paths: dict[str, _SubflowState] = {}
        for entry in entries:
            if len(entry) not in (2, 3):
                raise ValueError(
                    "Each path must be (name, mss_bytes) or (name, mss_bytes, initial_rtt_ms)."
                )
            name, mss_bytes = entry[0], entry[1]
            initial_rtt = entry[2] if len(entry) == 3 else None
            if not isinstance(name, str) or not name:
                raise ValueError("Path names must be non-empty strings.")
            if name in self._paths:
                raise ValueError(f"Duplicate path name: {name!r}.")
            if isinstance(mss_bytes, bool) or not isinstance(mss_bytes, int) or mss_bytes <= 0:
                raise ValueError(f"MSS for path {name!r} must be a positive integer.")
            if initial_rtt is not None:
                initial_rtt = self._validate_rtt(initial_rtt, name)
            window = max(
                float(mss_bytes * minimum_window_segments),
                float(mss_bytes * initial_windows[name]),
            )
            self._paths[name] = _SubflowState(
                name=name,
                mss_bytes=mss_bytes,
                rtt_ms=initial_rtt,
                congestion_window_bytes=window,
            )

        self._capacities: dict[str, float] = {}
        if capacity_mbps is not None:
            self._capacities = self._validate_capacities(capacity_mbps)

    @staticmethod
    def _resolve_initial_windows(
        initial_window_segments: int | Mapping[str, int],
        entries: Sequence[Tuple],
    ) -> dict[str, int]:
        names = [entry[0] for entry in entries]
        if isinstance(initial_window_segments, Mapping):
            unknown = set(initial_window_segments) - set(names)
            if unknown:
                raise KeyError(f"Unknown path(s) in initial windows: {sorted(unknown)!r}.")
            windows: dict[str, int] = {}
            for name in names:
                if name not in initial_window_segments:
                    raise ValueError(f"Missing initial window for path {name!r}.")
                segments = initial_window_segments[name]
                if isinstance(segments, bool) or not isinstance(segments, int) or segments < 1:
                    raise ValueError(
                        f"Initial window for path {name!r} must be a positive integer."
                    )
                windows[name] = segments
            return windows
        if (
            isinstance(initial_window_segments, bool)
            or not isinstance(initial_window_segments, int)
            or initial_window_segments < 1
        ):
            raise ValueError("Initial window must be a positive integer number of segments.")
        return {name: initial_window_segments for name in names}

    def _validate_rtt(self, rtt_ms: float, path_name: str) -> float:
        try:
            value = float(rtt_ms)
        except (TypeError, ValueError):
            raise ValueError(f"RTT for path {path_name!r} must be a positive number.") from None
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"RTT for path {path_name!r} must be a positive finite number.")
        return value

    def _validate_capacities(self, capacity_mbps: Mapping[str, float]) -> dict[str, float]:
        capacities: dict[str, float] = {}
        for name, capacity in capacity_mbps.items():
            if name not in self._paths:
                raise KeyError(f"Unknown path in capacity mapping: {name!r}.")
            try:
                value = float(capacity)
            except (TypeError, ValueError):
                raise ValueError(f"Capacity for path {name!r} must be a positive number.") from None
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"Capacity for path {name!r} must be positive and finite.")
            capacities[name] = value
        return capacities

    def _path(self, path_name: str) -> _SubflowState:
        try:
            return self._paths[path_name]
        except KeyError:
            raise KeyError(f"Unknown path: {path_name!r}.") from None

    def _require_all_rtts(self) -> None:
        missing = [name for name, state in self._paths.items() if state.rtt_ms is None]
        if missing:
            raise ValueError(
                "An RTT estimate is required for every subflow before the coupled "
                f"increase can be computed; missing: {missing!r}."
            )

    def alpha(self) -> float:
        """Return the current RFC 6356 LIA alpha (LIA groups only)."""
        if self.algorithm != "lia":
            raise ValueError("alpha() is only defined for the 'lia' algorithm.")
        self._require_all_rtts()
        total_window = self._total_window_bytes()
        if total_window <= 0.0:
            return 0.0
        rates = [
            state.congestion_window_bytes / (state.rtt_ms / 1000.0) ** 2
            for state in self._paths.values()
        ]
        denominator = sum(
            state.congestion_window_bytes / (state.rtt_ms / 1000.0)
            for state in self._paths.values()
        )
        if denominator <= 0.0:
            return 0.0
        return total_window * max(rates) / denominator**2

    def olia_alpha(self, path_name: str) -> float:
        """Return OLIA's signed ``alpha_r`` for one path (OLIA groups only)."""
        if self.algorithm != "olia":
            raise ValueError("olia_alpha() is only defined for the 'olia' algorithm.")
        self._require_all_rtts()
        path = self._path(path_name)
        best_paths, max_w_paths = self._olia_path_sets()
        collected_paths = best_paths - max_w_paths
        number_of_paths = len(self._paths)
        if path_name in collected_paths:
            return 1.0 / (number_of_paths * len(collected_paths))
        if path_name in max_w_paths and collected_paths:
            return -1.0 / (number_of_paths * len(max_w_paths))
        return 0.0

    def _olia_path_sets(self) -> tuple[set[str], set[str]]:
        self._require_all_rtts()
        best_values = {
            name: max(state.bytes_previous_interval, state.bytes_since_loss) ** 2
            / state.rtt_ms
            for name, state in self._paths.items()
        }
        best_value = max(best_values.values())
        best_paths = {
            name
            for name, value in best_values.items()
            if math.isclose(value, best_value, rel_tol=1e-12, abs_tol=0.0)
        }
        max_window = max(state.congestion_window_bytes for state in self._paths.values())
        max_w_paths = {
            name
            for name, state in self._paths.items()
            if math.isclose(
                state.congestion_window_bytes,
                max_window,
                rel_tol=1e-12,
                abs_tol=0.0,
            )
        }
        return best_paths, max_w_paths

    def _total_window_bytes(self) -> float:
        return sum(state.congestion_window_bytes for state in self._paths.values())

    def _increase_bytes(self, path: _SubflowState, acknowledged_bytes: float) -> float:
        mss = path.mss_bytes
        window = path.congestion_window_bytes
        if self.algorithm == "reno":
            return acknowledged_bytes * mss / window
        if self.algorithm == "lia":
            alpha = self.alpha()
            total_window = self._total_window_bytes()
            return min(
                alpha * acknowledged_bytes * mss / total_window,
                acknowledged_bytes * mss / window,
            )
        # OLIA: published Section 3 equation (1), in bytes and seconds.
        rtt_seconds = path.rtt_ms / 1000.0
        denominator = sum(
            state.congestion_window_bytes / (state.rtt_ms / 1000.0)
            for state in self._paths.values()
        )
        kelly_term = (window / rtt_seconds**2) / denominator**2
        alpha_r = self.olia_alpha(path.name)
        return (kelly_term + alpha_r / window) * mss * acknowledged_bytes

    def on_ack(self, path_name: str, acknowledged_bytes: float, rtt_ms: float) -> None:
        """Apply one ACK for ``path_name`` acknowledging ``acknowledged_bytes``.

        ``rtt_ms`` is the caller's current smoothed RTT estimate for the path
        in milliseconds. A zero-byte ACK is accepted as a no-op.
        """
        path = self._path(path_name)
        if not isinstance(acknowledged_bytes, (int, float)) or isinstance(
            acknowledged_bytes, bool
        ):
            raise ValueError("Acknowledged bytes must be a number.")
        if not math.isfinite(acknowledged_bytes) or acknowledged_bytes < 0.0:
            raise ValueError("Acknowledged bytes must be non-negative and finite.")
        path.rtt_ms = self._validate_rtt(rtt_ms, path_name)
        if acknowledged_bytes == 0.0:
            return

        path.acknowledgements += 1
        # OLIA needs the bytes acknowledged since the last loss for its path sets.
        path.bytes_since_loss += acknowledged_bytes
        before = path.congestion_window_bytes
        increase = self._increase_bytes(path, float(acknowledged_bytes))
        minimum_window = float(path.mss_bytes * self.minimum_window_segments)
        path.congestion_window_bytes = max(
            minimum_window,
            path.congestion_window_bytes + increase,
        )
        if path.congestion_window_bytes > before:
            path.window_increases += 1

    def on_loss(self, path_name: str) -> None:
        """Apply a loss indication on one subflow, halving only that subflow."""
        path = self._path(path_name)
        path.bytes_previous_interval = path.bytes_since_loss
        path.bytes_since_loss = 0.0
        minimum_window = float(path.mss_bytes * self.minimum_window_segments)
        path.congestion_window_bytes = max(
            minimum_window,
            path.congestion_window_bytes * 0.5,
        )

    def windows_bytes(self) -> dict[str, float]:
        """Return a snapshot of the current congestion windows in bytes."""
        return {
            name: state.congestion_window_bytes
            for name, state in self._paths.items()
        }

    def rates_mbps(
        self,
        capacity_mbps: Mapping[str, float] | None = None,
    ) -> dict[str, float]:
        """Return each path's window-implied send rate in Mbit/s.

        The rate is ``window_bytes / rtt`` converted to Mbit/s. If a capacity
        map is supplied (here or in the constructor), each rate is capped at
        the corresponding path capacity.
        """
        self._require_all_rtts()
        capacities = self._capacities
        if capacity_mbps is not None:
            capacities = self._validate_capacities(capacity_mbps)
        rates: dict[str, float] = {}
        for name, state in self._paths.items():
            rate_mbps = state.congestion_window_bytes * 8.0 / (state.rtt_ms * 1000.0)
            if name in capacities:
                rate_mbps = min(rate_mbps, capacities[name])
            rates[name] = rate_mbps
        return rates

    @property
    def ack_count(self) -> int:
        """Total number of non-zero ACKs processed by the group."""
        return sum(state.acknowledgements for state in self._paths.values())

    @property
    def window_increase_count(self) -> int:
        """Total number of ACKs that strictly increased the ACKed path's window."""
        return sum(state.window_increases for state in self._paths.values())
