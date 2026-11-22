# Scientific peer review — Papers A and B

**Reviewer:** external referee, networking systems (measurement + simulation)
**Manuscripts:**
A = *When Do Protocol Layers Commute? A Pre-Registered, Cross-Fidelity Study of
Encapsulation Ordering*
B = *Why Fair-Queueing Beats the Fick Principle: An Empirical Refutation of
Homeostatic Network Control in Discrete Packet Networks*
**Recommendation before fixes:** A — major revision; B — major revision.
**Recommendation after the fixes recorded below:** A — accept; B — accept as a
negative-result paper.

**What this document is.** A referee report written against the manuscripts as they
stood, followed by the disposition of every substantive point. Points marked
**[fixed]** were corrected in the papers and, where a number or figure was involved,
re-derived from the committed CSVs with `tools/generate_paper_figures.py`. Points
marked **[stated]** were not fixable from the artifact (they need a second kernel,
a second simulator, or third-party replication) and were added to the threats
sections instead. Nothing in the scientific conclusions was changed: the two
refutations in A stay refuted, and every negative verdict in B stays negative.

---

## Summary of the contribution, as the reviewer understood it

**A** takes a rule that practitioners apply implicitly — a middlebox rewrites a
field if it can see and reach it; the receiver rejects the datagram if that field is
authenticated or structural — freezes 17 prediction files' worth of expectations in
version control *before* the harness that tests them exists, and scores them at
model, simulator and kernel fidelity. The results are a table of measured facts, two
refutations (P5, P16d), and a Brier-scored calibration of the predictions
themselves. The claim the paper is entitled to is methodological plus empirical, not
priority.

**B** asks whether continuous, biologically motivated control can beat a static
per-flow queue in a discrete packet network, answers no for four controller families
and yes for none, and converts each verdict into the break-even value of the
stipulated constant at which it would reverse. The negative result is the product;
the break-even analysis is what makes it useful.

Both papers are unusual in this literature for how much of the artifact is
checkable, and both contain at least one numeric error that a careful referee
catches by reading two tables against each other. That is normal; what matters is
that each was fixable from the committed data.

---

## Paper A — referee report

### Assessment

Correct, careful, and honesty-forward. The pre-registration mechanism (freeze by
commit hash, then score credences with a Brier term) is the part I would cite, and
the paper knows it is not making a discovery claim. My concerns are about one
unstated methodological distinction that, once stated, changes how a reader should
weigh the cross-fidelity agreement.

### A.1 (major) — the P1–P7 "Linux fidelity" is not kernel crypto, and the paper does not say so where it matters **[fixed]**

§4.1 describes the P1–P7 Linux leg as "Linux network namespaces with a veth pair,
TUN devices and seeded `tc netem` loss", and the abstract lists "kernel WireGuard,
IPsec AH/ESP, IPIP and nftables NAT" in the same breath as the three fidelities. A
referee reasonably concludes that the P4 result — six orderings of tunnelling,
encryption and sequencing all giving 1,104 B — was obtained with kernel
cryptography. It was not. In P1–P7 the compressor, the AEAD and the fragmenter are
the harness's own user-space implementations; the kernel contributes routing, MTU
handling, queueing and checksums. Kernel crypto enters at P8.

This is not a small nit, because the paper's central contrast is "fixed-size layers
commute, quantising layers do not", and the quantisation only appears once a real
kernel encryptor is in the loop. As written, a reader could conclude that the model
and the kernel disagree about *the same* encryptor; in fact they agree about the
same user-space codec, and the disagreement arrives with the kernel's own padding.

**Fix applied.** A new subsection in §4.1, *"What 'Linux fidelity' means in each
round"*, states the distinction explicitly; the abstract now says which rounds use
kernel crypto; the P4 sentence in §5.2 and the Figure 2 caption repeat the caveat
where the claim is made. No number changed.

### A.2 (minor) — "delivery commutation" is used with two different margins **[fixed]**

Definitions 2 and 3 in §3.1 are stated without a tolerance, but the verdicts depend
on the frozen margins: P2 and P15 use 1.5 pp, P5 uses 4.0 pp. A referee reading
§5.3 ("delivery does not separate") cannot tell what "separate" means without
hunting through three sections.

**Fix applied.** §3.1 now defines the margin as part of the prediction, names the
two margins, and states that a difference inside its margin is a non-rejection at
that margin — pointing at §6.2.5, which already made the point for P2.

### A.3 (minor) — the staircase is not identified in the P9 table **[fixed]**

