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

"""Assemble and validate one coder's raw rows into ``study/coded_<coder>.csv``.

The coder writes one CSV row per incident into a packet ``rows/`` directory.  This
tool checks every row against the frozen template (field order, allowed values,
frame metadata, report hash) and writes the assembled file in the template's
column order.  A violation is reported and the row is left out; nothing is
silently repaired except the frame metadata and the ``coder`` column, which are
restored from ``study/frame.csv``.

Usage::

    py tools/assemble_coded_rows.py --coder C2 \\
        --rows-dir "$env:TEMP/c2-packet/rows" --out study/coded_c2.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

FIELDS = [
    "incident_id", "provider", "report_url", "report_sha256", "publication_date",
    "coder", "V1_trigger", "V1b_secondary_trigger", "V2_failed_plane",
    "V3_shared_dependency", "V4_blast_radius", "V5_independence_breach",
    "V6_fallback_outcome", "V7_central_controller",
    "V8a_tenant_isolation_retained", "V8b_multipath_or_multiprovider_retained",
    "V8c_tested_local_fallback_retained", "V9_duration_minutes",
    "V10_known_before_freeze", "evidence_V1", "evidence_V2", "evidence_V3",
    "evidence_V4", "evidence_V5", "evidence_V6", "evidence_V7", "evidence_V8",
    "notes",
]

ALLOWED = {
    "V1_trigger": "config_change software_release capacity_or_network_upgrade hardware_or_physical overload_or_cascade security_attack third_party_or_upstream other unclear",
    "V1b_secondary_trigger": "config_change software_release capacity_or_network_upgrade hardware_or_physical overload_or_cascade security_attack third_party_or_upstream other unclear",
    "V2_failed_plane": "data_plane control_plane identity_auth dns_naming config_distribution_orchestration network_backbone_physical storage_or_database_service other unclear",
    "V3_shared_dependency": "shared_global shared_regional localized unclear",
    "V4_blast_radius": "single_zone single_region multi_region global",
    "V5_independence_breach": "yes no unclear",
    "V6_fallback_outcome": "none_mentioned worked failed_or_not_triggered slow_or_manual",
    "V7_central_controller": "yes no unclear",
    "V8a_tenant_isolation_retained": "yes no unclear",
    "V8b_multipath_or_multiprovider_retained": "yes no unclear",
    "V8c_tested_local_fallback_retained": "yes no unclear",
    "V10_known_before_freeze": "yes no",
}
OPTIONAL = {"V1b_secondary_trigger"}


def load_frame(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["incident_id"]: row for row in csv.DictReader(handle)}


def check_row(row: dict[str, str], frame: dict[str, dict[str, str]], coder: str) -> list[str]:
    problems: list[str] = []
    incident_id = row["incident_id"]
    reference = frame.get(incident_id)
    if reference is None:
        return [f"incident not in the frozen frame"]
    if row["report_sha256"] != reference["report_sha256"]:
        problems.append("report_sha256 does not match the frame")
    if row["publication_date"] != reference["publication_date"]:
        problems.append(
            f"publication_date {row['publication_date']!r} != frame {reference['publication_date']!r}"
        )
    if row["provider"] != reference["provider"]:
        problems.append(f"provider {row['provider']!r} != frame {reference['provider']!r}")
    if row["coder"] != coder:
        problems.append(f"coder {row['coder']!r} != {coder}")
    for field, allowed in ALLOWED.items():
        value = row[field].strip()
        if not value:
            if field in OPTIONAL:
                continue
            problems.append(f"{field} is empty")
            continue
        if value not in allowed.split():
            problems.append(f"{field}={value!r} not in the frozen values")
    duration = row["V9_duration_minutes"].strip()
    if duration and duration != "unclear":
        try:
            if int(duration) < 0:
                problems.append("V9_duration_minutes is negative")
        except ValueError:
            problems.append(f"V9_duration_minutes={duration!r} is neither an integer nor unclear")
    if not row["notes"].strip() and not row["evidence_V1"].strip():
        problems.append("no evidence or note")
    return problems


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, default=ROOT / "study" / "frame.csv")
    parser.add_argument("--rows-dir", type=Path, required=True)
    parser.add_argument("--coder", default="C2")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    frame = load_frame(args.frame)
    rows: list[dict[str, str]] = []
    problems: list[str] = []
    seen: set[str] = set()

    for path in sorted(args.rows_dir.glob("*.csv")):
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            problems.append(f"{path.name}: empty file")
            continue
        parsed = list(csv.reader([raw]))
        if len(parsed) != 1 or len(parsed[0]) != len(FIELDS):
            length = len(parsed[0]) if parsed else 0
            problems.append(f"{path.name}: {length} fields, expected {len(FIELDS)}")
            continue
        row = dict(zip(FIELDS, [value.strip() for value in parsed[0]]))
        if row["incident_id"] in seen:
            problems.append(f"{row['incident_id']}: coded twice")
            continue
        issues = check_row(row, frame, args.coder)
        if issues:
            problems.extend(f"{path.name}: {issue}" for issue in issues)
            continue
        reference = frame[row["incident_id"]]
        row["provider"] = reference["provider"]
        row["report_url"] = reference["report_url"]
        row["report_sha256"] = reference["report_sha256"]
        row["publication_date"] = reference["publication_date"]
        row["coder"] = args.coder
        rows.append(row)
        seen.add(row["incident_id"])

    rows.sort(key=lambda row: row["incident_id"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"coded rows written: {len(rows)} of {len(frame)} frame incidents -> {args.out}")
    missing = sorted(set(frame) - seen)
    if missing:
        print(f"not coded ({len(missing)}): " + ", ".join(missing))
    if problems:
        print(f"validation problems ({len(problems)}):")
        for problem in problems[:40]:
            print("  " + problem)
        print(f"file written anyway; {len(problems)} problems to review", file=sys.stderr)
    else:
        print("validation: 0 problems")
    return 0 if not problems else 4


if __name__ == "__main__":
    raise SystemExit(main())
