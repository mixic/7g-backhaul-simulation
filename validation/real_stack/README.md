# Real-stack harness (P8-P12)

Executable form of [`docs/layering-real-stack-predictions.md`](../../docs/layering-real-stack-predictions.md),
which was frozen at commit `46c7b40` before any harness code existed. The harness
exercises **kernel WireGuard, kernel IPsec (`xfrm`: AH and ESP), kernel IPIP and kernel
NAT (`nftables`)** in three network namespaces, so agreement or disagreement is evidence
about the survival rule rather than about the repository's own codec.

> **Status: run against a kernel.** The frozen 20-runs-per-case protocol completed on
> WSL2 kernel `6.18.58.1-microsoft-standard-WSL2`: 15 case records (12 counted cases and
> their controls, 300 runs), all CONFIRMED. Interpretation is in
> [`docs/layering-real-stack-results.md`](../../docs/layering-real-stack-results.md), the
> raw rows are in `results/`. Kernel-free tests (`tests/test_real_stack.py`) pin the
> closed-form tables, parsers, gates and verdict rules. Record any future syntax fix as a
> dated addendum in the results document; never edit the frozen predictions.

## Requirements

Linux, **root**, and:

| Need | For |
|---|---|
| `iproute2` (`ip`, `tc`), `python3` | everything |
| `nftables` (`nft`), module `nft_masq` | NAT (P8, P12) |
| `wireguard-tools` (`wg`), module `wireguard` | P8c, P9, P10, P11 |
| module `ipip` | P10 |
| modules `esp4`, `ah4`, `xfrm_user` | P8a, P8b, P12 |
| modules `act_pedit`, `act_csum`, `cls_u32`, `sch_clsact` | P11 |
| `ethtool`, veth that allows TX **and** RX checksumming off | P12 (and P11a corroboration) |

```bash
apt install iproute2 nftables wireguard-tools ethtool
```

On Windows with WSL2 (as for the existing Linux harness) run as root:
`wsl -d Ubuntu -u root --cd <repo> -- python3 -m validation.real_stack.run --probe`.
The WSL2 kernel may lack AH or `act_pedit`; the affected cases then report **NOT RUN**
with the missing facility named, which is a legitimate outcome. A small Linux VM
with a distribution kernel avoids that.

## Use

```bash
python3 -m validation.real_stack.run --probe                  # facilities and per-case NOT RUN reasons
python3 -m validation.real_stack.run --dry-run --only P8a     # print every command of one run, execute nothing
python3 -m validation.real_stack.run --only P9 --runs 2       # smoke test one prediction
python3 -m validation.real_stack.run                          # the frozen protocol: 20 runs per case
```

`--only` takes case ids (`P8a`, `P10_w_to_y`) or prediction ids (`P11`).
**Read `--dry-run` output before the first real run.**

If a run is interrupted: `ip netns del rsA; ip netns del rsN; ip netns del rsB`.

## Outputs (`validation/real_stack/results/`)

| File | Content |
|---|---|
| `observations.csv` | raw rows in the repository's layering schema (`source, scenario, policy, seed, metric, value, unit`) |
| `verdicts.csv` | one verdict per case (P10 gives `P10a` and `P10b`) |
| `summary.md` | generated table plus the environment record |
| `environment.txt` | kernel, WSL2 flag, tool versions |
| `errors.txt` | setup failures (command, exit code, stderr) |

Interpretation goes in the hand-maintained `docs/layering-real-stack-results.md`,
which this tool never writes. Do not overwrite a refutation narrative there.

## Dispositions

CONFIRMED, REFUTED, INCONCLUSIVE (cause gate failed), INVALID (mutation gate failed, a
no-middlebox control failed, offload could not be disabled, packet counts off, or a setup
error) and NOT RUN (facility missing). Only CONFIRMED and REFUTED are evidence. Verdict
rules are in `verdict.py` and mirror the frozen text; the tests pin them down.

## Cases

| Case | Stack | Middlebox | Predicted |
|---|---|---|---|
| `P8a` / `P8a_control` | AH tunnel | NAT / none | 0 % / 100 % |
| `P8b` / `P8b_control` | ESP tunnel | NAT / none | 100 % / 100 % |
| `P8c` / `P8c_control` | WireGuard | NAT / none | 100 % plus learned endpoint / 100 % |
| `P9` | WireGuard | none | `wire = 60 + 16*ceil(L/16)` |
| `P10_y_to_w`, `P10_w_to_y` | IPIP then WG; WG then IPIP | none | `d(L)` = -4 or +12 |
| `P11a` / `P11b` / `P11c` | WireGuard | UDP length 9 (checksum untouched / recomputed) / ToS | 0 % / 0 % / 100 % |
| `P12a` / `P12b` / `P12c` | ESP transport | NAT with inner checksum / NAT with checksum 0 / none | 0 % / 100 % / 100 % |

## Harness parameters the frozen file does not fix

These are implementation choices; changing one is an addendum, not a new prediction.

- 5 packets per length in P9/P10 sweeps, 10 ms between packets, one sender process per length.
  Sweep packets are attributed to a length by capture timestamp.
- Delivery runs send 50 datagrams of 228 inner bytes (200 B UDP payload), 10 ms apart.
- Warm-up probes use UDP port 9998 (the measured flow uses 9999). WireGuard cases wait up to
  10 s for a completed handshake; IPsec cases send five probes to resolve ARP.
- The mangler is installed **after** warm-up, so handshake packets are never mangled.
- Offload is disabled on all four veth ends and **verified with `ethtool -k`** (TX and RX
  checksumming). veth marks received packets as already verified when RX checksumming is on,
  which would make P12a pass or fail for the wrong reason. If it cannot be turned off, the
  checksum-dependent cases are INVALID, not refuted.
- Wire size is the IPv4 total length from an `AF_PACKET` tap at `vA1` egress. Checksum values
  from that tap are unreliable (pre-offload) and no gate uses them.
- A case is judged only after all runs complete; a single deviating run refutes a prediction
  that states zero tolerance.

## Known risks to check on first contact (all resolved here)

1. `tc` syntax. Resolved on iproute2 6.19: the layered
   `pedit ex munge udp len set 9` form is rejected ("bad pedit parsing"); the harness
   uses the raw 2-byte form `pedit ex munge offset 24 u16 set 0x0009` (the outer UDP
   length sits at IPv4-header offset 24 = 20 IP + 4 UDP bytes). `csum udp`, `csum ip4h`
   and the `u32 match ip dport` filter work as written.
2. ESP transport-mode policy with a wildcard inbound source (`tmpl` without addresses).
3. Whether conntrack and masquerade pass protocols 50 and 51 address-only (the mutation gate
   will show it if not).
4. WireGuard timers: tests must finish well inside the 120 s rekey interval; passive
   keepalives travel B to A and are not captured at `vA1` egress.
5. The AH key length and truncation (`auth-trunc hmac(sha256) ... 128`) as accepted by your
   kernel and iproute2.
6. P10 nested tunnels: MTUs (ipip0 1400, ipip1 1480, wg0 1420) and routing loops between the
   overlay and underlay prefixes.

If a case is INVALID because of one of these, fix the harness, note it in an addendum, and
re-run; the prediction itself stays frozen.

## Scope

Measures sizes, delivery and drop causes. It does not evaluate cryptographic security, and
one kernel, one NAT implementation and veth links say nothing about arbitrary middleboxes.
