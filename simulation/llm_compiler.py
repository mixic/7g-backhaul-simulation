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

"""Cognitive Stack Compiler: a **Mock Oracle** plus guardrails.

**Not an LLM.** This is a deterministic *Mock Oracle*: it serialises the network
state into a prompt and returns a strict-JSON layer ordering. A real LLM (e.g. a
local model served through Ollama) is deliberately not required so the experiment
is reproducible without API keys or latency. The mock reads the prompt — it does
not hard-code a phase-to-stack table — and, with a seeded probability, emits a
*hallucination* so the guardrail's corrective action is exercised and logged.

**What H7 therefore tests.** Because the mock's *installed* output is the
canonical `C→E→F` order (the guardrail forces it on every hallucination), it is
bit-identical to the greedy heuristic. H7 tests the **symbolic guardrails against
injected hallucinated inputs**, not the reasoning capability of an actual LLM; the
wire-byte result is a property of the mock's policy, not of LLMs in general.

``simulation/guardrails.validate`` then enforces the P1/P5/P3 commutation rules
from ``docs/layering-predictions.md`` and forces the canonical stack on any
violation.  The corrected ordering is what the data plane actually installs.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from random import Random

from simulation.guardrails import (
    C,
    E,
    F,
    GuardrailResult,
    T,
    canonical_order,
    validate,
)

#: Full-name -> kind mapping used by the Oracle's JSON output.
NAME_TO_KIND = {"Compress": C, "Encrypt": E, "Tunnel": T, "Fragment": F}
KIND_TO_NAME = {v: k for k, v in NAME_TO_KIND.items()}

#: Probability that the mock Oracle emits a hallucination (seeded, deterministic).
HALLUCINATION_PROB = 0.25


@dataclass(frozen=True)
class CompileResult:
    """One Oracle proposal, its guardrail correction, and the timing."""

    order: tuple[str, ...]              # installed C/E/F order (innermost first)
    authenticate_outer: bool            # installed flag
    proposal_names: tuple[str, ...]     # what the Oracle proposed (full names)
    proposal_authenticate: bool         # what the Oracle proposed for auth
    violations: tuple                  # guardrail violations (empty when none)
    decision_time_s: float              # Oracle wall-clock time

    @property
    def intervened(self) -> bool:
        return bool(self.violations)


def build_prompt(state: dict) -> str:
    """Serialize the network state into the Oracle's prompt."""
    return (
        "Network state: "
        f"path_mtu={state['mtu']} "
        f"loss_rate={state['loss']:.4f} "
        f"compressibility={'high' if state['compressible'] else 'low'} "
        f"nat={'true' if state['nat'] else 'false'}"
    )


def _parse(prompt: str, key: str) -> str:
    match = re.search(rf"{key}=(\S+)", prompt)
    return match.group(1) if match else ""


def mock_llm(prompt: str, rng: Random) -> dict:
    """Deterministic mocked Oracle: read the prompt, propose, occasionally err.

    The learned policy is "compress first, then encrypt once, then fragment",
    which is optimal for both payload classes.  The mock is not a phase table:
    it extracts the compressibility and NAT flags from the prompt and, with a
    seeded probability, emits one of two documented hallucinations.
    """
    compressible = _parse(prompt, "compressibility") == "high"
    nat = _parse(prompt, "nat") == "true"

    order = ["Compress", "Encrypt", "Fragment"]
    authenticate = False

    if rng.random() < HALLUCINATION_PROB:
        # two hallucination classes, chosen at random
        if rng.random() < 0.5 and compressible:
            # P1: encrypt before compress on compressible data
            order = ["Encrypt", "Compress", "Fragment"]
        elif nat:
            # P3: authenticate the NAT-rewritten outer source address
            authenticate = True

    return {"stack": order, "authenticate_outer": authenticate}


def compile_stack(state: dict, rng: Random) -> CompileResult:
    """Run the Oracle and the guardrail for one network state."""
    prompt = build_prompt(state)
    start = time.perf_counter()
    proposal = mock_llm(prompt, rng)
    decision_time = time.perf_counter() - start

    proposal_names = tuple(proposal["stack"])
    proposal_kinds = [NAME_TO_KIND[name] for name in proposal_names]
    proposal_authenticate = bool(proposal["authenticate_outer"])

    result: GuardrailResult = validate(
        proposal_kinds, proposal_authenticate, state
    )

    return CompileResult(
        order=result.order,
        authenticate_outer=result.authenticate_outer,
        proposal_names=proposal_names,
        proposal_authenticate=proposal_authenticate,
        violations=result.violations,
        decision_time_s=decision_time,
    )


def greedy_heuristic(state: dict) -> CompileResult:
    """A hand-written if/else baseline: the same rules, no Oracle, no guardrail.

    It is intentionally readable so the reader can see that the optimal stack
    for these payload classes is a two-line rule.
    """
    compressible = bool(state.get("compressible", True))
    order = canonical_order(compressible)
    return CompileResult(
        order=order,
        authenticate_outer=False,
        proposal_names=tuple(KIND_TO_NAME[k] for k in order),
        proposal_authenticate=False,
        violations=(),
        decision_time_s=0.0,
    )


#: The fixed ISO-style baseline: fragment, then encrypt, then compress.  The
#: tunnel is always outermost.  It never adapts to the medium.
STATIC_ORDER: tuple[str, ...] = (F, E, C)


def static_stack(state: dict) -> CompileResult:
    """The static ISO baseline: a fixed order for every phase."""
    return CompileResult(
        order=STATIC_ORDER,
        authenticate_outer=False,
        proposal_names=tuple(KIND_TO_NAME[k] for k in STATIC_ORDER),
        proposal_authenticate=False,
        violations=(),
        decision_time_s=0.0,
    )


# Reference serialisation kept for the CSV (the mock's JSON, for auditability).
def proposal_json(result: CompileResult) -> str:
    return json.dumps(
        {
            "stack": list(result.proposal_names),
            "authenticate_outer": result.proposal_authenticate,
        }
    )
