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

"""Collect the M8 postmortem frame from the four official provider sources.

The frozen protocol fixes the publication window, the seeded sample size, the
seed and the eligibility rules (section 3 of
``docs/postmortem-study-predictions.md``); ``tools/build_postmortem_frame.py``
holds those constants and the sampling function.  This module only supplies the
part that could not be written until the four official indexes were fetched: the
per-provider extractors.

What each provider actually serves (checked 19 November 2026):

* **AWS** -- ``aws.amazon.com/premiumsupport/technology/pes/`` lists every
  Post-Event Summary as a plain ``/message/<id>/`` anchor with the date in the
  text *after* the anchor.  Report pages are server-rendered.
* **Cloudflare** -- ``blog.cloudflare.com/tag/post-mortem/`` is a static tag
  page; each post is a static page.  The original link parser handles it.
* **Google Cloud** -- ``status.cloud.google.com/summary`` lists affected
  products, not incidents.  Every product has a static
  ``products/<key>/history`` table with one row per incident: summary link,
  date and duration.  Crawling those tables enumerates the whole incident
  history without executing JavaScript.
* **Microsoft Azure** -- ``azure.status.microsoft/en-us/status/history/`` is
  server-rendered but pinned to "last 90 days"; the range dropdown is applied
  client-side and no query parameter changes the rendered range.  The historical
  PIRs are recovered from Internet Archive snapshots of the *same official
  page*, one snapshot per month, deduplicated by tracking ID.

Every raw page used is saved under ``study/indexes/`` and hashed, so the frame
can be rebuilt and the sample re-checked offline with
``--reports-source-dir`` / ``--index-cache``.

The tool does **not** code, and it does not decide eligibility on its own
authority: it applies the frozen rules mechanically, writes one row per
candidate with the reason, and marks the frame ``origin=agent`` so the human M8
owner can sign off or overrule any row.

Usage::

    # 1. fetch the indexes and the archived Azure snapshots, cache everything
    py tools/collect_postmortem_frame.py --fetch --cache-dir study/indexes

    # 2. enumerate candidates and inspect the eligibility decisions
    py tools/collect_postmortem_frame.py --dry-run --cache-dir study/indexes

    # 3. write the candidates list, the seed sample, the reports and the frame
    py tools/collect_postmortem_frame.py --cache-dir study/indexes \
        --reports-dir study/reports --frame study/frame.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html as html_module
import importlib.util
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "build_postmortem_frame", ROOT / "tools" / "build_postmortem_frame.py"
)
bf = importlib.util.module_from_spec(_SPEC)
sys.modules["build_postmortem_frame"] = bf
_SPEC.loader.exec_module(bf)

HTTP_HEADERS = {
    "User-Agent": "7g-postmortem-frame/0.2 (research; contact author)",
    "Accept-Language": "en",
}
WAYBACK_PREFIX = "https://web.archive.org/web/"

# Eligibility rules, section 3 of the frozen protocol (quoted in study/README.md).
MIN_IMPACT_MINUTES = 30

PLANNED_PATTERNS = (
    r"\bplanned\s+maintenance\b",
    r"\bscheduled\s+maintenance\b",
    r"\bmaintenance\s+window\b",
    r"\bdeprecation\b",
    r"\bend\s+of\s+(support|life)\b",
)
BREACH_PATTERNS = (
    r"\bdata\s+breach\b",
    r"\bsecurity\s+breach\b",
    r"\bunauthori[sz]ed\s+access\s+to\s+customer\s+data\b",
    r"\bexfiltrat",
)
SINGLE_CUSTOMER_PATTERNS = (
    r"\bsingle[- ]customer\b",
    r"\bone[- ]customer\b",
)


@dataclass
class Candidate:
    incident_id: str
    provider: str
    url: str
    title: str
    publication_date: str = ""
    duration_minutes: str = ""
    source: str = ""
    source_sha256: str = ""
    eligible: str = "review"
    duplicate_of: str = ""
    notes: str = ""
    report_sha256: str = ""
    extra: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# text extraction
# --------------------------------------------------------------------------- #

_DROP_BLOCKS = re.compile(
    r"<(script|style|svg|noscript|nav|header|footer)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_BLOCK_TAG = re.compile(
    r"</?(p|div|br|li|ul|ol|tr|td|th|table|h[1-6]|section|article|main|blockquote|pre)\b[^>]*>",
    re.IGNORECASE,
)
_ANY_TAG = re.compile(r"<[^>]+>", re.DOTALL)
_WS = re.compile(r"[ \t\r\f\v\xa0]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def html_to_text(html: str) -> str:
    """Convert an HTML document to plain text without a third-party parser."""
    if not html:
        return ""
    text = _DROP_BLOCKS.sub(" ", html)
    text = _BLOCK_TAG.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = html_module.unescape(text)
    lines = [_WS.sub(" ", line).strip() for line in text.split("\n")]
    kept = [line for line in lines if line]
    return _BLANK_LINES.sub("\n\n", "\n".join(kept)).strip()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# fetching with an offline cache
# --------------------------------------------------------------------------- #

@dataclass
class Fetcher:
    """Fetch a URL once, cache the raw bytes, and record failures by name."""

    cache_dir: Path | None = None
    refresh: bool = False
    timeout: float = 45.0
    failures: list[tuple[str, str]] = field(default_factory=list)

    def get(self, url: str, cache_name: str | None = None) -> str:
        if self.cache_dir is not None and cache_name is not None and not self.refresh:
            path = self.cache_dir / cache_name
            if path.exists():
                return path.read_text(encoding="utf-8", errors="replace")
        request = urllib.request.Request(url, headers=HTTP_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            self.failures.append((url, str(error)))
            return ""
        text = raw.decode("utf-8", errors="replace")
        if self.cache_dir is not None and cache_name is not None:
            path = self.cache_dir / cache_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return text


def _slug(text: str, limit: int = 60) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug[:limit].strip("-")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# AWS Post-Event Summaries
# --------------------------------------------------------------------------- #

_AWS_ANCHOR = re.compile(
    r'<a\s+href="(?P<href>https?://aws\.amazon\.com/message/[^"]+|/message/[^"]+)"'
    r'[^>]*>(?P<title>.*?)</a>(?P<after>(?:(?!<a\s).){0,220})',
    re.IGNORECASE | re.DOTALL,
)


def extract_aws(html: str, base: str = "https://aws.amazon.com/") -> list[Candidate]:
    """Extract AWS PES anchors; the publication date follows the anchor text."""
    out: list[Candidate] = []
    seen: set[str] = set()
    for match in _AWS_ANCHOR.finditer(html):
        url = urllib.parse.urljoin(base, match.group("href"))
        path = urllib.parse.urlparse(url).path.rstrip("/")
        key = path.split("/")[-1]
        if not key or key in seen:
            continue
        seen.add(key)
        title = html_to_text(match.group("title"))
        after = html_to_text(match.group("after"))
        published = bf.parse_date(after)
        out.append(
            Candidate(
                incident_id=f"aws-{key.lower()}",
                provider="AWS",
                url=url,
                title=title,
                publication_date=published,
                source="aws-pes",
                extra={"note": "date read from the text after the anchor"},
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Cloudflare post-mortems
# --------------------------------------------------------------------------- #

# The tag page links author and tag pages as well as posts; a post is a single
# non-reserved path segment.
CF_RESERVED_PREFIXES = {
    "author", "tag", "category", "tag-cloud", "page", "series", "search",
    "press-release", "sponsorships", "integration", "webinars",
}


def is_cloudflare_post(url: str) -> bool:
    segments = [part for part in urllib.parse.urlparse(url).path.split("/") if part]
    if len(segments) != 1:
        return False
    return segments[0].lower() not in CF_RESERVED_PREFIXES


def extract_cloudflare(html: str) -> list[Candidate]:
    """Reuse the frozen link parser for the Cloudflare tag page."""
    spec = next(spec for spec in bf.PROVIDERS if spec.key == "cloudflare")
    out: list[Candidate] = []
    for report in bf.extract_reports(html, spec):
        if not is_cloudflare_post(report.url):
            continue
        out.append(
            Candidate(
                incident_id=report.incident_id,
                provider=report.provider,
                url=report.url,
                title=report.title,
                publication_date=report.publication_date,
                source="cloudflare-tag",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Google Cloud incident history
# --------------------------------------------------------------------------- #

_GCP_PRODUCT_LINK = re.compile(
    r'href="(?:\.\./)*(?:products/)?(?P<key>[A-Za-z0-9_-]{12,40})/history"'
)
_GCP_ROW = re.compile(
    r"<tr\b(?P<row>.*?)</tr>", re.IGNORECASE | re.DOTALL
)
_GCP_ROW_LINK = re.compile(
    r'href="(?P<href>(?:\.\./)*incidents/[A-Za-z0-9]+)"', re.IGNORECASE
)
_GCP_TD_DATE = re.compile(
    r'class="[^"]*__date"[^>]*>(?P<value>.*?)</td>', re.IGNORECASE | re.DOTALL
)
_GCP_TD_DURATION = re.compile(
    r'class="[^"]*__duration-text"[^>]*>(?P<value>.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)
_DURATION_PART = re.compile(r"(?P<count>\d+)\s*(?P<unit>day|hr|hour|min|sec)", re.I)
_DURATION_FACTORS = {
    "day": 1440,
    "hr": 60,
    "hour": 60,
    "min": 1,
    "sec": 0.0,
}


def parse_duration_minutes(text: str) -> str:
    """Parse '1 hr, 23 min' / '2 days, 4 hr' / '45 min' into minutes as a string."""
    if not text:
        return ""
    total = 0.0
    found = False
    for match in _DURATION_PART.finditer(text):
        found = True
        total += float(match.group("count")) * _DURATION_FACTORS[
            match.group("unit").lower()
        ]
    if not found:
        return ""
    return str(int(round(total)))


def product_keys(summary_html: str) -> list[str]:
    """Unique Google product keys linked from the status summary page."""
    keys: list[str] = []
    seen: set[str] = set()
    for match in _GCP_PRODUCT_LINK.finditer(summary_html):
        key = match.group("key")
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def extract_gcp_history(history_html: str) -> list[Candidate]:
    """Extract incident rows (link, summary, date, duration) from a product page."""
    out: list[Candidate] = []
    for row_match in _GCP_ROW.finditer(history_html):
        row = row_match.group("row")
        link = _GCP_ROW_LINK.search(row)
        if not link:
            continue
        href = urllib.parse.urljoin(
            "https://status.cloud.google.com/", link.group("href")
        )
        incident_id = href.rstrip("/").split("/")[-1]
        summary = ""
        summary_match = re.search(
            r'class="[^"]*__summary-text"[^>]*>(?P<value>.*?)</span>',
            row,
            re.DOTALL,
        )
        if summary_match:
            summary = html_to_text(summary_match.group("value"))
        if not summary:
            summary = html_to_text(_ANY_TAG.sub(" ", row))
        date_match = _GCP_TD_DATE.search(row)
        published = bf.parse_date(html_to_text(date_match.group("value"))) if date_match else ""
        duration_match = _GCP_TD_DURATION.search(row)
        duration = (
            parse_duration_minutes(html_to_text(duration_match.group("value")))
            if duration_match
            else ""
        )
        out.append(
            Candidate(
                incident_id=f"gcp-{incident_id}",
                provider="Google Cloud",
                url=f"https://status.cloud.google.com/incidents/{incident_id}",
                title=summary,
                publication_date=published,
                duration_minutes=duration,
                source="gcp-product-history",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Azure PIRs from Internet Archive snapshots of the official history page
# --------------------------------------------------------------------------- #

_AZ_BLOCK = re.compile(
    r'data-target="#incident-history-collapse-(?P<track>[A-Za-z0-9-]+)"'
    r".*?"
    r'class="hide-text">(?P<date>[0-9/]{8,10})</span>'
    r".*?"
    r'class="[^"]*incident-history-title"[^>]*>(?P<title>.*?)</div>'
    r".*?"
    r'id="incident-history-collapse-(?P=track)"[^>]*>(?P<body>.*?)'
    r"</div>\s*</div>\s*</div>\s*</div>\s*</div>",
    re.IGNORECASE | re.DOTALL,
)


def _az_date(value: str) -> str:
    parts = value.strip().split("/")
    if len(parts) != 3:
        return ""
    month, day, year = (int(part) for part in parts)
    return bf._safe_iso(year, month, day)


def extract_azure(archived_html: str) -> list[Candidate]:
    """Extract Azure PIR blocks (tracking id, date, title, body) from a snapshot."""
    out: list[Candidate] = []
    for match in _AZ_BLOCK.finditer(archived_html):
        track = match.group("track").strip()
        body = html_to_text(match.group("body"))
        out.append(
            Candidate(
                incident_id=f"az-{track.lower()}",
                provider="Microsoft Azure",
                url=(
                    "https://azure.status.microsoft/en-us/status/history/"
                    f"#incident-history-collapse-{track}"
                ),
                title=html_to_text(match.group("title")),
                publication_date=_az_date(match.group("date")),
                source="azure-history-archive",
                extra={"tracking_id": track, "body_text": body},
            )
        )
    return out


def wayback_snapshots(
    fetcher: "Fetcher",
    url: str,
    start: date,
    end: date,
    cache_name: str,
) -> list[str]:
    """Monthly Internet Archive snapshot URLs for ``url`` inside the window."""
    cdx = (
        "http://web.archive.org/cdx/search/cdx"
        f"?url={urllib.parse.quote(url, safe='')}"
        f"&from={start:%Y%m%d}&to={end:%Y%m%d}"
        "&output=json&collapse=timestamp:6&filter=statuscode:200"
        "&fl=timestamp,original"
    )
    payload = fetcher.get(cdx, cache_name)
    if not payload:
        return []
    import json

    try:
        rows = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not rows or len(rows) < 2:
        return []
    snapshots: list[str] = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        snapshots.append(f"{WAYBACK_PREFIX}{row[0]}id_/{row[1]}")
    return snapshots


# --------------------------------------------------------------------------- #
# eligibility
# --------------------------------------------------------------------------- #

_MINUTES_CLAIM = re.compile(
    r"(?P<count>\d+(?:\.\d+)?)\s*(?P<unit>minutes?|hours?|hrs?)\b", re.IGNORECASE
)
_ZONES = r"(?:UTC|GMT|PDT|PST|PT|EDT|EST|ET)"
_TIME_PAIR = re.compile(
    r"(?P<h1>\d{1,2}:\d{2})\s*(?P<ampm1>AM|PM)?\s*" + _ZONES +
    r".{0,120}?(?P<h2>\d{1,2}:\d{2})\s*(?P<ampm2>AM|PM)?\s*" + _ZONES,
    re.IGNORECASE | re.DOTALL,
)


def _clock_to_minutes(clock: str, ampm: str) -> int:
    hour_text, minute_text = clock.split(":")
    hour = int(hour_text)
    if ampm:
        if ampm.upper() == "PM" and hour != 12:
            hour += 12
        elif ampm.upper() == "AM" and hour == 12:
            hour = 0
    return (hour % 24) * 60 + int(minute_text)


def stated_impact_minutes(text: str) -> tuple[str, str, str]:
    """Best-effort minutes of stated customer impact, the phrase, and its kind.

    ``kind`` is ``"claim"`` for an explicit duration ("failed for 47 minutes") and
    ``"pair"`` for a span between two clock times.  A pair can be a diagnostic
    timeline rather than the customer-impact window, so only a claim is used to
    *gate* eligibility; a pair is recorded as information and the row is kept with
    a note.  Returns ``("", "", "")`` when the text states nothing.
    """
    if not text:
        return "", "", ""
    for match in _TIME_PAIR.finditer(text):
        start = _clock_to_minutes(match.group("h1"), match.group("ampm1") or "")
        end = _clock_to_minutes(match.group("h2"), match.group("ampm2") or "")
        if end == start:
            continue
        if end < start:
            end += 24 * 60
        span = end - start
        if 0 < span < 24 * 60:
            return str(span), match.group(0)[:120].replace("\n", " "), "pair"
    claim = _MINUTES_CLAIM.search(text)
    if claim:
        count = float(claim.group("count"))
        unit = claim.group("unit").lower()
        minutes = count if unit.startswith("min") else count * 60
        return str(int(round(minutes))), claim.group(0), "claim"
    return "", "", ""


def _matches(patterns: Sequence[str], text: str) -> str:
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    return ""


def decide_eligibility(candidate: Candidate) -> Candidate:
    """Apply the frozen eligibility rules to one candidate, with the reason."""
    text = f"{candidate.title} {candidate.extra.get('body_text', '')}"
    reasons: list[str] = []

    planned = _matches(PLANNED_PATTERNS, text)
    if planned:
        reasons.append(f"planned or deprecation ({planned})")

    breach = _matches(BREACH_PATTERNS, text)
    if breach:
        reasons.append(f"security breach disclosure ({breach})")

    single = _matches(SINGLE_CUSTOMER_PATTERNS, text)
    if single:
        reasons.append(f"single customer ({single})")

    duration_note = ""
    minutes: int | None = None
    source = ""
    if candidate.duration_minutes:
        try:
            minutes = int(candidate.duration_minutes)
            source = "index"
        except ValueError:
            minutes = None
    if minutes is None:
        body = candidate.extra.get("body_text", "")
        claimed, phrase, kind = stated_impact_minutes(body)
        if claimed:
            minutes = int(claimed)
            source = f"report text {kind}: {phrase!r}"

    if minutes is None:
        duration_note = "impact duration not verifiable from index or text; flagged for review"
    elif minutes < MIN_IMPACT_MINUTES:
        reasons.append(f"impact {minutes} min < {MIN_IMPACT_MINUTES} ({source})")
    else:
        duration_note = f"impact {minutes} min ({source})"

    notes = "; ".join(reasons)
    if not reasons and duration_note:
        notes = duration_note
    return replace(
        candidate,
        eligible="no" if reasons else "yes",
        notes=notes,
    )


def apply_eligibility_overrides(
    candidates: Sequence[Candidate], path: Path | None
) -> list[Candidate]:
    """Apply ``study/eligibility.csv`` decisions over the mechanical rules."""
    if path is None or not path.exists():
        return list(candidates)
    mapping: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("incident_id") or "").strip()
            if key:
                mapping[key] = row
    merged: list[Candidate] = []
    for candidate in candidates:
        row = mapping.get(candidate.incident_id)
        if not row:
            merged.append(candidate)
            continue
        eligible = (row.get("eligible") or candidate.eligible).strip().lower()
        notes = (row.get("notes") or "").strip()
        merged.append(
            replace(
                candidate,
                eligible=eligible,
                duplicate_of=(row.get("duplicate_of") or "").strip(),
                notes=f"eligibility.csv: {notes}" if notes else candidate.notes,
            )
        )
    return merged


def merge_duplicates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Keep one row per incident id, preferring a dated row and the longest title."""
    by_id: dict[str, Candidate] = {}
    for candidate in candidates:
        current = by_id.get(candidate.incident_id)
        if current is None:
            by_id[candidate.incident_id] = candidate
            continue
        merged = current
        if not merged.publication_date and candidate.publication_date:
            merged = replace(merged, publication_date=candidate.publication_date)
        if not merged.duration_minutes and candidate.duration_minutes:
            merged = replace(merged, duration_minutes=candidate.duration_minutes)
        if len(candidate.title) > len(merged.title):
            merged = replace(merged, title=candidate.title)
        if candidate.extra.get("body_text") and not merged.extra.get("body_text"):
            merged = replace(
                merged,
                extra={**merged.extra, "body_text": candidate.extra["body_text"]},
            )
        if merged is not current:
            by_id[candidate.incident_id] = merged
    return list(by_id.values())


