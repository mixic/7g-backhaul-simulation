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

"""Generate every results table of Paper A from the committed CSVs.

No number in the output is typed by hand.  Every cell is computed from

* ``validation/layering/results``     P1-P7, three fidelities
* ``validation/real_stack/results``   P8-P12, Linux kernel stack
* ``validation/round2/results``       P13-P16 and the credence file

Static text (case labels, the *frozen predicted* values) lives in the dictionaries
at the top of this file and is marked as such; it is never presented as a result.

Usage::

    python3 tools/make_paper_tables.py                      # writes docs/paper-tables/
    python3 tools/make_paper_tables.py --format both --png  # Markdown + LaTeX + figure
    python3 tools/make_paper_tables.py --check              # recompute invariants, exit 1 on failure

``--check`` also verifies that every case has the frozen number of runs, which would
have caught a 2-run smoke test being reported as a 20-run protocol.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validation.real_stack import predictions as pred  # noqa: E402

LAYER_DIR = ROOT / "validation" / "layering" / "results"
RS_DIR = ROOT / "validation" / "real_stack" / "results"
R2_DIR = ROOT / "validation" / "round2" / "results"

INPUTS = {
    "layering verdicts": LAYER_DIR / "verdicts.csv",
    "layering model": LAYER_DIR / "model_observations.csv",
    "layering simpy": LAYER_DIR / "simpy_observations.csv",
    "layering linux": LAYER_DIR / "linux_observations.csv",
    "real-stack verdicts": RS_DIR / "verdicts.csv",
    "real-stack observations": RS_DIR / "observations.csv",
    "round2 verdicts": R2_DIR / "verdicts.csv",
    "round2 observations": R2_DIR / "observations.csv",
    "round2 calibration": R2_DIR / "calibration.md",
}

# --- Static text (labels and FROZEN predicted values; never results) -----------------

R1_LABEL = {
    "P1": "compress/encrypt size",
    "P2": "encrypt/fragment overhead",
    "P3": "integrity scope",
    "P4": "fixed-overhead commutation",
    "P5": "compress/fragment delivery",
    "P6": "survival sweep",
    "P7": "structural inertness",
}

# case -> (stack / middlebox, predicted outcome text, predicted delivery percent or None)
RS_CASE = {
    "P8a": ("AH tunnel + NAT", "0 %", 0),
    "P8a_control": ("AH tunnel, no NAT", "100 %", 100),
    "P8b": ("ESP tunnel + NAT", "100 %", 100),
    "P8b_control": ("ESP tunnel, no NAT", "100 %", 100),
    "P8c": ("WireGuard + NAT", "100 %", 100),
    "P8c_control": ("WireGuard, no NAT", "100 %", 100),
    "P11a": ("WireGuard, UDP length 9, checksum untouched", "0 %", 0),
    "P11b": ("WireGuard, UDP length 9, checksum recomputed", "0 %", 0),
    "P11c": ("WireGuard, inert ToS rewrite", "100 %", 100),
    "P12a": ("ESP transport + NAT, inner UDP checksum", "0 %", 0),
    "P12b": ("ESP transport + NAT, inner checksum zero", "100 %", 100),
    "P12c": ("ESP transport, no NAT", "100 %", 100),
}

# case -> (decapsulator, inner ECN, outer ECN set to)
R2_ECN = {
    "P13a": ("IPIP", "Not-ECT", "CE"),
    "P13b": ("IPIP", "Not-ECT", "ECT(0)"),
    "P13c": ("IPIP", "ECT(0)", "CE"),
    "P13d": ("WireGuard", "Not-ECT", "CE"),
    "P13e": ("WireGuard", "ECT(0)", "CE"),
    "P13f": ("ESP tunnel", "Not-ECT", "CE"),
    "P13g": ("ESP tunnel", "ECT(0)", "CE"),
    "P13h_ipip": ("IPIP", "both", "none (control)"),
    "P13h_wg": ("WireGuard", "both", "none (control)"),
    "P13h_esp": ("ESP tunnel", "both", "none (control)"),
}
R2_NAT_LABEL = {
    "P14a": "ESP tunnel + NAT, client 1 first",
    "P14b": "ESP tunnel + NAT, client 2 first",
    "P14c": "ESP-in-UDP (NAT-T) + NAT",
    "P14d": "ESP tunnel, no NAT",
}
R2_REPLAY_LABEL = {
    "P16a": "ESP, window 32, 100 ms reorder",
    "P16b": "ESP, window 32, 4 ms reorder",
    "P16c": "WireGuard, 100 ms reorder",
    "P16d": "ESP, window 256, 100 ms reorder",
}
# Frozen predictions for P15 (docs/layering-real-stack-predictions-round2.md section 7).
P15_FROZEN = {"E_to_F_bytes": 2112, "F_to_E_bytes": 2180, "delivery": 0.9025, "tolerance": 0.015}
CAL_TO_CASES = {
    "P13h": ["P13h_ipip", "P13h_wg", "P13h_esp"],
    "P15_bytes": ["P15a"],
    "P15_delivery": ["P15b"],
}

# --- Data loading ----------------------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class Obs:
    """Observation rows indexed by (scenario, policy, metric)."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows
        self._index: dict[tuple[str, str, str], dict[str, float]] = defaultdict(dict)
        for row in rows:
            self._index[(row["scenario"], row["policy"], row["metric"])][row["seed"]] = float(row["value"])

    def by_seed(self, scenario: str, policy: str, metric: str) -> dict[str, float]:
        return self._index.get((scenario, policy, metric), {})

    def vals(self, scenario: str, policy: str, metric: str) -> list[float]:
        return list(self.by_seed(scenario, policy, metric).values())

    def mean(self, scenario: str, policy: str, metric: str) -> float:
        values = self.vals(scenario, policy, metric)
        return statistics.fmean(values) if values else math.nan

    def runs(self, scenario: str, policy: str) -> int:
        seeds: set[str] = set()
        for (sc, pol, _), per_seed in self._index.items():
            if sc == scenario and pol == policy:
                seeds.update(per_seed)
        return len(seeds)

    def policies(self, scenario: str) -> list[str]:
        return sorted({pol for (sc, pol, _) in self._index if sc == scenario})


