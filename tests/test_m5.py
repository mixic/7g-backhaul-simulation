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

"""CI tests for the Cognitive Stack Compiler and its P1-P5 guardrails."""

from __future__ import annotations

import unittest
from random import Random

from simulation.guardrails import C, E, F, T, canonical_order, validate
from simulation.llm_compiler import (
    compile_stack,
    greedy_heuristic,
    mock_llm,
    static_stack,
)
from simulation.layering.layers import CompressLayer, EncryptLayer, FragmentLayer, TunnelLayer
from simulation.layering.stack import MiddleboxSpec, Stack
from simulation.mkb_controller import EwmaMkbController
from simulation.surgical.config import MKB_EWMA, SimConfig
from simulation.surgical.network import SimRun
from simulation.surgical.sim import run_and_score


def build(order, authenticate_outer, mtu=500):
    layers = []
    for kind in order:
        if kind == C:
            layers.append(CompressLayer(uid="C"))
        elif kind == E:
            aad = (("T", "src_addr"),) if authenticate_outer else ()
            layers.append(EncryptLayer(aad=aad, uid="E"))
        elif kind == F:
            layers.append(FragmentLayer(mtu=mtu, uid="F"))
        else:
            raise ValueError(kind)
    layers.append(TunnelLayer(uid="T"))
    return Stack(layers)


class GuardrailTests(unittest.TestCase):
    def test_p1_rejects_encrypt_before_compress_on_compressible(self):
        r = validate([E, C, F], False, {"compressible": True, "nat": False})
        self.assertTrue(r.intervened)
        self.assertIn("P1", [v.rule for v in r.violations])
        self.assertEqual(r.order, (C, E, F))

    def test_p5_rejects_fragment_before_compress_on_compressible(self):
        r = validate([F, E, C], False, {"compressible": True, "nat": False})
        self.assertTrue(r.intervened)
        self.assertIn("P5", [v.rule for v in r.violations])
        self.assertEqual(r.order, (C, E, F))

    def test_p3_rejects_authenticating_outer_under_nat(self):
        r = validate([C, E, F], True, {"compressible": True, "nat": True})
        self.assertTrue(r.intervened)
        self.assertIn("P3", [v.rule for v in r.violations])
        self.assertFalse(r.authenticate_outer)

    def test_valid_stack_passes_unchanged(self):
        r = validate([C, E, F], False, {"compressible": True, "nat": True})
        self.assertFalse(r.intervened)
        self.assertEqual(r.order, (C, E, F))
        self.assertFalse(r.authenticate_outer)

    def test_random_payload_allows_encrypt_before_compress(self):
        # P1 does not bind on incompressible data.
        r = validate([E, C, F], False, {"compressible": False, "nat": False})
        self.assertFalse(r.intervened)

    def test_canonical_order(self):
        self.assertEqual(canonical_order(True), (C, E, F))
        self.assertEqual(canonical_order(False), (C, E, F))


class CompilerTests(unittest.TestCase):
    def test_mock_llm_is_deterministic(self):
        prompt = "Network state: path_mtu=500 loss_rate=0.05 compressibility=high nat=true"
        a = mock_llm(prompt, Random(7))
        b = mock_llm(prompt, Random(7))
        self.assertEqual(a, b)

    def test_greedy_returns_canonical_order(self):
        r = greedy_heuristic({"compressible": True, "nat": True})
        self.assertEqual(r.order, (C, E, F))
        self.assertFalse(r.authenticate_outer)

    def test_static_is_fixed(self):
        r = static_stack({})
        self.assertEqual(r.order, (F, E, C))
        self.assertFalse(r.authenticate_outer)

    def test_compile_stack_corrects_hallucination(self):
        # Force many draws so at least the guarded path is exercised deterministically.
        rng = Random(1)
        results = [compile_stack({"compressible": True, "nat": True, "mtu": 500,
                                  "loss": 0.05}, rng) for _ in range(50)]
        # Every installed stack must be valid (C first, never auth outer under NAT).
        for r in results:
            self.assertEqual(r.order, (C, E, F))
            self.assertFalse(r.authenticate_outer)


class CodecIntegrationTests(unittest.TestCase):
    def test_nat_rewrite_preserves_auth_without_aad(self):
        stack = build((C, E, F), False, mtu=500)
        payload = b"a" * 1400
        nat = MiddleboxSpec(layer="T", field="src_addr",
                            value=b"\x0a\x00\x02\xff")
        result = stack.decode(stack.encode(payload), middlebox=nat)
        self.assertTrue(result.auth_ok)
        self.assertTrue(result.delivered)

    def test_wire_bytes_reduced_by_compress_first(self):
        optimal = build((C, E, F), False, mtu=500)
        suboptimal = build((F, E, C), False, mtu=500)
        payload = b"network homeostasis " * 70
        self.assertLess(optimal.wire_bytes(payload), suboptimal.wire_bytes(payload))


class EwmaControllerTests(unittest.TestCase):
    def test_ewma_controller_is_registered(self) -> None:
        sim = SimRun(SimConfig(name="exp1_ddos", seed=0, controller=MKB_EWMA))
        self.assertIsInstance(sim.controller, EwmaMkbController)

    def test_ewma_controller_runs_and_reports(self) -> None:
        r = run_and_score(SimConfig(name="exp1_ddos", seed=0,
                                    controller=MKB_EWMA).child(duration=45.0))
        self.assertGreaterEqual(r["edits"], 0)
        self.assertGreaterEqual(r["rer_event_count"], 0)
        self.assertGreater(r["goodput_shock"], 0.0)


if __name__ == "__main__":
    unittest.main()
