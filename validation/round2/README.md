# Round-2 real-stack harness (P13-P16)

Executable form of [`docs/layering-real-stack-predictions-round2.md`](../../docs/layering-real-stack-predictions-round2.md),
which was frozen at commit `1b7e6ac` **before any harness code existed** and is never
edited afterwards; corrections go into a dated addendum of the results document. Round 1
(P8-P12) lives in `validation/real_stack`; this package reuses its `Shell`, its
observation schema and its offload helper, and adds what round 2 needs: an ECN mangler,
ESP-in-UDP, a second client namespace, fragment / SPI / sequence capture and the depth
gates.

> **Status: run against one kernel.** WSL2 `6.18.58.1-microsoft-standard-WSL2`. The
> frozen replication clause asks for at least two kernels; only one is available on this
> host, and the results document records that as a limitation rather than averaging it.

## Requirements

Linux, **root**, and:

| Need | For |
|---|---|
| `iproute2` (`ip`, `tc`), `python3` | everything |
| modules `ipip` | P13a-c |
| `wireguard-tools` (`wg`), module `wireguard` | P13d-e, P15, P16c |
| modules `esp4`, `xfrm_user` | P13f-g, P14, P16a-b, P16d |
| `nftables` (`nft`), module `nft_masq` | P14a-c |
| `act_pedit`, `act_csum`, `cls_u32`, `sch_clsact` | P13 (ECN mangler) |
| `sch_netem` | P15 loss, P16 reorder |
| `ethtool` | fragment and replay size accounting (offloads off) |

```bash
apt install iproute2 nftables wireguard-tools ethtool
```

## Use

```bash
python3 -m validation.round2.run --probe                 # facilities and per-case NOT RUN reasons
python3 -m validation.round2.run --dry-run --only P13a   # print every command of one run, execute nothing
python3 -m validation.round2.run --only P13a --runs 1    # smoke test one case
python3 -m validation.round2.run                         # the frozen protocol: 20 runs per case
```

On Windows with WSL2, run as root:
`wsl -d Ubuntu -u root --cd <repo> -- python3 -m validation.round2.run`.

## Outputs (`validation/round2/results/`)

| File | Content |
|---|---|
| `observations.csv` | raw rows in the repository's layering schema |
| `verdicts.csv` | one disposition per case |
| `calibration.md` | credence, outcome and Brier term per scored prediction |
| `summary.md` | generated table, environment record, Brier score |
| `environment.txt` | kernel, WSL2 flag, tool versions, frozen commit hash |
| `errors.txt` | setup failures |

Interpretation goes in the hand-maintained
[`docs/layering-real-stack-results-round2.md`](../../docs/layering-real-stack-results-round2.md).

## Dispositions

CONFIRMED, REFUTED, INCONCLUSIVE (cause gate failed), INVALID (ECN, SPI, fragment or
depth gate failed; a P13 control failed; warm-up failed; setup error) and NOT RUN
(facility missing). Only CONFIRMED and REFUTED are evidence; the Brier score ignores the
rest. Rules are in `verdict.py`, mirrored by the kernel-free tests in
`tests/test_round2.py`.

## Cases

| Case | Stack | Manipulation | Predicted |
|---|---|---|---|
| `P13a`-`P13c` | IPIP | outer CE / outer ECT(0) / outer CE | 0 % / 100 % / 100 % |
| `P13d`-`P13e` | WireGuard | outer CE | 100 % |
| `P13f`-`P13g` | ESP tunnel | outer CE | 100 % |
| `P13h_ipip`, `P13h_wg`, `P13h_esp` | each | no mangler, half Not-ECT / half ECT(0) | 100 %, unchanged |
| `P14a`, `P14b` | two ESP clients + masquerade | first client warms up | first 100 %, second 0 % |
| `P14c` | two ESP-in-UDP clients + masquerade | distinct NAT-T ports | both 100 % |
| `P14d` | two ESP clients, no NAT | control | both 100 % |
| `P15_EtoF` | WireGuard, `wg0` MTU 2100 | encrypt then fragment | 2112 B per datagram |
| `P15_FtoE` | WireGuard, `wg0` MTU 1420 | fragment then encrypt | 2180 B per datagram |
| `P16a` | ESP tunnel, `replay-window 32` | netem 100 ms, 25 % reorder | delivered = reference count |
| `P16b` | ESP tunnel, `replay-window 32` | netem 4 ms, paced 2 ms | 100 % |
| `P16c` | WireGuard | netem 100 ms, 25 % reorder | 100 % |
| `P16d` | ESP tunnel, `replay-window 256` | netem 100 ms, 25 % reorder | 100 % |

## Implementation choices the frozen file does not fix

These are harness decisions, not predictions; each is also recorded in the results
document's addendum.

- Delivery cases send 50 datagrams of 228 inner bytes, 10 ms apart; warm-up probes use
  port 9998 and the measured flow port 9999, so handshake and ARP never enter a window.
- Wire size is the IPv4 *total length* from an `AF_PACKET` tap at `vA1` egress. A
  2000-packet burst needs a larger tap buffer than the 208 KB default; the sniffer asks
  for 32 MB and every namespace gets `rmem_max = 64 MB`.
- **P15 sender**: the sending socket clears DF (`IP_MTU_DISCOVER = IP_PMTUDISC_DONT`) so
  that the `F->E` ordering can fragment the inner datagram instead of failing with
  `EMSGSIZE`. Both orderings use the same sender.
- **P15 fragments**: a non-first IP fragment carries no UDP header, so the P15 capture
  predicate is "UDP to the WireGuard port **or** a non-first fragment"; a plain port match
  halves the fragment count.
- **P14c ESP-in-UDP**: the kernel only diverts ESP-in-UDP to xfrm when a UDP socket with
  `UDP_ENCAP_ESPINUDP` exists. The harness holds one on port 4500 in `rs2B`
  (`endpoints.py encaplisten`); without it the packets are delivered as plain UDP and
  `UdpInNoPorts` climbs.
- **P14 warm-up race**: the client that is *not* first has its ARP resolved by one plain
  UDP packet to the far underlay address, so the ESP conntrack race is decided by the
  first client's ESP traffic and not by warm-up probes.
- **P16 pacing**: the `D = 4 ms` case is paced at 2 ms per datagram. At the fastest rate
  the sender sustains, the observed depth is ~2000, which cannot satisfy the frozen
  depth gate (`<= 16`); the frozen text makes the depth gate, not the nominal delay, the
  definition of the case.
- **P16 replay window > 32**: on this kernel/iproute2, `replay-window 256` is accepted
  and silently turns the SA into an ESN SA (`anti-replay esn context`). That is recorded
  as measured, not worked around.
- One AEAD key is generated **once per SA pair**; both ends must share it.
- `netem` is installed with `limit 100000`; the default 1000-packet queue would drop P16
  packets before the replay window sees them.
