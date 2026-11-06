# Layering real-stack results (P8-P12)

**Predictions frozen at commit:** `46c7b40` (`docs/layering-real-stack-predictions.md`,
committed before any harness code).
**Results generated:** not yet.
**Verdict:** **NOT RUN.** The real-stack harness requires a Linux host with root
access, network namespaces, and the `wireguard`, `ipip`, `esp4`, `ah4`,
`act_pedit`, `act_csum` and `nft_masq` facilities. The environment that froze
this file (a WSL2 sandbox) does not provide them, so no case could be executed
under the stipulated conditions.

## Status

| Prediction | Status | Reason |
|---|---|---|
| P8 (AH/ESP/WireGuard through NAT) | **NOT RUN** | `unshare -n` denied, no `nft`/`wg`, no passwordless sudo |
| P9 (WireGuard wire overhead) | **NOT RUN** | no `wg` / wireguard module |
| P10 (IPIP/WireGuard quantisation) | **NOT RUN** | no `wg`/`ipip` setup privileges |
| P11 (tc pedit UDP length rewrite) | **NOT RUN** | no `act_pedit` / `act_csum` setup privileges |
| P12 (ESP transport + NAT inner checksum) | **NOT RUN** | no `esp4`/xfrm setup privileges |

## Environment observed at freeze time

| Item | Value |
|---|---|
| Host | WSL2, Ubuntu 26.04.1 LTS |
| Kernel | `6.18.54.1-microsoft-standard-WSL2` |
| `unshare -n true` | `Operation not permitted` |
| `sudo -n true` | `interactive authentication is required` |
| `nft` | not installed |
| `wg` | not installed |
| ns-3 | not installed (`~/ns-3-dev` absent) |

## Why these are NOT RUN rather than refuted

`layering-real-stack-predictions.md` §3 defines three dispositions: INVALID
(mutation gate fails), INCONCLUSIVE (cause gate names a different drop) and NOT
RUN (a required kernel facility is missing). This host trips the NOT RUN path
for every case: the namespace and netfilter facilities the harness needs are
unavailable, so no case could be executed under the stipulated conditions.
Recording a verdict would be fabricating a measurement.

## What the harness must do on a suitable host

The harness must reproduce the three-namespace topology of
`layering-real-stack-predictions.md` §2, the mutation and cause gates of §3, the
20-run × 50-datagram protocol of §5, and the counters and mangler setup of §7.
Raw observations must be written as CSV in the existing `validation_io` format,
and the hand-maintained results file must never overwrite a refutation
narrative.

## Addenda

(none yet)
