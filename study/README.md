# Postmortem study workspace

**Status: scaffold only.** The agent has not built a frame, fetched real
postmortems for coding, or coded any incident. The agent has read the predictions
and is therefore not a blind coder. M8 is human.

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
| `coded_c1.csv` | C1 | raw codes from the author |
| `coded_c2.csv` | C2 | raw codes from the independent coder |
| `coded_final.csv` | C3 | adjudicated final codes |
| `analysis/` | `tools/analyze_postmortems.py` | kappa, verdicts, unclear counts, Brier |

The coding template is
[`docs/postmortem-coding-template.csv`](../docs/postmortem-coding-template.csv).
The C2 prompt is
[`docs/postmortem-coder-prompt.md`](../docs/postmortem-coder-prompt.md).

## Build the frame (human)

1. Save the four official index pages into `indexes/` (or run
   `py tools/build_postmortem_frame.py --fetch --index-dir study/indexes`).
   The tool is a scaffold: if a provider changes its markup, update the parser
   and add a fixture test; do not hand-edit the frame silently.
2. Run a dry pass:

   ```bash
   py tools/build_postmortem_frame.py --index-dir study/indexes --dry-run
   ```

3. Review the candidates against the eligibility rules (official report, root
   cause stated, customer-visible impact at least 30 minutes, not single-customer,
   not planned maintenance, not a security breach disclosure). Write
   `study/eligibility.csv`. The agent does not decide eligibility.
4. Save the report texts, then build the frame:

   ```bash
   py tools/build_postmortem_frame.py --index-dir study/indexes \
       --eligibility-csv study/eligibility.csv --reports-dir study/reports
   ```

   Or copy already-saved texts with `--reports-source-dir`.
5. Check the frame gate:

   ```bash
   py tools/analyze_postmortems.py --frame study/frame.csv \
       --c1 study/coded_c1.csv --c2 study/coded_c2.csv \
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

```bash
py tools/analyze_postmortems.py \
    --frame study/frame.csv --c1 study/coded_c1.csv \
    --c2 study/coded_c2.csv --final study/coded_final.csv \
    --reports-dir study/reports --output-dir study/analysis
```

The script reports the full set and the set without
`known_before_freeze=yes`, the kappa gate, the size gate, `unclear` counts and
the Brier score. Synthetic tests are in `tests/test_postmortems.py` and
`tests/test_build_postmortem_frame.py`; they run before any real coding.
