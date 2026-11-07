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

"""Stipulated energy accounting for M6.

Every cost below is **stipulated** — it is a modelling choice, not a
measurement of deployed hardware — so that transmission, CPU processing,
state-churn and LLM inference can be compared on one Joule scale.

  E_tx    = 1e-7 J/byte            (radio/fiber transmission)
  E_cpu   = 1e-9 J/cycle           (processing)
    encrypt/compress = 100 cycles/byte
    EWMA/RER         = 50 cycles/tick
  E_churn = 5.0 J per surgical edit (queue flush, FIB update, context switch)
  E_llm   = 20.0 J per Oracle call  (local model inference)
"""

from __future__ import annotations

#: Joules per byte transmitted.
E_TX_PER_BYTE = 1e-7
#: Joules per CPU cycle.
E_CPU_PER_CYCLE = 1e-9
#: CPU cycles per byte for encryption / compression.
CYCLES_ENCRYPT_COMPRESS = 100
#: CPU cycles per control tick for an EWMA / RER update.
CYCLES_EWMA_RER = 50
#: Joules per surgical edit.
E_CHURN_PER_EDIT = 5.0
#: Joules per LLM Oracle call.
E_LLM_PER_CALL = 20.0


def tx_energy(nbytes: float) -> float:
    """Transmission energy for ``nbytes`` bytes."""
    return E_TX_PER_BYTE * nbytes


def cpu_energy(cycles: float) -> float:
    """Processing energy for ``cycles`` CPU cycles."""
    return E_CPU_PER_CYCLE * cycles


def ewma_energy(ticks: int) -> float:
    """CPU energy of running the EWMA/RER filter for ``ticks`` control ticks."""
    return cpu_energy(CYCLES_EWMA_RER * ticks)


def compress_energy(nbytes: float) -> float:
    """CPU energy of encrypting/compressing ``nbytes`` bytes."""
    return cpu_energy(CYCLES_ENCRYPT_COMPRESS * nbytes)


def churn_energy(nedits: int) -> float:
    """State-change energy for ``nedits`` surgical edits."""
    return E_CHURN_PER_EDIT * nedits


def llm_energy(ncalls: int) -> float:
    """Inference energy for ``ncalls`` LLM Oracle calls."""
    return E_LLM_PER_CALL * ncalls
