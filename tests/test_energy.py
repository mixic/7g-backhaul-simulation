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

"""CI tests for the stipulated M6 energy model."""

from __future__ import annotations

import unittest

from simulation.energy import (
    E_CHURN_PER_EDIT,
    E_CPU_PER_CYCLE,
    E_LLM_PER_CALL,
    E_TX_PER_BYTE,
    churn_energy,
    compress_energy,
    ewma_energy,
    llm_energy,
    tx_energy,
)


class EnergyModelTests(unittest.TestCase):
    def test_tx_energy(self) -> None:
        self.assertAlmostEqual(tx_energy(1000), E_TX_PER_BYTE * 1000)

    def test_churn_energy(self) -> None:
        self.assertAlmostEqual(churn_energy(10), E_CHURN_PER_EDIT * 10)

    def test_llm_energy(self) -> None:
        self.assertAlmostEqual(llm_energy(3), E_LLM_PER_CALL * 3)

    def test_ewma_energy(self) -> None:
        self.assertAlmostEqual(ewma_energy(300), E_CPU_PER_CYCLE * 50 * 300)

    def test_compress_energy(self) -> None:
        self.assertAlmostEqual(compress_energy(1000), E_CPU_PER_CYCLE * 100 * 1000)


if __name__ == "__main__":
    unittest.main()