@dataclass
class Data:
    layer_verdicts: list[dict[str, str]]
    layer: dict[str, Obs]
    rs: Obs
    rs_verdicts: list[dict[str, str]]
    r2: Obs
    r2_verdicts: list[dict[str, str]]
    calibration: list[tuple[str, float, int]]

    @classmethod
    def load(cls) -> "Data":
        return cls(
            layer_verdicts=read_csv(INPUTS["layering verdicts"]),
            layer={
                "model": Obs(read_csv(INPUTS["layering model"])),
                "simpy": Obs(read_csv(INPUTS["layering simpy"])),
                "linux": Obs(read_csv(INPUTS["layering linux"])),
            },
            rs=Obs(read_csv(INPUTS["real-stack observations"])),
            rs_verdicts=read_csv(INPUTS["real-stack verdicts"]),
            r2=Obs(read_csv(INPUTS["round2 observations"])),
            r2_verdicts=read_csv(INPUTS["round2 verdicts"]),
            calibration=parse_calibration(INPUTS["round2 calibration"].read_text(encoding="utf-8")),
        )


def parse_calibration(text: str) -> list[tuple[str, float, int]]:
    rows = []
    for line in text.splitlines():
        match = re.match(r"\|\s*(P[\w]+)\s*\|\s*([0-9.]+)\s*\|\s*([01])\s*\|", line)
        if match:
            rows.append((match.group(1), float(match.group(2)), int(match.group(3))))
    return rows


# --- Table model and renderers ------------------------------------------------------------


@dataclass
class Table:
    key: str
    title: str
    headers: list[str]
    rows: list[list[str]]
    notes: list[str] = field(default_factory=list)


def md_cell(text: str) -> str:
    return text.replace("|", "\\|")


def render_md(table: Table) -> str:
    out = [f"### {table.title}", "", "| " + " | ".join(table.headers) + " |",
           "|" + "|".join("---" for _ in table.headers) + "|"]
    out += ["| " + " | ".join(md_cell(cell) for cell in row) + " |" for row in table.rows]
    for note in table.notes:
        out += ["", f"*{note}*"]
    return "\n".join(out) + "\n"


_LATEX_ESCAPES = {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#", "$": r"\$", "{": r"\{", "}": r"\}",
                  "^": r"\^{}", "~": r"\textasciitilde{}", "\\": r"\textbackslash{}"}
_LATEX_SYMBOLS = {"→": r"$\rightarrow$", "≥": r"$\geq$", "≤": r"$\leq$", "±": r"$\pm$", "×": r"$\times$",
                  "–": "--", "✓": r"\checkmark", "−": "$-$"}


def latex_cell(text: str) -> str:
    escaped = "".join(_LATEX_ESCAPES.get(ch, ch) for ch in text)
    for symbol, replacement in _LATEX_SYMBOLS.items():
        escaped = escaped.replace(symbol, replacement)
    return escaped


def render_latex(table: Table) -> str:
    cols = "l" * len(table.headers)
    lines = [r"\begin{table}[t]", r"\centering", r"\small", f"\\caption{{{latex_cell(table.title)}}}",
             f"\\label{{tab:{table.key}}}", f"\\begin{{tabular}}{{{cols}}}", r"\toprule",
             " & ".join(latex_cell(h) for h in table.headers) + r" \\", r"\midrule"]
    lines += [" & ".join(latex_cell(cell) for cell in row) + r" \\" for row in table.rows]
    lines += [r"\bottomrule", r"\end{tabular}"]
    for note in table.notes:
        lines.append(f"\\par\\smallskip\\footnotesize {latex_cell(note)}")
    lines.append(r"\end{table}")
    return "\n".join(lines) + "\n"


