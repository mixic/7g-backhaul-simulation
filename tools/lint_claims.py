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

"""Fail the build when a paper claim drifts from the committed evidence.

This is a small, deliberately mechanical gate for Papers A and D.  It checks
three kinds of thing:

1. phrases that are not allowed in these papers because they overclaim
   (``results support``, ``pre-registered results``, ...);
2. Paper A's title/abstract vocabulary (``7G``, ``heterogeneous``) and the old
   rule wording (``survives a rewrite iff``);
3. numeric claims that must agree with the committed CSVs: the P16d delivered
   range, the P5 Linux delivery difference, the P15 wire totals, the round-2
   Brier score, and the headline counts.

The numeric side is computed from the same files as
``tools/make_paper_tables.py``.  It is a consistency check, not an independent
measurement: if the CSV is wrong, the lint cannot know.  What it does prevent is
a paper number being retyped, rounded into a different claim, or left behind
after a re-run.

Usage::

    python tools/lint_claims.py
    python tools/lint_claims.py --paper-a docs/paper-layering-testbed.md \
        --paper-d docs/paper-common-mode.md

Exit status is 0 when every check passes and 1 when any check fails.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

# Phrases that are banned in Papers A and D.  They are case-insensitive.
BANNED_PHRASES: tuple[tuple[str, str], ...] = (
    ("first direct", "priority claim that the evidence does not support"),
    ("apples-to-apples", "unverifiable comparison claim"),
    ("strongest available evidence", "unverifiable strength claim"),
    ("pre-registered results", "pre-registration covers predictions, not results"),
    ("results support", "a model check is not empirical support"),
)

PAPER_A_TITLE_BANNED = ("7G", "heterogeneous")
OLD_RULE_WORDING = "survives a rewrite iff"

# Paper-D headline numbers that must survive a rewrite.  These are not computed
# from a CSV in this lint because the common-mode summary is a run artifact; the
# values are fixed by the frozen 9 x 10 x 30 protocol and the deterministic
# scenario.  M6 re-derives and re-checks them against the committed sensitivity
# table; this gate catches a stale abstract.
PAPER_D_NUMBERS: tuple[tuple[str, str], ...] = (
    ("2,700 runs", "the frozen protocol is 9 arms x 10 events x 30 seeds"),
    ("44.38", "H19 interaction under the frozen scenario"),
    ("34.5", "tested minus untested fallback under the backhaul cut"),
)


@dataclass(frozen=True)
class Facts:
    """Numbers the papers are allowed to state, computed from committed data."""

    p16d_range: tuple[int, int]
    p5_diff: float
    p15_totals: tuple[int, int]
    brier: float
    counts: dict[str, tuple[int, int]]


def _load_generator():
    """Import ``tools/make_paper_tables.py`` without requiring a package."""
    path = ROOT / "tools" / "make_paper_tables.py"
    spec = importlib.util.spec_from_file_location("make_paper_tables_for_lint", path)
    if spec is None or spec.loader is None:  # pragma: no cover - import machinery
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # ``@dataclass`` resolves the module through sys.modules on Python 3.12+.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_facts(root: Path = ROOT) -> Facts:
    """Compute the checked numbers from the committed observation files."""
    mpt = _load_generator()
    data = mpt.Data.load()

    p16d = [int(value) for value in data.r2.vals("P16", "P16d", "delivered_datagrams")]
    if not p16d:
        raise ValueError("no P16d delivered_datagrams rows")

    p5_diff = data.layer["linux"].mean(
        "P5", "C_to_F", "delivery_percent"
    ) - data.layer["linux"].mean("P5", "F_to_C", "delivery_percent")

    p15 = set(
        int(round(value))
        for value in data.r2.vals("P15", "P15_EtoF", "wire_bytes_per_datagram")
    ) | set(
        int(round(value))
        for value in data.r2.vals("P15", "P15_FtoE", "wire_bytes_per_datagram")
    )
    if len(p15) != 2:
        raise ValueError(f"expected two P15 wire totals, got {sorted(p15)}")

    brier = sum(
        (credence - outcome) ** 2 for _, credence, outcome in data.calibration
    ) / len(data.calibration)
    counts = mpt.headline_counts(mpt.verdict_matrix(data))
    return Facts(
        p16d_range=(min(p16d), max(p16d)),
        p5_diff=p5_diff,
        p15_totals=tuple(sorted(p15)),  # type: ignore[arg-type]
        brier=brier,
        counts=counts,
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _title_and_abstract(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    title = ""
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break
    abstract = ""
    match = re.search(r"^##\s+Abstract\s*$", text, flags=re.MULTILINE)
    if match:
        rest = text[match.end() :]
        end = re.search(r"^##\s+", rest, flags=re.MULTILINE)
        abstract = rest[: end.start()] if end else rest
    return title, abstract


def _format_range(values: tuple[int, int]) -> str:
    return f"{values[0]}-{values[1]}"


def lint_text(
    paper_a: str,
    paper_d: str,
    facts: Facts,
    paper_a_name: str = "Paper A",
    paper_d_name: str = "Paper D",
) -> list[str]:
    """Return human-readable problems; an empty list means every check passed."""
    problems: list[str] = []

    for phrase, why in BANNED_PHRASES:
        for name, text in ((paper_a_name, paper_a), (paper_d_name, paper_d)):
            if phrase in text.lower():
                problems.append(f"{name}: banned phrase {phrase!r} ({why})")

    title, abstract = _title_and_abstract(paper_a)
    scope = f"{title}\n{abstract}"
    for word in PAPER_A_TITLE_BANNED:
        if re.search(rf"\b{re.escape(word)}\b", scope, flags=re.IGNORECASE):
            problems.append(
                f"{paper_a_name}: {word!r} appears in the title or abstract"
            )
    if OLD_RULE_WORDING in paper_a.lower():
        problems.append(f"{paper_a_name}: old rule wording {OLD_RULE_WORDING!r}")

    # P16d: every stated range must equal the CSV range.  The paper states it in
    # a table and in prose, so checking every occurrence is intentional.
    p16d_ranges = re.findall(
        r"P16d[^\n]*?(?<!\d)(\d{3})\s*(?:–|-|to)\s*(\d{3})(?!\d)", paper_a
    )
    if not p16d_ranges:
        problems.append(f"{paper_a_name}: no P16d delivered range found")
    for low, high in p16d_ranges:
        if (int(low), int(high)) != facts.p16d_range:
            problems.append(
                f"{paper_a_name}: P16d range {low}-{high} disagrees with CSV "
                f"{_format_range(facts.p16d_range)}"
            )

    p5_text = f"{facts.p5_diff:.2f}"
    if p5_text not in paper_a:
        problems.append(
            f"{paper_a_name}: P5 Linux delivery difference {p5_text} pp not stated"
        )

    for total in facts.p15_totals:
        if str(total) not in paper_a:
            problems.append(f"{paper_a_name}: P15 wire total {total} B not stated")

    brier_text = f"{facts.brier:.4f}"
    if brier_text not in paper_a:
        problems.append(f"{paper_a_name}: Brier score {brier_text} not stated")

    expected_counts = {
        "P1-P7": (6, 7),
        "P8-P12": (5, 5),
        "P13-P16": (17, 18),
    }
    for key, expected in expected_counts.items():
        actual = facts.counts.get(key)
        if actual != expected:
            problems.append(
                f"{paper_a_name}: source count {key} is {actual}, expected {expected}; "
                "update the paper and this lint together"
            )
    if not re.search(
        r"((six|6)\s*(of|/)\s*(seven|7)|six are confirmed)", paper_a, re.IGNORECASE
    ):
        problems.append(f"{paper_a_name}: P1-P7 count 'six of seven' not stated")
    if not re.search(
        r"(five further predictions|(five|5)\s*(of|/)\s*(5))", paper_a, re.IGNORECASE
    ):
        problems.append(f"{paper_a_name}: P8-P12 count 'five further predictions' not stated")
    if not re.search(r"(17|seventeen)\s*(of|/)\s*(18|eighteen)", paper_a, re.IGNORECASE):
        problems.append(f"{paper_a_name}: P13-P16 count '17 of 18' not stated")

    for token, why in PAPER_D_NUMBERS:
        if token not in paper_d:
            problems.append(f"{paper_d_name}: expected number {token!r} not stated ({why})")

    return problems


def lint_paths(
    paper_a: Path,
    paper_d: Path,
    facts: Facts | None = None,
) -> list[str]:
    return lint_text(
        _read(paper_a),
        _read(paper_d),
        facts if facts is not None else load_facts(),
        paper_a_name=str(paper_a),
        paper_d_name=str(paper_d),
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paper-a",
        type=Path,
        default=ROOT / "docs" / "paper-layering-testbed.md",
        help="Paper A Markdown",
    )
    parser.add_argument(
        "--paper-d",
        type=Path,
        default=ROOT / "docs" / "paper-common-mode.md",
        help="Paper D Markdown",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print one PASS line per check group as well as failures",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    facts = load_facts()
    problems = lint_paths(args.paper_a, args.paper_d, facts)
    if args.verbose:
        print(f"facts: P16d {facts.p16d_range}, P5 {facts.p5_diff:.2f}, "
              f"P15 {facts.p15_totals}, Brier {facts.brier:.4f}, counts {facts.counts}")
    if problems:
        for problem in problems:
            print(f"FAIL  {problem}")
        return 1
    print("PASS  Paper A and Paper D claims agree with the committed evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
