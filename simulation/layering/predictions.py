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

"""The formal survival condition and its per-case predictions.

The predictor reads only the layer order and the declared properties of each
layer.  It never consults the codec's field records or observed bytes.  That
separation is what makes the comparison a test rather than a tautology.

For a target field ``f`` introduced by layer index ``i``:

* ``visible`` - no encryption or compression layer is applied after ``i``;
* ``reachable`` - ``len(stack) - i <= max_depth`` for a middlebox whose fixed
  parser understands ``max_depth`` layers;
* ``authenticated`` - the target is in an encryption layer's AAD scope;
* ``mutation`` - the middlebox rewrote the field (reachable and visible);
* ``auth_ok`` - no mutation of an authenticated field;
* ``delivered`` - authentication passed and no mutated field was
  length/offset-bearing.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulation.layering.scenarios import STRUCTURAL_FIELDS, Case


@dataclass(frozen=True)
class Prediction:
    visible: bool
    reachable: bool
    authenticated: bool
    mutation: bool
    auth_ok: bool
    delivered: bool

    @property
    def auth_accept_percent(self) -> float:
        return 100.0 if self.auth_ok else 0.0

    @property
    def delivery_percent(self) -> float:
        return 100.0 if self.delivered else 0.0


def predict(case: Case) -> Prediction:
    """Evaluate the survival condition for one case."""
    if case.target is None:
        raise ValueError("A survival prediction needs a target field.")
    layer, field = case.target
    if layer not in case.kinds:
        raise ValueError(f"Target layer {layer} is not in case {case.name}.")
    index = case.kinds.index(layer)
    visible = not any(
        kind in {"E", "C"} for kind in case.kinds[index + 1 :]
    )
    depth = len(case.kinds) - index
    reachable = case.max_depth is None or depth <= case.max_depth
    authenticated = case.target in case.aad
    if authenticated and not visible:
        raise ValueError(
            f"Case {case.name} authenticates an invisible field."
        )
    mutation = reachable and visible
    auth_ok = not (mutation and authenticated)
    structural = case.structural or case.target in STRUCTURAL_FIELDS
    delivered = auth_ok and not (mutation and structural)
    return Prediction(
        visible=visible,
        reachable=reachable,
        authenticated=authenticated,
        mutation=mutation,
        auth_ok=auth_ok,
        delivered=delivered,
    )
