# M15 self-review: a hostile program-chair read of Papers A and B

**Purpose.** No human colleague was available, so this file simulates one — a
program chair who has read both manuscripts, the figures and the artifact, and who
is looking for a reason to reject. It has two rounds: the first read of the
delivered drafts, and a second read after the first set of fixes, which is where
the lab-notebook vocabulary, the double-counted energy term and an unreadable
figure were caught. It is written *before* the fixes, in the voice of
the reviewer, and each item ends with the concrete change made to the paper. The
papers in this repository are the post-fix versions; nothing here is a promise.

**Reviewer's summary verdict.** Paper A is a careful, honest measurement paper with
a real method and a real artifact, weakened by over-claiming in two sentences and by
a figure whose axes do damage to its own result. Paper B is a useful negative result
whose apparatus is stronger than its evidence: the simulator is the only fidelity,
the workload is synthetic, and the headline comparison is against the authors' *own*
implementation of an analogy rather than against a published controller. Both papers
are publishable in some form. Neither is ready as submitted.

---

## Paper A — *When Do Protocol Layers Commute?*

### A-1 (claims too broad). "first systematic, pre-registered, cross-fidelity commutation study"

The paper uses the word "first" and then spends a section explaining why the claim
is narrow. Pick one. As written, a chair reads the abstract, sees "first", reads
§6.3, sees "one kernel, one NAT, one encryptor", and concludes the authors are
having it both ways. Worse, "cross-fidelity" is doing rhetorical work that the data
do not support: the three fidelities are *one Python model, one SimPy model and one
kernel*, all authored by the same person from the same specification, and the paper
admits as much in §6.2.4. A model that shares its author's misunderstanding is not
an independent fidelity.

**Resolution.** The claim is now stated as "to our knowledge, the first … *within
the scope of §6.3*", with the scope in the same sentence, and §6.2.1 now says
explicitly that the model and SimPy legs are a consistency check rather than an
independent replication. "First" is retained only where it is defensible — the
pre-registration-by-commit-hash mechanism — and dropped everywhere it is not.

### A-2 (missing scope statement). IPv4 only

Nowhere does the paper say that every experiment is IPv4. IPv6 changes the header
layout, moves fragmentation into a fragment header, and removes router
fragmentation entirely — three of the paper's own field classes behave differently
there. A reviewer who works on IPv6 will read the whole paper as an IPv4 paper that
forgot to say so, and will distrust the generality paragraph.

**Resolution.** §3.4 and §6.3 now state that all experiments are IPv4, that the
IPv6 fragment header and the absence of router fragmentation are out of scope, and
that RFC 8200 / RFC 8201 are the relevant documents for a reader who wants the IPv6
analogue. The reference list gained RFC 8200, RFC 8201 and RFC 3168 (ECN, the base
of the RFC 6040 tunnelling rule that P13 tests).

### A-3 (unsupported abstract claim). "27 in-memory tamper tests"

The abstract asserts that 27 tamper tests prove each gate fails on corrupted data.
The body never mentions a tamper test, never names the test files, and never gives
the command. This is exactly the kind of orphaned number a chair uses to justify a
reject: either the tests exist and the paper is sloppy, or they do not and the paper
is wrong.

**Resolution.** They exist (`tests/test_make_paper_tables.py`, 10 tamper tests;
`tests/test_lint_claims.py`, 17), and §4.8 now says so, names the split, and gives
the command. The abstract keeps the number because the number is now checkable in
the body.

### A-4 (figure 1 does not earn its space). A cartoon beside a measurement

Figure 1 is a block diagram. It carries byte counts that Figure 2 already carries,
in a form whose geometry is meaningless ("nothing is drawn to scale"). A chair's
question is: why is this a figure instead of two sentences? As submitted the honest
answer is "because block diagrams look like systems papers".

**Resolution.** Figure 1's caption now states its job — it defines the *ordering*
notation (`C→E`, `E→C`, `E→F`, `F→E`) that the rest of the paper uses, and it is
explicitly a diagram, not a measurement; Figure 2 is the measurement. The
duplicated byte counts stay because they tie the notation to the numbers, and the
caption says so.

### A-5 (figure 2 axis). A truncated y-axis in a bar chart

Panel (a) of Figure 2 starts the y-axis at 11,850 B. Truncated axes are a classic
way to make a 1.8 % difference look like a 10× effect, and a chair will call it
manipulation unless the authors pre-empt it.

**Resolution.** The axis start is printed in the axis label *and* in a note on the
plot, the exact values are printed at the points, the Δ is annotated with its
decomposition (28 B × 8 fragments), and the caption now states why the truncation
is necessary — a zero-based axis renders the paper's own finding invisible — and
that no visual proportion is used to argue any claim. The dot-plot form (rather
than bars) was chosen deliberately: bars from a truncated baseline are read as
magnitudes, dots are read as positions.

