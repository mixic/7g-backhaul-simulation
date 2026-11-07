# Stipulated-constant sensitivity and break-even thresholds (M5/M6)

**Purpose.** The M5/M6 verdicts are partly set by stipulated constants (the
churn cost per edit, the LLM inference cost per call). A verdict that flips with
the constant is only as strong as the constant. This note restates each verdict as
a **break-even threshold**: the value of the constant at which the verdict would
reverse. A verdict whose break-even is far from the stipulation holds under a
wide range of stipulations; a verdict whose break-even is close to the
stipulation is fragile and is labelled as such.

The constants are in [`simulation/energy.py`](../simulation/energy.py):
`E_CHURN_PER_EDIT = 5.0 J`, `E_LLM_PER_CALL = 20.0 J`, `E_TX_PER_BYTE = 1e-7 J`.

## H9 — EWMA churn energy: stipulation-independent

`m5_ewma_mkb` spends **257.7 J** of churn energy vs `m4_raw_mkb` **239.7 J**,
because it issues **1546** edits vs **1438** (30 seeds). Both scale linearly with
`E_CHURN_PER_EDIT`, so the ratio is `257.7 / 239.7 = 1.075` at *any* positive
churn cost.

**Break-even.** The EWMA arm would win only if it issued *fewer* edits than the raw
MKB arm. It issues 7.5 % *more*, so **H9 is refuted for every positive
`E_CHURN_PER_EDIT`** — the constant cancels. This verdict is robust.

## H10 — LLM energy return: break-even wire saving ≈ 600 MB

`EROI = E_tx_saved / E_llm = (Δwire · 1e-7) / (20 · N_calls)`.
Setting `EROI = 1` gives the break-even wire saving

```text
Δwire* = 20 · N_calls / 1e-7 = 2·10⁸ · N_calls bytes.
```

For the modelled `N_calls = 3` (one per phase), `Δwire* = 6·10⁸ B = 600 MB`.
The observed saving is ≈ 1976 B, so `1976 / 6·10⁸ = 3.3·10⁻⁶`, the reported EROI.

**Break-even.** The LLM pays off **iff it saves more than ~600 MB of wire per
three-call transition**. The modelled flow saves ~2 KB, about five orders of
magnitude short. The verdict holds unless the transmission cost rises by ~10⁵× or
the inference cost falls to ~10⁻⁴ J/call. Labelled **stipulation-sensitive but
far from break-even**.

## H11 — static isolation cheapest: break-even churn cost ≈ 0.19 J/edit

For the M6 shockwave audit (per seed): static `E_tx = 918.2 J`, raw MKB
`E_tx = 909.3 J`, raw MKB edits ≈ `1438/30 = 47.9`. The raw MKB arm transmits
*less* energy (fewer bytes); static wins only through churn. Static is cheapest
iff

```text
E_tx_static < E_tx_dyn + c · edits_dyn
c > (918.2 − 909.3) / 47.9 = 0.186 J/edit.
```

**Break-even.** Static isolation wins **iff the churn cost exceeds ≈ 0.19 J per
edit**. The stipulated 5 J/edit is ~27× that, so H11 is robust to a wide range of
churn costs; it would reverse only if a surgical edit cost less than 0.19 J —
roughly a queue flush at consumer-SSD scale, which is not the modelled cost.

## H7 — LLM stack compiler vs the greedy heuristic

The mocked Oracle's *installed* stack is the canonical `C→E→F` (the guardrail
forces it on every hallucination), which is **bit-identical** to the greedy
heuristic: 2673.9 B for both, 30/30 seeds. H7 therefore tests the guardrail
against *injected* hallucinations, not a real LLM's search quality.

**Break-even.** The LLM would beat greedy only if it proposed a stack *strictly
better* than `C→E→F` for some phase. The mock never does; a real model would need
to find such a stack, and the wire-byte margin would then need to exceed the extra
inference cost (the H10 break-even). H7 is **a property of the mock's policy**, not
of LLMs in general, and the paper says so.

## M7 — dual-band detection (H13/H14): break-even false positives

The dual-band filter produced **115** false positives vs **6** for the fixed
single-LPF baseline. Churn energy scales with edits, and a false positive
triggers a multi-router surgical edit (~15–20 edits), so the false-positive cost
dominates.

**Break-even.** The dual-band arm beats the single-LPF baseline only if its extra
false positives cost less than the extra protection it buys. Measured:
dual-band `E_churn = 988 J` (goodput 0.66) vs LPF-only `355 J` (goodput 0.92). The
dual-band arm is worse on *both* axes, so the verdict does not depend on the
churn constant: any positive churn cost keeps static/LPF-only ahead.

## Summary

| Verdict | Break-even | Distance from stipulation | Robustness |
|---|---|---|---|
| H9 EWMA energy | any `E_CHURN_PER_EDIT > 0` (ratio) | constant cancels | **robust** |
| H10 LLM EROI | `Δwire > 600 MB` per 3 calls | ~5 orders of magnitude | robust to ordinary changes |
| H11 static cheapest | `E_CHURN_PER_EDIT > 0.186 J` | 27× below the 5 J stipulation | **robust** |
| H7 LLM vs greedy | LLM must beat `C→E→F` | mock never does | property of the mock |
| H13/H14 dual-band | any churn cost | both axes worse | **robust** |

The honest reading: **H9 and H11 are stipulation-independent or robust**, H10 is
sensitive to the inference cost but far from its break-even, and **H7 is a property
of the mocked Oracle**, not a claim about real LLMs.
