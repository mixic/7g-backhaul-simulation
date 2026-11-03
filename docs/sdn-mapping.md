# Mapping the role-fluid concepts onto an SDN stack

This document maps the repository's recent concepts — continuous dual-role
capacity split, authenticated name-class admission, signed demand trends, the
layered authentication scope and RFMP role epochs — onto the layers of a
Software-Defined Networking (SDN) stack, and defines the additional components
that turn that stack into a **Software-Defined Content Distribution Network**
(SD-CDN) or a **Software-Defined Backhaul** (SD-BH).

It is an architecture mapping plus a small executable control-plane prototype,
not a claim that any of this interoperates with OpenFlow, P4, ONOS, or a
production SDN controller.

## 1. SDN stack layers and their repository counterparts

| SDN layer | Function | Repository counterpart |
|---|---|---|
| Data plane (DP) | Per-packet forwarding, serving, admission, encapsulation | `simulation/dual_role.py` (serve/forward split), `simulation/layering/` (C/E/T/F/S), `simulation/rfmp.py` (role epochs, reordering) |
| Southbound interface (SB) | Controller-to-node instructions | `simulation/sdn_plane.py` (`SouthboundMessage`, `set_alpha`, epoch and admission actions) |
| Control plane (CP) | Global state, policy reconciliation, role/path computation | `simulation/sdn_plane.py` (`FloodAwareController`), `simulation/role_fluid.py` (potential field), `simulation/trends.py` (velocity/acceleration) |
| Northbound interface (NB) | Application policies and intent | not implemented; described in §4–§5 as a policy schema |
| Orchestration | Lifecycle of services, replicas, clusters | `simulation/orchestration.py` (Kubernetes-inspired scaler, multicloud placement) |
| Telemetry | State collection for the CP | `simulation/telemetry.py`, the per-tick link/α traces in `dual_role.py` |

In SDN terms, this repository is a **flow-level control model with a
simulated southbound interface**: the controller computes decisions and applies
them to the data-plane model; there is no wire protocol, no OpenFlow message
encoding, and no switch.

## 2. Mapping the new concepts

### 2.1 Continuous dual-role split (`α`)

The dual-role model splits each node's resource between serving (`α`) and
forwarding/load balancing (`1 − α`). In SDN terms:

- the **decision** is a control-plane function: it needs demand, link and
  attack state;
- the **execution** is a data-plane function: per-packet serve-versus-forward;
- the **interface** is a southbound `set_alpha` instruction.

The local controller in `dual_role.py` is a *distributed* control plane: each
node decides from local telemetry. The SDN variant in `sdn_plane.py` is a
*logically centralized* control plane: one policy computes `α` for all nodes
and pushes it over the SB interface.

### 2.2 Authenticated name-class admission

The attack-aware experiment admits only authenticated names and drops
unauthenticated flood volume. In SDN terms this is an **admission application**
on the control plane that installs a filtering rule at the data plane:

- NB: "only name classes signed by the content authority are eligible for
  serving";
- CP: classify the request's name class and compute the admitted volume;
- SB: `set_admission` with a class table and error parameters;
- DP: enforce the drop/allow decision.

The layered-protocol testbed supplies the *scope* constraint: a field that is
inside an integrity scope cannot be rewritten by a middlebox (or a controller)
without breaking authentication. The same rule applies here: the controller may
act on a name only if the name is authenticated and visible; a field an
attacker can rewrite (for example an unauthenticated header) is not a safe
input to the admission decision.

### 2.3 Signed velocity and acceleration

Velocity and acceleration are **control-plane analytics**: the CP estimates
demand/link trends from telemetry and may use them for proactive `set_alpha`
or `set_path_weight`. The signed-trend experiment showed that using the raw
signed second derivative globally causes role churn, so a production CP would
filter/localise the signal (deadband, low-pass, per-name-class) before issuing
instructions. The negative result is a design constraint on the CP, not just on
the DP.

### 2.4 RFMP role epochs

RFMP already defines role epochs and handoff windows. In the SDN mapping, the
CP owns the **epoch decision** and the DP executes it:

- SB action `start_epoch(node, role, boundary, headstart, tail)`;
- DP applies the transition mechanics in `simulation/rfmp.py`
  (overlap, duplicate suppression, bounded gap);
- telemetry reports the gap and duplicate rate back to the CP.

This is the missing loop: current RFMP validation scripts the epochs; the SDN
prototype here still drives the flow-level α, not RFMP epochs. Closing that
loop is the next engineering step (§6).

### 2.5 Layered authentication scope

The layering testbed's survival condition — a field is safe to mutate only if
it is visible and outside the integrity scope — becomes an **SB policy
constraint**. The controller must not install a rewrite of an authenticated
field, and it cannot rely on fields that are encrypted or unreachable by the
parser depth. This turns an encapsulation result into a control-plane
admissibility rule.