# --- Formatting helpers --------------------------------------------------------------------


def fnum(value: float, digits: int = 0) -> str:
    return "n/a" if math.isnan(value) else f"{value:,.{digits}f}".replace(",", "")


def frange(values: list[float], digits: int = 0) -> str:
    if not values:
        return "n/a"
    low, high = min(values), max(values)
    return fnum(low, digits) if low == high else f"{fnum(low, digits)}–{fnum(high, digits)}"


def mark(ok: bool) -> str:
    # ASCII on purpose: the Markdown tables are rendered to PDF with a Latin
    # Modern font that has no U+2713 glyph, so a check mark would silently
    # disappear.  "yes"/"no" is unambiguous in both Markdown and PDF.
    return "yes" if ok else "no"


def agg_verdict(verdicts: list[str]) -> str:
    if not verdicts:
        return "n/a"
    if "REFUTED" in verdicts:
        return "REFUTED"
    if all(v == "CONFIRMED" for v in verdicts):
        return "CONFIRMED"
    for status in ("INCONCLUSIVE", "INVALID", "NOT RUN"):
        if status in verdicts:
            return status
    return verdicts[0]


def verdict_of(rows: list[dict[str, str]], key: str, value: str) -> str:
    for row in rows:
        if row[key] == value:
            return row["verdict"]
    return "n/a"


# --- Tables ---------------------------------------------------------------------------------


def t_r1_verdicts(d: Data) -> Table:
    rows = []
    for p in R1_LABEL:
        cells = {r["fidelity"]: r["verdict"] for r in d.layer_verdicts if r["prediction"] == p}
        overall = agg_verdict([cells.get(f, "n/a") for f in ("model", "simpy", "linux")])
        rows.append([f"{p}: {R1_LABEL[p]}", cells.get("model", "n/a"), cells.get("simpy", "n/a"),
                     cells.get("linux", "n/a"), overall])
    return Table("verdicts_p1_p7", "P1–P7 verdicts by fidelity", ["Prediction", "Model", "SimPy", "Linux", "Overall"], rows,
                 ["Computed from validation/layering/results/verdicts.csv."])


def t_r1_quantities(d: Data) -> Table:
    fids = ("model", "simpy", "linux")
    rows: list[list[str]] = []

    def row(label: str, fn) -> None:
        rows.append([label] + [fn(d.layer[f], f) for f in fids])

    def wire(o: Obs, sc: str, pol: str) -> float:
        return o.mean(sc, pol, "wire_bytes")

    row("P1 text wire bytes, E→C / C→E (ratio)",
        lambda o, f: f"{wire(o, 'P1', 'E_to_C_text') / wire(o, 'P1', 'C_to_E_text'):.3f}")
    row("P2 wire bytes, E→F / F→E",
        lambda o, f: f"{fnum(wire(o, 'P2', 'E_to_F'))} / {fnum(wire(o, 'P2', 'F_to_E'))}")
    row("P2 byte difference (F→E − E→F)",
        lambda o, f: fnum(wire(o, "P2", "F_to_E") - wire(o, "P2", "E_to_F")))
    row("P2 delivery E→F / F→E (%)",
        lambda o, f: f"{o.mean('P2', 'E_to_F', 'delivery_percent'):.2f} / {o.mean('P2', 'F_to_E', 'delivery_percent'):.2f}")
    row("P4 wire bytes over the six orderings",
        lambda o, f: _distinct([o.mean("P4", p, "wire_bytes") for p in o.policies("P4")]))
    row("P5 fragments C→F / F→C",
        lambda o, f: f"{o.mean('P5', 'C_to_F', 'fragment_count'):.1f} / {o.mean('P5', 'F_to_C', 'fragment_count'):.1f}")
    row("P5 delivery C→F / F→C (%)",
        lambda o, f: f"{o.mean('P5', 'C_to_F', 'delivery_percent'):.2f} / {o.mean('P5', 'F_to_C', 'delivery_percent'):.2f}")
    row("P5 delivery difference (pp)",
        lambda o, f: f"{o.mean('P5', 'C_to_F', 'delivery_percent') - o.mean('P5', 'F_to_C', 'delivery_percent'):+.2f}")
    row("P6 cases checked", lambda o, f: str(len(o.policies("P6"))))
    return Table("quantities_p1_p7", "P1–P7 key quantities by fidelity", ["Quantity", "Model", "SimPy", "Linux"], rows,
                 ["Means over seeds from the model, SimPy and Linux observation CSVs; Linux uses fewer seeds than the model."])


