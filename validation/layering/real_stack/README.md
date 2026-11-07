# Real-stack layering harness (P8, P9)

Shell harnesses that reproduce the P8/P9 predictions in
[`../../docs/layering-real-stack-predictions.md`](../../docs/layering-real-stack-predictions.md)
on a Linux host with root, network namespaces, nftables and WireGuard/xfrm. They
were run on WSL2 as root (`wsl -u root`); the results are recorded in
[`../../docs/layering-real-stack-results.md`](../../docs/layering-real-stack-results.md).

| Script | Prediction | What it does |
|---|---|---|
| `p9.sh` | P9 | WireGuard `cA`–`cN`–`cB`; sends inner IPv4 packets of length `L` and captures the outer IP total length |
| `p8c.sh` | P8c | WireGuard through an nftables `masquerade`; counts delivery and checks the peer endpoint |
| `p8ab.sh` | P8a, P8b | IPsec tunnel mode (AH, ESP) through the same NAT; counts delivery and reads `XfrmInStateProtoError` |

## Running

```bash
sudo apt-get install -y nftables wireguard-tools tcpdump
tr -d '\r' < p9.sh  | sudo bash   # or p8c.sh / p8ab.sh
```

Each script builds fresh namespaces, fresh keys, and tears everything down at the
end. The capture and counter setup follows §7 of the predictions file. Raw
observations for the run in the results file are in
[`../results/real_stack_observations.csv`](../results/real_stack_observations.csv).

## Known limitation (P11)

P11 (`tc pedit` rewrite of the outer UDP length) is **not** in this directory in a
working form: the inert ToS control failed to deliver under checksum offload on
the veth pair, so the case is recorded INCONCLUSIVE, not refuted. Re-running with
`ethtool -K <dev> tx off` on the mangling path is the next step.
