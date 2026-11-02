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

import ipaddress
from dataclasses import dataclass
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class MobileIpBinding:
    session_id: str
    stable_ip: str
    access_locator: str
    generation: int


class MobileIpAnchor:
    """Keep a stable simulated virtual IP while the access-network locator changes."""

    def __init__(self, address_pool: str = "198.18.0.0/15") -> None:
        self.network = ipaddress.ip_network(address_pool)
        if self.network.version != 4 or self.network.num_addresses <= 2:
            raise ValueError("The simulation address pool must be an IPv4 network with host addresses.")
        self._bindings: Dict[str, MobileIpBinding] = {}

    def bind(self, session_id: str, access_locator: str) -> MobileIpBinding:
        if not session_id or not access_locator:
            raise ValueError("Session ID and access locator must not be empty.")
        current = self._bindings.get(session_id)
        if current is None:
            offset = 2 + len(self._bindings)
            if offset >= self.network.num_addresses - 1:
                raise RuntimeError("Simulated mobile IP address pool is exhausted.")
            stable_ip = str(self.network.network_address + offset)
            generation = 1
        else:
            stable_ip = current.stable_ip
            generation = current.generation + (current.access_locator != access_locator)
        binding = MobileIpBinding(session_id, stable_ip, access_locator, generation)
        self._bindings[session_id] = binding
        return binding

    def lookup(self, session_id: str) -> Optional[MobileIpBinding]:
        return self._bindings.get(session_id)


@dataclass(frozen=True)
class RadioCell:
    cell_id: str
    medium: str
    signal_dbm: float
    available: bool = True


@dataclass(frozen=True)
class HandoverDecision:
    status: str
    serving_cell: Optional[str]
    target_cell: Optional[str]
    stable_ip: Optional[str]
    generation: Optional[int]


class RadioHandoverController:
    """RSRP-like hysteresis/time-to-trigger handover with make-before-break semantics."""

    def __init__(
        self,
        ip_anchor: MobileIpAnchor,
        hysteresis_db: float = 3.0,
        time_to_trigger_samples: int = 2,
        minimum_signal_dbm: float = -120.0,
    ) -> None:
        if hysteresis_db < 0 or time_to_trigger_samples < 1:
            raise ValueError("Hysteresis must be non-negative and TTT must be at least one sample.")
        self.ip_anchor = ip_anchor
        self.hysteresis_db = hysteresis_db
        self.time_to_trigger_samples = time_to_trigger_samples
        self.minimum_signal_dbm = minimum_signal_dbm
        self._serving: Dict[str, RadioCell] = {}
        self._pending: Dict[str, tuple[str, int]] = {}

    def update(self, session_id: str, cells: Iterable[RadioCell]) -> HandoverDecision:
        if not session_id:
            raise ValueError("Session ID must not be empty.")
        candidates = [
            cell for cell in cells if cell.available and cell.signal_dbm >= self.minimum_signal_dbm
        ]
        current = self._serving.get(session_id)
        if current is not None:
            current = next((cell for cell in candidates if cell.cell_id == current.cell_id), None)

        if current is None:
            if not candidates:
                self._pending.pop(session_id, None)
                return HandoverDecision("unavailable", None, None, None, None)
            target = max(candidates, key=lambda cell: cell.signal_dbm)
            self._serving[session_id] = target
            previous_binding = self.ip_anchor.lookup(session_id)
            binding = self.ip_anchor.bind(session_id, target.cell_id)
            self._pending.pop(session_id, None)
            status = "handed_over" if previous_binding else "attached"
            return HandoverDecision(status, target.cell_id, target.cell_id, binding.stable_ip, binding.generation)

        target = max(candidates, key=lambda cell: cell.signal_dbm)
        if target.cell_id == current.cell_id or target.signal_dbm < current.signal_dbm + self.hysteresis_db:
            self._pending.pop(session_id, None)
            binding = self.ip_anchor.lookup(session_id)
            return HandoverDecision(
                "stable",
                current.cell_id,
                None,
                binding.stable_ip if binding else None,
                binding.generation if binding else None,
            )

        pending_cell, samples = self._pending.get(session_id, (target.cell_id, 0))
        samples = samples + 1 if pending_cell == target.cell_id else 1
        if samples < self.time_to_trigger_samples:
            self._pending[session_id] = (target.cell_id, samples)
            binding = self.ip_anchor.lookup(session_id)
            return HandoverDecision(
                "preparing",
                current.cell_id,
                target.cell_id,
                binding.stable_ip if binding else None,
                binding.generation if binding else None,
            )

        self._serving[session_id] = target
        self._pending.pop(session_id, None)
        binding = self.ip_anchor.bind(session_id, target.cell_id)
        return HandoverDecision("handed_over", target.cell_id, target.cell_id, binding.stable_ip, binding.generation)
