# M6 — ns-3.49 cross-validation of the transmission-energy arithmetic

**Reference:** `validation/ns3/m6-energy-transition.cc` (run with
`validation/ns3/run-m6.sh`). **SimPy baseline:** `results/m6/m6_exp2_raw.csv`.

## What is and is not cross-validated

The M6 energy model has four terms. Only one of them is packet-level and
therefore reproducible outside the SimPy codec:

| term | cost | ns-3 status |
|---|---|---|
| `E_tx` (transmission) | 10⁻⁷ J / byte | **cross-validated here** |
| `E_cpu` (processing) | 10⁻⁹ J / cycle | stipulated, constant 4.2·10⁻⁴ J |
| `E_churn` (state change) | 5 J / edit | stipulated, no ns-3 counterpart |
| `E_llm` (inference) | 20 J / call | stipulated, no ns-3 counterpart |

The ns-3 program is an independent C++ re-implementation of the deterministic
wire-byte arithmetic of `simulation/layering/`: it reproduces the SimPy payloads
with the exact MT19937 stream (Python 3.14 seeds with `init_by_array([seed], 1)`,
not `init_genrand`), and re-derives the static (`F→E→C→T`) and optimal
(`C→E→F→T`) wire sizes with real zlib.

## Result (30 paired seeds)

| arm | SimPy mean (B) | ns-3 mean (B) | max \|Δ\| (B) |
|---|---:|---:|---:|
| static_iso | 4650.00 | 4650.00 | **0.0** |
| greedy_heuristic | 2673.87 | 2730.40 | 142.0 |
| llm_compiler | 2673.87 | 2730.40 | 142.0 |

* `static_iso` matches **exactly** for every seed (fragmentation, AEAD (+28),
  tunnel (+28) and the incompressible-compression overhead (+11) are all
  reproduced bit-for-bit).
* The optimal stack matches the *structure* exactly; the remaining ~2 % is not
  an arithmetic error but a **zlib-implementation difference**: Python on
  Windows bundles **zlib-ng 1.3.1**, while this build links **stock zlib 1.3.1**.
  The two compress the same compressible payload to different sizes (e.g. the
  seed-7 payload compresses to 627 B under zlib-ng and 693 B under stock zlib).
  The payload bytes themselves were verified byte-for-byte identical for
  alphabet sizes 2, 5 and 9.

## EROI (H10)

| | E_tx_saved (J) | E_llm (J) | EROI |
|---|---:|---:|---:|
| SimPy (zlib-ng) | 1.976·10⁻⁴ | 60 | 3.29·10⁻⁶ |
| ns-3 (stock zlib) | 1.920·10⁻⁴ | 60 | 3.20·10⁻⁶ |

Both are five orders of magnitude below break-even: **H10 remains REFUTED** —
the LLM's 60 J inference cost is never recovered by the ~2·10⁻⁴ J transmission
saving, regardless of which zlib implementation computes the compressed size.

## Files

* `validation/ns3/m6-energy-transition.cc` — the ns-3.49 scratch program.
* `validation/ns3/m6-energy/CMakeLists.txt` — links zlib for the scratch build.
* `validation/ns3/run-m6.sh` — build + run driver.
* `output/ns3_m6_wirebytes.csv` — the ns-3 output (same schema as
  `results/m6/m6_exp2_raw.csv`).
