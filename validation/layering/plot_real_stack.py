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

"""Plots for the real-stack layering results (P8-P12).

Reads ``validation/layering/results/real_stack_observations.csv`` and writes two
figures into ``validation/layering/results/``:

  * ``real_stack_delivery.png`` -- P8a/P8b/P8c and P12 delivery (control vs NAT).
  * ``real_stack_wire_bytes.png`` -- P9/P10 measured vs predicted wire bytes.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
CSV = HERE / "results" / "real_stack_observations.csv"


def _r(x: int) -> int:
    return 16 * math.ceil(x / 16)


def _predicted(scenario: str, policy: str) -> int | None:
    # policy strings: WG_inner_Lxx (P9), YtoW_Lxx, WtoY_Lxx (P10)
    if "_L" not in policy:
        return None
    l = int(policy.split("_L")[1])
    if scenario == "P9":
        return 60 + _r(l)
    if scenario == "P10" and policy.startswith("YtoW"):
        return 60 + _r(l + 20)
    if scenario == "P10" and policy.startswith("WtoY"):
        return 80 + _r(l)
    return None


def _delivery_plot(rows: list[dict], out: Path) -> None:
    order = [
        ("P8a", "AH_tunnel_control", "P8a control"),
        ("P8a", "AH_tunnel_nat", "P8a NAT"),
        ("P8b", "ESP_tunnel_control", "P8b control"),
        ("P8b", "ESP_tunnel_nat", "P8b NAT"),
        ("P8c", "WG_control", "P8c control"),
        ("P8c", "WG_nat", "P8c NAT"),
        ("P12", "control", "P12 control"),
        ("P12", "nat_csum", "P12 NAT+csum"),
        ("P12", "nat_nocsum", "P12 NAT+nocsum"),
    ]
    vals = []
    labels = []
    colors = []
    for scen, pol, lab in order:
        got = [r for r in rows
               if r["scenario"] == scen and r["policy"] == pol
               and r["metric"] == "delivery_percent"]
        vals.append(float(got[0]["value"]) if got else 0.0)
        labels.append(lab)
        colors.append("#27ae60" if (got and float(got[0]["value"]) >= 99)
                      else "#c0392b")
    fig, ax = plt.subplots(figsize=(9, 4.4))
    bars = ax.bar(range(len(vals)), vals, color=colors)
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylim(0, 110)
    ax.set_ylabel("delivery (%)")
    ax.set_title("Real-stack layering: P8/P12 delivery (control vs NAT)")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}%",
                ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _wire_plot(rows: list[dict], out: Path) -> None:
    pts = []
    for r in rows:
        if r["metric"] != "wire_bytes":
            continue
        p = _predicted(r["scenario"], r["policy"])
        if p is None:
            continue
        pts.append((p, float(r["value"]), f'{r["scenario"]} {r["policy"]}'))
    fig, ax = plt.subplots(figsize=(6.5, 5.2))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ax.scatter(xs, ys, s=32, color="#1f6feb", zorder=3)
    lo, hi = min(xs + ys) - 10, max(xs + ys) + 10
    ax.plot([lo, hi], [lo, hi], ls="--", lw=0.9, color="#999999", label="y = x")
    ax.set_xlabel("predicted wire bytes")
    ax.set_ylabel("measured wire bytes")
    ax.set_title("Real-stack layering: P9/P10 measured vs predicted")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main() -> int:
    with CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    _delivery_plot(rows, HERE / "results" / "real_stack_delivery.png")
    _wire_plot(rows, HERE / "results" / "real_stack_wire_bytes.png")
    print(f"wrote 2 figures from {CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