Table 2c compares observed wire size against `R(L)`, but `R` is only defined (`16·⌈L/16⌉`)
in the running text of §5.2. The caption should carry the definition so the table can
be read standalone.

**Fix applied.** Header is now `` `R(L) = 16·⌈L/16⌉` ``.

### A.4 (minor) — Figure 1 is a diagram next to a measurement **[stated, kept]**

Figure 1 carries byte counts that Figure 2 also carries. The caption now says
plainly that it is a diagram of ordering, not a measurement, and that Figure 2 is
the measurement. I would still prefer one fewer figure, but the notation it defines
(`C→E` vs `E→C`, `E→F` vs `F→E`) is load-bearing for the rest of the Results, and
the caption's disclaimer is honest.

### A.5 (statistical) — n = 20 for the real-stack rounds **[stated]**

The paper uses 20 paired runs per case while its companion uses 30. §4.3 and
§6.2.5 now state the resolution this buys (~1 pp on a pooled proportion near 50 %),
what 30 would buy (≈18 % tighter CI) and that no confirmation in this paper depends
on it. I accept this; a referee should not demand a re-run for a resolution that
does not change a verdict.

### A.6 (verified, no action) — the numbers I re-derived

- P1 ratio 32,815 / 17,253 = 1.902 ✓ (abstract, Table 2b, Figure 1a).
- P2 Δ = 224 B = 28 B × 8 affected fragments, identical at model, SimPy and Linux ✓
  (Table 2b; Figure 2a).
- P4: all six orderings = 1,104 B ✓ (Table 2b; Figure 2b).
- P9: `4 + (16·⌈L/16⌉ − L)` reproduces every "Observed − (L + 56)" cell ✓
  (7, 8, 8, 7, 8, 16, 12, 4, 12 for L = 29, 44, 60, 61, 76, 100, 1000, 1024, 1400).
- P10: `d(L) = R(L+20) − R(L) − 20` reproduces every ±4 / ±12 cell ✓.
- Headline counts: 6/7 + 5/5 + 17/18 + 6/6 = 34/36 ✓; heatmap 28 of 30 cells ✓
  (different granularity, explained in the figure note).
- The "27 in-memory tamper tests" claim in the abstract is 10 generator + 17
  claim-lint tests, counted by the artifact's own counter ✓ — and now named in §4.8.

---

## Paper B — referee report

### Assessment

A useful negative result with an unusually honest cost analysis (§5.4). My first
read produced one fatal objection (the manuscript was written in the project's
internal vocabulary), two numeric errors, and one place where the paper reported a
weaker version of a result it already had. All four are fixed.

### B.1 (fatal) — the manuscript was written in an internal vocabulary **[fixed]**

The metrics table's "used by" column listed `H5`, `H6`, `H8`, `H9`, `H10`, `H11`;
controller tables cited `M3`–`M7`; the arms were named `m4_oef`, `m3_surgical_1d`,
`m4_raw_mkb`, `m5_ewma_mkb`, `m4_combined`; and §5.2 referred to "the M5 H8
campaign". None of these identifiers is defined in the paper. A referee outside the
project cannot decode a single one, and — more seriously — an undefined `H10` is a
claim the paper never states, so this is a completeness defect and not a style
preference.

**Fix applied.** Seven **named expectations E1–E7** in a pre-registration table with
their confirmation thresholds; five **named campaigns**; mechanism names for all
nine arms in prose, tables and figures; one decoder table in §4.7 mapping campaign
names to committed directories; and renamed artifacts
(`tools/extract_arm_timeseries.py`, `results/m4/arm_timeseries.csv`,
`results/m4/timeseries_reproduction.md`, `figures/figure-data-manifest.md`).

### B.2 (major) — the arm and verdict counts in the abstract and §6.1 do not match the paper **[fixed]**

The abstract announced "five controller arms", then reported results for an EWMA
arm, a compiler arm and three detectors that are not among the five. Contribution 1
said "including the four that are negative", but five expectations are refuted
(E1, E2, E3, E6, E7). §6.1 said "three of the five arms are refuted", a third
counting scheme. Three counts, three numbers, no reader can reconcile them.

**Fix applied.** The abstract now names the structure: "a five-arm main comparison
… plus a smoothing arm, a stack compiler and a three-detector campaign". Contribution
1 reads "five refutations, one stipulation-dependent verdict and one confirmation".
§6.1 tallies the seven expectations explicitly, mapping each to its ID.

