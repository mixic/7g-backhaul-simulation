# M16 self-review: Paper D against a hostile SIGCOMM referee

**Scope.** This note records a simulated referee report on
`docs/paper-common-mode.md` after the M16 revision, and the resolution applied to
each point. Where a requested input was not present in the committed data, the
resolution is a report — not an invention — and it is listed in §R6.

## R1. "This is still a simulation paper wearing a measurement paper's clothes"

**Critique.** The paper's contribution is a model, yet the framing still reads as
if the numbers were facts about clouds. A referee will ask what the numbers are
evidence *for*.

**Resolution.** The abstract now opens with the method ("We present a stochastic
simulation model, not an empirical measurement of a specific cloud provider") and
closes with the claim boundary ("We do not claim to have measured AWS, Azure,
Google Cloud"). §1 states the four contributions, the first of which is the model.
Every results paragraph reports a sampled statistic with its interval and names
the model quantity it samples. §4.3 states explicitly which four criteria are
exact in the model and therefore carry zero-width intervals.

**Residual risk.** A referee may still read Table 1's architectures as claims about
providers. The table's caption and §3.7 say "structural analogues"; that is the
strongest statement the data support.

## R2. "The incident corpus is too small and too selected to anchor anything"

**Critique.** Fifteen purposively chosen, high-profile postmortems cannot support a
rate estimate, and the paper's own assumption (shared control planes dominate)
almost certainly shapes the selection.

**Resolution.** The corpus is pre-registered with a mechanical rubric
(`docs/m16-incident-corpus.md`), every entry carries a public URL, and the paper
states the composition descriptively: 14 of 15 originated in shared control planes,
11 of 15 were triggered by a configuration push. §6.6.2 states the selection
problem in the referee's own terms: the corpus is not a random sample, it
over-represents high-profile incidents, and it anchors an assumption rather than
validating a prediction. The paper makes no significance claim from N = 15.

## R3. "Where is the break-even band that the abstract promised?"

**Critique.** The planning document for this revision asked for the band
[0.848, 0.921]. Only 0.848 exists in `docs/paper-tables/common-mode-mc-break-even.csv`.

**Resolution.** The 0.921 upper edge is **not in the committed tables** and is
therefore not stated. The abstract reports the three thresholds the data does
contain — 0.848 (normal-cost ceiling), 0.800 (containment floor), 0.688
(interaction) — and says in as many words that "no upper edge of that band exists
in the committed tables". Manufacturing an upper edge from a second criterion that
does not bind would have been the failure mode this note exists to prevent.

**What would fix it.** A sweep of the *containment* criterion against a rising
efficiency, which the committed sensitivity table does not contain: `a6_ai`
increases monotonically with efficiency and never crosses down. The upper bound
would have to come from a cost criterion the model does not currently carry (for
example a per-tenant price of boundary complexity).

## R4. "Figure 3 was specified as a component-pair heatmap; it is an arm-by-event heatmap"

**Critique.** The requested figure was a matrix of component pairs; the delivered
figure is architecture × incident class.

**Resolution.** The committed Monte-Carlo tables record one incident class per
replication (`common-mode-mc-summary.csv`, `common-mode-per-seed.csv`); they record
no component pair, so a pair-incidence matrix cannot be computed without inventing
co-occurrence data. Figure 10 plots the matrix that *is* recorded, and its caption
says so. The substitution is also listed in §R6.

## R5. "Figures 1–5 are numbered 8–12. Explain."

**Critique.** A referee counting figures will find eight existing figures and five
new ones.

**Resolution.** The paper previously carried seven figures (1–7) with in-text
cross-references. Adding five figures as 1–5 would have renumbered every existing
reference and its caption, risking silent mis-citation in a paper whose tables and
figures are cross-checked by number. The five new figures were therefore appended
as 8–12 and placed next to the results they explain. All ten figures named in the
text resolve.

## R6. Missing inputs, reported rather than fabricated

| Requested input | Status | What the paper does instead |
|---|---|---|
| 0.921 upper edge of the efficiency band | Not in any committed table | Reports 0.848, 0.800, 0.688 only; states there is no upper edge in the data |
| Component-pair incidence matrix | Not recorded per replication | Figure 10 draws architecture × incident class, captioned as a substitution |
| Per-campaign (500) raw availability for the violins | Only mean and 95 % CI are committed; the 30-seed file is a subsample whose A1 records are all 100 % | Figure 8 plots the per-replication **contrast** distributions, which are committed at n = 2 000 |
| 18 verified postmortems ("13 of 18" in the plan) | 15 could be verified with a public URL; three plan entries (Azure Front Door Oct 2025, M365 Sep 2025, AI-connector Nov 2025) could not be confirmed at a vendor URL in this session | Corpus is N = 15; the abstract states 14 of 15 and 11 of 15, not 13 of 18 |
| Body text for ten of the fifteen corpus entries | Vendor pages returned HTTP 200 with title/date, but the extraction tool truncated the article body | Each entry is marked `page` in the corpus evidence table; the coding relies on the mechanism that page documents, and the limitation is stated in the corpus |

## R7. Language

The revision removes hedges ("could be", "might suggest", "it seems", "we
believe", "very", "really", "quite"): a search of the manuscript finds none. Claims
are stated as "we find", "the model predicts", "the evidence shows", and every
quantitative claim is qualified as model-derived or corpus-derived.

## R8. References

The new citations are real and were checked against publisher or vendor pages:
Gill, Jain and Nagappan (SIGCOMM 2011); Govindan, Minei, Kallahalla, Koley and
Vahdat (SIGCOMM 2016); Bronson, Aghayev, Charapko and Zhu (HotOS 2021); AWS
Builders' Library on static stability; the CrowdStrike Channel File 291 root-cause
analysis; Patterson et al. (HotOS 2003). They are appended to §8 as a BibTeX block.
**Known gap:** the pre-existing §8 is a numbered reference list, and it was not
converted wholesale to BibTeX in this revision because the body text cites it by
number; a conversion would have to renumber every in-text citation. This is stated
rather than glossed.

## R9. What would still fail review

- One kernel-independent model, no measured failure rates. The paper says so, but a
  referee who wants one real deployment's input will not be satisfied.
- The corpus cannot distinguish "shared control planes dominate" from "shared
  control-plane incidents are the ones vendors publish postmortems about".
- The 0.848 threshold is the model's, not a deployment's.

These are limits of the study design, not of its reporting, and the paper states
them as such.
