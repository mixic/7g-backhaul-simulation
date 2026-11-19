# Postmortem study workspace

**Status: frame and two blind coding passes done; C1 and C3 still human.** The
agent built the frame from the four official indexes (88 incidents, frozen in
`frame.csv` at commit `434ee71`), ran the protocol's independent coder (C2) as an
isolated LLM session per report, and ran a replicate blind pass (C2b) for a
reliability estimate. **No author C1 and no C3 adjudication exist**, so E1-E8 are
unadjudicated and no verdict is claimed. The execution record, every deviation
and the measured C2-vs-C2b kappa are in
[`docs/postmortem-study-status.md`](../docs/postmortem-study-status.md).

The agent did not code blind by accident: no coder session received the
predictions file, and the codebook was extracted as section 4 only. The agent
read the gates and verdict rules (sections 5-6) only after both coding passes
were frozen and committed.

The frozen protocol is
[`docs/postmortem-study-predictions.md`](../docs/postmortem-study-predictions.md).
Read it before touching this directory. The codebook is section 4; the gates are
section 5; the verdict rules are section 6.

## Files

| Path | Who writes it | What it is |
|---|---|---|
| `indexes/` | human | saved official index pages (`aws.html`, `azure.html`, `google.html`, `cloudflare.html`) |
| `frame-candidates.csv` | human/tool | optional working list before eligibility review |
| `eligibility.csv` | human | one row per candidate: `incident_id,eligible,duplicate_of,notes` |
| `frame.csv` | tool + human | the frozen frame: incident IDs, URLs, dates, SHA-256 of each saved report |
| `reports/` | tool + human | saved report text, one file per incident (`<incident_id>.txt`) |
| `coded_c1.csv` | C1 | raw codes from the author (still owed) |
| `coded_c2.csv` | C2 | raw codes from the independent coder (done, commit `6061002`) |
| `coded_c2b.csv` | C2b | replicate blind pass by the same model configuration (done) |
| `c2-rows/`, `c2-packet/` | tool | the raw one-row answers and the exact packet the coder received |
| `coded_final.csv` | C3 | adjudicated final codes (still owed) |
| `analysis/` | `tools/analyze_postmortems.py`, `tools/analyze_m8_status.py` | kappa, verdicts, unclear counts, Brier |

The coding template is
[`docs/postmortem-coding-template.csv`](../docs/postmortem-coding-template.csv).
The C2 prompt is
[`docs/postmortem-coder-prompt.md`](../docs/postmortem-coder-prompt.md).
The M8 execution record is
[`docs/postmortem-study-status.md`](../docs/postmortem-study-status.md).

## Build the frame

Done on 19 November 2026 by the agent, with the frozen constants (window
2023-01-01..2026-10-31, 40 per provider, seed 2026). The runnable path is
[`tools/collect_postmortem_frame.py`](../tools/collect_postmortem_frame.py), which
implements the four provider extractors and reports failures per provider rather
than silently shrinking the frame:

```bash
py tools/collect_postmortem_frame.py --fetch --cache-dir study/indexes   # network
py tools/collect_postmortem_frame.py --cache-dir study/indexes --dry-run  # offline
py tools/collect_postmortem_frame.py --cache-dir study/indexes \
    --eligibility-csv study/eligibility.csv --reports-dir study/reports \
    --frame study/frame.csv --manifest study/indexes/MANIFEST.csv
```

The older scaffold `tools/build_postmortem_frame.py` still holds the frozen
constants and the sampling function and is imported by the collector.

The eligibility decisions in `study/eligibility.csv` are the agent's, recorded
with reasons, and **still need the author's sign-off**.

       --final study/coded_final.csv --reports-dir study/reports
   ```

   The analyzer refuses mismatched report hashes. No coding starts until
   `frame.csv` and the saved reports are committed.

## Freeze and code

- Commit `frame.csv` and `reports/` before C1 or C2 sees a report.
- C1 and C2 code independently. C2 receives the codebook, one report and the
  prompt, not this repository's predictions.
- C3 adjudicates every disagreement; `coded_final.csv` is C3's code.
- No prediction text is edited after the freeze; corrections go to a dated
  addendum.

## Analyze

The protocol path, once `coded_c1.csv` and `coded_final.csv` exist:

```bash
py tools/analyze_postmortems.py \
    --frame study/frame.csv --c1 study/coded_c1.csv \
    --c2 study/coded_c2.csv --final study/coded_final.csv \
    --reports-dir study/reports --output-dir study/analysis
```

It refuses to run without C1. Until then, the status analysis reports what two
blind passes can support, with the measured C2-vs-C2b kappa and both labelled
scenarios:

```bash
py tools/analyze_m8_status.py --frame study/frame.csv \
    --c2 study/coded_c2.csv --c2b study/coded_c2b.csv \
    --reports-dir study/reports --output-dir study/analysis
```

The script reports the full set and the set without
`known_before_freeze=yes`, the kappa gate, the size gate, `unclear` counts and
the Brier score. Synthetic tests are in `tests/test_postmortems.py`,
`tests/test_build_postmortem_frame.py` and
`tests/test_collect_postmortem_frame.py`; they run before any real coding.
