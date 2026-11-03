# SDN control-plane results

**Claim:** pre-registered in [`docs/sdn-mapping.md`](sdn-mapping.md) §6.
**Verdict: CONFIRMED.** The SDN role-override policy preserves steady-state
delivery and raises legitimate delivery to the unattacked target from 92.08 %
to 99.07 % under the DDoS flood (+6.99 pp, against a required +5 pp).

This is a flow-level prototype of the control-plane/data-plane split, not an
OpenFlow implementation. The attack alert is stipulated perfect: the controller
reads the scenario's flood schedule, standing in for a detection system.

## 1. Arms (12 paired seeds)

| Arm | Steady delivered | Flood E1 | Flood E2 (attacked) | Flood E3 | Flood total |
|---|---:|---:|---:|---:|---:|
| separated roles | 99.23 % | 99.05 | 84.14 | 98.79 | 80.89 |
| local fluid | 99.24 % | 98.98 | 71.61 | 92.08 | 64.91 |
| SDN override | 99.24 % | 99.35 | 70.82 | 99.07 | 64.86 |

## 2. Pre-registered tests

| Test | Value | Threshold | Result |
|---|---:|---|---|
| steady guard | 0.00 pp loss | ≤ 0.5 pp | **PASS** |
| flood isolation | E3 99.07 %, +6.99 pp | E3 ≥ 95 %, gain ≥ 5 pp | **PASS** |

With no flood alert the controller emits no southbound instructions and the
local fluid loop runs unchanged, so the steady-state trace is identical
(99.24 %). During the flood the controller overrides the local loop: the
attacked target and interior nodes are pinned to `α = 0` (forward-only), the
unattacked edge targets to `α = 1` (serve). `E3` therefore keeps its local
serving capacity instead of releasing it under global pressure.

## 3. What this does and does not show

- It shows the value of the **control-plane/data-plane split** in this model:
  a policy with global attack knowledge can express a role override that the
  local controller cannot, and it protects the unattacked target.
- It does **not** reduce the attack's total congestion. Flood total delivered
  is 64.86 % versus 64.91 % for the local arm: the flood still transits the
  mesh. Protection comes from keeping `E3`'s serving capacity local, not from
  dropping attack volume. Combining this policy with the authenticated
  name-class admission from [`attack-aware.md`](attack-aware.md) is the obvious
  next step.
- The attacked target's legitimate delivery is essentially unchanged
  (70.82 % vs 71.61 %), because `α = 0` at `E2` removes local serving there.
- The alert is stipulated perfect. Detection, classification and the
  false-positive/false-negative costs are not solved here.
- The prototype implements only the `set_alpha` southbound action. Path
  weights, admission tables, RFMP epochs and name-class verification are
  mapped in the document but not wired.
- It is not an OpenFlow/P4/ONOS implementation and does not interoperate with
  a real switch.

## 4. SD-CDN and SD-BH implications

The mapping in [`sdn-mapping.md`](sdn-mapping.md) identifies the additional
components:

- **SD-CDN:** name/content controller, replica placement, cache controller,
  admission controller, role/α controller, telemetry, origin/ingress policy.
  Only the role/α and admission pieces have executable prototypes; placement
  and name verification remain module-level models or unimplemented.
- **SD-BH:** link-state collector, path computation, RFMP epoch orchestrator,
  tunnel/encapsulation manager, admission, SLO controller, telemetry. The path
  and role pieces exist as models; epoch orchestration is still scripted.

The experiment supports the *architecture* claim (a central policy can
override local role control), not a performance claim against a production
SDN, CDN or backhaul controller.

## 5. Reproduction

```powershell
py -3 tools\benchmark_sdn.py --output-dir figures
py -3 tools\plot_sdn.py --input-dir figures --output-dir figures
py -3 -m pytest tests\test_sdn_plane.py -q
```

Outputs: `figures/sdn_summary.csv`, `figures/sdn_verdict.csv`,
`figures/sdn_control.png`.

## 6. Limitations

- Flow-level model; no packets, no OpenFlow, no real switch or controller.
- One topology, one flood profile, perfect attack alert.
- The policy is role pinning; it is close to the separated baseline during the
  flood, and its value is the ability to revert to local fluid control when the
  alert clears.
- The RFMP loop is still open: the controller drives the flow model, not RFMP
  role epochs.