## 3. Additional components for an SD-CDN

An SD-CDN adds content-aware applications to the SDN stack. The following are
missing from the current repository and are the natural build items:

| Component | Role | Interface | Status |
|---|---|---|---|
| Name/content controller | Maps names to replicas; owns the name-class table | NB policy → CP | partial (`simulation/name_fabric.py`) |
| Replica placement controller | Chooses cache/server locations from demand | NB policy → orchestration | model exists (`simulation/cdn.py`) |
| Cache controller | Warming, eviction, hit-ratio caps | DP + telemetry | model exists |
| Admission controller | Authenticated name classes, flood filtering | SB `set_admission` | prototype (`sdn_plane.py`, attack-aware model) |
| Role/α controller | Serve-versus-forward split | SB `set_alpha` | prototype |
| Telemetry collector | Per-node load, hit ratio, α, latency | SB → CP | model traces |
| Origin/ingress policy | What may enter the mesh, and at what rate | NB policy | not implemented |

The SD-CDN control loop is: name/content app expresses intent → CP reconciles
placement, admission and role split → SB installs `set_alpha`,
`set_admission`, `set_replica` → DP serves/forwards → telemetry returns.

## 4. Additional components for an SD-BH

An SD-BH is the transport-focused subset. It needs:

| Component | Role | Interface | Status |
|---|---|---|---|
| Link-state collector | Capacity, latency, MTU, loss per link | telemetry → CP | model exists |
| Path computation / TE | Path weights and water-filling | SB `set_path_weight` | model exists (`role_fluid.py`) |
| Role/epoch orchestrator | RFMP epochs and role transitions | SB `start_epoch` | specified, scripted |
| Tunnel/encapsulation manager | T/E/S stack selection per path | SB `set_stack` | model exists (`simulation/layering/`) |
| Admission/attack policy | Shared with SD-CDN | SB `set_admission` | prototype |
| SLO/priority controller | Per-class latency/throughput targets | NB policy | not implemented |
| Telemetry | One-way delay, loss, reorder, duplicates | SB → CP | model exists |

The SD-BH loop is: transport app states SLOs and failure policy → CP computes
paths, stacks and role epochs → SB installs them → DP forwards with the RFMP
and layering rules → telemetry closes the loop.

## 5. Shared interfaces (schemas)

A minimal SB message:

```text
SouthboundMessage(node, action, value)
  action ∈ {set_alpha, set_admission, set_path_weight, start_epoch, set_stack}
```

A minimal NB intent:

```json
{
  "service": "content-origin-42",
  "name_classes": {"signed": "serve", "unsigned": "drop"},
  "slo": {"p95_latency_ms": 100, "min_delivery_percent": 95},
  "flood_policy": {"attacked_target": "forward_only", "unattacked_edges": "serve"},
  "telemetry": ["alpha", "link_load", "hit_ratio", "p95_latency"]
}
```

These are documentation schemas, not implemented encodings. The executable
prototype implements only `set_alpha` for the flood policy.

## 6. Executable prototype and falsifiable claim

`simulation/sdn_plane.py` implements:

- `SouthboundMessage` — the controller-to-node instruction;
- `FloodAwareController` — a CP policy that, on an attack alert, pins the
  attacked target to `α = 0` (forward-only) and unattacked edge targets to
  `α = 1` (serve), leaving interior nodes as forwarders; with no alert it
  returns no instructions and the data-plane local loop keeps running;
- `SDNDualRoleSimulation` — applies the southbound instructions instead of the
  local update.

The pre-registered claim is:

> An SDN controller that pushes the flood-aware role policy over the southbound
> interface preserves steady-state delivery within 0.5 pp of the local fluid
> controller, and under the DDoS flood delivers at least 95 % legitimate
> traffic to the unattacked target `E3`, at least 5 pp above the local
> controller.

It is refuted if the steady guard or the flood isolation bound fails. The
attack alert is stipulated perfect (the controller knows which target is
flooded), which is the SDN analogue of the perfect classifier; it is not a
claim about attack detection.

The prototype does **not** implement OpenFlow, P4, a real switch, RFMP epoch
messages, name verification, cache placement or path-weight messages. It
demonstrates the control-plane/data-plane split and the policy override on the
flow model only.

## 7. What this mapping does and does not establish

- It establishes a concrete correspondence between every recent concept and an
  SDN layer, and it identifies the missing SD-CDN/SD-BH components.
- It does not establish that the resulting architecture outperforms a
  production SDN, CDN or backhaul controller; no such controller was run.
- The SDN prototype is flow-level. RFMP epoch control, real name verification,
  cache-placement control and path-weight messages remain unimplemented.
- The attack alert is stipulated; the admission rates in the attack-aware
  experiment are stipulated. Detection and classification are the hard parts
  and are not solved here.