def _distinct(values: list[float]) -> str:
    unique = sorted({round(v, 6) for v in values if not math.isnan(v)})
    if len(unique) == 1:
        return f"{fnum(unique[0])} (all equal)"
    return ", ".join(fnum(v) for v in unique)


def t_rs_cases(d: Data) -> Table:
    rows = []
    for case, (label, predicted, _) in RS_CASE.items():
        scenario = re.match(r"(P\d+)", case).group(1)
        delivery = d.rs.vals(scenario, case, "delivery_percent")
        gates = []
        for metric in ("mutation_gate", "cause_gate", "endpoint_gate"):
            values = d.rs.vals(scenario, case, metric)
            if values:
                gates.append(f"{metric.split('_')[0]} {mark(all(v == 1 for v in values))}")
        rows.append([case, label, predicted, f"{fnum(statistics.fmean(delivery), 1)} ({frange(delivery)})" if delivery else "n/a",
                     str(d.rs.runs(scenario, case)), ", ".join(gates) or "—", verdict_of(d.rs_verdicts, "case", case)])
    return Table("realstack_cases", "Real-stack cases P8, P11, P12",
                 ["Case", "Stack / middlebox", "Predicted delivery", "Observed % mean (min–max)", "Runs", "Gates", "Verdict"], rows,
                 ["Predicted values are the frozen ones; observed values are computed from validation/real_stack/results/observations.csv."])


def t_rs_p9(d: Data) -> Table:
    rows = []
    for length in pred.P9_LENGTHS:
        pol = f"P9_L{length}"
        low, high = d.rs.vals("P9", pol, "wire_bytes_min"), d.rs.vals("P9", pol, "wire_bytes_max")
        observed = frange(low + high)
        ok = bool(low) and all(v == pred.wg_wire(length) for v in low + high)
        dev = (min(low) - length - pred.STIPULATED_COMPOSITE) if low else math.nan
        rows.append([str(length), str(pred.r16(length)), str(pred.wg_wire(length)), observed, fnum(dev), mark(ok)])
    return Table("realstack_p9", "P9: WireGuard wire size against the formula 60 + 16*ceil(L/16)",
                 ["Inner length L (B)", "R(L)", "Predicted wire (B)", "Observed wire (B)", "Observed − (L + 56)", "Match"], rows,
                 ["Column 5 is the error of the stipulated 56-byte composite overhead."])


def t_rs_p10(d: Data) -> Table:
    rows = []
    for length in pred.P10_LENGTHS:
        y = d.rs.vals("P10", f"P10_y_to_w_L{length}", "wire_bytes_min")
        w = d.rs.vals("P10", f"P10_w_to_y_L{length}", "wire_bytes_min")
        if not y or not w:
            rows.append([str(length), "n/a", "n/a", "n/a", str(pred.p10_d(length)), "✗"])
            continue
        delta = min(y) - min(w)
        ok = len(set(y)) == 1 and len(set(w)) == 1 and delta == pred.p10_d(length)
        rows.append([str(length), str(length % 16), fnum(min(y)), fnum(min(w)), f"{int(delta):+d} (predicted {pred.p10_d(length):+d})", mark(ok)])
    return Table("realstack_p10", "P10: IPIP and WireGuard nesting order",
                 ["Inner length L (B)", "L mod 16", "Wire, IPIP then WG (B)", "Wire, WG then IPIP (B)", "Difference d(L)", "Match"], rows,
                 ["d(L) is never zero, so exact commutation of the two layers fails on a real stack."])


def t_decap(d: Data) -> Table:
    rows = []
    for case, (stack, inner, outer) in R2_ECN.items():
        sent = d.r2.vals("P13", case, "sent_datagrams")
        delivered = d.r2.vals("P13", case, "delivered_datagrams")
        total = sum(delivered)
        parts = []
        for metric, label in (("inner_tos_ce", "CE"), ("inner_tos_ect0", "ECT(0)"), ("inner_tos_notect", "Not-ECT")):
            count = sum(d.r2.vals("P13", case, metric))
            if total and count:
                parts.append(f"{label} {100 * count / total:.0f} %")
        errors = d.r2.vals("P13", case, "ipip_rx_frame_errors_delta")
        cause = f"rx_frame_errors {frange(errors)}/run" if stack == "IPIP" and errors else "—"
        pct = 100 * total / sum(sent) if sent else math.nan
        rows.append([case, stack, inner, outer, f"{fnum(pct, 0)} %", " / ".join(parts) or "—", cause,
                     verdict_of(d.r2_verdicts, "case", case)])
    return Table("decap_ecn", "P13: outer ECN codepoint set to CE or ECT(0) after NAT, by decapsulator",
                 ["Case", "Decapsulator", "Inner ECN", "Outer ECN set to", "Delivery", "Inner ECN at receiver", "Cause counter", "Verdict"], rows,
                 ["Receiver composition is the share of delivered datagrams per codepoint; computed from the inner_tos_* counters."])


