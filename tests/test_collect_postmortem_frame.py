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

"""Fixture tests for the per-provider postmortem frame extractors.

Each fixture is a trimmed copy of the real markup fetched on 19 November 2026,
so a provider markup change breaks a test instead of silently shrinking the
frame.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "collect_postmortem_frame", ROOT / "tools" / "collect_postmortem_frame.py"
)
cp = importlib.util.module_from_spec(_SPEC)
sys.modules["collect_postmortem_frame"] = cp
_SPEC.loader.exec_module(cp)


AWS_INDEX = """
<p>Post-Event Summaries will remain available for a minimum of 5 years.</p>
<ul>
 <li><a href="/message/101925/">Summary of the Amazon DynamoDB Service Disruption in the Northern Virginia (US-EAST-1) Region</a>&nbsp;October 19, 2025<br></li>
 <li><a href="https://aws.amazon.com/message/073024/">Summary of the Amazon Kinesis Data Streams Service Event in Northern Virginia (US-EAST-1) Region</a>&nbsp;July 30, 2024<br></li>
 <li><a href="https://aws.amazon.com/message/061323/">Summary of the AWS Lambda Service Event in Northern Virginia (US-EAST-1) Region</a> June 13, 2023<br></li>
</ul>
"""


class HtmlToTextTests(unittest.TestCase):
    def test_drops_script_and_style(self) -> None:
        text = cp.html_to_text(
            "<html><style>a{color:red}</style><script>var x=1;</script>"
            "<p>Hello&nbsp;world</p></html>"
        )
        self.assertEqual(text, "Hello world")

    def test_block_tags_become_line_breaks(self) -> None:
        text = cp.html_to_text("<div>one</div><div>two</div><p>three</p>")
        self.assertEqual(text.split("\n"), ["one", "two", "three"])

    def test_entities_are_unescaped(self) -> None:
        self.assertEqual(cp.html_to_text("<p>a &amp; b &#8211; c</p>"), "a & b – c")

    def test_empty(self) -> None:
        self.assertEqual(cp.html_to_text(""), "")


class AwsTests(unittest.TestCase):
    def test_extracts_three_reports(self) -> None:
        candidates = cp.extract_aws(AWS_INDEX)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].incident_id, "aws-101925")
        self.assertTrue(candidates[0].url.startswith("https://aws.amazon.com/message/101925/"))

    def test_date_is_taken_from_after_the_anchor(self) -> None:
        candidates = cp.extract_aws(AWS_INDEX)
        self.assertEqual(candidates[0].publication_date, "2025-10-19")
        self.assertEqual(candidates[1].publication_date, "2024-07-30")
        self.assertEqual(candidates[2].publication_date, "2023-06-13")

    def test_absolute_and_relative_hrefs_deduplicate(self) -> None:
        html = AWS_INDEX + (
            '<a href="https://aws.amazon.com/message/101925/">again</a> October 19, 2025'
        )
        self.assertEqual(len(cp.extract_aws(html)), 3)


CLOUDFLARE_INDEX = """
<a href="https://blog.cloudflare.com/tag/post-mortem/">Post mortems</a>
<p>2024-03-05 <a href="https://blog.cloudflare.com/some-outage/">Some outage</a></p>
<p>2023-11-02 <a href="https://blog.cloudflare.com/other-outage/">Other outage</a></p>
"""


class CloudflareTests(unittest.TestCase):
    def test_reuses_the_frozen_parser(self) -> None:
        candidates = cp.extract_cloudflare(CLOUDFLARE_INDEX)
        ids = [candidate.incident_id for candidate in candidates]
        self.assertIn("cloudflare-some-outage", ids)
        self.assertEqual(
            next(c.publication_date for c in candidates if c.incident_id.endswith("some-outage")),
            "2024-03-05",
        )


GCP_HISTORY = """
<table class="ise88CpWulY__psd-table">
  <thead><tr><th>Summary</th><th>Date</th><th>Duration</th></tr></thead>
  <tbody>
   <tr>
    <th class="ise88CpWulY__summary" scope="row">
      <a href="../../incidents/2Hd52dn3PqYGTD5zdp7v">
        <span class="ise88CpWulY__summary-text">Elevated error rate for BigQuery</span>
      </a>
    </th>
    <td class="ise88CpWulY__date">8 May 2024</td>
    <td class="ise88CpWulY__duration">
      <div class="ise88CpWulY__icon-container">
        <span class="ise88CpWulY__duration-text">1 hr, 23 min</span>
      </div>
    </td>
   </tr>
   <tr>
    <th class="ise88CpWulY__summary" scope="row">
      <a href="../../incidents/eWat683pNnkMT7orVDBV">
        <span class="ise88CpWulY__summary-text">Network issue in europe-west1</span>
      </a>
    </th>
    <td class="ise88CpWulY__date">3 March 2022</td>
    <td class="ise88CpWulY__duration"><span class="ise88CpWulY__duration-text">45 min</span></td>
   </tr>
  </tbody>
