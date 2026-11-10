# Real-stack layering harness (bash, exploratory)

Shell harnesses that reproduced the P8/P9/P10/P12 predictions in
[`../../docs/layering-real-stack-predictions.md`](../../docs/layering-real-stack-predictions.md)
on a Linux host with root, network namespaces, nftables and WireGuard/xfrm. They
were run on WSL2 as root (`wsl -u root`). These scripts were the first-contact
exploration; the **committed, canonical harness is the Python package in
[`../../validation/real_stack/`](../../real_stack/README.md)**, and the results
recorded in
[`../../docs/layering-real-stack-results.md`](../../layering-real-stack-results.md)
come from that package (frozen 20-run protocol). These scripts are kept for
reproduction and for the record of how the ToS-control defect was found.

| Script | Prediction | What it does |
|---|---|---|
| `p9.sh` | P9 | WireGuard `cA`–`cN`–`cB`; sends inner IPv4 packets of length `L` and captures the outer IP total length |
| `p8c.sh` | P8c | WireGuard through an nftables `masquerade`; counts delivery and checks the peer endpoint |
| `p8ab.sh` | P8a, P8b | IPsec tunnel mode (AH, ESP) through the same NAT; counts delivery and reads `XfrmInStateProtoError` |
| `p10.sh` | P10 | both nested IPIP/WireGuard orderings |
| `p10wy.sh` | P10 `W→Y` | the WireGuard-then-IPIP ordering with the nested endpoint over `ipip1` |
| `p11v2.sh` | P11 | exploratory `tc pedit` on the outer UDP length; the inert ToS control failed here (see below) |
| `p12.sh` | P12 | ESP transport + NAT, inner checksum computed vs zeroed |

## Running

```bash
sudo apt-get install -y nftables wireguard-tools tcpdump ethtool
tr -d '\r' < p9.sh  | sudo bash   # or any other script
```

Each script builds fresh namespaces, fresh keys, and tears everything down at the
end. Raw observations for the canonical run are in
[`../../../validation/real_stack/results/observations.csv`](../../real_stack/results/observations.csv).

## P11: the ToS-control defect in this bash set

`p11v2.sh` is the script whose inert ToS control delivered 0/50 and made P11 look
INCONCLUSIVE. The defect was in the **mangler setup**, not in the kernel: it used
a `root prio` qdisc and a `csum ip` action. The Python harness installs a
`clsact` qdisc with `pedit … csum ip4h`, and its inert control delivers 100 %;
P11 is therefore **CONFIRMED** in
[`docs/layering-real-stack-results.md`](../../layering-real-stack-results.md).

When a `pedit` case misbehaves, bisect it with:

1. `tc -s filter show dev <dev> egress` — the filter's packet counter must rise.
2. `tcpdump -i <peer> -n` — the mangled packets must leave the router.
3. A **no-op** pedit (`ip tos set 0`) — if delivery stays 100 %, the filter is
   sound and a failing rewrite is the rewrite's effect.
4. `ethtool -k` on all veth ends — TX **and** RX checksumming must be off.
