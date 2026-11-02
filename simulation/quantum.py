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

from dataclasses import dataclass
from math import ceil, floor, isfinite


class QuantumResourceUnavailable(RuntimeError):
    """Raised when a modeled quantum link cannot supply the requested resource."""


@dataclass(frozen=True)
class QuantumGenerationResult:
    source_qubits: int
    quantum_frames: int
    generated_key_bits: int
    buffered_key_bits: int


@dataclass
class QuantumResourceLink:
    """Abstract QKD/entanglement resource, separate from a classical byte link."""

    peer_a: str
    peer_b: str
    max_qubits_per_frame: int
    qubit_rate_per_second: float
    fidelity: float = 0.99
    available: bool = True
    buffered_key_bits: int = 0

    def __post_init__(self) -> None:
        if not self.peer_a or not self.peer_b or self.peer_a == self.peer_b:
            raise ValueError("A quantum link must connect two distinct named peers.")
        if (
            not isinstance(self.max_qubits_per_frame, int)
            or isinstance(self.max_qubits_per_frame, bool)
            or self.max_qubits_per_frame <= 0
        ):
            raise ValueError("Quantum frame capacity must be a positive integer number of qubits.")
        if not isfinite(self.qubit_rate_per_second) or self.qubit_rate_per_second < 0:
            raise ValueError("Qubit rate must be non-negative and finite.")
        if not isfinite(self.fidelity) or not 0 <= self.fidelity <= 1:
            raise ValueError("Fidelity must be between zero and one.")
        if (
            not isinstance(self.buffered_key_bits, int)
            or isinstance(self.buffered_key_bits, bool)
            or self.buffered_key_bits < 0
        ):
            raise ValueError("Buffered key bits must be a non-negative integer.")

    def connects(self, peer_a: str, peer_b: str) -> bool:
        return {self.peer_a, self.peer_b} == {peer_a, peer_b}

    def generate_key_material(self, elapsed_seconds: float) -> QuantumGenerationResult:
        if not isfinite(elapsed_seconds) or elapsed_seconds < 0:
            raise ValueError("Elapsed time must be non-negative and finite.")
        if not self.available or elapsed_seconds == 0:
            return QuantumGenerationResult(0, 0, 0, self.buffered_key_bits)

        source_qubits = floor(self.qubit_rate_per_second * elapsed_seconds)
        quantum_frames = ceil(source_qubits / self.max_qubits_per_frame)
        generated_key_bits = floor(source_qubits * self.fidelity)
        self.buffered_key_bits += generated_key_bits
        return QuantumGenerationResult(
            source_qubits=source_qubits,
            quantum_frames=quantum_frames,
            generated_key_bits=generated_key_bits,
            buffered_key_bits=self.buffered_key_bits,
        )

    def reserve_key_bits(self, requested_bits: int) -> int:
        if (
            not isinstance(requested_bits, int)
            or isinstance(requested_bits, bool)
            or requested_bits <= 0
        ):
            raise ValueError("Requested key material must be a positive integer number of bits.")
        if not self.available:
            raise QuantumResourceUnavailable("Quantum resource link is unavailable.")
        if self.buffered_key_bits < requested_bits:
            raise QuantumResourceUnavailable(
                f"Quantum link has {self.buffered_key_bits} buffered key bits; "
                f"{requested_bits} are required."
            )
        self.buffered_key_bits -= requested_bits
        return requested_bits