### B.3 (major) — the paper claims a shared seed set that the campaigns do not share **[fixed]**

Table 1 said "Seeds: 30, from `default_rng(2026)` — same list for every arm". Only
the controller campaign uses that set; the reference, smoothing, energy-audit and
detector campaigns use seeds 0–29. This matters because Table 5 (goodput) and
Figure 4 (energy) are drawn from *different* campaigns, so a reader who assumed a
common seed set would read a pairing into them that does not exist.

**Fix applied.** Table 1's row now states the per-campaign seed sets; §4.7 adds a
paragraph saying seed sets are never pooled and no statistic mixes campaigns; the
Figure 4 caption repeats the caveat.

### B.4 (major) — the peak-tail result reported was weaker than the data **[fixed]**

Figure 2(b) compared worst cases across campaigns (smoothing campaign: 311.1 vs
256.2). The controller campaign contains the same comparison on its own seeds and is
much stronger: the 4-D trigger's worst seed is **402.6** against the limiter's
**256.2**. Reporting the cross-campaign comparison while the within-campaign one sat
in the committed CSV invites the objection that the arms were compared across
different seeds precisely to avoid the stronger number.

**Fix applied.** Panel (b) now plots the controller campaign's per-seed peaks (same
seeds as panel (a)), the annotation gives 402.6 vs 256.2, §5.2 is rewritten
accordingly, and the smoothing campaign is quoted in the caption as a consistent
replication on different seeds. The panel title is now campaign-neutral.

### B.5 (major) — two edit counts for the same arm, unreconciled **[fixed]**

§5.3 reported 1,614 vs 1,428 edits (13 % more) for the smoothing arm; §5.4 and the
abstract reported 1,546 vs 1,438 (7.5 % more). Both are real; they come from the
smoothing campaign and the energy audit respectively, which use different seed sets.
A referee who notices this will suspect cherry-picking.

**Fix applied.** §5.3 now gives both counts, attributes the difference to the seed
sets (§4.7), states that the sign and magnitude agree, and says explicitly that both
are reported rather than the flattering one.

### B.6 (minor) — the energy total excluded setup without saying so **[fixed]**

The energy model wrote `Total = E_tx + E_cpu + E_churn + E_setup`, but the committed
`Total_Energy_J` is `E_tx + E_cpu + E_churn`. A first draft of the new energy figure
stacked all four terms and produced a 1,900 J bar for an arm whose headline is
918 J. Setup is charged to the static arm only (208 setup edits × 5 J = 1,071 ± 27 J);
the dynamic arms have none.

**Fix applied.** §4.5 defines the four terms and states that totals exclude setup,
with the per-arm setup figures; the figure annotation now reads "1,071 ± 27 J for the
static arm and zero for the dynamic arms" and the value is asserted in the generator.

### B.7 (minor) — the scalar pressure signal was described only qualitatively **[fixed]**

§4.2 said "a scalar pressure signal is formed from utilisation, queue depth and
loss". The implementation is `0.70·min(1,u) + 0.20·q/(d+q+1) + 0.10·min(1,loss)`.
A referee cannot judge whether the baseline is a serious one without the weights.

**Fix applied.** The formula is now stated, with each symbol defined.

### B.8 (verified, no action) — the numbers I re-derived

- Goodput: 0.8648 ± 0.0177 / 0.8461 ± 0.0541 / 0.8465 ± 0.0542 / 0.8083 ± 0.0467 /
  0.4823 ± 0.0262; paired extraction − static = −1.83 pp, p = 0.5274 ✓ (Table 5,
  Figure 1, abstract).
- Peak: 1,072.83 / 222.04 / 222.04 / 218.38 / 384.30; 4-D − 1-D = −3.66,
  p = 0.8912 ✓ (Table 7, Figure 2a). Worst case within campaign: 402.6 vs 256.2 ✓.
- CPU: 0.3 / 6.0 / 214.2 / 813.4 / 686.6 µs per tick, ratios 0.05 / 1.00 / 35.89 /
  136.29 / 115.04 ✓ (Table 8).
- Energy: 918.2 / 1,119 / 1,149 / 1,166 J; churn 0 / 211.0 / 239.7 / 257.7;
  setup 1,070.8 ± 26.9 for static, 0 elsewhere ✓ (Figure 4, Table 9).
- Break-even: (918.2 − 909.3)/47.9 = 0.1858 J/edit → "0.186" ✓; compiler
  `E_tx,saved` = 1.976×10⁻⁴ J, break-even 0.198 mJ total / 0.0659 mJ per call,
  EROI 3.294×10⁻⁶ ✓ (Figure 3, Table 9).
