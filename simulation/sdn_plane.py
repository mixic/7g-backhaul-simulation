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

"""Minimal SDN control-plane prototype for the dual-role data plane.

This is the executable part of ``docs/sdn-mapping.md``.  It separates:

* a **controller** that reconciles a northbound flood policy into southbound
  instructions;
* a **data plane** (the existing ``DualRoleSimulation``) that applies the
  instructions instead of running its local controller.

Only the ``set_alpha`` action is implemented.  Path weights, RFMP epochs,
admission tables and name-class verification are described in the mapping but
are not wired here.  The attack alert is stipulated perfect: the controller
reads the scenario's attack schedule, which stands in for a detection system.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulation.dual_role import ORIGIN, DualRoleSimulation

#: Demand-side nodes that can serve content.
EDGE_TARGETS = ("E1", "E2", "E3")


@dataclass(frozen=True)
class SouthboundMessage:
    """One controller-to-node instruction."""

    node: str
    action: str
    value: float


class FloodAwareController:
    """Central flood policy: forward-only on the attacked target.

    On an alert the controller pins the attacked target and every interior node
    to ``alpha = 0`` (pure forwarding) and the unattacked edge targets to
    ``alpha = 1`` (pure serving).  With no alert it emits no instructions, so
    the data plane keeps its local fluid controller.  The policy therefore
    switches between local control and an explicit role override without
    replacing the data-plane model.
    """

    def reconcile(self, simulation: DualRoleSimulation) -> list[SouthboundMessage]:
        attack = simulation.scenario.attack(simulation.tick)
        attacking = {target for target, volume in attack.items() if volume > 0.0}
        if not attacking:
            return []
        messages: list[SouthboundMessage] = []
        for name in simulation.nodes:
            if name == ORIGIN:
                continue
            value = 1.0 if (name in EDGE_TARGETS and name not in attacking) else 0.0
            messages.append(SouthboundMessage(name, "set_alpha", value))
        return messages


class SDNDualRoleSimulation(DualRoleSimulation):
    """Dual-role data plane driven by a logically centralized controller."""

    def __init__(self, scenario, seed: int, controller=None, **kwargs) -> None:
        super().__init__(scenario, "fluid", seed, **kwargs)
        self.policy = controller or FloodAwareController()

    def update_alpha(self) -> None:
        messages = self.policy.reconcile(self)
        if not messages:
            super().update_alpha()
            return
        updated = dict(self.alpha)
        for message in messages:
            if message.action == "set_alpha":
                updated[message.node] = max(0.0, min(1.0, message.value))
        delta = sum(
            abs(updated[name] - self.alpha[name]) for name in updated
        ) / max(1, len(updated) - 1)
        self.alpha_deltas.append(delta)
        self.alpha = updated


def simulate_sdn(scenario, seed: int, controller=None, **kwargs):
    """Run one SDN-controlled replicate on a scenario key or Scenario."""
    return SDNDualRoleSimulation(scenario, seed, controller=controller, **kwargs).run()