def t_decap_matrix(d: Data) -> Table:
    def cell(case: str) -> str:
        delivered = sum(d.r2.vals("P13", case, "delivered_datagrams"))
        if delivered == 0:
            errors = d.r2.vals("P13", case, "ipip_rx_frame_errors_delta")
            return f"drop ({frange(errors)} frame errors/run)" if errors and max(errors) else "drop"
        for metric, label in (("inner_tos_ce", "CE"), ("inner_tos_ect0", "ECT(0)"), ("inner_tos_notect", "Not-ECT")):
            if sum(d.r2.vals("P13", case, metric)) == delivered:
                return f"deliver, inner {label}"
        return "deliver"
    rows = [["IPIP", cell("P13a"), cell("P13c")], ["WireGuard", cell("P13d"), cell("P13e")], ["ESP tunnel", cell("P13f"), cell("P13g")]]
    return Table("decap_matrix", "Decapsulation of an outer CE mark",
                 ["Decapsulator", "Outer CE, inner Not-ECT", "Outer CE, inner ECT(0)"], rows,
                 ["The same visible, unauthenticated field is fatal on one stack and inert on two."])


def t_nat_key(d: Data) -> Table:
    rows = []
    for case, label in R2_NAT_LABEL.items():
        def pair(prefix: str) -> str:
            delivered = d.r2.vals("P14", case, f"delivered_{prefix}")
            sent = d.r2.vals("P14", case, f"sent_{prefix}")
            return f"{frange(delivered)}/{frange(sent)}"
        spi1 = frange(d.r2.vals("P14", case, "spi_seen_client1"))
        spi2 = frange(d.r2.vals("P14", case, "spi_seen_client2"))
        sport2 = d.r2.vals("P14", case, "outer_sport_client2")
        sport = f"{fnum(min(sport2))}–{fnum(max(sport2))}" if sport2 and max(sport2) > 0 else "—"
        rows.append([case, label, pair("client1"), pair("client2"), f"{spi1} / {spi2}",
                     frange(d.r2.vals("P14", case, "ct_esp_entries_after")), sport, verdict_of(d.r2_verdicts, "case", case)])
    return Table("nat_key", "P14: two ESP clients behind one NAT",
                 ["Case", "Setup", "Client 1 delivered/sent", "Client 2 delivered/sent", "ESP SPI on wire (1 / 2)",
                  "ESP conntrack entries", "Client 2 translated src port", "Verdict"], rows,
                 ["Counts are per run (min–max over runs); SPI counts come from the capture at the NAT's outbound interface."])


def t_frag(d: Data) -> Table:
    rows = []
    for label, pol, key in (("E→F (encrypt, then fragment)", "P15_EtoF", "E_to_F_bytes"),
                            ("F→E (fragment, then encrypt)", "P15_FtoE", "F_to_E_bytes")):
        sent = sum(d.r2.vals("P15", pol, "sent_datagrams"))
        delivered = sum(d.r2.vals("P15", pol, "delivered_datagrams"))
        pooled = delivered / sent if sent else math.nan
        rows.append([label, _distinct(d.r2.vals("P15", pol, "wire_bytes_per_datagram")), str(P15_FROZEN[key]),
                     frange(d.r2.vals("P15", pol, "wire_packets_per_datagram")), f"{pooled:.4f}",
                     f"{P15_FROZEN['delivery']} ± {P15_FROZEN['tolerance']}"])
    delta = (d.r2.mean("P15", "P15_FtoE", "wire_bytes_per_datagram") - d.r2.mean("P15", "P15_EtoF", "wire_bytes_per_datagram"))
    return Table("fragmentation", "P15: fragmentation placement around WireGuard",
                 ["Ordering", "Wire bytes per datagram", "Predicted (frozen)", "Packets per datagram", "Pooled delivery", "Predicted delivery (frozen)"],
                 rows, [f"Observed byte difference F→E − E→F: {fnum(delta)} B. Verdicts: P15a {verdict_of(d.r2_verdicts, 'case', 'P15a')}, "
                        f"P15b {verdict_of(d.r2_verdicts, 'case', 'P15b')}."])


def _replay_notes(d: Data) -> list[str]:
    note = ("'Equals reference filter' is true when delivered datagrams equal the count a reference sliding-window filter "
            "accepts on the captured wire order, in every run.")
    refuted = [c for c in R2_REPLAY_LABEL if verdict_of(d.r2_verdicts, "case", c) == "REFUTED"]
    matching = [c for c in refuted if all(v == 1 for v in d.r2.vals("P16", c, "delivery_matches_reference"))]
    if matching:
        note += (f" For {', '.join(matching)} the reference filter also predicts the delivered count exactly, so the refuted "
                 "expectation is the predicted delivery level, not the replay-window mechanism.")
    return [note]