def in_window(candidate: Candidate, start: date, end: date) -> bool:
    if not candidate.publication_date:
        return False
    try:
        published = date.fromisoformat(candidate.publication_date)
    except ValueError:
        return False
    return start <= published <= end


# --------------------------------------------------------------------------- #
# report text
# --------------------------------------------------------------------------- #

_AWS_MAIN = re.compile(
    r'<main\b[^>]*>(?P<body>.*?)</main>', re.IGNORECASE | re.DOTALL
)
_CF_ARTICLE = re.compile(
    r'<article\b[^>]*>(?P<body>.*?)</article>', re.IGNORECASE | re.DOTALL
)
_GCP_BODY = re.compile(r"(?is)<table\b[^>]*>(?P<body>.*?)</table>")


def report_text(candidate: Candidate, page_html: str) -> str:
    """Extract the readable report body for one incident."""
    if candidate.provider == "Microsoft Azure":
        body = candidate.extra.get("body_text", "")
        header = f"{candidate.title}\n\nTracking ID: {candidate.extra.get('tracking_id', '')}\n"
        return f"{candidate.title}\n\n{header}\n{body}".strip()
    if not page_html:
        return ""
    match = None
    if candidate.provider == "AWS":
        match = _AWS_MAIN.search(page_html)
    elif candidate.provider == "Cloudflare":
        match = _CF_ARTICLE.search(page_html) or _AWS_MAIN.search(page_html)
    elif candidate.provider == "Google Cloud":
        match = _GCP_BODY.search(page_html)
    body_html = match.group("body") if match else page_html
    body = html_to_text(body_html)
    header = f"# {candidate.title}\n\nURL: {candidate.url}\nPublished: {candidate.publication_date}\n\n"
    return header + body