### A-6 (figure 3 mislabelled cell). P16 is red, but three of four sub-cases confirmed

The heatmap scores P16 as REFUTED in one cell. That is defensible (the prediction
is refuted if any of its sub-cases is), but the figure does not say so, and a
reader who knows the text will think the figure contradicts it.

**Resolution.** The in-figure note and the caption now state that a cell is a
*prediction × fidelity*, not a sub-case; that P16 is scored REFUTED because P16d
is; and that the headline count of 34 of 36 is computed over sub-cases, which is
why 28 of 30 cells and 34 of 36 predictions are both correct.

### A-7 (structure). Results arrived before the method that produced them

The previous draft had "Results I / II / III" as top-level sections, so a reader met
P8's verdicts before the gates that decide whether a verdict is admissible. The
required §1–§8 layout fixes the macro order but not the micro order, and the micro
order still matters.

**Resolution.** Methodology now precedes every result, and *within* results the
order is: overview → size regime → verdict map → fragmentation → integrity →
rounds 2/3 → counts → the two remaining predictions. The verdict map is placed
after the two size figures so that the figures are numbered in order of first
reference.

### A-8 (missing citation). Middlebox *parsing*, not just middlebox presence

The paper's central variable is "parse depth". Honda et al. measure that
middleboxes rewrite options; the paper that established that middleboxes parse only
to a fixed depth, and that this depth is what determines what they can rewrite, is
not cited. A reviewer who knows that literature will ask for it.

**Resolution.** §2.1 now separates the two claims explicitly: Honda et al. supply
the incentive argument, this paper supplies the mechanism argument, and the parse
depth is defined operationally in §3.3 as a byte offset from the start of the outer
IP header with no claim about deployed depths. (We do not cite a paper we cannot
verify; the definition is ours and is labelled as such.)

### A-9 (statistical). n = 20, and P2's "equality" is a non-rejection

P2's delivery difference is 0.19 pp with a paired CI of 0.33 pp; P15's is 0.38 pp
against a 1.5 pp margin chosen in the prediction file. Neither is an equivalence
test. A chair who reads "commute in delivery" will assume equivalence.

**Resolution.** §6.2.5 now says both are non-rejections, gives the CI, states what
30 seeds would and would not change, and §4.3 states the resolution the 20-run
design buys. The word "equality" is no longer used for a non-rejection.

---

## Paper B — *Why Fair-Queueing Beats the Fick Principle*

### B-1 (the straw man). Who, exactly, is being refuted?

This is the review's most serious objection. The paper refutes "bio-inspired network
control" but the controllers under test are the authors' own constructions. No
published Fick-principle controller is named, compared against, or shown to have
the properties the authors attribute to the field. As written, the paper proves that
*two controllers the authors built* lose to fair queueing. That is a useful negative
result about a design pattern; it is not the refutation of a literature that the
title implies.

**Resolution.** The paper now says this out loud rather than hoping nobody asks.
§2.2 states that the arms are faithful to one reading of the biology and are
implementations of that reading, not re-implementations of a specific published
controller; §6.2.5 concedes that a claim about "bio-inspired control" in general
would be too broad and states the claim the evidence supports. The title is kept
because "the Fick principle" names the design pattern under test, and the abstract's
first sentence now says "we test one reading of that analogy". A chair can disagree
with the framing; a chair cannot say it was hidden.

### B-2 (single fidelity). SimPy is the only witness

Paper A has three fidelities; Paper B has one simulator, no kernel, no hardware.
The 30-seed design quantifies sampling noise and says nothing about model error.
Every number in the paper could be wrong in the same direction and the paper would
look identical.

**Resolution.** This was already stated; it is now stated as a *threat to
validity* (§6.2.1) with the specific biases named (free per-flow state favours the
biological arms; no driver queue or offload makes the baseline weaker; discrete
event ordering perturbs arms differently because they issue different numbers of
edits), and §4.1 says in one sentence that the 30-seed design is a substitute for
cross-fidelity replication and cannot replace it.

### B-3 (the "bound" is nearly trivial). §3.2 asserts a definition that proves nothing

A buffer holds packets; therefore a continuous law cannot place it between packets.
True, and almost contentless. Presenting it as a "Definition" with a "bound" gives
it more weight than the argument carries, and a chair who notices will discount the
paper's structural claim — which is a pity, because the structural claim is the
interesting part.

