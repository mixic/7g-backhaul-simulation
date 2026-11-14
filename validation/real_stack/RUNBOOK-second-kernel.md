# Runbook: second-kernel replication (M3)

**Owner: human (H).** The agent cannot run this: the available host is one WSL2
kernel, uid 1000, with no passwordless root. This runbook is prepared so a human
with a native Linux VM can execute the frozen round-2 protocol on a second kernel
and compare it mechanically. Do not fabricate a second-kernel result. If no host
exists, the status is **NOT RUN** and Paper A's abstract and limits say one
kernel.

The frozen protocol is
[`docs/layering-real-stack-predictions-round2.md`](../../docs/layering-real-stack-predictions-round2.md)
(P13-P16, 20 runs per case). The first kernel is
`6.18.58.1-microsoft-standard-WSL2`; its results are in
`validation/round2/results/`.

## 1. Host and packages

Use a native Linux VM (Ubuntu 24.04/26.04 or a distribution kernel), not WSL2 if
possible. The point is a different kernel, not a different userspace only.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv iproute2 nftables wireguard-tools ethtool
sudo modprobe ipip
sudo modprobe esp4
sudo modprobe xfrm_user
sudo modprobe wireguard
```

Check the facilities:

```bash
uname -r
python3 --version
ip -V
nft --version
wg --version
ethtool --version
id -u    # must be 0 for the harness
```

## 2. Clean checkout at the release commit

Run on a scratch clone so the committed first-kernel results are not overwritten:

```bash
git clone https://github.com/mixic/7g-backhaul-simulation.git /tmp/7g-second-kernel
cd /tmp/7g-second-kernel
git checkout <release-commit>
git rev-parse HEAD
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -q
```

Record the commit hash. The frozen predictions are not edited; if a harness
command needs a syntax fix on this kernel, record it as a dated addendum in the
results document, not as a change to the predictions.

## 3. Probe and dry-run

```bash
python3 -m validation.real_stack.run --probe
python3 -m validation.round2.run --probe
python3 -m validation.real_stack.run --dry-run --only P8a
python3 -m validation.round2.run --dry-run --only P13a
```

Read the dry-run output before executing. A missing facility gives a **NOT RUN**
case with its name; that is a legitimate outcome, not a failure to hide. A small
VM with a distribution kernel should have `ipip`, `esp4`, `wireguard`,
`nft_masq`, `act_pedit`, `act_csum` and `sch_netem`.

## 4. Run the frozen protocols

```bash
python3 -m validation.real_stack.run          # P8-P12, 20 runs per case
python3 -m validation.round2.run              # P13-P16, 20 runs per case
```

Both write `observations.csv`, `verdicts.csv`, `environment.txt` and
`summary.md` under `validation/real_stack/results/` and
`validation/round2/results/`. The round-2 run also writes `calibration.md`.
Check `errors.txt` is empty; if it is not, report the setup failure, do not
average it away.

## 5. Results layout

Copy the two result directories into the main repository under a kernel id:

```bash
KERNEL_ID=$(uname -r | tr -c 'A-Za-z0-9._-' '_')
cd /path/to/main/7g-backhaul-simulation
mkdir -p "results/${KERNEL_ID}/round1" "results/${KERNEL_ID}/round2"
cp /tmp/7g-second-kernel/validation/real_stack/results/* \
   "results/${KERNEL_ID}/round1/"
cp /tmp/7g-second-kernel/validation/round2/results/* \
   "results/${KERNEL_ID}/round2/"
cp /tmp/7g-second-kernel/validation/round2/results/environment.txt \
   "results/${KERNEL_ID}/environment.txt"
```

The layout is:

```text
results/<kernel-id>/
  environment.txt
  round1/{observations.csv,verdicts.csv,summary.md,environment.txt,errors.txt}
  round2/{observations.csv,verdicts.csv,calibration.md,summary.md,environment.txt,errors.txt}
  comparison.md
```

Do not copy a file you did not generate. If a case is NOT RUN, its row says so.

## 6. Compare the two kernels

```bash
python3 tools/compare_kernels.py \
    --left validation/round2/results \
    --right "results/${KERNEL_ID}/round2" \
    --out "results/${KERNEL_ID}/comparison.md"
```

The tool writes per-case verdicts side by side and every differing observation
(with scenario, policy, seed and metric). It does not decide which kernel is
right. A verdict disagreement is a **finding**: report it, quote the differing
observation, and state which gate differs. Do not edit the frozen predictions.

For round 1:

```bash
python3 tools/compare_kernels.py \
    --left validation/real_stack/results \
    --right "results/${KERNEL_ID}/round1" \
    --out "results/${KERNEL_ID}/comparison-round1.md"
```

## 7. Report

- Add a dated addendum to
  [`docs/layering-real-stack-results-round2.md`](../../docs/layering-real-stack-results-round2.md)
  with the kernel, the comparison file, and every disagreement.
- If every case agrees, say so and say what the second kernel does **not**
  establish (same userspace, same harness, one VM).
- If a case disagrees, report it as a finding; the frozen prediction is not
  changed. If the disagreement is a gate failure, report it as INVALID/NOT RUN,
  not as a refutation.
- Update Paper A's abstract and limits only with the actual result; if no second
  kernel was run, keep the one-kernel shortfall statement.

## 8. Stop conditions

- No root or missing facility: stop, report NOT RUN with the facility name.
- A frozen file would have to change: stop and ask the human owner.
- A test fails and the cause is not understood: stop and report.
- The comparison shows a disagreement: report it; do not "fix" the first kernel.
