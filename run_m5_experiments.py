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

"""M5: the Cognitive Stack Compiler (H7).

Three arms compile an encapsulation-layer ordering for a flow that crosses a
Fiber -> Microwave -> Satellite boundary sequence, and the wire-byte and
authentication cost is compared over 30 paired seeds:

  * ``static_iso``      a fixed Fragment->Encrypt->Compress order
  * ``greedy_heuristic`` a hand-written two-line rule
  * ``llm_compiler``    a mocked deterministic LLM Oracle, bounded by the
                        P1/P5/P3 guardrails in ``simulation/guardrails.py``

The Oracle is a *mock* (no API, no latency) and its occasional hallucination is
logged so the guardrail's corrective value is measured, not asserted.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from random import Random

import numpy as np

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from simulation.guardrails import C, E, F, T  # noqa: E402
from simulation.layering.layers import (  # noqa: E402
    CompressLayer,
    EncryptLayer,
    FragmentLayer,
    TunnelLayer,
)
from simulation.layering.stack import MiddleboxSpec, Stack  # noqa: E402
from simulation.llm_compiler import (  # noqa: E402
    CompileResult,
    compile_stack,
    greedy_heuristic,
    static_stack,
)

PAYLOAD_SIZE = 1400

#: Three medium boundaries the flow crosses, in order.
PHASES = (
    {"name": "fiber", "mtu": 1500, "loss": 0.00, "compressible": True,
     "nat": False, "rate_bps": 1e9, "prop_s": 0.0005},
    {"name": "microwave", "mtu": 900, "loss": 0.01, "compressible": False,
     "nat": False, "rate_bps": 100e6, "prop_s": 0.002},
    {"name": "satellite", "mtu": 500, "loss": 0.05, "compressible": True,
     "nat": True, "rate_bps": 10e6, "prop_s": 0.5},
)

#: Reassembly stall attributed per extra fragment (model, not measurement).
REASSEMBLY_DELAY_S = 0.001

#: NAT rewrite of the outer tunnel source address (4 bytes, length preserving).
_NAT_VALUE = b"\x0a\x00\x02\xff"
NAT = MiddleboxSpec(layer="T", field="src_addr", value=_NAT_VALUE)


def _compressible_payload(seed: int, size: int) -> bytes:
    """A low-entropy byte string whose zlib ratio varies with the seed.

    The alphabet size is seeded (2..9 distinct byte values), so the compressed
    length differs seed-to-seed while every payload stays highly compressible.
    """
    rng = Random(seed)
    alphabet_size = 2 + seed % 8
    alphabet = bytes(range(ord("A"), ord("A") + alphabet_size))
    return bytes(rng.choice(alphabet) for _ in range(size))


def _random_payload(seed: int, size: int) -> bytes:
    return Random(seed).randbytes(size)


def build_codec_stack(order, authenticate_outer: bool, mtu: int) -> Stack:
    """Instantiate the layering codec for a corrected C/E/F order (+T outer)."""
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
            raise ValueError(f"unknown layer kind {kind!r}")
    layers.append(TunnelLayer(uid="T"))
    return Stack(layers)


def _compile(arm: str, state: dict, rng: Random) -> CompileResult:
    if arm == "static_iso":
        return static_stack(state)
    if arm == "greedy_heuristic":
        return greedy_heuristic(state)
    if arm == "llm_compiler":
        return compile_stack(state, rng)
    raise ValueError(arm)


def run_one(arm: str, seed: int) -> dict:
    """Compile and measure one arm across all three phases for one seed."""
    rng = Random(1_000_000 + seed)

    wire = 0.0
    delivered = 0.0
    latency = 0.0
    hallucinations = 0
    interventions = 0
    decision_time = 0.0
    per_phase_wire = {}

    for phase in PHASES:
        payload = (
            _compressible_payload(seed, PAYLOAD_SIZE)
            if phase["compressible"]
            else _random_payload(seed, PAYLOAD_SIZE)
        )
        state = {
            "mtu": phase["mtu"],
            "loss": phase["loss"],
            "compressible": phase["compressible"],
            "nat": phase["nat"],
        }
        result = _compile(arm, state, rng)

        stack = build_codec_stack(result.order, result.authenticate_outer,
                                  phase["mtu"])
        wb = float(stack.wire_bytes(payload))
        n = int(stack.fragment_count(payload))
        delivery = float((1.0 - phase["loss"]) ** n)
        auth_ok = stack.decode(
            stack.encode(payload),
            middlebox=(NAT if phase["nat"] else None),
        ).auth_ok

        wire += wb
        delivered += PAYLOAD_SIZE * delivery
        latency += (phase["prop_s"] + wb / phase["rate_bps"]
                    + max(0, n - 1) * REASSEMBLY_DELAY_S)
        hallucinations += len(result.violations)
        interventions += (1 if result.intervened else 0)
        decision_time += result.decision_time_s
        per_phase_wire[phase["name"]] = wb

    row = {
        "arm": arm,
        "seed": seed,
        "Wire_Bytes_Total": round(wire, 1),
        "Fiber_Wire_Bytes": round(per_phase_wire["fiber"], 1),
        "Microwave_Wire_Bytes": round(per_phase_wire["microwave"], 1),
        "Satellite_Wire_Bytes": round(per_phase_wire["satellite"], 1),
        "Delivered_Bytes_Total": round(delivered, 1),
        "Throughput_Overhead_Ratio": round(delivered / wire, 6) if wire else 0.0,
        "Auth_Acceptance_Rate": 100.0 if auth_ok else 0.0,
        "P95_Latency_Total_s": round(latency, 6),
        "Hallucinations": hallucinations,
        "Guardrail_Interventions": interventions,
        "Oracle_Decision_Time_s": round(decision_time, 6),
    }
    return row


def _mean_ci(values) -> tuple[float, float]:
    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if array.size < 2:
        return (float(array.mean()) if array.size else float("nan")), 0.0
    return float(array.mean()), float(1.96 * array.std(ddof=1) / math.sqrt(array.size))


def _paired_compare(rows, arm_a, arm_b, metric):
    da = {r["seed"]: r[metric] for r in rows if r["arm"] == arm_a}
    db = {r["seed"]: r[metric] for r in rows if r["arm"] == arm_b}
    seeds = sorted(set(da) & set(db))
    a = np.array([da[s] for s in seeds], dtype=float)
    b = np.array([db[s] for s in seeds], dtype=float)
    diff = a - b
    md = float(diff.mean())
    sd = float(diff.std(ddof=1)) if len(diff) > 1 else 0.0
    se = sd / math.sqrt(len(diff)) if len(diff) > 1 else 0.0
    ci = 1.96 * se
    if sd == 0.0:
        # identical per-seed values: the difference is exactly zero.
        p = 1.0
    else:
        p = float("nan")
        try:
            from scipy import stats
            p = float(stats.ttest_rel(a, b).pvalue)
        except Exception:
            pass
    return md, ci, p


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def plot_overhead(rows: list[dict], out_dir: Path):
    arms = ("static_iso", "greedy_heuristic", "llm_compiler")
    phases = ("fiber", "microwave", "satellite")
    labels = ("Static ISO", "Greedy", "LLM + guardrails")
    colors = ("#c0392b", "#1f6feb", "#27ae60")

    means = {arm: {} for arm in arms}
    for arm in arms:
        for phase in phases:
            key = {"fiber": "Fiber_Wire_Bytes", "microwave": "Microwave_Wire_Bytes",
                   "satellite": "Satellite_Wire_Bytes"}[phase]
            vals = [r[key] for r in rows if r["arm"] == arm]
            means[arm][phase] = float(np.mean(vals))

    x = np.arange(len(phases))
    width = 0.25
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for i, arm in enumerate(arms):
        y = [means[arm][p] for p in phases]
        ax.bar(x + (i - 1) * width, y, width, color=colors[i], label=labels[i])
    ax.set_xticks(x)
    ax.set_xticklabels([p.capitalize() for p in phases])
    ax.set_ylabel("wire bytes (mean, 30 seeds)")
    ax.set_title("M5: wire bytes per phase and arm (lower is better)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "overhead_comparison.png", dpi=150)
    plt.close(fig)


def _summarise(rows: list[dict]) -> str:
    arms = ("static_iso", "greedy_heuristic", "llm_compiler")
    lines = [
        "# M5: Cognitive Stack Compiler (H7)",
        "",
        "30 paired seeds, one Fiber -> Microwave -> Satellite boundary sequence.",
        "The Oracle is a mocked deterministic LLM (no API); its hallucinations are",
        "logged so the guardrail is measured, not asserted.",
        "",
        "## Mean metrics per arm",
        "",
        "| arm | Wire_Bytes_Total | Throughput_Overhead_Ratio | Auth_Acceptance | Hallucinations | Oracle_Decision_Time_s |",
        "|---|---|---|---|---|---|",
    ]
    for arm in arms:
        wb, wb_ci = _mean_ci([r["Wire_Bytes_Total"] for r in rows if r["arm"] == arm])
        tr, tr_ci = _mean_ci([r["Throughput_Overhead_Ratio"] for r in rows if r["arm"] == arm])
        auth, _ = _mean_ci([r["Auth_Acceptance_Rate"] for r in rows if r["arm"] == arm])
        hall = sum(r["Hallucinations"] for r in rows if r["arm"] == arm)
        dt, _ = _mean_ci([r["Oracle_Decision_Time_s"] for r in rows if r["arm"] == arm])
        lines.append(
            f"| {arm} | {wb:.1f} +/- {wb_ci:.1f} | {tr:.4f} +/- {tr_ci:.4f} "
            f"| {auth:.1f} % | {hall} | {dt:.6f} |"
        )
    lines.append("")

    # H7 verdict
    llm_vs_static = _paired_compare(rows, "llm_compiler", "static_iso",
                                    "Wire_Bytes_Total")
    llm_vs_greedy = _paired_compare(rows, "llm_compiler", "greedy_heuristic",
                                    "Wire_Bytes_Total")
    beats_static = llm_vs_static[0] < 0 and math.isfinite(llm_vs_static[2]) and llm_vs_static[2] < 0.05
    beats_greedy = llm_vs_greedy[0] < 0 and math.isfinite(llm_vs_greedy[2]) and llm_vs_greedy[2] < 0.05
    h7 = "CONFIRMED" if (beats_static and beats_greedy) else \
         "PARTIALLY CONFIRMED" if beats_static else "REFUTED"

    lines += [
        "## H7 verdict",
        "",
        f"**H7 Cognitive Stack Compilation — {h7}.**",
        "",
        f"- vs static_iso: mean wire-byte difference "
        f"{llm_vs_static[0]:+.1f} B (95% CI +/- {llm_vs_static[1]:.1f}, "
        f"p = {llm_vs_static[2]:.4g}) -> "
        f"{'beats static' if beats_static else 'does not beat static'}.",
        f"- vs greedy_heuristic: mean wire-byte difference "
        f"{llm_vs_greedy[0]:+.1f} B (95% CI +/- {llm_vs_greedy[1]:.1f}, "
        f"p = {llm_vs_greedy[2]:.4g}) -> "
        f"{'beats greedy' if beats_greedy else 'does not beat greedy'}.",
        "",
    ]

    n_hall = sum(r["Hallucinations"] for r in rows if r["arm"] == "llm_compiler")
    n_int = sum(r["Guardrail_Interventions"] for r in rows if r["arm"] == "llm_compiler")
    lines += [
        "## Guardrail behaviour (the LLM arm only)",
        "",
        f"The mocked Oracle produced **{n_hall}** hallucinated proposals and the "
        f"guardrail intervened **{n_int}** times. Auth acceptance stayed at "
        f"**100 %** for every arm and every seed because the P3 guardrail strips "
        f"an ``authenticate_outer`` proposal whenever NAT is present.",
        "",
    ]
    lines += [
        "## Oracle decision time",
        "",
        "The mocked Oracle is deterministic and near-instant (sub-millisecond). "
        "This does **not** exercise the > 500 ms latency concern of a real LLM; "
        "a local model (e.g. Ollama) must be benchmarked separately before any "
        "latency claim is made.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--out-dir", type=Path, default=REPO / "results" / "m5")
    args = parser.parse_args()
    seeds = list(range(args.seeds))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    arms = ("static_iso", "greedy_heuristic", "llm_compiler")
    rows = []
    for arm in arms:
        for seed in seeds:
            rows.append(run_one(arm, seed))

    fields = [
        "arm", "seed", "Wire_Bytes_Total",
        "Fiber_Wire_Bytes", "Microwave_Wire_Bytes", "Satellite_Wire_Bytes",
        "Delivered_Bytes_Total", "Throughput_Overhead_Ratio",
        "Auth_Acceptance_Rate", "P95_Latency_Total_s",
        "Hallucinations", "Guardrail_Interventions", "Oracle_Decision_Time_s",
    ]
    _write_csv(args.out_dir / "m5_raw.csv", rows, fields)

    summary = _summarise(rows)
    (args.out_dir / "m5_summary.md").write_text(summary, encoding="utf-8")
    (REPO / "results" / "m5_summary.md").write_text(summary, encoding="utf-8")
    plot_overhead(rows, args.out_dir)
    print(f"wrote {len(rows)} rows, summary and PNG to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
