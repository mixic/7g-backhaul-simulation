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

import random
from math import exp
from typing import Dict, Iterable, Optional, Tuple

from .environment import TransportMedium

RoutingState = Tuple[Tuple[str, int, int, int], ...]


class TabularQRoutingAgent:
    """Masked tabular Q-learning policy over quantized per-link network conditions."""

    def __init__(
        self,
        learning_rate: float = 0.2,
        discount_factor: float = 0.9,
        exploration_rate: float = 0.1,
        rng: Optional[random.Random] = None,
    ) -> None:
        if not 0 < learning_rate <= 1:
            raise ValueError("Learning rate must be in (0, 1].")
        if not 0 <= discount_factor <= 1:
            raise ValueError("Discount factor must be in [0, 1].")
        if not 0 <= exploration_rate <= 1:
            raise ValueError("Exploration rate must be in [0, 1].")
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.exploration_rate = exploration_rate
        self.rng = rng or random.Random()
        self.q_values: Dict[Tuple[RoutingState, str], float] = {}

    @staticmethod
    def state(channels: Iterable[TransportMedium]) -> RoutingState:
        return tuple(
            (
                medium.name,
                int(medium.available),
                min(4, int(medium.current_load * 5)),
                min(4, int(medium.get_pressure_score() * 5)),
            )
            for medium in channels
        )

    def choose_action(
        self,
        channels: Iterable[TransportMedium],
        baseline_weights: Optional[Dict[str, float]] = None,
        explore: bool = True,
    ) -> str:
        channel_list = list(channels)
        available = [medium for medium in channel_list if medium.available]
        if not available:
            raise RuntimeError("No available routing actions.")
        observed_state = self.state(channel_list)
        if explore and self.rng.random() < self.exploration_rate:
            return self.rng.choice(available).name

        scores = {
            medium.name: self.q_values.get((observed_state, medium.name), 0.0)
            for medium in available
        }
        best_score = max(scores.values())
        best = [name for name, score in scores.items() if score == best_score]
        if best_score == 0.0 and baseline_weights:
            return max(best, key=lambda name: baseline_weights.get(name, 0.0))
        return sorted(best)[0]

    def action_weights(
        self,
        channels: Iterable[TransportMedium],
        baseline_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        channel_list = list(channels)
        observed_state = self.state(channel_list)
        weights: Dict[str, float] = {}
        for medium in channel_list:
            if not medium.available:
                continue
            baseline = (baseline_weights or {}).get(medium.name, 0.0)
            learned_value = self.q_values.get((observed_state, medium.name), 0.0)
            weights[medium.name] = baseline * exp(min(20.0, max(-20.0, learned_value)))
        return weights

    def update(
        self,
        state: RoutingState,
        action: str,
        reward: float,
        next_state: RoutingState,
        terminal: bool = False,
    ) -> float:
        if not -1.0 <= reward <= 1.0:
            raise ValueError("Routing rewards must be normalized to [-1, 1].")
        key = (state, action)
        current = self.q_values.get(key, 0.0)
        future = 0.0
        if not terminal:
            available_names = [
                name
                for name, is_available, _, _ in next_state
                if is_available
            ]
            if available_names:
                future = max(
                    (
                        self.q_values.get((next_state, name), 0.0)
                        for name in available_names
                    ),
                    default=0.0,
                )
        updated = current + self.learning_rate * (
            reward + self.discount_factor * future - current
        )
        self.q_values[key] = updated
        return updated

    def learn_transition(
        self,
        channels: Iterable[TransportMedium],
        action: str,
        reward: float,
        next_state: Optional[RoutingState] = None,
        terminal: bool = False,
    ) -> float:
        channel_list = list(channels)
        current_state = self.state(channel_list)
        return self.update(
            current_state,
            action,
            reward,
            next_state if next_state is not None else current_state,
            terminal,
        )
