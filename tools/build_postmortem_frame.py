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

"""Build the postmortem sampling frame from official provider indexes.

This is the **scaffold** for M8, not a completed frame.  It parses a saved
official index page per provider, extracts report links and dates, applies the
publication window, merges human eligibility decisions, applies the seeded
40-per-provider sample of section 3 of the frozen protocol, fetches or copies
each report, and writes ``study/frame.csv`` with a SHA-256 of every saved report.

The agent does not code real postmortems and does not declare eligibility.  The
human M8 owner saves the official indexes, reviews eligibility, and runs this
tool.  If the sandbox has no network, the frame step is marked H; the tool still
works offline from ``--index-dir`` and ``--reports-source-dir``.

Usage::

    # 1. save the official indexes (or let --fetch do it)
    py tools/build_postmortem_frame.py --fetch --index-dir study/indexes

    # 2. review study/frame-candidates.csv, write study/eligibility.csv
    py tools/build_postmortem_frame.py --index-dir study/indexes \\
        --eligibility-csv study/eligibility.csv --reports-dir study/reports

The output is not frozen until a human commits ``study/frame.csv`` and the
saved reports before any coding starts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]

WINDOW_START = date(2023, 1, 1)
WINDOW_END = date(2026, 10, 31)
SAMPLE_SIZE = 40
SEED = 2026

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    name: str
    index_url: str
    index_filename: str
    link_pattern: str
    id_prefix: str


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        "aws",
        "AWS",
        "https://aws.amazon.com/premiumsupport/technology/pes/",
        "aws.html",
        r"/premiumsupport/technology/pes/",
        "aws-",
    ),
    ProviderSpec(
        "azure",
        "Microsoft Azure",
        "https://azure.status.microsoft/en-us/status/history/",
        "azure.html",
        r"/status/history/|/status/incident|tracking",
        "az-",
    ),
    ProviderSpec(
        "google",
        "Google Cloud",
        "https://status.cloud.google.com/summary",
        "google.html",
        r"/incidents/",
        "gcp-",
    ),
    ProviderSpec(
        "cloudflare",
        "Cloudflare",
        "https://blog.cloudflare.com/tag/post-mortem/",
        "cloudflare.html",
        r"blog\.cloudflare\.com/",
        "cf-",
    ),
)


@dataclass
class ReportRef:
    incident_id: str
    provider: str
    url: str
    title: str
    publication_date: str = ""
    eligible: str = "review"
    duplicate_of: str = ""
    notes: str = ""


@dataclass
class Anchor:
    href: str
    text: str
    before: str


class AnchorParser(HTMLParser):
    """Collect anchors plus the text immediately before each one."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[Anchor] = []
        self._current: dict[str, str] | None = None
        self._since_anchor = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href", "")
        if href:
            self._current = {"href": href, "text": "", "before": self._since_anchor[-500:]}

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"] += data
        self._since_anchor += data
        if len(self._since_anchor) > 2000:
            self._since_anchor = self._since_anchor[-2000:]

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current is not None:
            self.anchors.append(
                Anchor(
                    href=self._current["href"].strip(),
                    text=" ".join(self._current["text"].split()),
                    before=" ".join(self._current["before"].split()),
                )
            )
            self._current = None
            self._since_anchor = ""