def t_replay(d: Data) -> Table:
    rows = []
    for case, label in R2_REPLAY_LABEL.items():
        delivered = d.r2.vals("P16", case, "delivered_datagrams")
        sent = d.r2.vals("P16", case, "sent_datagrams")
        ref_ok = d.r2.vals("P16", case, "delivery_matches_reference")
        rows.append([case, label, frange(d.r2.vals("P16", case, "reorder_depth")), f"{frange(delivered)} of {frange(sent)}",
                     mark(bool(ref_ok) and all(v == 1 for v in ref_ok)), frange(d.r2.vals("P16", case, "seq_error_delta")),
                     verdict_of(d.r2_verdicts, "case", case)])
    return Table("replay", "P16: replay window against reordering",
                 ["Case", "Stack / window / reorder", "Observed reorder depth", "Delivered (min–max)", "Equals reference filter",
                  "Sequence errors", "Verdict"], rows,
                 _replay_notes(d))


def calibration_stats(d: Data) -> dict[str, float]:
    n = len(d.calibration)
    brier = statistics.fmean((c - o) ** 2 for _, c, o in d.calibration) if n else math.nan
    return {"n": n, "brier": brier, "expected_refutations": sum(1 - c for _, c, _ in d.calibration),
            "observed_refutations": sum(1 for _, _, o in d.calibration if o == 0)}


def t_calibration(d: Data) -> Table:
    rows = [[p, f"{c:.2f}", str(o), f"{(c - o) ** 2:.4f}"] for p, c, o in d.calibration]
    s = calibration_stats(d)
    return Table("calibration", "Round-2 credences and outcomes", ["Prediction", "Credence", "Outcome (1 = confirmed)", "Brier term"], rows,
                 [f"Brier score {s['brier']:.4f} over {int(s['n'])} scored predictions; expected refutations at these credences "
                  f"{s['expected_refutations']:.1f}, observed {int(s['observed_refutations'])}."])


# --- Verdict matrix and headline counts -----------------------------------------------------


def verdict_matrix(d: Data) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for p in R1_LABEL:
        for r in d.layer_verdicts:
            if r["prediction"] == p:
                out.append({"round": "P1-P7", "prediction": p, "fidelity": r["fidelity"], "verdict": r["verdict"]})
    for p in ("P8", "P9", "P10", "P11", "P12"):
        verdicts = [r["verdict"] for r in d.rs_verdicts if r["prediction"] == p]
        out.append({"round": "P8-P12", "prediction": p, "fidelity": "kernel", "verdict": agg_verdict(verdicts)})
    for pid, _, _ in d.calibration:
        cases = CAL_TO_CASES.get(pid, [pid])
        verdicts = [verdict_of(d.r2_verdicts, "case", c) for c in cases]
        out.append({"round": "P13-P16", "prediction": pid, "fidelity": "kernel", "verdict": agg_verdict(verdicts)})
    return out


def headline_counts(matrix: list[dict[str, str]]) -> dict[str, tuple[int, int]]:
    groups: dict[str, list[str]] = defaultdict(list)
    per_pred: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in matrix:
        per_pred[(row["round"], row["prediction"])].append(row["verdict"])
    for (rnd, _), verdicts in per_pred.items():
        groups[rnd].append(agg_verdict(verdicts))
    counts = {rnd: (sum(1 for v in vs if v == "CONFIRMED"), len(vs)) for rnd, vs in groups.items()}
    counts["total"] = (sum(c for c, _ in counts.values()), sum(n for _, n in counts.values()))
    return counts


def t_counts(matrix: list[dict[str, str]]) -> Table:
    counts = headline_counts(matrix)
    rows = [[rnd, f"{c} of {n}"] for rnd, (c, n) in counts.items()]
    return Table("headline_counts", "Headline counts (a prediction is confirmed only if every fidelity confirms it)",
                 ["Round", "Confirmed"], rows,
                 ["Use these numbers in the abstract; do not retype them."])