def fetch_report(
    fetcher: Fetcher, candidate: Candidate, cache_name: str
) -> str:
    if candidate.provider == "Microsoft Azure":
        return report_text(candidate, "")
    page = fetcher.get(candidate.url, cache_name)
    if not page:
        return ""
    return report_text(candidate, page)


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #

def collect_candidates(
    fetcher: Fetcher,
    providers: Sequence[str],
    start: date,
    end: date,
    eligibility_csv: Path | None = None,
) -> list[Candidate]:
    candidates: list[Candidate] = []

    if "aws" in providers:
        html = fetcher.get(
            "https://aws.amazon.com/premiumsupport/technology/pes/", "aws.html"
        )
        candidates.extend(extract_aws(html))

    if "cloudflare" in providers:
        html = fetcher.get("https://blog.cloudflare.com/tag/post-mortem/", "cloudflare.html")
        candidates.extend(extract_cloudflare(html))

    if "google" in providers:
        summary = fetcher.get("https://status.cloud.google.com/summary", "google-summary.html")
        keys = product_keys(summary)
        for key in keys:
            page = fetcher.get(
                f"https://status.cloud.google.com/products/{key}/history",
                f"gcp-products/{key}.html",
            )
            if page:
                candidates.extend(extract_gcp_history(page))

    if "azure" in providers:
        snapshots = wayback_snapshots(
            fetcher,
            "https://azure.status.microsoft/en-us/status/history/",
            start,
            end,
            "azure-cdx.json",
        )
        for snapshot in snapshots:
            stamp = snapshot.split("/web.archive.org/web/")[-1].split("/")[0]
            page = fetcher.get(snapshot, f"azure-archive/{stamp}.html")
            if page:
                candidates.extend(extract_azure(page))

    merged = merge_duplicates(candidates)
    windowed = [candidate for candidate in merged if in_window(candidate, start, end)]
    decided = [decide_eligibility(candidate) for candidate in windowed]
    decided = apply_eligibility_overrides(decided, eligibility_csv)
    return sorted(decided, key=lambda c: (c.provider, c.incident_id))


