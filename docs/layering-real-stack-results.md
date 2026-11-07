# Layering real-stack results (P8-P12)

**Predictions frozen at commit:** `46c7b40` (`docs/layering-real-stack-predictions.md`,
committed before any harness code).
**Results generated:** real-stack harness run on WSL2 as root (`wsl -u root`);
raw observations in `validation/layering/results/real_stack_observations.csv`.
**Verdict summary:** **P8a, P8b, P8c and P9 CONFIRMED; P11 INCONCLUSIVE; P10 and
P12 NOT RUN in this pass.** The earlier "NOT RUN" disposition is superseded: this
host *does* provide namespaces, nftables, WireGuard and the xfrm (`esp4`/`ah4`)
facilities, so four of the five predictions could be executed.

## Status

| Prediction | Status | Evidence |
|---|---|---|
| P8a (AH tunnel through NAT) | **CONFIRMED** | control 50/50, NAT 0/50; `XfrmInStateProtoError` = 50 |
| P8b (ESP tunnel through NAT) | **CONFIRMED** | control 50/50, NAT 50/50 |
| P8c (WireGuard through NAT) | **CONFIRMED** | control 50/50, NAT 50/50; peer endpoint = NAT address `10.200.2.1` |
| P9 (WireGuard wire overhead) | **CONFIRMED** | all 9 lengths exact: 92, 108, 124, 124, 140, 172, 1068, 1084, 1468 B |
| P10 (IPIP/WireGuard quantisation) | **NOT RUN** | not attempted in this pass |
| P11 (tc pedit UDP-length rewrite) | **INCONCLUSIVE** | cases a/b delivered 0/50 as predicted, but the inert ToS control (c) also delivered 0/50, so the setup is not validated |
| P12 (ESP transport + inner checksum) | **NOT RUN** | not attempted in this pass |

## Confirmed results

### P8 — NAT against real integrity scopes

Three-namespace topology (`cA`–`cN`–`cB`), `nftables masquerade` on `cN` egress,
50 datagrams per case, controls without NAT.

| Case | Stack | Control delivery | NAT delivery | Predicted | Cause gate |
|---|---|---|---|---|---|
| a | AH tunnel | 100 % | **0 %** | 0 % | `XfrmInStateProtoError` +50 |
| b | ESP tunnel | 100 % | **100 %** | 100 % | none |
| c | WireGuard | 100 % | **100 %** | 100 % | peer endpoint shows NAT `10.200.2.1` |

P8a confirms that the outer source address is inside the AH integrity scope: the
masquerade rewrite invalidates the AH ICV, and the kernel reports exactly 50
`XfrmInStateProtoError` for the 50 datagrams. P8b confirms the recorded
asymmetry: the outer source is outside the ESP integrity scope, so the same
rewrite delivers 100 %. P8c confirms WireGuard survives NAT and learns the
translated endpoint.

### P9 — WireGuard wire overhead

For an inner IPv4 packet of length `L`, the outer IP total length is exactly
`wire(L) = 60 + 16·⌈L/16⌉`:

| L | 29 | 44 | 60 | 61 | 76 | 100 | 1000 | 1024 | 1400 |
|---|---|---|---|---|---|---|---|---|---|
| predicted | 92 | 108 | 124 | 124 | 140 | 172 | 1068 | 1084 | 1468 |
| measured | 92 | 108 | 124 | 124 | 140 | 172 | 1068 | 1084 | 1468 |

This converts the stipulated 56 B composite (`E = 28`, `T = 28`, no padding) into
a measured overhead; the stipulation is low by `4 + (16·⌈L/16⌉ − L)` bytes, i.e.
4–16 B depending on `L mod 16`. This is a calibration finding, not a failure of
P9.

## P11 — why INCONCLUSIVE, not refuted

The structural rewrites of the outer UDP length (cases a and b) delivered 0/50 as
predicted. But the inert control (case c: rewrite only the outer ToS, which is
outside WireGuard's integrity scope) also delivered 0/50, where 100 % was
predicted. Per §3 of the predictions file, a control failure means the setup, not
the rule, decided the outcome; recording a refutation would be fabricating it.
The likely cause is an interaction between `tc pedit` and checksum offload on the
veth pair, which needs a clean `ethtool -K … tx off` path and a re-run. **P11 is
therefore INCONCLUSIVE and must be re-run; the two 0/50 results are not evidence
for or against the rule.**

## P10 and P12 — not run in this pass

The nested IPIP-over-WireGuard topologies (P10) and the ESP-transport plus NAT
inner-checksum case (P12) were not attempted in this pass. They remain NOT RUN,
which is neither confirmed nor refuted.

## Environment

| Item | Value |
|---|---|
| Host | WSL2, Ubuntu 26.04.1 LTS |
| Kernel | `6.18.54.1-microsoft-standard-WSL2` |
| Root | `wsl -u root` available (`id -u` = 0) |
| `unshare -n true` | OK |
| `nft` / `wg` | installed via `apt` |
| `esp4`/`ah4`/`ipip`/`act_pedit`/`act_csum`/`wireguard` | present |

This supersedes the "Environment observed at freeze time" table in the earlier
version of this file, which recorded the sandbox that could not run the cases.

## Model consequences (from `layering-real-stack-predictions.md` §9)

| Outcome | Model consequence | Status here |
|---|---|---|
| P8a, P8c, P11 confirmed | survival rule holds against independent implementations | P8a, P8c confirmed; P11 open |
| P8b refuted | add a lookup-key field class | not refuted (P8b confirmed) |
| P9 confirmed | replace the stipulated 56 B composite by `60 + R(L)`; mark `W` quantised | **confirmed** |
| P10b confirmed | amend P4: commutation needs fixed (non-quantised) size effects | not run |
| P12a confirmed | add derived dependency edges between layers | not run |
| any INCONCLUSIVE or NOT RUN | report as such; do not infer a verdict | P10, P11, P12 |

## Addenda

- **2026 (harness run).** P8a/P8b/P8c/P9 confirmed on WSL2 as root. P11
  inconclusive (inert control failed; re-run with checksum offload disabled).
  P10/P12 not attempted. Harness scripts are in `output/` (session scratch); a
  committed `validation/layering/run_real_stack.py` is the next step.