**Resolution.** §3.2 now states a *Proposition* with a two-line proof sketch, and
concedes in the same paragraph that it is close to trivial as mathematics and
decisive only as an empirical statement about *these* controllers — because the
interesting question is not whether the bound exists but whether it binds at the
operating point the controllers choose. The figure that illustrates it is labelled a
schematic and its role is limited to explaining the shared pattern of the failures.

### B-4 (figure 1 shows nothing). Three lines that coincide

The time-series figure plots three nearly identical curves for 60 seconds and
shades a 10-second window. The reader's reaction is "so what" — which is the point,
but a figure has to earn the reaction by showing the difference that the text
claims. As submitted, the difference is invisible.

**Resolution.** Figure 1 now carries an inset that zooms the shock window (28–42 s,
40–100 % y-range) with the same three curves, so the reader can see that MKB dips to
~55 % while static and OEF stay near 80 %, and that the OEF curve is inside the
static band. The annotation box gives the shock-window means and the paired test
computed in the figure script from the raw CSV.

### B-5 (unsupported table). H13/H14 appear in the break-even table but nowhere else

The break-even table lists "H13/H14 dual-band" as robust. Neither hypothesis is
described, and no result is reported. A chair reads that as a result recycled from
another paper.

**Resolution.** New §5.6 reports H13/H14 from `results/m7_summary.md`: dual-band
detection is refuted (115 false positives against 6 for the single-LPF baseline,
with essentially equal latency) and dual-band protection is refuted (goodput 0.659
against 0.915, churn energy 988 J against 355 J). The verdict is robust to the churn
constant because the arm is worse on both axes, which is why it belongs in the
break-even table.

### B-6 (missing citation). No fair-queueing-adjacent control paper explains the baseline's cost

The paper asserts, correctly, that the simulator prices per-flow WFQ state at zero.
It does not cite what that state costs in practice, so the claim that the real
margin is smaller is unsupported.

**Resolution.** §2.3 now cites DRR and core-stateless fair queueing for *why* the
state is cheap in hardware (deficit counters, stateless core) and §6.1 uses that to
bound the bias in both directions rather than asserting it. The honest conclusion —
that we cannot say which direction dominates — replaces the stronger claim.

### B-7 (structure). The mechanism was in §3, the evidence in §5, and the two never met

The previous draft stated the discrete-packet argument in an introduction and then
never used it to explain a measured result.

**Resolution.** §5.5 now ties the schematic to the measured arms: the shared edit,
the quantised state, and the resulting collapse of the biological arms back onto
their own baseline. §6.1 restates the mechanism as the paper's explanation and §7
names the experiments that would falsify it.

---

## Cross-paper issues

### X-1 (reproducibility). Paper B's Figure 1 needed a data file that did not exist

The committed CSVs contain no per-arm time series; `run_m4_experiments.py` computes
one in memory for a PNG and discards it. A figure without a committed source is a
placeholder with extra steps.

**Resolution.** `tools/extract_arm_timeseries.py` re-runs the frozen harness on
the committed seed set and refuses to write
`results/m4/arm_timeseries.csv` unless all 150 recomputed aggregate rows match
`results/m4/final_benchmark_raw.csv` at the file's own precision. The reproduction
record is committed, the paper's §4.6 explains it, and the figure is drawn from the
verified trace. This is the only place in either paper where a number is regenerated
rather than read, and it is disclosed in the caption.

### X-2 (figures must be checkable). No provenance

Neither figure set came with a statement of which CSV produced which number.

**Resolution.** `tools/generate_paper_figures.py` asserts every plotted value against
the claim the text makes about it (so a silent data change breaks the build) and
writes `figures/figure-data-manifest.md`, a table of all 67 plotted values with their
source files. Two panels are schematic — A-1 (ordering diagram) and B-5 (discrete
bound) — and both are labelled as such in figure and caption.

### X-3 (README). Deliverables were unlinked

The repository's top-level README linked the paper PDFs but not the new figure
artifacts.

**Resolution.** README now links the ten figure PDFs, the manifest, the figure
generator and the trace extractor, and lists the paper-level reproduction commands.

---

## Round 2 — after the first revision

The revised drafts were re-read. Four new objections survived the first pass, and
one of them was a data error rather than a writing problem.

### X-4 (fatal on first read). The manuscript reads like a lab notebook

The metrics table had a "Used by" column whose entries were internal hypothesis IDs
(`H5`, `H6`, `H8`, `H9`, `H10`, `H11`); the controller table cited "M3", "M4",
"M5", "M6", "M7"; the arm names were internal keys (`m4_oef`, `m3_surgical_1d`,
`m4_raw_mkb`, `m5_ewma_mkb`, `m4_combined`); and the text said "the M5 H8 campaign".
A reader outside the project has no way to decode any of it, and a reviewer reads
it as a manuscript assembled from a work log rather than written for an audience.
This is not cosmetic: an undefined `H10` is a claim the paper never states, so the
defect is also a completeness defect.