</table>
"""

GCP_SUMMARY = """
<a href="products/duAxoF9U3MBmoAihC67y/history">BigQuery</a>
<a href="products/qar4NvXDickuQgSVbW3G/history">Cloud Run</a>
<a href="products/duAxoF9U3MBmoAihC67y/history">BigQuery again</a>
"""


class GoogleTests(unittest.TestCase):
    def test_product_keys_are_unique(self) -> None:
        keys = cp.product_keys(GCP_SUMMARY)
        self.assertEqual(keys, ["duAxoF9U3MBmoAihC67y", "qar4NvXDickuQgSVbW3G"])

    def test_rows_carry_summary_date_and_duration(self) -> None:
        rows = cp.extract_gcp_history(GCP_HISTORY)
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first.incident_id, "gcp-2Hd52dn3PqYGTD5zdp7v")
        self.assertEqual(first.title, "Elevated error rate for BigQuery")
        self.assertEqual(first.publication_date, "2024-05-08")
        self.assertEqual(first.duration_minutes, "83")
        self.assertEqual(
            first.url, "https://status.cloud.google.com/incidents/2Hd52dn3PqYGTD5zdp7v"
        )

    def test_duration_parsing(self) -> None:
        self.assertEqual(cp.parse_duration_minutes("1 hr, 23 min"), "83")
        self.assertEqual(cp.parse_duration_minutes("2 days, 4 hr"), "3120")
        self.assertEqual(cp.parse_duration_minutes("18 min"), "18")
        self.assertEqual(cp.parse_duration_minutes("N/A"), "")


AZURE_SNAPSHOT = """
<div class="month-incident-container">
 <button class="row incident-history-header" type="button" data-toggle="collapse"
         data-target="#incident-history-collapse-7Q30-010">
   <span class="hide-text">09/30/2026</span>
   <div class="col-md-8 incident-history-title">
       Post Incident Review (PIR) &ndash; Network Connectivity &ndash; Gateway service degradation
   </div>
   <div class="col-md-3 incident-history-tracking-id">Tracking ID: 7Q30-010</div>
 </button>
 <div class="row">
   <div class="collapse incident-history-collapse" id="incident-history-collapse-7Q30-010">
     <div class="card-body">
       <p><strong>What happened?</strong></p>
       <p>Between 20:30 UTC and 02:15 UTC, customers using Azure VPN Gateway
          experienced intermittent failures.</p>
       <p><strong>What was the impact?</strong></p>
       <p>Requests failed for 47 minutes.</p>
     </div>
   </div>
 </div>
