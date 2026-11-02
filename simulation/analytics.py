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

import csv
from pathlib import Path
from typing import Dict, Iterable, Optional

from .continuity import TransferResult
from .environment import TransportMedium

_FIELDS = (
    "timestamp",
    "record_type",
    "session_id",
    "principal",
    "stable_ip",
    "medium",
    "load",
    "latency_ms",
    "loss_probability",
    "pressure",
    "mtu_bytes",
    "routing_share",
    "bytes",
    "fragments",
    "attempts",
    "retries",
    "elapsed_ms",
    "goodput_mbps",
    "continuity_preserved",
    "cache_hit",
    "cache_hit_ratio",
)


class CSVNetworkLogger:
    """Append simulation KPI and per-medium snapshots to a historical CSV file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _append(self, rows: Iterable[Dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=_FIELDS, extrasaction="raise")
            if write_header:
                writer.writeheader()
            writer.writerows(rows)

    def log_network_snapshot(
        self,
        timestamp: float,
        channels: Iterable[TransportMedium],
        routing_distribution: Dict[str, float],
    ) -> None:
        rows = []
        for medium in channels:
            rows.append(
                {
                    "timestamp": timestamp,
                    "record_type": "link",
                    "medium": medium.name,
                    "load": round(medium.current_load, 6),
                    "latency_ms": round(medium.base_latency * (1 + medium.current_load), 6),
                    "loss_probability": round(
                        min(1.0, medium.packet_loss_base * (1 + medium.current_load)),
                        6,
                    ),
                    "pressure": round(medium.get_pressure_score(), 6),
                    "mtu_bytes": medium.current_mtu_bytes,
                    "routing_share": round(routing_distribution.get(medium.name, 0.0), 8),
                }
            )
        self._append(rows)

    def log_transfer(
        self,
        timestamp: float,
        result: TransferResult,
        cache_hit: Optional[bool] = None,
        cache_hit_ratio: Optional[float] = None,
    ) -> None:
        self._append(
            [
                {
                    "timestamp": timestamp,
                    "record_type": "transfer",
                    "session_id": result.session_id,
                    "principal": result.principal or "",
                    "stable_ip": result.stable_ip or "",
                    "medium": "|".join(sorted(set(result.media_used))),
                    "bytes": len(result.payload),
                    "fragments": len(result.fragments),
                    "attempts": result.attempts,
                    "retries": result.retries,
                    "elapsed_ms": round(result.elapsed_ms, 6),
                    "goodput_mbps": round(result.goodput_mbps, 6),
                    "continuity_preserved": bool(result.payload == b"".join(
                        fragment.payload for fragment in sorted(result.fragments, key=lambda item: item.offset_bytes)
                    )),
                    "cache_hit": "" if cache_hit is None else cache_hit,
                    "cache_hit_ratio": "" if cache_hit_ratio is None else round(cache_hit_ratio, 6),
                }
            ]
        )