def parse_date(text: str) -> str:
    """Return the first date in ``text`` as ISO, or an empty string."""
    if not text:
        return ""
    iso = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
        return _safe_iso(year, month, day)
    month_first = re.search(
        r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(20\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )
    if month_first:
        month = MONTHS[month_first.group(1).lower()]
        return _safe_iso(int(month_first.group(3)), month, int(month_first.group(2)))
    day_first = re.search(
        r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(20\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )
    if day_first:
        month = MONTHS[day_first.group(2).lower()]
        return _safe_iso(int(day_first.group(3)), month, int(day_first.group(1)))
    return ""


def _safe_iso(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _slug(provider: str, url: str) -> str:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", path.split("/")[-1]).strip("-").lower()
    if not slug:
        slug = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{provider}-{slug}"


def extract_reports(html: str, spec: ProviderSpec) -> list[ReportRef]:
    """Extract report links that match the provider's index pattern."""
    parser = AnchorParser()
    parser.feed(html)
    pattern = re.compile(spec.link_pattern)
    reports: list[ReportRef] = []
    seen: set[str] = set()
    for anchor in parser.anchors:
        href = urllib.parse.urljoin(spec.index_url, anchor.href)
        if not pattern.search(href):
            continue
        # An in-page anchor or the index itself is not a report.
        if href.split("#")[0].rstrip("/") == spec.index_url.rstrip("/"):
            continue
        if href.rstrip("/") == spec.index_url.rstrip("/"):
            continue
        incident_id = _slug(spec.key, href)
        if incident_id in seen:
            continue
        seen.add(incident_id)
        publication_date = parse_date(anchor.text) or parse_date(anchor.before)
        reports.append(
            ReportRef(
                incident_id=incident_id,
                provider=spec.name,
                url=href,
                title=anchor.text or href,
                publication_date=publication_date,
            )
        )
    return reports


def filter_window(
    reports: Sequence[ReportRef],
    start: date = WINDOW_START,
    end: date = WINDOW_END,
) -> list[ReportRef]:
    filtered = []
    for report in reports:
        if not report.publication_date:
            continue
        published = date.fromisoformat(report.publication_date)
        if start <= published <= end:
            filtered.append(report)
    return filtered


def select_sample(
    reports: Sequence[ReportRef],
    sample_size: int = SAMPLE_SIZE,
    seed: int = SEED,
) -> list[ReportRef]:
    """Seeded sample over lexicographically sorted incident IDs, per protocol."""
    ordered = sorted(reports, key=lambda report: report.incident_id)
    if len(ordered) <= sample_size:
        return ordered
    chosen = set(random.Random(seed).sample([r.incident_id for r in ordered], sample_size))
    return [report for report in ordered if report.incident_id in chosen]


def fetch_text(url: str, timeout: float = 30.0) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "7g-postmortem-frame/0.1 (research; contact author)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merge_dates(reports: Sequence[ReportRef], path: Path | None) -> list[ReportRef]:
    if path is None or not path.exists():
        return list(reports)
    mapping = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mapping[row["incident_id"].strip()] = row.get("publication_date", "").strip()
    return [
        replace(report, publication_date=mapping.get(report.incident_id, report.publication_date))
        for report in reports
    ]


def merge_eligibility(
    reports: Sequence[ReportRef], path: Path | None
) -> list[ReportRef]:
    if path is None or not path.exists():
        return [replace(report, eligible="review") for report in reports]
    mapping = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mapping[row["incident_id"].strip()] = row
    merged = []
    for report in reports:
        row = mapping.get(report.incident_id, {})
        merged.append(
            replace(
                report,
                eligible=(row.get("eligible", "review") or "review").strip().lower(),
                duplicate_of=row.get("duplicate_of", "").strip(),
                notes=row.get("notes", "").strip(),
            )
        )
    return merged


def _read_index(index_dir: Path, spec: ProviderSpec) -> str:
    path = index_dir / spec.index_filename
    if not path.exists():
        raise FileNotFoundError(
            f"missing index {path}; save the official index or run with --fetch"
        )
    return path.read_text(encoding="utf-8", errors="replace")


def build_frame(
    index_dir: Path,
    reports_dir: Path,
    providers: Sequence[ProviderSpec] = PROVIDERS,
    start: date = WINDOW_START,
    end: date = WINDOW_END,
    sample_size: int = SAMPLE_SIZE,
    seed: int = SEED,
    dates_csv: Path | None = None,
    eligibility_csv: Path | None = None,
    reports_source_dir: Path | None = None,
    fetch_reports: bool = True,
) -> list[dict[str, str]]:
    """Build frame rows.  Does not write them; see ``write_frame``."""
    frame_rows: list[dict[str, str]] = []
    for spec in providers:
        html = _read_index(index_dir, spec)
        reports = merge_dates(extract_reports(html, spec), dates_csv)
        reports = merge_eligibility(filter_window(reports, start, end), eligibility_csv)
        eligible = [report for report in reports if report.eligible == "yes" and not report.duplicate_of]
        selected = select_sample(eligible, sample_size, seed)
        for report in selected:
            if reports_source_dir is not None:
                source = reports_source_dir / f"{report.incident_id}.txt"
                if not source.exists():
                    raise FileNotFoundError(f"missing saved report {source}")
                data = source.read_bytes()
            elif fetch_reports:
                data = fetch_text(report.url).encode("utf-8")
            else:
                data = b""
            reports_dir.mkdir(parents=True, exist_ok=True)
            target = reports_dir / f"{report.incident_id}.txt"
            if data:
                target.write_bytes(data)
            frame_rows.append(
                {
                    "incident_id": report.incident_id,
                    "provider": report.provider,
                    "report_url": report.url,
                    "report_sha256": hash_bytes(data) if data else "",
                    "publication_date": report.publication_date,
                    "eligible": report.eligible,
                    "duplicate_of": report.duplicate_of,
                    "notes": report.notes,
                }
            )
    return frame_rows


def write_frame(rows: Sequence[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "incident_id",
        "provider",
        "report_url",
        "report_sha256",
        "publication_date",
        "eligible",
        "duplicate_of",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-dir", type=Path, default=ROOT / "study" / "indexes")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "study" / "reports")
    parser.add_argument("--reports-source-dir", type=Path, default=None)
    parser.add_argument("--frame", type=Path, default=ROOT / "study" / "frame.csv")
    parser.add_argument("--dates-csv", type=Path, default=None)
    parser.add_argument("--eligibility-csv", type=Path, default=None)
    parser.add_argument("--window-start", type=date.fromisoformat, default=WINDOW_START)
    parser.add_argument("--window-end", type=date.fromisoformat, default=WINDOW_END)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--provider", choices=[spec.key for spec in PROVIDERS], action="append")
    parser.add_argument("--fetch", action="store_true", help="fetch the official index pages")
    parser.add_argument("--dry-run", action="store_true", help="parse and filter only")
    args = parser.parse_args(list(argv) if argv is not None else None)

    specs = tuple(spec for spec in PROVIDERS if not args.provider or spec.key in args.provider)
    if args.fetch:
        args.index_dir.mkdir(parents=True, exist_ok=True)
        for spec in specs:
            try:
                text = fetch_text(spec.index_url)
            except Exception as error:  # noqa: BLE001 - report the exact fetch problem
                print(f"fetch failed for {spec.name}: {error}")
                return 2
            (args.index_dir / spec.index_filename).write_text(text, encoding="utf-8")
            print(f"saved {spec.index_filename}")
    if args.dry_run:
        for spec in specs:
            html = _read_index(args.index_dir, spec)
            reports = merge_dates(extract_reports(html, spec), args.dates_csv)
            reports = merge_eligibility(
                filter_window(reports, args.window_start, args.window_end),
                args.eligibility_csv,
            )
            eligible = [r for r in reports if r.eligible == "yes" and not r.duplicate_of]
            selected = select_sample(eligible, args.sample_size, args.seed)
            print(f"{spec.name}: {len(reports)} in window, {len(eligible)} eligible, {len(selected)} selected")
        return 0
    rows = build_frame(
        args.index_dir,
        args.reports_dir,
        providers=specs,
        start=args.window_start,
        end=args.window_end,
        sample_size=args.sample_size,
        seed=args.seed,
        dates_csv=args.dates_csv,
        eligibility_csv=args.eligibility_csv,
        reports_source_dir=args.reports_source_dir,
        fetch_reports=args.reports_source_dir is None,
    )
    if not rows:
        print("no eligible incidents; supply --eligibility-csv (the agent does not decide eligibility)")
        return 1
    write_frame(rows, args.frame)
    print(f"wrote {len(rows)} rows to {args.frame}")
    print("next: commit frame.csv and the saved reports before any coding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