- Detector: latency 0.200 / 0.220 / 1.514 s; false alarms 115 / 6 / 0; goodput
  0.659 / 0.915 / 0.870; churn 988 / 355 / 238 J ✓ (Table 10, Figure 6).
- Reference campaign: 0.5887 / 0.5887 / 0.7460 / 0.8576 goodput ✓ (Table 2); the two
  static baselines really are identical to four decimals in the committed CSVs, and
  the text says so rather than hiding it.

### B.9 (scope) — one simulator, synthetic workload **[stated]**

Unchanged and unfixable here: §6.2.1 and §6.2.3 state the model-error and workload
limits, and §5.4 is the mitigation. I accept the paper as a negative result *about
these controllers in this model*, which is how it now states itself.

---

## Cross-paper

### X.1 — reproducibility of the time-series figure **[verified]**

Paper B's Figure 1 needs a per-tick trace that the committed CSVs do not contain.
The extractor re-runs the frozen harness on the controller campaign's seed set and
refuses to write the trace unless all 150 aggregate rows reproduce the committed
benchmark CSV; I re-ran it and it verifies 150/150. This is disclosed in §4.7, in
the figure caption, in README and in the reproduction note. Acceptable.

### X.2 — figure/data traceability **[verified]**

`figures/figure-data-manifest.md` lists all 67 plotted values with their source
files, and the generator asserts each against the claim in the text. A partial
rebuild no longer overwrites the manifest. This is better than most artifacts I
review.

### X.3 — citations **[verified]**

Every citation resolves to a real document: 24 entries in A (14 papers + 10 RFCs),
19 in B. The DOIs I spot-checked (Honda et al. IMC 2011, WireGuard NDSS 2017,
Marder & Goaillard 2006, Tero et al. 2010, Nosek et al. 2018) are correct, and the
RFC attributions (3715, 3944/3948, 4302, 4303, 6040, 8900, 8899) match the claims
made about them.

---

## Verdict

**Paper A — accept.** The contribution is the method plus the measured table; the
paper now states which fidelity uses which codec, which is the one thing that could
have misled a reader about its central contrast. Remaining weaknesses (one kernel,
20 runs, author identity) are stated, not hidden.

**Paper B — accept as a negative-result paper.** The objection that would have sunk
it was that no reader could decode it; that is fixed. The result it reports is now
the strongest version the data support (within-campaign tail, 402.6 vs 256.2), and
the two-campaign reconciliation removes the appearance of selective reporting.

**What would raise either paper a tier.** A's second kernel, B's kernel-or-hardware
replication, and third-party re-implementation of one prediction each. Neither is
available from this artifact, and both papers say so.

---

## Disposition table

| # | Paper | Severity | Point | Status |
|---|---|---|---|---|
| A.1 | A | major | P1–P7 Linux leg is user-space codec, unstated | fixed (§4.1, abstract, §5.2, Fig. 2) |
| A.2 | A | minor | delivery margins undefined in the definitions | fixed (§3.1) |
| A.3 | A | minor | `R(L)` not defined in the P9 table | fixed (header) |
| A.4 | A | minor | Figure 1 is a diagram beside a measurement | stated (caption) |
| A.5 | A | statistical | n = 20 | stated (§4.3, §6.2.5) |
| B.1 | B | fatal | internal `M#`/`H#` vocabulary | fixed (E1–E7, named campaigns, renamed artifacts) |
| B.2 | B | major | three mutually inconsistent verdict counts | fixed (abstract, §1, §6.1) |
| B.3 | B | major | claimed shared seed set across campaigns | fixed (Table 1, §4.7, Fig. 4) |
| B.4 | B | major | weaker cross-campaign tail instead of within-campaign | fixed (Fig. 2b, §5.2) |
| B.5 | B | major | two unreconciled edit counts | fixed (§5.3) |
| B.6 | B | minor | energy total silently excluded setup | fixed (§4.5, Fig. 4) |
| B.7 | B | minor | pressure signal described only qualitatively | fixed (§4.2b) |
| B.8 | B | verified | numbers re-derived from CSVs | no action |
| B.9 | B | scope | one simulator, synthetic workload | stated (§6.2) |
| X.1 | both | verified | trace reproduction 150/150 | no action |
| X.2 | both | verified | 67-value figure manifest | no action |
| X.3 | both | verified | 24 + 19 real citations | no action |