</div>
</div>
"""


class AzureTests(unittest.TestCase):
    def test_extracts_the_pir_block(self) -> None:
        rows = cp.extract_azure(AZURE_SNAPSHOT)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.incident_id, "az-7q30-010")
        self.assertEqual(row.publication_date, "2026-09-30")
        self.assertIn("Gateway service degradation", row.title)
        self.assertIn("What happened?", row.extra["body_text"])
        self.assertIn("47 minutes", row.extra["body_text"])

    def test_report_text_keeps_the_inline_body(self) -> None:
        row = cp.extract_azure(AZURE_SNAPSHOT)[0]
        text = cp.report_text(row, "")
        self.assertIn("Tracking ID: 7Q30-010", text)
        self.assertIn("What was the impact?", text)


class EligibilityTests(unittest.TestCase):
    def candidate(self, **kwargs) -> "cp.Candidate":
        base = dict(
            incident_id="x-1",
            provider="AWX",
            url="https://example.invalid/x",
            title="Service disruption",
            publication_date="2024-01-01",
        )
        base.update(kwargs)
        return cp.Candidate(**base)

    def test_short_impact_is_ineligible(self) -> None:
        row = cp.decide_eligibility(self.candidate(duration_minutes="12"))
        self.assertEqual(row.eligible, "no")
        self.assertIn("12 min", row.notes)

    def test_long_impact_is_eligible(self) -> None:
        row = cp.decide_eligibility(self.candidate(duration_minutes="47"))
        self.assertEqual(row.eligible, "yes")

    def test_missing_duration_is_reviewed(self) -> None:
        row = cp.decide_eligibility(self.candidate(duration_minutes=""))
        self.assertEqual(row.eligible, "yes")
        self.assertIn("flagged for review", row.notes)

    def test_planned_maintenance_is_excluded(self) -> None:
        row = cp.decide_eligibility(self.candidate(title="Scheduled maintenance on 3 May"))
        self.assertEqual(row.eligible, "no")

    def test_breach_is_excluded(self) -> None:
        row = cp.decide_eligibility(self.candidate(title="Data breach notification"))
        self.assertEqual(row.eligible, "no")

    def test_single_customer_is_excluded(self) -> None:
        row = cp.decide_eligibility(
            self.candidate(title="Degradation for a single-customer workload")
        )
        self.assertEqual(row.eligible, "no")

    def test_stated_duration_from_a_time_pair(self) -> None:
        text = (
            "Between 20:30 UTC on 30 September 2026 and 02:15 UTC on "
            "1 October 2026, customers experienced failures."
        )
        minutes, phrase, kind = cp.stated_impact_minutes(text)
        self.assertEqual(minutes, "345")
        self.assertIn("20:30", phrase)
        self.assertEqual(kind, "pair")

    def test_stated_duration_from_a_minutes_claim(self) -> None:
        minutes, phrase, kind = cp.stated_impact_minutes("Requests failed for 47 minutes.")
        self.assertEqual(minutes, "47")
        self.assertIn("47 minutes", phrase)
        self.assertEqual(kind, "claim")

    def test_no_stated_duration_is_unverifiable(self) -> None:
        self.assertEqual(cp.stated_impact_minutes("The service was degraded."), ("", "", ""))

    def test_ineligible_duration_comes_from_the_text_when_the_index_is_silent(self) -> None:
        row = cp.decide_eligibility(
            self.candidate(
                duration_minutes="",
                extra={"body_text": "Failed for 12 minutes."},
            )
        )
        self.assertEqual(row.eligible, "no")
        self.assertIn("12 min", row.notes)


class CloudflarePostFilterTests(unittest.TestCase):
    def test_author_and_tag_pages_are_not_posts(self) -> None:
        self.assertFalse(cp.is_cloudflare_post("https://blog.cloudflare.com/author/silverlock/"))
        self.assertFalse(cp.is_cloudflare_post("https://blog.cloudflare.com/tag/post-mortem/"))

    def test_single_segment_post_is_a_post(self) -> None:
        self.assertTrue(cp.is_cloudflare_post("https://blog.cloudflare.com/18-november-2025-outage/"))


class MergeAndWindowTests(unittest.TestCase):
    def test_duplicates_merge_keeping_the_longer_title_and_dates(self) -> None:
        rows = [
            cp.Candidate("gcp-a", "Google Cloud", "u1", "short"),
            cp.Candidate(
                "gcp-a", "Google Cloud", "u1", "a much longer title", "2024-02-02", "30"
            ),
        ]
        merged = cp.merge_duplicates(rows)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].title, "a much longer title")
        self.assertEqual(merged[0].publication_date, "2024-02-02")
        self.assertEqual(merged[0].duration_minutes, "30")

    def test_window_filter_uses_the_frozen_dates(self) -> None:
        inside = cp.Candidate("x-1", "P", "u", "t", "2023-01-01")
        outside = cp.Candidate("x-2", "P", "u", "t", "2022-12-31")
        self.assertTrue(cp.in_window(inside, cp.bf.WINDOW_START, cp.bf.WINDOW_END))
        self.assertFalse(cp.in_window(outside, cp.bf.WINDOW_START, cp.bf.WINDOW_END))

    def test_missing_date_is_outside_the_window(self) -> None:
        row = cp.Candidate("x-1", "P", "u", "t", "")
        self.assertFalse(cp.in_window(row, cp.bf.WINDOW_START, cp.bf.WINDOW_END))


class SamplingTests(unittest.TestCase):
    def test_sample_is_seeded_and_per_provider(self) -> None:
        rows = [
            cp.Candidate(f"p-{index:03d}", "Provider", "u", "t", "2024-01-01", "60", eligible="yes")
            for index in range(60)
        ]
        first = cp.sample_eligible(rows, 40, cp.bf.SEED)
        second = cp.sample_eligible(rows, 40, cp.bf.SEED)
        self.assertEqual([row.incident_id for row in first], [row.incident_id for row in second])
        self.assertEqual(len(first), 40)

    def test_small_universe_is_kept_whole(self) -> None:
        rows = [
            cp.Candidate(f"q-{index}", "Provider", "u", "t", "2024-01-01", "60", eligible="yes")
            for index in range(5)
        ]
        self.assertEqual(len(cp.sample_eligible(rows, 40, cp.bf.SEED)), 5)

    def test_ineligible_rows_are_not_sampled(self) -> None:
        rows = [
            cp.Candidate("q-1", "Provider", "u", "t", "2024-01-01", "60", eligible="no"),
            cp.Candidate("q-2", "Provider", "u", "t", "2024-01-01", "60", eligible="yes"),
        ]
        chosen = cp.sample_eligible(rows, 40, cp.bf.SEED)
        self.assertEqual([row.incident_id for row in chosen], ["q-2"])


if __name__ == "__main__":
    unittest.main()