def write_index_manifest(cache_dir: Path, path: Path) -> int:
    """Record every cached page with its URL and SHA-256 (audit trail)."""
    rows: list[tuple[str, str, str, int, str]] = []
    top = {
        "aws.html": "https://aws.amazon.com/premiumsupport/technology/pes/",
        "cloudflare.html": "https://blog.cloudflare.com/tag/post-mortem/",
        "google-summary.html": "https://status.cloud.google.com/summary",
        "azure-cdx.json": (
            "http://web.archive.org/cdx/search/cdx?url="
            "https://azure.status.microsoft/en-us/status/history/"
        ),
    }
    for name, url in top.items():
        file = cache_dir / name
        if file.exists():
            rows.append(
                ("index", url, name, file.stat().st_size, _sha256(file.read_text(encoding="utf-8", errors="replace")))
            )
    for file in sorted((cache_dir / "gcp-products").glob("*.html")):
        url = f"https://status.cloud.google.com/products/{file.stem}/history"
        rows.append(
            ("product-history", url, f"gcp-products/{file.name}", file.stat().st_size,
             _sha256(file.read_text(encoding="utf-8", errors="replace")))
        )
    for file in sorted((cache_dir / "azure-archive").glob("*.html")):
        stamp = file.name.split("id_")[0]
        url = (
            f"{WAYBACK_PREFIX}{stamp}id_/"
            "https://azure.status.microsoft/en-us/status/history/"
        )
        rows.append(
            ("azure-snapshot", url, f"azure-archive/{file.name}", file.stat().st_size,
             _sha256(file.read_text(encoding="utf-8", errors="replace")))
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kind", "url", "local_path", "bytes", "sha256"])
        writer.writerows(rows)
    return len(rows)


def write_candidates(rows: Sequence[Candidate], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "incident_id",
                "provider",
                "report_url",
                "title",
                "publication_date",
                "duration_minutes",
                "source",
                "eligible",
                "duplicate_of",
                "notes",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.incident_id,
                    row.provider,
                    row.url,
                    row.title,
                    row.publication_date,
                    row.duration_minutes,
                    row.source,
                    row.eligible,
                    row.duplicate_of,
                    row.notes,
                ]
            )


