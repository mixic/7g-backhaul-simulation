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

"""The savant controller: asymmetric, extreme compensation on one node.

On a kinematic shockwave the node deliberately sheds its general transit role:
`alpha` is driven toward `savant_alpha` through the same double integrator used
by the surgical controller, and the affected class is given top priority on what
remains.  A :class:`~simulation.savant.starvation.StarvationLogger` counts every
request of an *other* flow dropped at the node while savant mode is active, and
the node is marked in :attr:`SimRun.savant_active_nodes` so the data plane can
attribute drops exactly.

The edit is node-local: it does not spread to other nodes unless a spatial
baseline reroutes traffic in response to the induced failure.
"""

from __future__ import annotations

from simulation.savant.starvation import StarvationLogger
from simulation.surgical.config import SAVANT
from simulation.surgical.controllers import SurgicalController


class SavantController(SurgicalController):
    """H4: compensatory hyper-specialisation (the "savant" mechanism)."""

    name = SAVANT

    def __init__(self, cfg, sim):
        super().__init__(cfg, sim)
        self.starvation = StarvationLogger()
        sim.savant_log = self.starvation
        if not hasattr(sim, "savant_active_nodes"):
            sim.savant_active_nodes = set()

    def on_tick(self, t, obs):
        dt = self._dt(t)
        self._step_governors(t, dt)
        self._release(t, obs)
        self._detect(t, obs)
        self._top_up(t, obs)

    def _edit(self, node, cls, t):
        if not self._spend(node, self._cost(), t):
            return False
        self.sim.enable_class(node, cls, 1.0, 1.0)
        self.sim.set_weight(node, cls, 1.0)      # the affected circuit gets the lane
        self.sim.set_limit(node, cls, 0.60)
        self.active[node] = {"phase": "in", "cls": cls,
                             "until": t + self.cfg.edit_hold,
                             "p0": max(0.2, self.sim.node_pressure.get(node, 0.5))}
        # the sacrifice: shed general transit at this node
        self._gov(node, ("a", 0), self.sim.states[node].alpha,
                  self.cfg.savant_alpha)
        self.starvation.activate(node)
        self.sim.savant_active_nodes.add(node)
        return True

    def _release(self, t, obs):
        super()._release(t, obs)
        for node, e in list(self.active.items()):
            if e["phase"] != "out":
                continue
            if e.get("alpha_restored"):
                continue
            e["alpha_restored"] = True
            self._gov(node, ("a", 0), self.sim.states[node].alpha,
                      self.sim.topo.alpha0[node])

    def sweep(self):
        for node, e in list(self.active.items()):
            if e["phase"] != "out":
                continue
            self.starvation.deactivate(node)
            self.sim.savant_active_nodes.discard(node)
            if e["cls"] is not None:
                self.sim.disable_class(node, e["cls"])
            self.active.pop(node, None)
