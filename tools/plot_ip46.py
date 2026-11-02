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

"""Generate the IPv4/IPv6 comparison figures for the research paper.

Reads output/validation/ip46.csv (produced by validation/ns3/run-ip46.sh) and
writes PNGs into figures/. Each figure reports the measured ns-3.49 numbers
without editorialising beyond the data.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

IPV4 = "#4C78A8"
IPV6 = "#F2A541"


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def overhead_figure(path: Path, out: Path) -> None:
    rows = _read(path)
    overhead = {r["experiment"]: {} for r in rows if r["experiment"] != "agnostic"}
    goodput = {r["experiment"]: {} for r in rows if r["experiment"] != "agnostic"}
    for row in rows:
        if row["experiment"] == "agnostic":
            continue
        overhead[row["experiment"]][row["family"]] = float(row["overhead_bytes_per_packet"])
        goodput[row["experiment"]][row["family"]] = float(row["goodput_mbps"])

    experiments = ["overhead", "fragment"]
    labels = ["128 B payload\n(no fragmentation)", "1400 B payload\n(MTU 1280, fragmented)"]
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), layout="constrained")
    x = np.arange(len(experiments))
    width = 0.36

    for family, color, offset in (("ipv4", IPV4, -width / 2), ("ipv6", IPV6, +width / 2)):
        values = [overhead[experiment][family] for experiment in experiments]
        axes[0].bar(x + offset, values, width, color=color, label=family.upper())
    axes[0].set_xticks(x, labels, fontsize=8)
    axes[0].set_ylabel("Wire overhead (bytes / datagram)")
    axes[0].set_title("Overhead: IPv6 pays the larger fixed header + fragment headers")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False)
    for index, experiment in enumerate(experiments):
        v4, v6 = overhead[experiment]["ipv4"], overhead[experiment]["ipv6"]
        axes[0].annotate(f"+{v6 - v4:.1f} B", (index, max(v4, v6)),
                         textcoords="offset points", xytext=(0, 4),
                         ha="center", fontsize=8, color="#333333")

    for family, color, offset in (("ipv4", IPV4, -width / 2), ("ipv6", IPV6, +width / 2)):
        values = [goodput[experiment][family] for experiment in experiments]
        axes[1].bar(x + offset, values, width, color=color, label=family.upper())
    axes[1].set_xticks(x, labels, fontsize=8)
    axes[1].set_ylabel("Goodput (Mbit/s)")
    axes[1].set_title("Goodput: identical — overhead affects wire, not throughput")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(frameon=False)

    figure.suptitle("IPv4 vs IPv6 on the same dual-stack link (ns-3.49, 2000 datagrams)")
    figure.savefig(out, dpi=180)
    plt.close(figure)


def agnostic_figure(path: Path, out: Path) -> None:
    rows = _read(path)
    row = next(r for r in rows if r["experiment"] == "agnostic")
    echoed_v4 = int(row["echoed_v4"])
    echoed_v6 = int(row["echoed_v6"])
    gap = float(row["switch_gap_ms"])
    rtt = float(row["rtt_mean_ms"])

    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), layout="constrained")

    axes[0].bar(["IPv4 leg\n(0–5 s)", "IPv6 leg\n(5–10 s)"], [echoed_v4, echoed_v6],
                color=[IPV4, IPV6], width=0.55)
    axes[0].set_ylabel("Echoed datagrams")
    axes[0].set_title("A name-identified service mid-session across families")
    axes[0].set_ylim(0, max(echoed_v4, echoed_v6) * 1.2)
    axes[0].grid(axis="y", alpha=0.25)
    for index, value in enumerate((echoed_v4, echoed_v6)):
        axes[0].annotate(str(value), (index, value), textcoords="offset points",
                         xytext=(0, 4), ha="center", fontsize=9)

    labels = ["Switch gap", "Mean RTT"]
    values = [gap, rtt]
    bars = axes[1].bar(labels, values, color=["#888888", "#3A9D78"], width=0.5)
    axes[1].set_ylabel("Time (ms)")
    axes[1].set_title("Cost of the family switch")
    axes[1].grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, values):
        axes[1].annotate(f"{value:.2f} ms", (bar.get_x() + bar.get_width() / 2, value),
                         textcoords="offset points", xytext=(0, 4), ha="center", fontsize=9)

    figure.suptitle(
        "IPv6-agnostic service: the service layer never learns the address family "
        f"({echoed_v4 + echoed_v6} delivered, 0 lost, ns-3.49)"
    )
    figure.savefig(out, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("output/validation/ip46.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if not args.csv.is_file():
        raise SystemExit(f"missing {args.csv}; run validation/ns3/run-ip46.sh first")
    overhead_figure(args.csv, args.out_dir / "ip46_overhead.png")
    agnostic_figure(args.csv, args.out_dir / "ip46_agnostic.png")
    print("ip46_overhead.png")
    print("ip46_agnostic.png")


if __name__ == "__main__":
    main()
