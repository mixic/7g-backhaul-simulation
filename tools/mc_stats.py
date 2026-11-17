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

"""Monte Carlo statistics: means, confidence intervals and permutation tests.

The functions are deliberately small and dependency-light: the benchmark writes
CSVs that other tools (and readers) must be able to reproduce without importing a
statistics framework.  Every interval is a percentile bootstrap of the mean; every
p-value is a two-sided sign-flip permutation test.  The random seed of the
resampling is a constant of the analysis, so a rerun reproduces the intervals.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

#: Resampling constants of the frozen analysis.
BOOTSTRAP_RESAMPLES = 10_000
PERMUTATION_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20_260_111
PERMUTATION_SEED = 20_260_112

#: The nominal level and the Bonferroni level for twelve criteria.
NOMINAL_LEVEL = 0.95
BONFERRONI_LEVEL = 1.0 - 0.05 / 12.0


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean of a non-empty sequence."""
    items = np.asarray(values, dtype=float)
    return float(items.mean()) if items.size else 0.0


def sd(values: Sequence[float]) -> float:
    """Sample standard deviation (ddof = 1)."""
    items = np.asarray(values, dtype=float)
    if items.size < 2:
        return 0.0
    return float(items.std(ddof=1))


def t_interval(
    values: Sequence[float], level: float = NOMINAL_LEVEL
) -> tuple[float, float, float]:
    """Analytic normal-approximation interval, used only for summaries."""
    items = np.asarray(values, dtype=float)
    if items.size < 2:
        centre = float(items.mean()) if items.size else 0.0
        return centre, centre, centre
    centre = float(items.mean())
    half = 1.959963984540054 * float(items.std(ddof=1)) / math.sqrt(items.size)
    if level != NOMINAL_LEVEL:
        from statistics import NormalDist

        half = NormalDist().inv_cdf(0.5 + level / 2.0) * float(
            items.std(ddof=1)
        ) / math.sqrt(items.size)
    return centre, centre - half, centre + half


def bootstrap_means(
    values: Sequence[float],
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    chunk: int = 1000,
) -> np.ndarray:
    """Percentile-bootstrap replicates of the mean of ``values``."""
    items = np.asarray(values, dtype=float)
    size = int(items.size)
    if size == 0:
        raise ValueError("bootstrap needs at least one observation")
    rng = np.random.default_rng(seed)
    replicates = np.empty(resamples, dtype=float)
    done = 0
    while done < resamples:
        take = min(chunk, resamples - done)
        indices = rng.integers(0, size, size=(take, size))
        replicates[done : done + take] = items[indices].mean(axis=1)
        done += take
    return replicates


def bootstrap_interval(
    values: Sequence[float],
    level: float = NOMINAL_LEVEL,
    replicates: np.ndarray | None = None,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval of the mean."""
    draws = bootstrap_means(values) if replicates is None else replicates
    alpha = 1.0 - level
    return (
        float(np.quantile(draws, alpha / 2.0)),
        float(np.quantile(draws, 1.0 - alpha / 2.0)),
    )


def permutation_p_two_sided(
    values: Sequence[float],
    centre: float = 0.0,
    resamples: int = PERMUTATION_RESAMPLES,
    seed: int = PERMUTATION_SEED,
    chunk: int = 1000,
) -> float:
    """Two-sided sign-flip permutation p-value for ``mean(values) == centre``."""
    items = np.asarray(values, dtype=float) - centre
    size = int(items.size)
    if size == 0:
        return 1.0
    observed = abs(float(items.mean()))
    if observed == 0.0:
        return 1.0
    rng = np.random.default_rng(seed)
    exceed = 0
    done = 0
    while done < resamples:
        take = min(chunk, resamples - done)
        signs = rng.choice([-1.0, 1.0], size=(take, size))
        statistics = np.abs((signs * items).mean(axis=1))
        exceed += int(np.count_nonzero(statistics >= observed - 1e-15))
        done += take
    return float(exceed / resamples)