def draw_matrix_png(matrix: list[dict[str, str]], path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError:
        return False
    cols = ["model", "simpy", "linux", "kernel"]
    names = ["Model", "SimPy", "Linux netns", "Linux kernel"]
    order: list[tuple[str, str]] = []
    cells: dict[tuple[str, str, str], str] = {}
    for row in matrix:
        key = (row["round"], row["prediction"])
        if key not in order:
            order.append(key)
        cells[(row["round"], row["prediction"], row["fidelity"])] = row["verdict"]
    colors = {"CONFIRMED": "#4c9f70", "REFUTED": "#c0504d", "INCONCLUSIVE": "#e0b040", "INVALID": "#999999", "NOT RUN": "#cccccc"}
    fig, ax = plt.subplots(figsize=(5.6, 0.26 * len(order) + 1.2))
    for y, (rnd, pid) in enumerate(order):
        for x, col in enumerate(cols):
            verdict = cells.get((rnd, pid, col))
            if verdict:
                ax.add_patch(plt.Rectangle((x, y), 0.92, 0.82, color=colors.get(verdict, "#ffffff")))
        ax.text(-0.1, y + 0.4, pid, ha="right", va="center", fontsize=7)
    ax.set_xlim(0, len(cols))
    ax.set_ylim(len(order), 0)
    ax.set_xticks([i + 0.46 for i in range(len(cols))])
    ax.set_xticklabels(names, fontsize=7)
    ax.xaxis.tick_top()
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.legend(handles=[Patch(color=c, label=v) for v, c in colors.items() if v in {r["verdict"] for r in matrix}],
              fontsize=6, loc="lower center", bbox_to_anchor=(0.5, -0.08), ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return True


# --- Checks (recompute invariants from raw observations) ------------------------------------


def run_checks(d: Data, expect_runs: int) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))

    # Frozen protocol: every kernel case has the frozen number of runs.
    for label, obs in (("real-stack", d.rs), ("round2", d.r2)):
        scenarios = sorted({row["scenario"] for row in obs.rows})
        bad = []
        for sc in scenarios:
            for pol in obs.policies(sc):
                if "_L" in pol and pol.split("_L")[-1].isdigit():
                    continue
                if obs.runs(sc, pol) != expect_runs:
                    bad.append(f"{pol}:{obs.runs(sc, pol)}")
        check(f"{label}: every case has {expect_runs} runs", not bad, ", ".join(bad[:8]))

    # P9 / P10 arithmetic against raw wire bytes.
    p9_bad = [L for L in pred.P9_LENGTHS
              if not all(v == pred.wg_wire(L) for v in d.rs.vals("P9", f"P9_L{L}", "wire_bytes_min") + d.rs.vals("P9", f"P9_L{L}", "wire_bytes_max"))
              or not d.rs.vals("P9", f"P9_L{L}", "wire_bytes_min")]
    check("P9: wire = 60 + 16*ceil(L/16) for every L and run", not p9_bad, f"lengths {p9_bad}")
    p10_bad = []
    for L in pred.P10_LENGTHS:
        y = d.rs.by_seed("P10", f"P10_y_to_w_L{L}", "wire_bytes_min")
        w = d.rs.by_seed("P10", f"P10_w_to_y_L{L}", "wire_bytes_min")
        if not y or any(y.get(s) - w.get(s) != pred.p10_d(L) for s in y):
            p10_bad.append(L)
    check("P10: d(L) matches R(L+20) - R(L) - 20 for every L and run", not p10_bad, f"lengths {p10_bad}")
    check("P10: d(L) is never zero", all(pred.p10_d(L) != 0 for L in pred.P10_LENGTHS))

    # Delivery extremes for kernel cases with a 0/100 prediction.
    extreme_bad = []
    for case, (_, _, expected) in RS_CASE.items():
        sc = re.match(r"(P\d+)", case).group(1)
        values = d.rs.vals(sc, case, "delivery_percent")
        if not values or any(v != expected for v in values):
            extreme_bad.append(case)
    check("P8/P11/P12: delivery equals the predicted extreme in every run", not extreme_bad, ", ".join(extreme_bad))

    # P1-P7 consistency across fidelities.
    for fid, obs in d.layer.items():
        wires = {round(obs.mean("P4", p, "wire_bytes"), 6) for p in obs.policies("P4")}
        check(f"P4 ({fid}): six orderings give one wire size", len(wires) == 1, str(sorted(wires)))
    diffs = {fid: round(o.mean("P2", "F_to_E", "wire_bytes") - o.mean("P2", "E_to_F", "wire_bytes"), 6) for fid, o in d.layer.items()}
    check("P2: byte difference is identical across fidelities", len(set(diffs.values())) == 1, str(diffs))

    # P13 internal consistency.
    ecn_bad = [c for c in R2_ECN if not all(v == 1 for v in d.r2.vals("P13", c, "ecn_gate"))]
    check("P13: ECN mutation gate passed in every run", not ecn_bad, ", ".join(ecn_bad))
    check("P13a: IPIP frame errors equal datagrams sent in every run",
          d.r2.by_seed("P13", "P13a", "ipip_rx_frame_errors_delta") == d.r2.by_seed("P13", "P13a", "sent_datagrams"))

    # P14 / P15 / P16.
    check("P14: SPI and NAT gates passed in every run",
          all(v == 1 for c in R2_NAT_LABEL for m in ("spi_gate", "nat_gate") for v in d.r2.vals("P14", c, m)))
    e_to_f = set(d.r2.vals("P15", "P15_EtoF", "wire_bytes_per_datagram"))
    f_to_e = set(d.r2.vals("P15", "P15_FtoE", "wire_bytes_per_datagram"))
    check("P15: wire bytes equal the frozen 2112 / 2180 in every run",
          e_to_f == {P15_FROZEN["E_to_F_bytes"]} and f_to_e == {P15_FROZEN["F_to_E_bytes"]}, f"{sorted(e_to_f)} / {sorted(f_to_e)}")
    for pol in ("P15_EtoF", "P15_FtoE"):
        pooled = sum(d.r2.vals("P15", pol, "delivered_datagrams")) / sum(d.r2.vals("P15", pol, "sent_datagrams"))
        check(f"P15 ({pol}): pooled delivery inside the frozen band",
              abs(pooled - P15_FROZEN["delivery"]) <= P15_FROZEN["tolerance"], f"{pooled:.4f}")
    ref_bad = [c for c in R2_REPLAY_LABEL if not all(v == 1 for v in d.r2.vals("P16", c, "delivery_matches_reference"))]
    check("P16: delivery equals the reference replay filter in every run (all four cases)", not ref_bad, ", ".join(ref_bad))
    for c in R2_REPLAY_LABEL:
        delivered = d.r2.by_seed("P16", c, "delivered_datagrams")
        sent = d.r2.by_seed("P16", c, "sent_datagrams")
        errors = d.r2.by_seed("P16", c, "seq_error_delta")
        ok = all(sent[s] - delivered[s] == errors[s] for s in delivered)
        check(f"P16 ({c}): sequence errors equal sent - delivered", ok)

    # Calibration file against the verdict CSV.
    mismatches = []
    for pid, _, outcome in d.calibration:
        verdicts = [verdict_of(d.r2_verdicts, "case", c) for c in CAL_TO_CASES.get(pid, [pid])]
        if (agg_verdict(verdicts) == "CONFIRMED") != bool(outcome):
            mismatches.append(pid)
    check("calibration.md outcomes agree with verdicts.csv", not mismatches, ", ".join(mismatches))
    return results


