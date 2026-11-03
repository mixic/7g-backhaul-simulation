# Dual-role results: continuous α versus separated roles

**Claim and scenarios:** frozen in [`docs/dual-role.md`](dual-role.md), written
before the comparison was run. The DDoS question in §5.1 is explicitly
exploratory: it was added after the main run.

**Verdict:** the main claim is **REFUTED**. The controller improves delivered
fraction in the middle of the load range, but at the frozen acceptance point it
misses both bounds: goodput is 3.7 % higher (needs 5 %) and p95 latency is
2.23 × the separated baseline (needs ≤ 1.5 ×). The exploratory DDoS result is
also negative: under a focused flood, the fluid controller delivers **less**
traffic to an unattacked target than the separated baseline.

Environment: Windows 11, Python 3.14.7, 12 paired seeds, 120 ticks per run.
The CSVs and figures are committed; commands are in §5.

## 1. Main comparison (means over 12 paired seeds)

| Scenario | Mode | Delivered goodput | Delivered | p95 latency | mean \|Δα\| |
|---|---|---:|---:|---:|---:|
| steady | fluid | 119.18 ± 0.12 Mbps | 99.24 ± 0.01 % | 11.91 ± 0.48 ms | 0.115 |
| steady | separated | 119.17 ± 0.12 Mbps | 99.23 ± 0.01 % | 5.00 ± 0.00 ms | 0.000 |
| flash crowd | fluid | 143.71 ± 0.13 Mbps | 95.71 ± 0.08 % | 24.33 ± 0.46 ms | 0.120 |
| flash crowd | separated | 142.51 ± 0.15 Mbps | 94.91 ± 0.03 % | 13.13 ± 0.01 ms | 0.000 |
| DDoS flood | fluid | 159.40 ± 0.19 Mbps | 64.91 ± 0.15 % | 21.80 ± 1.37 ms | 0.129 |
| DDoS flood | separated | 198.63 ± 0.19 Mbps | 80.89 ± 0.14 % | 37.95 ± 0.09 ms | 0.000 |

At nominal load the two arms are indistinguishable in delivery (≈99.2 %); the
fluid arm pays a latency cost (11.9 ms versus 5.0 ms) because it serves some
traffic at interior nodes, adding link and queueing delay.

## 2. Throughput versus load and the frozen acceptance test

The separated arm first falls below 95 % delivered at **L\* = 1.4 ×** nominal.

| Test at L\* | Fluid | Separated | Ratio | Threshold | Result |
|---|---:|---:|---:|---:|---|
| delivered goodput | 164.26 Mbps | 158.36 Mbps | 1.037 | ≥ 1.05 | **FAIL** |
| p95 latency | 20.04 ms | 8.98 ms | 2.231 | ≤ 1.5 | **FAIL** |

Both frozen bounds fail, so the claim is refuted at the pre-registered point.
The controller does sustain a higher delivered *fraction* through the middle of
the sweep — at 1.3 ×, 98.2 % versus 95.8 %; at 1.5 ×, 96.3 % versus 92.7 % — but
the goodput margin is below 5 % and the latency penalty is above the bound.

Above 1.7 × the fluid arm degrades faster than the separated arm: at 2.0 × it
delivers 80.6 % versus 86.7 %, and 193.5 versus 208.3 Mbps. The pressure signal
keeps committing capacity to serving, which becomes the wrong action once the
mesh is saturated.

## 3. Exploratory DDoS evaluation

The `ddos` scenario adds a stipulated +250 Mbps flood at `E2` for 60 s. The
model cannot distinguish malicious from legitimate bytes; this is a demand
flood, not a security mechanism.

| Target | Fluid | Separated | Difference |
|---|---:|---:|---:|
| `E1` (unattacked) | 98.98 ± 0.02 % | 99.05 ± 0.02 % | −0.07 pp |
| `E2` (attacked) | 52.51 ± 0.17 % | 73.70 ± 0.16 % | −21.19 pp |
| `E3` (unattacked) | 92.08 ± 0.15 % | 98.79 ± 0.03 % | **−6.71 pp** |
| Total delivered | 64.91 % | 80.89 % | −15.98 pp |

The exploratory sub-claim — fluid delivery to the unattacked targets is at
least as high as separated — is **refuted** for `E3` by 6.7 pp with disjoint
intervals. The mechanism is visible in the α trace: the flood raises pressure
at the attacked edge and the interior nodes, and the controller responds by
committing more capacity to serving (higher α) and therefore less to
forwarding (lower 1 − α). Transit for the *other* targets is starved exactly
when it is needed. In this model the controller "serves the attack".

The attacked target itself receives less fluid delivery (52.5 % versus
73.7 %). That is not scrubbing: it is a side-effect of the reduced forwarding
capacity, and it comes with a 16 pp loss of total goodput and 6.7 pp of
collateral loss at an unattacked target.

**What this does and does not show.** It shows that a local
pressure-maximising serve controller is not a DDoS defence: it cannot classify
traffic, and its action (serve more under pressure) is the opposite of what a
flood requires (shed or rate-limit, and keep forwarding capacity for legitimate
traffic). It does not show that a *different* controller could not help; a
DDoS-aware variant would need to drive α **down** under attack-shaped pressure,
or separate attack traffic before it reaches the role controller. That is a
concrete next experiment, not a result of this one.

## 4. Figures

- `figures/dual_role_alpha.png` — α(t) and 1 − α(t) for `E2` and `M1` during the
  flash crowd, with the fixed separated levels dashed.
- `figures/dual_role_throughput.png` — delivered goodput and delivered fraction
  versus offered load, with L\* marked and the 95 % line.
- `figures/dual_role_latency_cdf.png` — volume-weighted latency CDF for the
  flash crowd.
- `figures/dual_role_stability.png` — mean |Δα| per control step, showing the
  damped adaptation (and the fixed baseline at zero).
- `figures/dual_role_ddos.png` — delivery by target under the flood, with `E2`
  marked as attacked.

## 5. Reproduction

```powershell
py -3 tools\benchmark_dual_role.py --output-dir figures --replicates 12 --seed 2026
py -3 tools\plot_dual_role.py --input-dir figures --output-dir figures
py -3 -m pytest tests\test_dual_role.py -q
```

The benchmark writes `dual_role_summary.csv`, `dual_role_per_seed.csv`,
`dual_role_sweep.csv`, `dual_role_verdict.csv`, `dual_role_alpha_trace.csv`,
`dual_role_stability.csv`, `dual_role_latency_cdf.csv` and
`dual_role_ddos.csv` under `figures/`. The verdict file is the mechanical
application of the frozen acceptance tests; it reports both bounds as failed.

## 6. Limitations

- Flow-level model: no packets, no TCP/ACK clock, no retransmission, no
  congestion control.
- Topology, demand, controller gains and cache parameters are stipulated, not
  calibrated; results are conditional on them.
- The DDoS scenario is a demand surge. There is no attack classification,
  scrubbing, rate limiting or source authentication, so this is not an
  evaluation of DDoS *defence*.
- The separated baseline is one reasonable fixed-role design, not the only one;
  a different static design could change the comparison.
- This is a single-author simulation; no independent replication yet.
