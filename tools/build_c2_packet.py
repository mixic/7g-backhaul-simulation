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

"""Build the isolated C2 coding packet for the postmortem study (M8).

The frozen protocol requires that C2 receives **only** the coder prompt, the
codebook and one report at a time, and never the predictions, the hypotheses or
another coder's codes.  This tool materialises exactly that packet outside the
repository, so a coder session cannot wander into ``docs/``:

    <packet>/PROMPT.md          the frozen prompt with its header filled
    <packet>/codebook.md        section 4 of the frozen protocol
    <packet>/items/<id>.md      one report, its frame metadata and its hash
    <packet>/index.csv          incident id, hash, provider, date, report bytes
    <packet>/rows/              where the coder writes its one-row CSV answers

Every report hash is checked against ``study/frame.csv`` before an item is
written; a mismatch stops the build.

Usage::

    py tools/build_c2_packet.py --frame study/frame.csv \\
        --reports-dir study/reports --codebook study/c2-packet/codebook.md \\
        --out "$env:TEMP/c2-packet" --model "deepseek-official/deepseek-flash"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

FIELDS = [
    "incident_id",
    "provider",
    "report_url",
    "report_sha256",
    "publication_date",
    "coder",
    "V1_trigger",
    "V1b_secondary_trigger",
    "V2_failed_plane",
    "V3_shared_dependency",
    "V4_blast_radius",
    "V5_independence_breach",
    "V6_fallback_outcome",
    "V7_central_controller",
    "V8a_tenant_isolation_retained",
    "V8b_multipath_or_multiprovider_retained",
    "V8c_tested_local_fallback_retained",
    "V9_duration_minutes",
    "V10_known_before_freeze",
    "evidence_V1",
    "evidence_V2",
    "evidence_V3",
    "evidence_V4",
    "evidence_V5",
    "evidence_V6",
    "evidence_V7",
    "evidence_V8",
    "notes",
]

PROMPT_HEADER = """# Postmortem coder prompt (C2) -- instantiated

| Field | Value |
|---|---|
| Coder ID | C2 |
| Model name | `{model}` |
| Model version / API snapshot | {version} |
| Prompt commit | {prompt_commit} |
| Codebook commit | {codebook_commit} |
| Date coding started | {date} |
| Frame commit | {frame_commit} |
| Items to code | {items} (one report per session) |

This is the only material the C2 coder receives: this prompt, `codebook.md` and
one file from `items/`. The coder does not receive the predictions (E1-E8), the
hypotheses, another coder's codes, or any summary of the expected result.
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_frame(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_packet(
    frame_rows: list[dict[str, str]],
    reports_dir: Path,
    codebook: Path,
    out_dir: Path,
    header_values: dict[str, str],
) -> tuple[int, list[str]]:
    """Write the packet; return the item count and any hash mismatches."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "items").mkdir(parents=True)
    (out_dir / "rows").mkdir(parents=True)
    shutil.copyfile(codebook, out_dir / "codebook.md")
    frozen_prompt = ROOT / "docs" / "postmortem-coder-prompt.md"
    body = frozen_prompt.read_text(encoding="utf-8")
    (out_dir / "PROMPT.md").write_text(
        PROMPT_HEADER.format(**header_values)
        + "\n## Frozen prompt text (verbatim from docs/postmortem-coder-prompt.md)\n\n"
        + body,
        encoding="utf-8",
    )

    mismatches: list[str] = []
    index_rows: list[list[str]] = []
    for row in frame_rows:
        incident_id = row["incident_id"]
        report_path = reports_dir / f"{incident_id}.txt"
        if not report_path.exists():
            mismatches.append(f"{incident_id}: report missing")
            continue
        data = report_path.read_bytes()
        digest = sha256_bytes(data)
        if digest != row["report_sha256"]:
            mismatches.append(f"{incident_id}: hash {digest} != frame {row['report_sha256']}")
            continue
        text = data.decode("utf-8", errors="replace")
        item = (
            f"incident_id: {incident_id}\n"
            f"report_sha256: {digest}\n"
            f"provider: {row['provider']}\n"
            f"publication_date: {row['publication_date']}\n\n"
            f"{text}\n"
        )
        (out_dir / "items" / f"{incident_id}.md").write_text(item, encoding="utf-8")
        index_rows.append(
            [
                incident_id,
                digest,
                row["provider"],
                row["publication_date"],
                str(len(data)),
            ]
        )

    with (out_dir / "index.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["incident_id", "report_sha256", "provider", "publication_date", "bytes"])
        writer.writerows(index_rows)
    return len(index_rows), mismatches


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, default=ROOT / "study" / "frame.csv")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "study" / "reports")
    parser.add_argument(
        "--codebook", type=Path, default=ROOT / "study" / "c2-packet" / "codebook.md"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="deepseek-official/deepseek-flash")
    parser.add_argument("--version", default="DSH harness session model; no separate API snapshot exposed")
    parser.add_argument("--prompt-commit", default="(this commit)")
    parser.add_argument("--codebook-commit", default="(this commit)")
    parser.add_argument("--frame-commit", default="(this commit)")
    parser.add_argument("--date", default="")
    args = parser.parse_args(list(argv) if argv is not None else None)

    date = args.date or __import__("datetime").date.today().isoformat()
    rows = load_frame(args.frame)
    header = {
        "model": args.model,
        "version": args.version,
        "prompt_commit": args.prompt_commit,
        "codebook_commit": args.codebook_commit,
        "frame_commit": args.frame_commit,
        "date": date,
        "items": str(len(rows)),
    }
    count, mismatches = build_packet(
        rows, args.reports_dir, args.codebook, args.out, header
    )
    print(f"wrote {count} items to {args.out}")
    if mismatches:
        for problem in mismatches[:10]:
            print(f"hash problem: {problem}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
