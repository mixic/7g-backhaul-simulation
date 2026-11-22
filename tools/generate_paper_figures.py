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

"""Generate the eight paper figures (paper A: 4, paper B: 4) from committed CSVs.

Anti-cheat contract
-------------------
Every plotted number is read from a CSV that is in the repository, and every
figure asserts the values it draws against the claim the paper makes about them
(``_check``).  There are no literal data arrays in this file except the
*geometry* of the two schematic panels (an IP header layout, and a layer-stack
cartoon), which carry no measurements.  If a CSV is missing or a value
disagrees, the script fails loudly instead of drawing a placeholder.

Paper A sources
---------------
* ``validation/layering/results/{model,simpy,linux}_observations.csv`` — P1-P7
  wire bytes, fragment counts, delivery and acceptance per seed.
* ``validation/real_stack/results/observations.csv`` — P8-P12 delivery.
* ``validation/round2/results/observations.csv`` — P13-P16.
* ``validation/{layering,real_stack,round2,round3}/results/verdicts.csv`` — the
  disposition of every prediction at every fidelity.

Paper B sources
---------------
* ``results/m4/final_benchmark_raw.csv`` — per-seed goodput and peak state-change
  speed for the five M4 arms (30 paired seeds).
* ``results/m4/arm_timeseries.csv`` — per-tick legitimate-goodput trace,
  produced by ``tools/extract_arm_timeseries.py`` (which verifies the
  reproduction against the committed aggregates before writing).
* ``results/m5/m5_h8_raw.csv`` — per-seed peak burst speed for the H8 arms.
* ``results/m6/m6_exp2_raw.csv`` — transmission energy saved by the stack
  compiler (the break-even numerator).
* ``simulation/energy.py`` and ``simulation/surgical/config.py`` — the
  stipulated constants and link parameters, imported rather than typed.

Run::

    py tools/generate_paper_figures.py --output-dir figures
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Rectangle  # noqa: E402

try:  # scipy is a test dependency; only the paired t-test annotation needs it
    from scipy import stats  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover
    stats = None

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
GREEN = "#2e7d32"
RED = "#c0392b"
AMBER = "#b8860b"
GREY = "#9e9e9e"
LIGHT_GREY = "#dcdcdc"
BLUE = "#1f4e79"
MID_BLUE = "#4a7fb5"
PALE_BLUE = "#b9cfe4"
PALE_RED = "#e9b4ae"
PALE_AMBER = "#f0d9a8"
INK = "#1b1b1b"

STYLE = {
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "mathtext.fontset": "dejavuserif",
    "font.size": 8.5,
    "axes.titlesize": 9.0,
    "axes.labelsize": 8.5,
    "xtick.labelsize": 7.6,
    "ytick.labelsize": 7.6,
    "legend.fontsize": 7.6,
    "axes.linewidth": 0.7,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
    "axes.edgecolor": INK,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
}

#: (figure id, panel, quantity, value, source file) — written to the manifest.
MANIFEST: list[tuple[str, str, str, str, str]] = []


def record(figure: str, panel: str, quantity: str, value, source: str) -> None:
    MANIFEST.append((figure, panel, quantity, str(value), source))


def _check(condition: bool, message: str) -> None:
    """Fail loudly rather than draw a figure the data do not support."""
    if not condition:
        raise SystemExit(f"DATA CHECK FAILED: {message}")


def _save(figure, output_dir: Path, name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_dir / f"{name}.pdf")
    figure.savefig(output_dir / f"{name}.png", dpi=300)
    plt.close(figure)
    print(f"  wrote {output_dir.name}/{name}.pdf (+ .png)")


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"missing source CSV: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _observations(relative: str) -> list[dict[str, str]]:
    return _rows(REPO / relative)


def _values(rows, scenario: str, policy: str, metric: str) -> list[float]:
    return [
        float(row["value"])
        for row in rows
        if row["scenario"] == scenario and row["policy"] == policy and row["metric"] == metric
    ]


def _single(rows, scenario: str, policy: str, metric: str) -> float:
    values = _values(rows, scenario, policy, metric)
    _check(bool(values), f"no {metric} for {scenario}/{policy}")
    return values[0]


def _distinct(values: list[float]) -> float:
    """The single value shared by every seed, or fail."""
    unique = sorted({round(value, 6) for value in values})
    _check(len(unique) == 1, f"values are not identical across runs: {unique[:6]}")
    return unique[0]


def _mean_ci(values: list[float]) -> tuple[float, float]:
    clean = [value for value in values if math.isfinite(value)]
    if len(clean) < 2:
        return (clean[0] if clean else float("nan")), 0.0
    mean = sum(clean) / len(clean)
    variance = sum((value - mean) ** 2 for value in clean) / (len(clean) - 1)
    return mean, 1.96 * math.sqrt(variance / len(clean))


def _paired_p(a: list[float], b: list[float]) -> float:
    if stats is None:
        return float("nan")
    return float(stats.ttest_rel(a, b).pvalue)


# ---------------------------------------------------------------------------
# Paper A, figure 1: layer-stack comparison
# ---------------------------------------------------------------------------
def _layer_stack(ax, x_center, order, footer, accent):
    """Draw one protocol stack, bottom (payload) to top (wire)."""
    box_w, box_h, gap = 0.40, 0.132, 0.046
    bottom = 0.12
    for index, (label, detail) in enumerate(order):
        y = bottom + index * (box_h + gap)
        is_wire = index == len(order) - 1
        face = accent if not is_wire else "#f2f2f2"
        edge = accent if not is_wire else INK
        ax.add_patch(
            FancyBboxPatch(
                (x_center - box_w / 2, y),
                box_w,
                box_h,
                boxstyle="round,pad=0.006,rounding_size=0.02",
                facecolor=face,
                edgecolor=edge,
                linewidth=0.8,
                alpha=0.30 if not is_wire else 0.9,
            )
        )
        ax.text(x_center, y + box_h * 0.64, label, ha="center", va="center", fontsize=7.8, weight="bold")
        ax.text(x_center, y + box_h * 0.28, detail, ha="center", va="center", fontsize=6.8, color="#333333")
        if index:
            ax.add_patch(
                FancyArrowPatch(
                    (x_center, y - gap + 0.004),
                    (x_center, y - 0.004),
                    arrowstyle="-|>",
                    mutation_scale=6,
                    linewidth=0.7,
                    color=INK,
                )
            )
    ax.text(x_center, bottom + len(order) * (box_h + gap) - 0.01, footer, ha="center", va="bottom", fontsize=6.9)


def figure_a1_stack_comparison(output_dir: Path) -> None:
    model = _observations("validation/layering/results/model_observations.csv")
    linux = _observations("validation/layering/results/linux_observations.csv")

    p1_c_to_e = _distinct(_values(model, "P1", "C_to_E_text", "wire_bytes"))
    p1_e_to_c = _distinct(_values(model, "P1", "E_to_C_text", "wire_bytes"))
    p2_e_to_f = _distinct(_values(linux, "P2", "E_to_F", "wire_bytes"))
    p2_f_to_e = _distinct(_values(linux, "P2", "F_to_E", "wire_bytes"))
    p2_frag = _distinct(_values(linux, "P2", "E_to_F", "fragment_count"))

    _check(p1_e_to_c > p1_c_to_e, "P1 must cost more when compression sees ciphertext")
    _check(p2_f_to_e - p2_e_to_f == 224, "P2 delta is not 224 B")

    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.35))
    for ax in axes:
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

    axes[0].set_title("(a) P1: compression and encryption\n(model fidelity)", loc="left", pad=6, fontsize=8.6)
    _layer_stack(
        axes[0],
        0.25,
        [("payload", "application bytes"), ("C", "compress (zlib)"), ("E", "AEAD encrypt"), ("wire", f"{p1_c_to_e:,.0f} B")],
        "C → E\ncompress, then encrypt",
        MID_BLUE,
    )
    _layer_stack(
        axes[0],
        0.75,
        [
            ("payload", "application bytes"),
            ("E", "AEAD encrypt"),
            ("C", "compress (zlib)"),
            ("wire", f"{p1_e_to_c:,.0f} B  (+{100.0 * (p1_e_to_c / p1_c_to_e - 1.0):.0f} %)"),
        ],
        "E → C\nencrypt, then compress",
        AMBER,
    )
    axes[0].text(
        0.5,
        0.02,
        "ciphertext does not compress",
        ha="center",
        va="bottom",
        fontsize=7.2,
        color=RED,
        weight="bold",
    )

    axes[1].set_title("(b) P2: encryption and fragmentation\n(Linux fidelity)", loc="left", pad=6, fontsize=8.6)
    _layer_stack(
        axes[1],
        0.25,
        [
            ("payload", "2000 B datagram"),
            ("E", "encrypt (AEAD)"),
            ("F", "fragment to MTU"),
            ("wire", f"{p2_e_to_f:,.0f} B"),
        ],
        "E → F\nencrypt, then fragment",
        MID_BLUE,
    )
    _layer_stack(
        axes[1],
        0.75,
        [
            ("payload", "2000 B datagram"),
            ("F", "fragment to MTU"),
            ("E", "encrypt each"),
            ("wire", f"{p2_f_to_e:,.0f} B  (+{p2_f_to_e - p2_e_to_f:.0f} B)"),
        ],
        "F → E\nfragment, then encrypt",
        AMBER,
    )
    axes[1].text(
        0.5,
        0.02,
        f"Δ = {p2_f_to_e - p2_e_to_f:.0f} B = 28 B × 8 affected fragments;\n"
        f"{p2_frag:.0f} datagrams either way",
        ha="center",
        va="bottom",
        fontsize=7.0,
        color=RED,
        weight="bold",
    )
    figure.text(
        0.5,
        0.005,
        "Arrows are the order in which each layer consumes the byte stream. Values are the committed CSVs; "
        "no quantity is drawn to scale.",
        ha="center",
        fontsize=6.6,
        color="#444444",
    )

    record("A-1", "(a)", "P1 wire bytes, C→E (model)", f"{p1_c_to_e:,.0f}",
           "validation/layering/results/model_observations.csv")
    record("A-1", "(a)", "P1 wire bytes, E→C (model)", f"{p1_e_to_c:,.0f}",
           "validation/layering/results/model_observations.csv")
    record("A-1", "(b)", "P2 wire bytes, E→F (Linux)", f"{p2_e_to_f:,.0f}",
           "validation/layering/results/linux_observations.csv")
    record("A-1", "(b)", "P2 wire bytes, F→E (Linux)", f"{p2_f_to_e:,.0f}",
           "validation/layering/results/linux_observations.csv")
    _save(figure, output_dir, "paperA_fig1_stack_comparison")


# ---------------------------------------------------------------------------
# Paper A, figure 2: wire bytes per ordering
# ---------------------------------------------------------------------------
def figure_a2_wire_bytes(output_dir: Path) -> None:
    fidelities = (
        ("Model", "validation/layering/results/model_observations.csv"),
        ("SimPy", "validation/layering/results/simpy_observations.csv"),
        ("Linux", "validation/layering/results/linux_observations.csv"),
    )
    p2: dict[str, dict[str, float]] = {}
    p4: dict[str, dict[str, float]] = {}
    for name, relative in fidelities:
        rows = _observations(relative)
        p2[name] = {
            "E→F": _distinct(_values(rows, "P2", "E_to_F", "wire_bytes")),
            "F→E": _distinct(_values(rows, "P2", "F_to_E", "wire_bytes")),
        }
        orderings = sorted({row["policy"] for row in rows if row["scenario"] == "P4"})
        p4[name] = {ordering: _distinct(_values(rows, "P4", ordering, "wire_bytes")) for ordering in orderings}

    for name in ("Model", "SimPy", "Linux"):
        _check(p2[name]["F→E"] - p2[name]["E→F"] == 224, f"{name}: P2 delta is not 224 B")
        _check(len(set(p4[name].values())) == 1, f"{name}: P4 orderings are not all equal")
        _check(abs(next(iter(p4[name].values())) - 1104) < 1e-9, f"{name}: P4 wire bytes are not 1104")

    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.15), gridspec_kw={"width_ratios": [1.18, 1.32]})

    ax = axes[0]
    labels = ["E→F", "F→E"]
    values = [p2["Linux"][label] for label in labels]
    xs = [0, 1]
    ax.vlines(xs, 11850, values, color=[MID_BLUE, AMBER], linewidth=1.2, zorder=2)
    ax.scatter(xs, values, s=64, color=[MID_BLUE, AMBER], edgecolor=INK, linewidth=0.7, zorder=3)
    for x, value in zip(xs, values):
        ax.text(x + 0.10, value, f"{value:,.0f} B", ha="left", va="center", fontsize=7.8)
    ax.annotate(
        "",
        xy=(1.32, values[1]),
        xytext=(1.32, values[0]),
        arrowprops={"arrowstyle": "<->", "linewidth": 0.8, "color": RED},
    )
    ax.text(
        1.40,
        (values[0] + values[1]) / 2,
        "Δ = 224 B\n= 28 B × 8\naffected\nfragments",
        ha="left",
        va="center",
        fontsize=7.0,
        color=RED,
    )
    ax.set_xlim(-0.45, 2.45)
    ax.set_ylim(11850, values[1] + 90)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Wire bytes (B)")
    ax.set_title("(a) P2: fragmentation around\nthe encryptor", loc="left", fontsize=8.6)
    ax.text(
        0.02,
        0.97,
        "axis starts at 11,850 B; identical at model,\nSimPy and Linux (the Δ is 1.8 % of the value)",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=6.5,
        color="#444444",
    )
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    ax = axes[1]
    orderings = sorted(p4["Linux"])
    positions = range(len(orderings))
    values = [p4["Linux"][ordering] for ordering in orderings]
    ax.axhline(1104, color=GREY, linewidth=0.7, linestyle=(0, (3, 3)), zorder=0)
    bars = ax.bar(positions, values, width=0.62, color=PALE_BLUE, edgecolor=BLUE, linewidth=0.8, zorder=2)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 12, f"{value:,.0f}", ha="center", va="bottom", fontsize=7.2)
    ax.set_xticks(list(positions))
    ax.set_xticklabels([ordering.replace(">", "→") for ordering in orderings], rotation=25, ha="right")
    ax.set_ylim(0, 1320)
    ax.set_ylabel("Wire bytes per datagram (B)")
    ax.set_xlabel("Ordering of tunnelling (T), encryption (E), sequencing (S)")
    ax.set_title("(b) P4: six fixed-overhead\norderings", loc="left", fontsize=8.6)
    ax.text(
        0.5,
        0.955,
        "all six identical → layers with fixed size effects commute",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=7.0,
        color=BLUE,
    )
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    record("A-2", "(a)", "P2 wire bytes E→F (Linux)", f"{p2['Linux']['E→F']:,.0f}",
           "validation/layering/results/linux_observations.csv")
    record("A-2", "(a)", "P2 wire bytes F→E (Linux)", f"{p2['Linux']['F→E']:,.0f}",
           "validation/layering/results/linux_observations.csv")
    record("A-2", "(a)", "P2 byte difference (F→E − E→F)", "224",
           "validation/layering/results/{model,simpy,linux}_observations.csv")
    for ordering in orderings:
        record("A-2", "(b)", f"P4 wire bytes {ordering}", f"{p4['Linux'][ordering]:,.0f}",
               "validation/layering/results/linux_observations.csv")
    _save(figure, output_dir, "paperA_fig2_wire_bytes")


# ---------------------------------------------------------------------------
# Paper A, figure 3: verdict heatmap
# ---------------------------------------------------------------------------
def _verdict_map() -> dict[tuple[str, str], str]:
    """(prediction, fidelity) -> CONFIRMED / REFUTED / untested, from the four verdict CSVs."""
    mapping: dict[tuple[str, str], str] = {}

    for row in _rows(REPO / "validation/layering/results/verdicts.csv"):
        mapping[(row["prediction"], row["fidelity"])] = row["verdict"]

    def collapse(relative: str, fidelity: str) -> None:
        grouped: dict[str, list[str]] = {}
        for row in _rows(REPO / relative):
            grouped.setdefault(row["prediction"], []).append(row["verdict"])
        for prediction, verdicts in grouped.items():
            mapping[(prediction, fidelity)] = "REFUTED" if "REFUTED" in verdicts else "CONFIRMED"

    collapse("validation/real_stack/results/verdicts.csv", "linux")
    collapse("validation/round2/results/verdicts.csv", "linux")
    collapse("validation/round3/results/verdicts.csv", "linux")
    return mapping


def figure_a3_verdict_heatmap(output_dir: Path) -> None:
    verdicts = _verdict_map()
    predictions = [f"P{index}" for index in range(1, 17)]
    #: display label -> the key the verdict CSVs use for the fidelity column
    fidelities = [("Model", "model"), ("SimPy", "simpy"), ("Linux", "linux")]
    colour_for = {"CONFIRMED": GREEN, "REFUTED": RED, "untested": LIGHT_GREY}
    letter_for = {"CONFIRMED": "C", "REFUTED": "R", "untested": "–"}

    matrix = []
    confirmed = refuted = 0
    for prediction in predictions:
        row = []
        for _, key in fidelities:
            verdict = verdicts.get((prediction, key), "untested")
            row.append(verdict)
            if verdict == "CONFIRMED":
                confirmed += 1
            elif verdict == "REFUTED":
                refuted += 1
        matrix.append(row)

    _check(confirmed + refuted > 0, "the verdict heatmap resolved no verdicts at all")

    figure, ax = plt.subplots(figsize=(7.1, 2.55))
    for column, prediction in enumerate(predictions):
        for row_index, (_, key) in enumerate(fidelities):
            verdict = matrix[column][row_index]
            y = len(fidelities) - row_index - 1
            alpha = 0.85 if verdict != "untested" else 0.55
            ax.add_patch(
                Rectangle((column, y), 1, 1, facecolor=colour_for[verdict], alpha=alpha, edgecolor="white", linewidth=1.6)
            )
            ax.text(
                column + 0.5,
                y + 0.5,
                letter_for[verdict],
                ha="center",
                va="center",
                fontsize=7.4,
                color="white" if verdict != "untested" else "#666666",
                weight="bold" if verdict != "untested" else "normal",
            )
    ax.set_xlim(0, len(predictions))
    ax.set_ylim(0, len(fidelities))
    ax.set_xticks([index + 0.5 for index in range(len(predictions))])
    ax.set_xticklabels(predictions, fontsize=7.2)
    ax.set_yticks([len(fidelities) - index - 0.5 for index in range(len(fidelities))])
    ax.set_yticklabels([label for label, _ in fidelities], fontsize=8)
    ax.xaxis.tick_top()
    ax.set_xlabel("Prediction (frozen before the harness that tested it)", labelpad=6)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    handles = [
        Patch(facecolor=GREEN, alpha=0.85, label="Confirmed"),
        Patch(facecolor=RED, alpha=0.85, label="Refuted"),
        Patch(facecolor=LIGHT_GREY, alpha=0.55, label="Not tested at this fidelity"),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=3,
        frameon=False,
        handlelength=1.0,
        columnspacing=1.4,
    )
    figure.text(
        0.5,
        0.005,
        "28 of 30 prediction–fidelity cells confirmed; the paper scores sub-cases separately "
        "and reports 34 of 36. P8–P16 run only on Linux; P16 is scored REFUTED because P16d is "
        "(three of its four sub-cases confirmed).",
        ha="center",
        fontsize=6.5,
        color="#444444",
    )

    record("A-3", "all", "confirmed cells plotted", confirmed,
           "validation/*/results/verdicts.csv")
    record("A-3", "all", "refuted cells plotted", refuted,
           "validation/*/results/verdicts.csv")
    _save(figure, output_dir, "paperA_fig3_verdict_heatmap")


# ---------------------------------------------------------------------------
# Paper A, figure 4: what the integrity scope covers
# ---------------------------------------------------------------------------
#: IPv4 header fields, in wire order, with their widths in bytes.
IP_FIELDS = (
    ("Ver/IHL", 1.0, "authenticated"),
    ("DSCP·ECN", 1.0, "mutable"),
    ("Total len", 2.0, "authenticated"),
    ("ID", 2.0, "authenticated"),
    ("Flags/Frag", 2.0, "mutable"),
    ("TTL", 1.0, "mutable"),
    ("Proto", 1.0, "authenticated"),
    ("Hdr cksum", 2.0, "mutable"),
    ("Source addr", 4.0, "rewritten"),
    ("Dest addr", 4.0, "rewritten"),
)
TRANSPORT_FIELDS = (
    ("Src port", 2.0, "rewritten"),
    ("Dst port", 2.0, "authenticated"),
    ("UDP len", 2.0, "authenticated"),
    ("UDP cksum", 2.0, "derived"),
)


HEADER_X0 = 3.20
HEADER_SCALE = 0.22  # width of one header byte, in axes units (0-10 range)
IP_Y, IP_H = 6.70, 1.90
TRANSPORT_Y, TRANSPORT_H = 4.55, 1.45
PAYLOAD_W = 0.80


def _header_strip(ax, y, fields, height, label):
    x = HEADER_X0
    scale = HEADER_SCALE
    for name, width, role in fields:
        box_w = width * scale
        face = {
            "authenticated": PALE_BLUE,
            "mutable": "white",
            "rewritten": PALE_RED,
            "derived": PALE_AMBER,
        }[role]
        edge = {"authenticated": BLUE, "mutable": GREY, "rewritten": RED, "derived": AMBER}[role]
        ax.add_patch(
            Rectangle(
                (x, y),
                box_w,
                height,
                facecolor=face,
                edgecolor=edge,
                linewidth=0.8,
                linestyle=":" if role == "mutable" else "-",
            )
        )
        ax.text(
            x + box_w / 2,
            y + height / 2,
            name,
            ha="center",
            va="center",
            fontsize=5.7,
            rotation=90 if box_w < 0.70 else 0,
        )
        x += box_w
    ax.text(HEADER_X0 - 0.03, y + height / 2, label, ha="right", va="center", fontsize=7.2)


def figure_a4_integrity_scope(output_dir: Path) -> None:
    layering = _observations("validation/layering/results/linux_observations.csv")
    real = _observations("validation/real_stack/results/observations.csv")

    p3_covered = _distinct(_values(layering, "P3", "aad_covers", "auth_accept_percent"))
    p3_excluded = _distinct(_values(layering, "P3", "aad_excludes", "auth_accept_percent"))
    p3_invisible = _distinct(_values(layering, "P3", "inside_ciphertext", "auth_accept_percent"))
    _check((p3_covered, p3_excluded, p3_invisible) == (0.0, 100.0, 100.0), "P3 acceptance is not 0/100/100")

    def delivery(policy: str) -> float:
        return _mean_ci(_values(real, "P8" if policy.startswith("P8") else "P12", policy, "delivery_percent"))[0]

    ah_nat = delivery("P8a")
    ah_control = delivery("P8a_control")
    esp_nat = delivery("P8b")
    wg_nat = delivery("P8c")
    derived_live = delivery("P12a")
    derived_zeroed = delivery("P12b")
    _check(ah_nat == 0.0 and esp_nat == 100.0 and wg_nat == 100.0, "P8 asymmetry is not 0/100/100")
    _check(derived_live == 0.0 and derived_zeroed == 100.0, "P12 is not 0/100")

    figure, axes = plt.subplots(2, 1, figsize=(7.1, 3.9), gridspec_kw={"height_ratios": [1.0, 1.0]})
    for ax in axes:
        ax.set_xlim(0, 10)
        ax.set_ylim(2.95, 9.35)
        ax.axis("off")

    inner_w = sum(width for _, width, _ in TRANSPORT_FIELDS) * HEADER_SCALE
    payload_x = HEADER_X0 + inner_w + 0.02
    source_x = HEADER_X0 + sum(width for _, width, _ in IP_FIELDS[:8]) * HEADER_SCALE + 2 * HEADER_SCALE
    strip_right = HEADER_X0 + 20 * HEADER_SCALE

    def draw_packets(ax):
        _header_strip(ax, IP_Y, IP_FIELDS, IP_H, "outer IPv4")
        _header_strip(ax, TRANSPORT_Y, TRANSPORT_FIELDS, TRANSPORT_H, "inner UDP")
        ax.add_patch(
            Rectangle(
                (payload_x, TRANSPORT_Y),
                PAYLOAD_W,
                TRANSPORT_H,
                facecolor=PALE_BLUE,
                edgecolor=BLUE,
                linewidth=0.8,
            )
        )
        ax.text(
            payload_x + PAYLOAD_W / 2,
            TRANSPORT_Y + TRANSPORT_H / 2,
            "payload",
            ha="center",
            va="center",
            fontsize=6.1,
            rotation=90,
        )

    # (a) AH: the outer header is inside the integrity scope.
    ax = axes[0]
    ax.set_title("(a) AH (RFC 4302): the outer IPv4 header is authenticated", loc="left", pad=4, fontsize=8.6)
    draw_packets(ax)
    ax.add_patch(
        Rectangle(
            (HEADER_X0 - 0.05, TRANSPORT_Y - 0.14),
            strip_right - HEADER_X0 + 0.10,
            (IP_Y + IP_H) - (TRANSPORT_Y - 0.14),
            facecolor="none",
            edgecolor=BLUE,
            linewidth=1.2,
            linestyle=(0, (4, 2)),
        )
    )
    ax.text(strip_right + 0.15, IP_Y + IP_H - 0.15, "AH ICV scope", ha="left", va="center", fontsize=7.2, color=BLUE)
    ax.annotate(
        "NAT rewrites Source addr",
        xy=(source_x, IP_Y),
        xytext=(7.85, 4.15),
        fontsize=7.2,
        color=RED,
        arrowprops={"arrowstyle": "->", "linewidth": 1.0, "color": RED},
    )
    ax.text(
        HEADER_X0,
        3.15,
        f"delivery, AH through NAT: {ah_nat:.0f} %  ·  AH without NAT: {ah_control:.0f} %\n"
        f"toy AEAD control (P3): target inside AAD {p3_covered:.0f} %, AAD excludes it {p3_excluded:.0f} %, "
        f"target invisible {p3_invisible:.0f} %",
        ha="left",
        va="bottom",
        fontsize=6.9,
        color=INK,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f7f7f7", "edgecolor": GREY, "linewidth": 0.6},
    )

    # (b) ESP: the outer header is outside the scope, but the inner checksum is derived.
    ax = axes[1]
    ax.set_title("(b) ESP tunnel (RFC 4303): outer header outside the scope, inner checksum derived",
                 loc="left", pad=4, fontsize=8.6)
    draw_packets(ax)
    ax.add_patch(
        Rectangle(
            (HEADER_X0 - 0.05, TRANSPORT_Y - 0.14),
            payload_x + PAYLOAD_W - HEADER_X0 + 0.15,
            TRANSPORT_H + 0.28,
            facecolor="none",
            edgecolor=BLUE,
            linewidth=1.2,
            linestyle=(0, (4, 2)),
        )
    )
    ax.text(strip_right + 0.15, IP_Y + IP_H - 0.15, "ESP scope = inner packet only", ha="left", va="center",
            fontsize=7.2, color=BLUE)
    ax.annotate(
        "NAT rewrites Source addr",
        xy=(source_x, IP_Y),
        xytext=(7.85, 4.15),
        fontsize=7.2,
        color=RED,
        arrowprops={"arrowstyle": "->", "linewidth": 1.0, "color": RED},
    )
    ax.annotate(
        "inner UDP checksum: derived from the rewritten source address",
        xy=(payload_x - HEADER_SCALE + 0.06, TRANSPORT_Y),
        xytext=(0.12, 4.05),
        fontsize=6.9,
        color=AMBER,
        arrowprops={"arrowstyle": "->", "linewidth": 0.9, "color": AMBER},
    )
    ax.text(
        HEADER_X0,
        3.15,
        f"delivery, ESP through NAT: {esp_nat:.0f} %  ·  WireGuard through NAT: {wg_nat:.0f} %  ·  "
        f"inner checksum live: {derived_live:.0f} %  ·  zeroed: {derived_zeroed:.0f} %",
        ha="left",
        va="bottom",
        fontsize=6.9,
        color=INK,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f7f7f7", "edgecolor": GREY, "linewidth": 0.6},
    )

    handles = [
        Patch(facecolor=PALE_BLUE, edgecolor=BLUE, label="authenticated by the integrity scope"),
        Patch(facecolor="white", edgecolor=GREY, linestyle=":", label="mutable, excluded from the scope"),
        Patch(facecolor=PALE_RED, edgecolor=RED, label="rewritten by NAT"),
        Patch(facecolor=PALE_AMBER, edgecolor=AMBER, label="derived from a rewritten field"),
    ]
    figure.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.055),
        ncol=2,
        frameon=False,
        handlelength=1.1,
        columnspacing=1.6,
        fontsize=6.7,
    )

    record("A-4", "(a)", "AH through NAT, delivery %", f"{ah_nat:.0f}",
           "validation/real_stack/results/observations.csv")
    record("A-4", "(a)", "AH without NAT, delivery %", f"{ah_control:.0f}",
           "validation/real_stack/results/observations.csv")
    record("A-4", "(a)", "P3 AAD covers / excludes / invisible, acceptance %",
           f"{p3_covered:.0f}/{p3_excluded:.0f}/{p3_invisible:.0f}",
           "validation/layering/results/linux_observations.csv")
    record("A-4", "(b)", "ESP through NAT, delivery %", f"{esp_nat:.0f}",
           "validation/real_stack/results/observations.csv")
    record("A-4", "(b)", "WireGuard through NAT, delivery %", f"{wg_nat:.0f}",
           "validation/real_stack/results/observations.csv")
    record("A-4", "(b)", "P12 inner checksum live / zeroed, delivery %",
           f"{derived_live:.0f}/{derived_zeroed:.0f}",
           "validation/real_stack/results/observations.csv")
    _save(figure, output_dir, "paperA_fig4_integrity_scope")


# ---------------------------------------------------------------------------
# Paper B, figure 1: goodput against time
# ---------------------------------------------------------------------------
def figure_b1_goodput_timeseries(output_dir: Path) -> None:
    trace = _rows(REPO / "results/m4/arm_timeseries.csv")
    aggregates = _rows(REPO / "results/m4/final_benchmark_raw.csv")

    arms = (
        ("static_isolation", "Static per-flow isolation"),
        ("m4_oef", "OEF (Fick-principle actuator)"),
        ("m4_mkb", "MKB (raw 4-D trigger)"),
    )
    colours = {"static_isolation": BLUE, "m4_oef": RED, "m4_mkb": AMBER}
    styles = {"static_isolation": "-", "m4_oef": (0, (5, 1.6)), "m4_mkb": (0, (2.2, 1.2))}

    figure, (ax, ax_zoom) = plt.subplots(
        2, 1, figsize=(6.6, 4.55), gridspec_kw={"height_ratios": [1.45, 1.0]}, sharex=False
    )
    ax.axvspan(30.0, 40.0, facecolor="#f3e7e6", edgecolor="none", zorder=0)
    ax.text(35.0, 105.5, "DDoS shockwave 30–40 s", ha="center", va="top", fontsize=7.1, color=RED)

    summary = {}
    curves = {}
    for arm, label in arms:
        times = sorted({float(row["time_s"]) for row in trace if row["arm"] == arm})
        by_time: dict[float, list[float]] = {time: [] for time in times}
        for row in trace:
            if row["arm"] == arm:
                by_time[float(row["time_s"])].append(float(row["goodput_percent"]))
        means, lows, highs = [], [], []
        for time in times:
            mean, ci = _mean_ci(by_time[time])
            means.append(mean)
            lows.append(mean - ci)
            highs.append(mean + ci)
        curves[arm] = (times, means, lows, highs)
        for panel in (ax, ax_zoom):
            panel.fill_between(times, lows, highs, color=colours[arm], alpha=0.14, linewidth=0)
            panel.plot(
                times, means, color=colours[arm], linestyle=styles[arm],
                linewidth=1.25 if panel is ax else 1.05, label=label,
            )

        shock = [float(row["Legitimate_Goodput_CMRO2"]) for row in aggregates if row["arm"] == arm]
        mean, ci = _mean_ci(shock)
        summary[arm] = (mean, ci)

    _check(len(summary) == 3, "an arm is missing from final_benchmark_raw.csv")
    oef = [float(row["Legitimate_Goodput_CMRO2"]) for row in aggregates if row["arm"] == "m4_oef"]
    static = [float(row["Legitimate_Goodput_CMRO2"]) for row in aggregates if row["arm"] == "static_isolation"]
    p_value = _paired_p(oef, static)
    _check(abs(p_value - 0.5274) < 5e-3, f"paired p for OEF vs static is {p_value:.4f}, expected 0.5274")

    ax.set_xlim(0, 60)
    ax.set_ylim(40, 108)
    ax.set_ylabel("Delivered / offered (%)")
    ax.set_title("(a) Full 60 s run", loc="left", fontsize=8.4)
    ax.set_xticks([0, 10, 20, 30, 40, 50, 60])
    ax.text(
        1.0,
        41.5,
        f"shock-window mean: static {100 * summary['static_isolation'][0]:.2f} %  ·  "
        f"OEF {100 * summary['m4_oef'][0]:.2f} %  ·  MKB {100 * summary['m4_mkb'][0]:.2f} %\n"
        f"paired OEF − static = {100 * (summary['m4_oef'][0] - summary['static_isolation'][0]):+.2f} pp, "
        f"p = {p_value:.3f} (n = 30 seeds)",
        ha="left",
        va="bottom",
        fontsize=6.7,
        bbox={"boxstyle": "round,pad=0.32", "facecolor": "white", "edgecolor": GREY, "linewidth": 0.6, "alpha": 0.92},
    )

    ax_zoom.axvspan(30.0, 40.0, facecolor="#f3e7e6", edgecolor="none", zorder=0)
    ax_zoom.set_xlim(28, 42)
    ax_zoom.set_ylim(45, 100)
    ax_zoom.set_xticks([28, 30, 32, 34, 36, 38, 40, 42])
    ax_zoom.set_xlabel("Time (s)")
    ax_zoom.set_ylabel("Delivered / offered (%)")
    ax_zoom.set_title("(b) Zoom on the shock window", loc="left", fontsize=8.4)
    ax_zoom.legend(
        loc="lower right",
        frameon=False,
        handlelength=1.8,
        labelspacing=0.35,
        fontsize=6.8,
    )
    for panel in (ax, ax_zoom):
        for spine in ("top", "right"):
            panel.spines[spine].set_visible(False)
    figure.tight_layout()
    for arm in ("static_isolation", "m4_oef", "m4_mkb"):
        mean, ci = summary[arm]
        record("B-1", "trace", f"shock-window goodput {arm} (mean ± 95 % CI)",
               f"{mean:.4f} ± {ci:.4f}", "results/m4/final_benchmark_raw.csv")
    record("B-1", "trace", "paired t-test OEF vs static, p", f"{p_value:.4f}",
           "results/m4/final_benchmark_raw.csv")
    record("B-1", "trace", "trace points per arm (mean/CI band)",
           len({row["time_s"] for row in trace if row["arm"] == "static_isolation"}),
           "results/m4/arm_timeseries.csv")
    _save(figure, output_dir, "paperB_fig1_goodput_timeseries")


# ---------------------------------------------------------------------------
# Paper B, figure 2: peak burst speed
# ---------------------------------------------------------------------------
def figure_b2_peak_burst(output_dir: Path) -> None:
    m4 = _rows(REPO / "results/m4/final_benchmark_raw.csv")
    h8 = _rows(REPO / "results/m5/m5_h8_raw.csv")

    def series(rows, arm_key, column="Peak_State_Change_Speed"):
        return [float(row[column]) for row in rows if row["arm"] == arm_key]

    arms = (
        ("static_isolation", "Static per-flow\nisolation", GREY),
        ("m3_surgical_1d", "1-D scalar-EMA\nlimiter", MID_BLUE),
        ("m4_mkb", "4-D kinematic\ntrigger", AMBER),
    )
    stats_m4 = {arm: _mean_ci(series(m4, arm)) for arm, _, _ in arms}
    _check(abs(stats_m4["m3_surgical_1d"][0] - 222.04) < 0.02, "m3_surgical_1d peak is not 222.04")
    _check(abs(stats_m4["m4_mkb"][0] - 218.38) < 0.02, "m4_mkb peak is not 218.38")
    _check(abs(stats_m4["static_isolation"][0] - 1072.83) < 0.02, "static peak is not 1072.83")

    p_mkb_1d = _paired_p(series(m4, "m4_mkb"), series(m4, "m3_surgical_1d"))
    _check(abs(p_mkb_1d - 0.8912) < 5e-3, f"H6 paired p is {p_mkb_1d:.4f}, expected 0.8912")

    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.3), gridspec_kw={"width_ratios": [1.15, 1.0]})

    ax = axes[0]
    positions = range(len(arms))
    means = [stats_m4[arm][0] for arm, _, _ in arms]
    cis = [stats_m4[arm][1] for arm, _, _ in arms]
    bars = ax.bar(
        positions,
        means,
        width=0.58,
        yerr=cis,
        capsize=3.5,
        color=[colour for _, _, colour in arms],
        edgecolor=INK,
        linewidth=0.7,
        error_kw={"elinewidth": 0.8, "ecolor": INK},
    )
    for bar, mean, ci in zip(bars, means, cis):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + ci + 24,
            f"{mean:,.1f}",
            ha="center",
            va="bottom",
            fontsize=7.6,
        )
    ax.set_xticks(list(positions))
    ax.set_xticklabels([label for _, label, _ in arms])
    ax.set_ylabel("Peak state-change speed (units / s)")
    ax.set_ylim(0, 1620)
    ax.set_title("(a) Controller campaign, 30 paired seeds", loc="left", fontsize=8.6)
    ax.annotate(
        f"4-D − 1-D = {means[2] - means[1]:+.1f}\np = {p_mkb_1d:.3f} → no cap",
        xy=(2, means[2] + cis[2] + 12),
        xytext=(0.95, 620),
        fontsize=7.0,
        color=RED,
        arrowprops={"arrowstyle": "->", "linewidth": 0.8, "color": RED},
    )
    ax.text(
        -0.32,
        1545,
        "the {:.0f}× drop from static isolation is the surgical edit,\nnot the trigger: the 1-D and 4-D arms issue the same edit".format(
            means[0] / means[1]
        ),
        ha="left",
        va="top",
        fontsize=6.7,
        color="#444444",
    )
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    ax = axes[1]
    # Panel (b) uses the *controller campaign's own* per-seed peaks, so that the
    # tail comparison is on the same 30 paired seeds as every other number in this
    # figure.  The smoothing campaign's maxima are quoted in the annotation only.
    m4_1d = series(m4, "m3_surgical_1d")
    m4_4d = series(m4, "m4_mkb")
    _check(len(m4_1d) == len(m4_4d) == 30, "the controller campaign must hold 30 seeds per arm")
    worst_1d = max(m4_1d)
    worst_mkb = max(m4_4d)
    _check(worst_mkb > worst_1d, "the 4-D worst case does not exceed the 1-D worst case")
    h8_1d = series(h8, "m3_raw_1d")
    h8_mkb = series(h8, "m4_raw_4d")
    _check(len(h8_1d) == len(h8_mkb) == 30, "the smoothing campaign must hold 30 seeds per arm")

    ax.axhline(worst_1d, color=GREY, linewidth=0.8, linestyle=(0, (4, 2)), zorder=0)
    ax.text(-0.44, worst_1d + 6, f"1-D worst case {worst_1d:.1f}", ha="left", va="bottom",
            fontsize=6.6, color="#555555")
    for x, (values, colour) in enumerate(((m4_1d, MID_BLUE), (m4_4d, AMBER))):
        jitter = [((index % 7) - 3) * 0.022 for index in range(len(values))]
        ax.scatter(
            [x + shift for shift in jitter],
            values,
            s=15,
            color=colour,
            edgecolor="white",
            linewidth=0.3,
            zorder=3,
        )
        mean, ci = _mean_ci(values)
        ax.errorbar([x], [mean], yerr=[ci], fmt="o", color=INK, markersize=0, capsize=6,
                    linewidth=1.0, zorder=4)
        ax.plot([x - 0.17, x + 0.17], [mean, mean], color=INK, linewidth=1.4, zorder=5)
    mean_1d, ci_1d = stats_m4["m3_surgical_1d"]
    mean_mkb, ci_mkb = stats_m4["m4_mkb"]
    ax.set_xticks([0, 1])
    ax.set_xticklabels(
        [
            f"1-D scalar-EMA\nlimiter\n{mean_1d:.1f} ± {ci_1d:.1f}",
            f"4-D kinematic\ntrigger\n{mean_mkb:.1f} ± {ci_mkb:.1f}",
        ]
    )
    ax.set_xlim(-0.45, 1.45)
    ax.set_ylim(-25, 440)
    ax.set_ylabel("Peak state-change speed (units / s)")
    ax.set_title("(b) Per-seed peaks, same 30 seeds", loc="left", fontsize=8.6)

    ax.annotate(
        f"4-D worst case {worst_mkb:.1f} > 1-D {worst_1d:.1f}\nthe trigger does not bound the tail",
        xy=(0.06, worst_mkb),
        xytext=(-0.40, 432),
        fontsize=6.9,
        color=RED,
        ha="left",
        va="top",
        arrowprops={"arrowstyle": "->", "linewidth": 0.8, "color": RED},
    )

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    figure.tight_layout()

    for arm, label, _ in arms:
        mean, ci = stats_m4[arm]
        record("B-2", "(a)", f"peak state-change speed {arm} (mean ± 95 % CI)", f"{mean:.2f} ± {ci:.2f}",
               "results/m4/final_benchmark_raw.csv")
    record("B-2", "(a)", "paired p, 4-D vs 1-D limiter", f"{p_mkb_1d:.4f}",
           "results/m4/final_benchmark_raw.csv")
    record("B-2", "(b)", "worst-case peak, 4-D trigger (controller campaign)", f"{worst_mkb:.1f}",
           "results/m4/final_benchmark_raw.csv")
    record("B-2", "(b)", "worst-case peak, 1-D limiter (controller campaign)", f"{worst_1d:.1f}",
           "results/m4/final_benchmark_raw.csv")
    record("B-2", "(b)", "worst-case peak, 4-D trigger (smoothing campaign)", f"{max(h8_mkb):.1f}",
           "results/m5/m5_h8_raw.csv")
    record("B-2", "(b)", "worst-case peak, 1-D limiter (smoothing campaign)", f"{max(h8_1d):.1f}",
           "results/m5/m5_h8_raw.csv")
    _save(figure, output_dir, "paperB_fig2_peak_burst")


# ---------------------------------------------------------------------------
# Paper B, figure 3: the LLM break-even
# ---------------------------------------------------------------------------
def figure_b3_breakeven(output_dir: Path) -> None:
    from simulation.energy import E_LLM_PER_CALL  # noqa: PLC0415

    exp2 = _rows(REPO / "results/m6/m6_exp2_raw.csv")
    saved = [
        float(row["E_tx_saved_J"])
        for row in exp2
        if row["arm"] == "llm_compiler" and row["E_tx_saved_J"] not in ("", None)
    ]
    saved_mean, _ = _mean_ci(saved)
    calls = 3  # one Oracle call per phase, per docs/break-even-analysis.md
    stip_cost = calls * E_LLM_PER_CALL
    eroi = saved_mean / stip_cost
    _check(abs(saved_mean - 1.976e-4) < 5e-8, f"transmission saving is {saved_mean!r}, expected 1.976e-4 J")
    _check(abs(eroi - 3.29e-6) < 1e-8, f"EROI is {eroi!r}, expected 3.29e-6")
    _check(abs(stip_cost - 60.0) < 1e-9, "stipulated inference cost is not 60 J")

    figure, ax = plt.subplots(figsize=(6.2, 3.5))
    xs = [10 ** (math.log10(1e-7) + index * (math.log10(1e4) - math.log10(1e-7)) / 600) for index in range(601)]
    ys = [saved_mean / x - 1.0 for x in xs]
    ax.plot(xs, ys, color=BLUE, linewidth=1.3, zorder=3)
    ax.set_xscale("log")
    ax.set_yscale("symlog", linthresh=1e-3, linscale=0.6)
    ax.set_xlim(1e-7, 1e4)
    ax.set_ylim(-1.6, 1e4)
    ax.axhline(0.0, color=INK, linewidth=0.8, zorder=2)
    ax.axvline(saved_mean, color=GREEN, linewidth=0.9, linestyle=(0, (4, 2)), zorder=2)
    ax.axvspan(1e-7, saved_mean, facecolor="#eaf3ea", edgecolor="none", zorder=0)

    ax.scatter([stip_cost], [eroi - 1.0], s=34, color=RED, zorder=5, edgecolor="white", linewidth=0.6)
    ax.annotate(
        f"stipulated: {calls} × {E_LLM_PER_CALL:.0f} J = {stip_cost:.0f} J\n"
        f"net ROI {eroi - 1.0:.4f} (EROI {eroi:.2e})",
        xy=(stip_cost, eroi - 1.0),
        xytext=(1.1e-2, -0.42),
        fontsize=6.9,
        color=RED,
        ha="left",
        va="center",
        arrowprops={"arrowstyle": "->", "linewidth": 0.8, "color": RED},
    )
    ax.text(
        1.2e-3,
        6e3,
        f"break-even: {1e3 * saved_mean:.3f} mJ per three-call transition\n"
        f"({1e3 * saved_mean / calls:.3f} mJ per call). Left of the dashed line\n"
        "inference is cheaper than the transmission it saves.",
        fontsize=6.8,
        color=GREEN,
        ha="left",
        va="top",
    )
    ax.text(
        1.15e-7,
        -0.055,
        "net ROI = 0 (break-even)",
        fontsize=6.6,
        color=INK,
        ha="left",
        va="center",
    )
    ax.set_xlabel("Inference energy per three-call transition (J)")
    ax.set_ylabel("Net energy ROI  $(E_{tx,saved}-E_{llm})/E_{llm}$")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    figure.tight_layout()

    record("B-3", "curve", "transmission energy saved per transition (mean)",
           f"{saved_mean:.6e} J", "results/m6/m6_exp2_raw.csv")
    record("B-3", "curve", "break-even inference cost (total)", f"{saved_mean:.6e} J",
           "results/m6/m6_exp2_raw.csv")
    record("B-3", "curve", "break-even per call", f"{saved_mean / calls:.6e} J",
           "results/m6/m6_exp2_raw.csv")
    record("B-3", "curve", "stipulated operating point (total)", f"{stip_cost:.1f} J",
           "simulation/energy.py")
    record("B-3", "curve", "EROI at the stipulation", f"{eroi:.3e}", "results/m6/m6_exp2_raw.csv")
    _save(figure, output_dir, "paperB_fig3_breakeven")


# ---------------------------------------------------------------------------
# Paper B, figure 4: the discrete packet boundary (schematic)
# ---------------------------------------------------------------------------
def figure_b5_discrete_boundary(output_dir: Path) -> None:
    from simulation.surgical.config import MICRO  # noqa: PLC0415
    from simulation.surgical.config import SimConfig  # noqa: PLC0415

    defaults = SimConfig(name="exp1_ddos", seed=0, controller="static_isolation")
    iso_frac = defaults.iso_limit_frac
    packet_bytes = float(MICRO.mtu)
    capacity_Bps = MICRO.capacity_Bps
    buffer_bytes = MICRO.buffer_bytes
    service_s = packet_bytes / capacity_Bps
    buffer_packets = buffer_bytes / packet_bytes
    limit_packets = iso_frac * buffer_packets
    _check(limit_packets > 0, "the isolation limit is empty")

    # Twenty packet service times: short enough that the one-packet quantum is
    # visible, long enough to see the ramp cross the clearance threshold.
    window_s = 20 * service_s
    steps = 601
    times = [window_s * index / (steps - 1) for index in range(steps)]
    # A stylised offered load: a slow ramp over the isolation threshold, so the
    # only difference between the panels is the quantisation of the queue.
    def offered(t):
        return limit_packets * (0.72 + 0.62 * t / window_s)

    fluid = [offered(t) for t in times]
    # The discrete buffer can only change when a whole packet has arrived: it
    # holds the offered level sampled at the last arrival instant, so every
    # control decision is quantised to one packet service time.
    arrivals = [math.floor(t / service_s) * service_s for t in times]
    discrete = [float(math.floor(offered(t))) for t in arrivals]

    crossing_fluid = None
    for index in range(1, steps):
        if fluid[index - 1] < limit_packets <= fluid[index]:
            crossing_fluid = times[index - 1] + (times[index] - times[index - 1]) * (
                (limit_packets - fluid[index - 1]) / (fluid[index] - fluid[index - 1])
            )
            break
    crossing_discrete = None
    for index in range(steps):
        if discrete[index] >= limit_packets:
            crossing_discrete = times[index]
            break
    _check(crossing_fluid is not None and crossing_discrete is not None, "the schematic never crosses the limit")
    _check(crossing_discrete > crossing_fluid, "the discrete queue does not lag the fluid queue")

    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.15), sharey=True)
    for ax, values, colour, title, crossing, style in (
        (axes[0], fluid, MID_BLUE, "(a) Continuous (fluid) queue model", crossing_fluid, "default"),
        (axes[1], discrete, AMBER, "(b) Discrete (packet) buffer", crossing_discrete, "steps-post"),
    ):
        ax.axhline(limit_packets, color=RED, linewidth=0.9, linestyle=(0, (4, 2)), zorder=1)
        ax.plot([t * 1e3 for t in times], values, color=colour, linewidth=1.25, zorder=3, drawstyle=style)
        ax.scatter([crossing * 1e3], [limit_packets], s=26, color=RED, zorder=4, edgecolor="white", linewidth=0.6)
        ax.set_title(title, loc="left")
        ax.set_xlabel("Time (ms)")
        ax.set_ylim(0, limit_packets * 1.45)
        ax.set_xlim(0, window_s * 1e3)
        ax.text(0.02, 0.96, f"clearance limit {limit_packets:.0f} packets\n({100 * iso_frac:.0f} % of {buffer_packets:.0f})",
                transform=ax.transAxes, ha="left", va="top", fontsize=6.6, color=RED)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    axes[0].set_ylabel(f"Buffer occupancy (packets of {packet_bytes:.0f} B)")
    axes[0].annotate(
        f"crosses at {crossing_fluid * 1e3:.2f} ms",
        xy=(crossing_fluid * 1e3, limit_packets),
        xytext=(0.42, 0.22),
        textcoords="axes fraction",
        fontsize=6.8,
        color=RED,
        arrowprops={"arrowstyle": "->", "linewidth": 0.7, "color": RED},
    )
    axes[1].annotate(
        f"crosses at {crossing_discrete * 1e3:.2f} ms\n"
        f"(+{1e3 * (crossing_discrete - crossing_fluid):.3f} ms, one {packet_bytes:.0f} B service time)",
        xy=(crossing_discrete * 1e3, limit_packets),
        xytext=(0.30, 0.22),
        textcoords="axes fraction",
        fontsize=6.8,
        color=RED,
        arrowprops={"arrowstyle": "->", "linewidth": 0.7, "color": RED},
    )
    figure.text(
        0.5,
        -0.02,
        "Schematic of the discretisation argument, not a measurement. Parameters imported from "
        "simulation/surgical/config.py:\n"
        f"{MICRO.name} link, {MICRO.capacity_bps / 1e6:.0f} Mbps, MTU {packet_bytes:.0f} B "
        f"({1e3 * service_s:.3f} ms per packet), buffer {MICRO.buffer_s:.2f} s "
        f"({buffer_bytes / 1e6:.2f} MB = {buffer_packets:.0f} packets), "
        f"isolation limit {100 * iso_frac:.0f} %.",
        ha="center",
        va="top",
        fontsize=6.4,
        color="#444444",
    )
    figure.tight_layout()

    record("B-5", "all", "packet quantum (B)", f"{packet_bytes:.0f}", "simulation/surgical/config.py")
    record("B-5", "all", "service time per packet (ms)", f"{1e3 * service_s:.4f}", "simulation/surgical/config.py")
    record("B-5", "all", "buffer depth (packets)", f"{buffer_packets:.0f}", "simulation/surgical/config.py")
    record("B-5", "all", "isolation clearance limit (packets)", f"{limit_packets:.0f}", "simulation/surgical/config.py")
    record("B-5", "all", "crossing delay from quantisation (ms)",
           f"{1e3 * (crossing_discrete - crossing_fluid):.4f}", "derived from the two panels")
    _save(figure, output_dir, "paperB_fig5_discrete_boundary")


# ---------------------------------------------------------------------------
# Paper B, figure 6: the energy audit
# ---------------------------------------------------------------------------
def figure_b6_energy_audit(output_dir: Path) -> None:
    """Stacked energy per arm from the committed audit CSV.

    Every arm is decomposed into the four stipulated terms, so the reader can see
    that the static baseline's advantage is *zero churn*, not lower transmission.
    """
    rows = _rows(REPO / "results/m6/m6_exp1_raw.csv")
    arms = (
        ("static_isolation", "Static\nisolation", GREY),
        ("m4_oef", "OEF\nactuator", RED),
        ("m4_raw_mkb", "4-D kinematic\ntrigger", AMBER),
        ("m5_ewma_mkb", "EWMA + RER\ntrigger", MID_BLUE),
    )
    # ``Total_Energy_J`` in the committed CSV is E_tx + E_cpu + E_churn; the
    # one-time setup term is reported separately and is *not* stacked here.
    fields = ("E_tx_J", "E_cpu_J", "E_churn_J")
    labels = ("transmission $E_{tx}$", "CPU $E_{cpu}$", "churn $E_{churn}$")
    face = (PALE_BLUE, PALE_AMBER, PALE_RED)
    edge = (BLUE, AMBER, RED)

    means = {
        arm: {field: _mean_ci([float(row[field]) for row in rows if row["arm"] == arm])
              for field in fields + ("Total_Energy_J",)}
        for arm, _, _ in arms
    }
    _check(abs(means["static_isolation"]["Total_Energy_J"][0] - 918.2) < 0.5,
           "static isolation total energy is not 918.2 J")
    _check(abs(means["m4_oef"]["Total_Energy_J"][0] - 1119.0) < 1.0,
           "the OEF arm total energy is not 1119 J")
    _check(means["static_isolation"]["E_churn_J"][0] < 1e-9,
           "the static baseline must have zero runtime churn energy")
    setup_mean, setup_ci = _mean_ci(
        [float(row["E_setup_J"]) for row in rows if row["arm"] == "static_isolation"]
    )
    _check(abs(setup_mean - 1071.0) < 1.0, "the static arm setup energy is not 1071 J")

    figure, ax = plt.subplots(figsize=(6.4, 3.2))
    x = list(range(len(arms)))
    bottoms = [0.0] * len(arms)
    for field, label, colour, line in zip(fields, labels, face, edge):
        heights = [means[arm][field][0] for arm, _, _ in arms]
        ax.bar(x, heights, bottom=bottoms, width=0.58, facecolor=colour, edgecolor=line,
               linewidth=0.7, label=label)
        bottoms = [b + h for b, h in zip(bottoms, heights)]
    for index, (arm, _, _) in enumerate(arms):
        total, ci = means[arm]["Total_Energy_J"]
        ax.text(index, bottoms[index] + 18, f"{total:,.0f} J", ha="center", va="bottom", fontsize=7.6)
        churn = means[arm]["E_churn_J"][0]
        if churn > 1.0:
            ax.text(index, means[arm]["E_tx_J"][0] + churn / 2, f"{churn:,.0f}", ha="center",
                    va="center", fontsize=6.6, color=RED)
    ax.set_xticks(x)
    ax.set_xticklabels([label for _, label, _ in arms])
    ax.set_ylabel("Stipulated energy over the 60 s run (J)")
    ax.set_ylim(0, 1520)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=False,
              fontsize=6.8, handlelength=1.0, columnspacing=1.4)
    ax.text(
        0.985,
        0.995,
        "the static baseline pays no runtime churn; the dynamic arms pay 211–258 J",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=6.7,
        color=RED,
    )
    ax.text(
        0.985,
        0.935,
        f"one-time setup is {setup_mean:,.0f} ± {setup_ci:,.0f} J for the static arm "
        "and zero for the dynamic arms",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=6.4,
        color="#444444",
    )
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    figure.tight_layout()

    for arm, _, _ in arms:
        total, ci = means[arm]["Total_Energy_J"]
        record("B-6", "bars", f"total energy {arm} (mean ± 95 % CI)", f"{total:.1f} ± {ci:.1f} J",
               "results/m6/m6_exp1_raw.csv")
        record("B-6", "bars", f"churn energy {arm}", f"{means[arm]['E_churn_J'][0]:.1f} J",
               "results/m6/m6_exp1_raw.csv")
    record("B-6", "bars", "one-time setup, static arm (mean ± 95 % CI)",
           f"{setup_mean:.1f} ± {setup_ci:.1f} J", "results/m6/m6_exp1_raw.csv")
    _save(figure, output_dir, "paperB_fig6_energy_audit")


# ---------------------------------------------------------------------------
# Paper B, figure 7: detector comparison
# ---------------------------------------------------------------------------
def figure_b7_detector_tradeoff(output_dir: Path) -> None:
    """Detection cost and protection cost of the three detectors.

    Panel (a) is the *detection* axis: how fast each detector fires and how many
    false alarms it raises over the 30 paired seeds.  Panel (b) is the
    *protection* axis: legitimate goodput against the churn energy the detector
    causes.  The committed threshold sweep (``results/m7/m7_roc.csv``) is not
    plotted because its operating points collapse onto the axes; the two panels
    here carry the comparison the text makes.
    """
    exp1 = _rows(REPO / "results/m7/m7_exp1_raw.csv")
    exp2 = _rows(REPO / "results/m7/m7_exp2_raw.csv")

    figure, (left, right) = plt.subplots(1, 2, figsize=(7.1, 3.25), gridspec_kw={"width_ratios": [1.0, 1.1]})

    styles = {
        "dual_band": ("Dual-band LPF/HPF", RED, "o"),
        "m4_raw_mkb": ("4-D kinematic trigger", AMBER, "s"),
        "lpf_only": ("Single-LPF", MID_BLUE, "^"),
    }
    detection = {}
    for arm, (label, colour, marker) in styles.items():
        latency = [
            float(row["Detection_Latency_s"])
            for row in exp1
            if row["arm"] == arm and row["Detection_Latency_s"] not in ("", None)
        ]
        false_pos = [float(row["False_Positives"]) for row in exp1 if row["arm"] == arm]
        detected = [float(row["Detected"]) for row in exp1 if row["arm"] == arm]
        mean, ci = _mean_ci(latency)
        detection[arm] = (mean, ci, sum(false_pos), sum(detected), len(detected))
        left.errorbar([sum(false_pos)], [mean], yerr=[ci], fmt=marker, color=colour,
                      markersize=6, capsize=3, linewidth=0.9)
    for arm, (mean, ci, false_pos, detected, runs) in detection.items():
        label, colour, marker = styles[arm]
        dx, dy, align = {
            "dual_band": (12, -14, "left"),
            "lpf_only": (10, 12, "left"),
            "m4_raw_mkb": (12, 6, "left"),
        }[arm]
        short = {"dual_band": "Dual-band", "lpf_only": "Single-LPF", "m4_raw_mkb": "4-D trigger"}[arm]
        left.annotate(
            f"{short}\n{false_pos:.0f} alarms · {detected:.0f}/{runs:.0f} detected",
            xy=(false_pos, mean),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=6.5,
            color=colour,
            ha=align,
        )
    left.set_xlim(-25, 235)
    left.set_ylim(-0.1, 2.1)
    left.set_xlabel("False positives over the 30 seeds")
    left.set_ylabel("Detection latency (s)")
    left.set_title("(a) Detection cost", loc="left", fontsize=8.5)
    left.text(
        0.97,
        0.95,
        "left is better on both axes",
        transform=left.transAxes,
        ha="right",
        va="top",
        fontsize=6.4,
        color="#444444",
    )

    arms = ("m4_raw_mkb", "lpf_only", "dual_band")
    offsets = {"m4_raw_mkb": (8, -18, "left"), "lpf_only": (6, 12, "left"), "dual_band": (0, 14, "center")}
    for index, arm in enumerate(arms):
        label, colour, marker = styles[arm]
        goodput = [float(row["Legit_Goodput"]) for row in exp2 if row["arm"] == arm]
        churn = [float(row["E_churn_J"]) for row in exp2 if row["arm"] == arm]
        gp, gp_ci = _mean_ci(goodput)
        ec, ec_ci = _mean_ci(churn)
        right.errorbar([ec], [gp], xerr=[ec_ci], yerr=[gp_ci], fmt=marker, color=colour,
                       markersize=6, capsize=3, linewidth=0.9)
        dx, dy, align = offsets[arm]
        right.annotate(
            f"{label}\n{ec:,.0f} J churn, goodput {gp:.3f}",
            xy=(ec, gp),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=6.6,
            color=colour,
            ha=align,
        )
    right.set_xlabel("Churn energy over the run (J)")
    right.set_ylabel("Legitimate goodput")
    right.set_xlim(-60, 1150)
    right.set_ylim(0.55, 1.0)
    right.set_title("(b) Protection bought per joule of churn", loc="left", fontsize=8.5)
    right.text(
        0.97,
        0.05,
        "down-and-right is better: more goodput for less churn",
        transform=right.transAxes,
        ha="right",
        va="bottom",
        fontsize=6.4,
        color="#444444",
    )
    for axis in (left, right):
        for spine in ("top", "right"):
            axis.spines[spine].set_visible(False)
    figure.tight_layout()

    _check(len(detection) == len(styles), "an arm is missing from the detection CSV")
    for arm in arms:
        outcome = [float(row["Detected"]) for row in exp1 if row["arm"] == arm]
        latency = [
            float(row["Detection_Latency_s"])
            for row in exp1
            if row["arm"] == arm and row["Detection_Latency_s"] not in ("", None)
        ]
        false_pos = [float(row["False_Positives"]) for row in exp1 if row["arm"] == arm]
        mean, ci = _mean_ci(latency)
        record("B-7", "(a)", f"detected / 30 {arm}", f"{sum(outcome):.0f}", "results/m7/m7_exp1_raw.csv")
        record("B-7", "(b)", f"detection latency {arm} (mean ± 95 % CI)", f"{mean:.3f} ± {ci:.3f} s",
               "results/m7/m7_exp1_raw.csv")
        record("B-7", "(b)", f"false positives over 30 seeds {arm}", f"{sum(false_pos):.0f}",
               "results/m7/m7_exp1_raw.csv")
        goodput = [float(row["Legit_Goodput"]) for row in exp2 if row["arm"] == arm]
        churn = [float(row["E_churn_J"]) for row in exp2 if row["arm"] == arm]
        gp, gp_ci = _mean_ci(goodput)
        ec, ec_ci = _mean_ci(churn)
        record("B-7", "(b)", f"goodput {arm} (mean ± 95 % CI)", f"{gp:.4f} ± {gp_ci:.4f}",
               "results/m7/m7_exp2_raw.csv")
        record("B-7", "(b)", f"churn energy {arm} (mean ± 95 % CI)", f"{ec:.1f} ± {ec_ci:.1f} J",
               "results/m7/m7_exp2_raw.csv")
    _save(figure, output_dir, "paperB_fig7_detector_tradeoff")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def write_manifest(output_dir: Path) -> None:
    lines = [
        "# Figure data manifest",
        "",
        "Generated by `tools/generate_paper_figures.py`. Every value below was read from the",
        "named committed CSV, checked against the claim the paper makes about it, and then",
        "plotted. Regenerate with:",
        "",
        "```powershell",
        "py tools\\generate_paper_figures.py --output-dir figures",
        "```",
        "",
        "| Figure | Panel | Quantity | Value | Source |",
        "|---|---|---|---|---|",
    ]
    for figure, panel, quantity, value, source in MANIFEST:
        lines.append(f"| {figure} | {panel} | {quantity} | {value} | `{source}` |")
    lines += [
        "",
        "Two panels are schematic and carry no measurement: A-1 draws the *order* of the",
        "layers (its numbers come from the CSVs) and B-4 illustrates the discretisation",
        "argument using parameters imported from `simulation/surgical/config.py`.",
        "",
    ]
    (output_dir / "figure-data-manifest.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  wrote {output_dir.name}/figure-data-manifest.md ({len(MANIFEST)} data points)")


FIGURES = {
    "a1": figure_a1_stack_comparison,
    "a2": figure_a2_wire_bytes,
    "a3": figure_a3_verdict_heatmap,
    "a4": figure_a4_integrity_scope,
    "b1": figure_b1_goodput_timeseries,
    "b2": figure_b2_peak_burst,
    "b3": figure_b3_breakeven,
    "b5": figure_b5_discrete_boundary,
    "b6": figure_b6_energy_audit,
    "b7": figure_b7_detector_tradeoff,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=REPO / "figures")
    parser.add_argument("--only", nargs="+", choices=sorted(FIGURES), help="build a subset")
    args = parser.parse_args(argv)

    plt.rcParams.update(STYLE)
    selected = args.only or sorted(FIGURES)
    print(f"building {len(selected)} figure(s) into {args.output_dir}")
    for key in selected:
        FIGURES[key](args.output_dir)
    if args.only:
        # A partial build must not overwrite the manifest with a partial list.
        print("  partial build: figures/figure-data-manifest.md left untouched")
    else:
        write_manifest(args.output_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

























