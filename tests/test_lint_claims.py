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

"""Tests for tools/lint_claims.py.

The positive test proves the committed papers pass.  Every other test tampers
with one fact -- a phrase, a number in the paper, or a number in the computed
facts -- and expects the lint to go red.  A lint that cannot fail is not a gate.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("lint_claims", ROOT / "tools" / "lint_claims.py")
lint = importlib.util.module_from_spec(_SPEC)
sys.modules["lint_claims"] = lint
_SPEC.loader.exec_module(lint)


class LintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.facts = lint.load_facts()
        cls.paper_a = (ROOT / "docs" / "paper-layering-testbed.md").read_text(encoding="utf-8")
        cls.paper_d = (ROOT / "docs" / "paper-common-mode.md").read_text(encoding="utf-8")

    def problems(self, paper_a: str | None = None, paper_d: str | None = None, facts=None) -> str:
        return "\n".join(
            lint.lint_text(
                self.paper_a if paper_a is None else paper_a,
                self.paper_d if paper_d is None else paper_d,
                self.facts if facts is None else facts,
            )
        )

    def test_committed_papers_pass(self) -> None:
        self.assertEqual(self.problems(), "")

    def test_facts_are_the_committed_values(self) -> None:
        self.assertEqual(self.facts.p16d_range, (673, 717))
        self.assertAlmostEqual(self.facts.p5_diff, 12.35, places=2)
        self.assertEqual(self.facts.p15_totals, (2112, 2180))
        self.assertAlmostEqual(self.facts.brier, 0.0833, places=4)
        self.assertEqual(self.facts.counts["P1-P7"], (6, 7))
        self.assertEqual(self.facts.counts["P8-P12"], (5, 5))
        self.assertEqual(self.facts.counts["P13-P16"], (17, 18))

    def test_each_banned_phrase_is_caught(self) -> None:
        for phrase, _ in lint.BANNED_PHRASES:
            with self.subTest(phrase=phrase):
                text = self.paper_d + f"\n\n{phrase}\n"
                self.assertIn("banned phrase", self.problems(paper_d=text))

    def test_7g_in_title_is_caught(self) -> None:
        text = self.paper_a.replace(
            "# Which Rewrites Survive?",
            "# 7G Which Rewrites Survive?",
            1,
        )
        self.assertNotEqual(text, self.paper_a)
        self.assertIn("7G", self.problems(paper_a=text))

    def test_heterogeneous_in_abstract_is_caught(self) -> None:
        text = self.paper_a.replace(
            "## Abstract\n", "## Abstract\n\nA heterogeneous stack. ", 1
        )
        self.assertNotEqual(text, self.paper_a)
        self.assertIn("heterogeneous", self.problems(paper_a=text))

    def test_old_rule_wording_is_caught(self) -> None:
        text = self.paper_a + "\nA rewrite survives a rewrite iff the field is visible.\n"
        self.assertIn("old rule wording", self.problems(paper_a=text))

    def test_wrong_p16d_range_in_paper_is_caught(self) -> None:
        text = self.paper_a.replace("673–717", "674–718")
        self.assertNotEqual(text, self.paper_a)
        self.assertIn("P16d range", self.problems(paper_a=text))

    def test_p16d_fact_change_is_caught(self) -> None:
        facts = dataclasses.replace(self.facts, p16d_range=(674, 718))
        self.assertIn("P16d range", self.problems(facts=facts))

    def test_wrong_p5_difference_is_caught(self) -> None:
        text = self.paper_a.replace("12.35", "12.34")
        self.assertNotEqual(text, self.paper_a)
        self.assertIn("P5 Linux delivery difference", self.problems(paper_a=text))

    def test_p5_fact_change_is_caught(self) -> None:
        facts = dataclasses.replace(self.facts, p5_diff=12.34)
        self.assertIn("P5 Linux delivery difference", self.problems(facts=facts))

    def test_wrong_p15_total_is_caught(self) -> None:
        text = self.paper_a.replace("2112", "2111")
        self.assertNotEqual(text, self.paper_a)
        self.assertIn("P15 wire total", self.problems(paper_a=text))

    def test_p15_fact_change_is_caught(self) -> None:
        facts = dataclasses.replace(self.facts, p15_totals=(2111, 2181))
        self.assertIn("P15 wire total", self.problems(facts=facts))

    def test_wrong_brier_is_caught(self) -> None:
        text = self.paper_a.replace("0.0833", "0.0834")
        self.assertNotEqual(text, self.paper_a)
        self.assertIn("Brier score", self.problems(paper_a=text))

    def test_brier_fact_change_is_caught(self) -> None:
        facts = dataclasses.replace(self.facts, brier=0.0834)
        self.assertIn("Brier score", self.problems(facts=facts))

    def test_count_change_is_caught(self) -> None:
        counts = dict(self.facts.counts)
        counts["P13-P16"] = (18, 18)
        facts = dataclasses.replace(self.facts, counts=counts)
        self.assertIn("source count P13-P16", self.problems(facts=facts))

    def test_missing_paper_d_number_is_caught(self) -> None:
        text = self.paper_d.replace("44.38", "44.4")
        self.assertNotEqual(text, self.paper_d)
        self.assertIn("expected number '44.38'", self.problems(paper_d=text))


if __name__ == "__main__":
    unittest.main()