def write_frame(rows: Sequence[Candidate], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "incident_id",
                "provider",
                "report_url",
                "report_sha256",
                "publication_date",
                "eligible",
                "duplicate_of",
                "notes",
                "duration_minutes",
                "origin",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.incident_id,
                    row.provider,
                    row.url,
                    row.report_sha256,
                    row.publication_date,
                    row.eligible,
                    row.duplicate_of,
                    row.notes,
                    row.duration_minutes,
                    "agent",
                ]
            )


def sample_eligible(
    rows: Sequence[Candidate], sample_size: int, seed: int
) -> list[Candidate]:
    """Seed-sample per provider with the frozen function and seed."""
    out: list[Candidate] = []
    providers = sorted({row.provider for row in rows})
    for provider in providers:
        eligible = [
            row for row in rows if row.provider == provider and row.eligible == "yes"
        ]
        eligible.sort(key=lambda row: row.incident_id)
        chosen = bf.select_sample(
            eligible,  # type: ignore[arg-type]
            sample_size,
            seed,
        )
        out.extend(chosen)
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "study" / "indexes")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "study" / "reports")
    parser.add_argument("--reports-source-dir", type=Path, default=None)
    parser.add_argument("--frame", type=Path, default=ROOT / "study" / "frame.csv")
    parser.add_argument("--eligibility-csv", type=Path, default=None)
    parser.add_argument(
        "--candidates", type=Path, default=ROOT / "study" / "frame-candidates.csv"
    )
    parser.add_argument("--window-start", type=date.fromisoformat, default=bf.WINDOW_START)
    parser.add_argument("--window-end", type=date.fromisoformat, default=bf.WINDOW_END)
    parser.add_argument("--sample-size", type=int, default=bf.SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=bf.SEED)
    parser.add_argument(
        "--provider",
        choices=["aws", "cloudflare", "google", "azure"],
        action="append",
    )
    parser.add_argument("--fetch", action="store_true", help="refresh the cached pages")
    parser.add_argument(
        "--manifest", type=Path, default=None,
        help="write the cached-page manifest (URL + SHA-256) to this path",
    )
    parser.add_argument("--dry-run", action="store_true", help="enumerate only")
    args = parser.parse_args(list(argv) if argv is not None else None)

    providers = args.provider or ["aws", "cloudflare", "google", "azure"]
    fetcher = Fetcher(cache_dir=args.cache_dir, refresh=args.fetch)
    rows = collect_candidates(
        fetcher,
        providers,
        args.window_start,
        args.window_end,
        eligibility_csv=args.eligibility_csv,
    )

    if fetcher.failures:
        for url, error in fetcher.failures[:10]:
            print(f"fetch failed: {url}: {error}")

    if args.manifest is not None:
        count = write_index_manifest(args.cache_dir, args.manifest)
        print(f"wrote {count} manifest rows to {args.manifest}")

    write_candidates(rows, args.candidates)
    by_provider: dict[str, list[Candidate]] = {}
    for row in rows:
        by_provider.setdefault(row.provider, []).append(row)
    for provider in sorted(by_provider):
        group = by_provider[provider]
        eligible = [row for row in group if row.eligible == "yes"]
        print(
            f"{provider}: {len(group)} candidates in window, "
            f"{len(eligible)} eligible"
        )

    if args.dry_run:
        return 0

    selected = sample_eligible(rows, args.sample_size, args.seed)
    if not selected:
        print("no eligible incidents")
        return 1

    missing: list[str] = []
    dropped: list[Candidate] = []
    kept: list[Candidate] = []
    for candidate in selected:
        cache_name = f"reports/{candidate.incident_id}.html"
        if args.reports_source_dir is not None:
            source = args.reports_source_dir / f"{candidate.incident_id}.txt"
            if not source.exists():
                missing.append(candidate.incident_id)
                continue
            text = source.read_text(encoding="utf-8")
        else:
            text = fetch_report(fetcher, candidate, cache_name)
        if not text.strip():
            missing.append(candidate.incident_id)
            continue
        # Post-fetch eligibility check: the index is silent for AWS, Cloudflare
        # and Azure, so the stated impact is read from the report text.  A stated
        # impact below the frozen minimum removes the row and is reported.
        if not candidate.duration_minutes:
            claimed, phrase, kind = stated_impact_minutes(text)
            if claimed:
                candidate = replace(
                    candidate,
                    duration_minutes=claimed,
                    notes=(candidate.notes + "; " if candidate.notes else "")
                    + f"post-fetch impact {claimed} min ({kind}: {phrase!r})",
                )
                if kind == "claim" and int(claimed) < MIN_IMPACT_MINUTES:
                    dropped.append(
                        replace(
                            candidate,
                            eligible="no",
                            notes=candidate.notes
                            + f"; dropped: stated impact < {MIN_IMPACT_MINUTES} min",
                        )
                    )
                    continue
            else:
                candidate = replace(
                    candidate,
                    notes=(candidate.notes + "; " if candidate.notes else "")
                    + "post-fetch: impact not stated in the text",
                )
        candidate.report_sha256 = _sha256(text)
        kept.append(candidate)
        args.reports_dir.mkdir(parents=True, exist_ok=True)
        # write bytes: Path.write_text translates newlines on Windows and the
        # frame hashes the text, so a text-mode write would break every hash
        (args.reports_dir / f"{candidate.incident_id}.txt").write_bytes(
            text.encode("utf-8")
        )

    written = [candidate for candidate in kept if candidate.report_sha256]
    write_frame(written, args.frame)
    if dropped:
        write_candidates(dropped, args.frame.with_name("frame-dropped.csv"))
        print(f"dropped {len(dropped)} rows after the post-fetch check: frame-dropped.csv")
    print(f"wrote {len(written)} frame rows to {args.frame}")
    if missing:
        print(
            "reports missing for: " + ", ".join(sorted(missing)),
        )
        print("the frame does not include those rows; record them as NOT RUN")
    print("next: commit frame.csv and the saved reports before any coding")
    return 0 if not missing else 3


if __name__ == "__main__":
    raise SystemExit(main())