# --- Driver ---------------------------------------------------------------------------------


def provenance() -> str:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    lines = [f"Generated by tools/make_paper_tables.py at repository commit {commit}. Do not edit by hand.", "", "Input files (sha256, first 12 hex):"]
    for name, path in INPUTS.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.exists() else "missing"
        lines.append(f"- {name}: `{path.relative_to(ROOT)}` {digest}")
    return "\n".join(lines)


def build_tables(d: Data, matrix: list[dict[str, str]]) -> list[Table]:
    return [t_r1_verdicts(d), t_r1_quantities(d), t_rs_cases(d), t_rs_p9(d), t_rs_p10(d), t_decap(d), t_decap_matrix(d),
            t_nat_key(d), t_frag(d), t_replay(d), t_calibration(d), t_counts(matrix)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "paper-tables")
    parser.add_argument("--format", choices=("md", "latex", "both"), default="md")
    parser.add_argument("--png", action="store_true", help="also draw the verdict matrix (needs matplotlib)")
    parser.add_argument("--check", action="store_true", help="recompute invariants; exit 1 on any failure")
    parser.add_argument("--expect-runs", type=int, default=20, help="runs per kernel case in the frozen protocol")
    parser.add_argument("--stdout", action="store_true", help="print the Markdown to stdout instead of writing files")
    args = parser.parse_args(argv)

    missing = [str(p) for p in INPUTS.values() if not p.exists()]
    if missing:
        print("missing input files:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 2
    data = Data.load()
    matrix = verdict_matrix(data)
    tables = build_tables(data, matrix)

    status = 0
    if args.check:
        for name, ok, detail in run_checks(data, args.expect_runs):
            print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
            status |= 0 if ok else 1

    md = provenance() + "\n\n" + "\n".join(render_md(t) for t in tables)
    if args.stdout:
        print(md)
        return status
    args.out.mkdir(parents=True, exist_ok=True)
    if args.format in ("md", "both"):
        (args.out / "tables.md").write_text(md, encoding="utf-8")
    if args.format in ("latex", "both"):
        header = "% " + provenance().replace("\n", "\n% ") + "\n\n"
        (args.out / "tables.tex").write_text(header + "\n".join(render_latex(t) for t in tables), encoding="utf-8")
    with (args.out / "verdict_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("round", "prediction", "fidelity", "verdict"))
        writer.writeheader()
        writer.writerows(matrix)
    if args.png:
        if not draw_matrix_png(matrix, args.out / "verdict_matrix.png"):
            print("matplotlib not available; skipped verdict_matrix.png", file=sys.stderr)
    counts = headline_counts(matrix)
    print("headline counts: " + "; ".join(f"{k} {c}/{n}" for k, (c, n) in counts.items()))
    print(f"wrote {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    return status


if __name__ == "__main__":
    sys.exit(main())
