# Why Fair-Queueing Beats the Fick Principle

## An Empirical Refutation of Homeostatic Network Control in Discrete Packet Networks

**Milan Nikolic** · Independent Researcher · <m_nikolic@yahoo.com>

**Status:** focused negative-result paper (paper B of the split; paper A is
[`paper-layering-testbed.md`](paper-layering-testbed.md)). The layering testbed is
mentioned here only as a methodological influence; the layering results are in
paper A.

## Abstract

Biologically inspired control — the Fick principle (OEF), homeostatic set-points,
and multidimensional kinematic baselining (MKB) — is often proposed as a way to
stabilise congestion in heterogeneous backhaul. This paper tests it. Over M3–M6,
on a 100-node three-medium SimPy fabric and 30 paired seeds, we compare static
per-flow fair-queueing with the Fick-principle OEF actuator, the 4-D MKB trigger,
an EWMA-smoothed trigger with Random Early Redirection, and an LLM stack compiler.
The negative result is consistent: **in this simulated testbed, under the
stipulated discrete packet model, static isolation outperformed continuous
bio-inspired control** on legitimate goodput and on energy. We state the result as
a **boundary on these controllers and workloads**, not as a fundamental limit on
bio-inspired control, and we restate each verdict as a break-even threshold so it
holds under any stipulation (see [`break-even-analysis.md`](break-even-analysis.md)).

## 1. Introduction

The motivating idea is that the Fick principle — `CMRO2 = CBF · OEF · Ca` — maps
onto network metabolism: when delivered throughput (CBF) falls, an extraction
fraction (OEF) should rise to protect legitimate traffic (CMRO2). M4 and M5 test
this idea directly, alongside a multidimensional kinematic trigger that watches the
geometry of a 4-D state vector `[CBF, OEF, Queue, Drop]`.

The testbed is the SimPy fabric of [`simulation/layering/`](../simulation/layering/)
and [`simulation/surgical/`](../simulation/surgical/): a 100-node mesh of fiber,
microwave and satellite links under a 10 s DDoS shockwave at t = 30 s. The
control-plane edit (isolation, RER) is shared with the static baseline, so the arms
differ only in their trigger.

## 2. Controllers under test

| Arm | Trigger | Actuator | Source |
|---|---|---|---|
| `static_isolation` | none (always on) | per-flow fair-queueing | M3 confound |
| `m4_oef` | CBF drop vs EMA | OEF weight on the bulk class | [M4](../results/m4_summary.md) |
| `m4_raw_mkb` | 4-D vector residual | surgical isolation | [M4](../results/m4_summary.md) |
| `m5_ewma_mkb` | EWMA of v and a + RER | surgical isolation + redirect | [M5](../results/m5/m5_summary.md) |
| `llm_compiler` | mocked Oracle + P1–P5 guardrails | stack ordering `C→E→F` | [M5](../results/m5/m5_summary.md) |

## 3. What the evidence shows

- **M3:** the static per-flow isolation baseline delivers **86.5 %** legitimate
  goodput under the shockwave — the number every dynamic arm must beat.
- **M4:** the Fick principle is **refuted**. The OEF actuator cannot beat static
  isolation (0.8465 vs 0.8648, paired p = 0.53): a DDoS flood *raises* total
  delivered throughput, so the CBF-drop premise that drives OEF never fires.
  Running OEF and MKB together is *worse* (goodput 0.48).
- **M5:** the EWMA-smoothed trigger plus RER is **refuted** for its peak-burst
  claim (the synchronous surgical edit, not the trigger, sets the peak) and is
  **refuted** on energy: it issues 7.5 % *more* edits than raw MKB.
- **M6:** the energy audit makes the boundary explicit. `static_isolation` has
  **zero runtime churn energy** and is the cheapest arm (918.2 J); the LLM
  compiler's EROI is ≈ 3·10⁻⁶ (see §4). The verdicts are restated as break-even
  thresholds in [`break-even-analysis.md`](break-even-analysis.md): H11 holds for
  any churn cost above ≈ 0.19 J/edit, and H9 is independent of the constant.

## 4. Stipulation dependence (why "refuted" is too strong for H10)

The H10 verdict is **stipulation-dependent**, not absolute. With
`EROI = (Δwire · 1e-7) / (20 · N_calls)`, the compiler is viable *if and only if*

```text
E_llm_breakeven  <  E_tx_saved        i.e.     Δwire > 600 MB per 3-call transition.
```

At the stipulated 20 J/call and 10⁻⁷ J/B, the modelled flow saves ≈ 2 KB — about
five orders of magnitude short. We therefore report **H10 as
"stipulation-dependent"** with the break-even above, not as an unconditional
refutation.

## 5. What this does and does not show

- **Shows:** for this fabric, these controllers and these loads, continuous
  bio-inspired compensation did not beat static isolation, and lost once churn
  energy was counted.
- **Does not show:** that bio-inspired control cannot work in general. The
  static baseline in SimPy does **not** price the per-flow WFQ state maintenance
  that real hardware must pay (per-flow queues, hashing, decrementing timers), so
  the *real-hardware* margin is smaller than the simulated one. The result bounds
  this model, not the paradigm.
- **The Fick analogy** remains a useful design intuition; the empirical test did
  not confirm the mechanism under a flood.

## 6. Methodological influence

The survival/commutation discipline used to bound the claims here — freeze the
prediction, name a cause gate, report INCONCLUSIVE rather than refuted when the
setup decides the outcome — was developed in the layering testbed, paper A
([`paper-layering-testbed.md`](paper-layering-testbed.md)).

## Cross-references

- [`m6-energy-paper.md`](m6-energy-paper.md) — the energy audit in full.
- [`break-even-analysis.md`](break-even-analysis.md) — break-even thresholds.
- [`../results/m4_summary.md`](../results/m4_summary.md) — M4 verdicts.
- [`../results/m5/m5_summary.md`](../results/m5/m5_summary.md) — M5 verdicts.
- [`paper-layering-testbed.md`](paper-layering-testbed.md) — paper A (layering).
