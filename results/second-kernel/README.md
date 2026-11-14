# Second-kernel results: NOT RUN

**Status: NOT RUN.** No native Linux host or second kernel is available to the
agent. The available host is WSL2 kernel
`6.18.58.1-microsoft-standard-WSL2`, the same kernel as the reported run; it is
not a replication.

The runbook is
[`validation/real_stack/RUNBOOK-second-kernel.md`](../../validation/real_stack/RUNBOOK-second-kernel.md).
A human with a native Linux VM should create:

```text
results/<kernel-id>/
  environment.txt
  round1/{observations.csv,verdicts.csv,summary.md,environment.txt,errors.txt}
  round2/{observations.csv,verdicts.csv,calibration.md,summary.md,environment.txt,errors.txt}
  comparison.md
  comparison-round1.md
```

Do not add fabricated data here. If the run is not performed, Paper A keeps the
one-kernel shortfall in its abstract and limits.