**Resolution (Paper B).** The vocabulary is gone.

- The hypotheses became **seven named expectations, E1–E7**, each stated in full in
  a pre-registration table with its confirmation threshold, and referred to by name
  or number thereafter ("the compiler repayment expectation"), never left undefined.
- The milestones became **named campaigns**: reference campaign, controller
  campaign, energy audit, smoothing and compiler campaign, detector campaign. A
  decoder table maps campaign names to the committed directories once, in the
  reproduction section, and those directory keys appear nowhere else in the prose.
- The arms are named by mechanism everywhere — in prose, in tables and in both
  affected figures: *static per-flow isolation*, *1-D scalar-EMA limiter*, *OEF
  actuator*, *4-D kinematic trigger*, *smoothed trigger with early redirection*,
  *LLM stack compiler*, *dual-band detector*, *single-LPF detector*. The "naming"
  paragraph that reconciled three sets of internal keys is deleted because there is
  nothing left to reconcile.
- Artifact names that embedded a milestone were renamed: `tools/extract_arm_timeseries.py`,
  `results/m4/arm_timeseries.csv`, `results/m4/timeseries_reproduction.md`,
  `figures/figure-data-manifest.md`.

**Resolution (Paper A).** It carried one such reference — the manifest filename
`m15-figure-manifest.md` — now renamed. Its predictions P1–P17 stay: they are the
paper's own identifiers, defined in the paper, and are exactly the kind of label a
reader can follow.

### X-5 (a real error, not a style issue). The energy total double-counted setup

The energy model in §4.5 said total energy was `E_tx + E_cpu + E_churn + E_setup`.
The committed CSV's `Total_Energy_J` is `E_tx + E_cpu + E_churn`; `E_setup` is the
one-time 1,040–1,100 J paid per run and is reported separately. The first draft of
the new energy figure stacked all four terms, which pushed the static-isolation bar
past 1,900 J and would have contradicted the paper's own 918 J headline.

**Resolution.** The model, the metric table and the figure now agree: three terms
stacked, setup named in a separate annotation and excluded from the totals, with a
sentence saying so. This is the one place in the revision where the reviewer found
a genuine error rather than an omission.

### X-6 (a figure that could not be read). The detector figure plotted a degenerate
ROC

The committed threshold sweep collapses onto the axes (true-positive rate 1.0 at
almost every threshold, false-positive rate 0 or 1), so a "ROC" drawn from it looks
like a line from (0,0) to (1,1) with two dots, and the point labels overprinted each
other. A figure that cannot be read is not a figure.

**Resolution.** Figure 6 now carries the two comparisons the text actually makes:
panel (a) is *detection cost* (latency against false alarms over 30 seeds) and
panel (b) is *protection cost* (goodput against churn energy). The sweep file stays
committed and its operating points are still cited, but the paper no longer claims
to plot a curve it cannot draw.

### X-7 (missing from the first revision). Nothing showed the energy or the detector
campaign

The paper argued about churn energy and about detectors while showing only the
timeseries, the peak burst, the break-even and the schematic. A reader had to take
the energy decomposition and the detector comparison on trust.

**Resolution.** Two figures were added, generated by the same script from the same
committed CSVs: **Figure 4** (energy audit — three stacked terms per arm, the
picture that makes "static isolation pays no churn" visible) and **Figure 6**
(detector trade-off, both axes). Paper B now carries six figures, and every one of
them is asserted against the values in the text.

---

## What the reviewer would still reject

Not everything is fixed, and pretending otherwise would be the same dishonesty this
review is meant to catch.

1. **One kernel (Paper A).** The frozen two-kernel clause is unmet. No amount of
   prose fixes it; it needs a second kernel, and the paper says so in the abstract,
   in §4.3 and in §6.2.3.
2. **One simulator (Paper B).** Same problem in a different place. The break-even
   analysis is a mitigation, not a substitute.
3. **Author identity.** The predictors wrote the harness. §6.2.4 reports it; only a
   third party can remove it.
4. **The parse-depth definition (Paper A) is ours, not measured.** A deployed
   middlebox's parse depth is an empirical quantity that this paper does not measure.
5. **Paper B's workload is synthetic.** A ramping flood and heavy-tailed flow sizes
   would change the magnitudes; the paper argues the directions survive and does not
   claim more.

A chair who weighs artifacts heavily would accept Paper A with majors and Paper B as
a short negative-result paper. A chair who weighs novelty over rigor would reject
both. Neither verdict is settled by this file, and the papers should not pretend
that it is.


