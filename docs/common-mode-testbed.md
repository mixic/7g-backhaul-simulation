# Common-mode testbed guide

**Status: implemented.** The flow-level testbed is in
[`simulation/common_mode.py`](../simulation/common_mode.py); the frozen protocol
is [`common-mode-predictions.md`](common-mode-predictions.md) and the 30-seed
results are in [`common-mode-results.md`](common-mode-results.md).

This guide is for running and extending the testbed. The scenario constants are
frozen for the reported experiment; changing them requires a new prediction file
and a new results section, not an edit to the frozen one.

## 1. What is in the testbed

| Piece | Role |
|---|---|
| `build_backhaul_scenario()` | six tenants, three aggregation sites, three providers, two clouds, shared identity/DNS/AI, shared tenant gateway, global controller, local fallbacks |
| `ARMS` | nine mechanisms from concentration to isolation + multipath + tested fallback |
| `EVENT_KINDS` | ten outage events, from a single link to a combined AI + link failure |
| `build_seed_inputs()` | one event, demand vector and fallback vector per seed, shared by all arms |
| `simulate()` | one arm, one seed, one event; returns availability, recovery, blast radius, path independence, fallback rate and cost |
| `tools/benchmark_common_mode.py` | the 30-seed paired run and three CSVs |

The model is flow-level: capacity and dependency conjunction, not packets. A
tenant is served only when its data path, control plane, tenant boundary and
fallback (when needed) are available together.

## 2. Run it

All arms, all events, 30 paired seeds:

```bash
py -3 tools/benchmark_common_mode.py --seeds 30
```

A subset (verdicts are skipped unless all arms and events are present):

```bash
py -3 tools/benchmark_common_mode.py --seeds 5 --events link ai_link --arms A1 A3 A6 A9
```

One arm/event from Python:

```python
from simulation import common_mode as cm

scenario = cm.build_backhaul_scenario()
result = cm.simulate(
    cm.ARMS["A6"], scenario=scenario, seed=2026, event_kind="ai_link"
)
print(result.availability_event, result.recovery_s, result.fallback_rate)
```

Outputs go to `output/common-mode/` by default:

| File | Content |
|---|---|
| `common_mode_per_seed.csv` | one row per seed, event and arm |
| `common_mode_summary.csv` | mean and 95 % CI per event and arm |
| `common_mode_verdicts.csv` | H16-H20 criteria, thresholds, per-seed pass fractions |

### 2.1 Sensitivity and break-even

The constants can be varied one at a time without touching the frozen defaults:

```bash
py -3 tools/benchmark_common_mode.py --sensitivity --seeds 30 --sensitivity-points 25
```

It writes `common-mode-sensitivity.csv` (the grid), `common-mode-break-even.csv`
(one row per constant and criterion), and a generated Markdown table under
`docs/paper-tables/`. The simulator takes an optional
`simulation.common_mode.ScenarioParams`; `simulate(..., params=...)` uses the
override for that call and never mutates the module constants. The default
`simulate(...)` is bit-identical to the frozen run (tested in
`tests/test_common_mode_sensitivity.py`).

## 3. Add an arm

Add an `Arm` to `ARMS` in `simulation/common_mode.py`:

```python
"A10": Arm(
    "A10", "my approach", "disjoint3", True, True, True, "tested", "local"
),
```

The fields are:

| Field | Values | Meaning |
|---|---|---|
| `path_policy` | `single`, `shortest3`, `disjoint3` | how paths are selected |
| `tenant_isolation` | `True`/`False` | whether the shared tenant gateway is on the availability path |
| `independent_control` | `True`/`False` | whether local identity/DNS replaces the shared services |
| `one_way` | `True`/`False` | whether the AI endpoint is off the availability path and local policy serves at 0.9 efficiency |
| `fallback` | `tested`, `untested`, `None` | activation probability, delay and capacity |
| `controller` | `none`, `local`, `global` | whether reallocation is absent, local or centralized |

If the arm needs a new mechanism, extend `_control_ok()` or `_service()` and add
a unit test. Then add the arm to the frozen predictions **before** running it;
the existing results do not cover a new arm.

## 4. Add an event

1. Add the name to `EVENT_KINDS`.
2. Add its targets in `_event_targets()`: failed nodes and/or failed links.
3. Add a unit test that the named link/node exists.
4. Freeze the event and its expected effect in a new predictions file.
5. Run the benchmark with `--events <new-event>`.

Events share their start and duration draws across arms; do not give one arm a
different schedule.

## 5. Change the scenario

`build_backhaul_scenario()` defines the nodes, links, SRLG groups, tenants and
shared dependencies. If you change it:

- keep every provider→cloud path ending at a cloud node; path enumeration stops
  at `c1`/`c2`;
- keep the `agg-j` SRLG grouping if you want a shared conduit to be testable;
- update the counts in `tests/test_common_mode.py`;
- write a new prediction file with the new constants and expected outcomes;
- do not compare the new run with the old results as if the scenario were the
  same.

## 6. Real-stack extension (not implemented)

The flow-level testbed is the reported experiment. A real-stack variant would
use Linux network namespaces:

- two disjoint paths from a client to a server through two routers;
- ECMP multipath at the client (multiple flows, so the hash uses both paths);
- `ip link set ... down` or `tc` for the outage;
- an `nftables` cut for the control plane;
- a UDP probe with sequence numbers to measure delivery.

A hardware data diode cannot be emulated by software; an nftables inbound cut is
the closest analogue and should be labelled as such. The real-stack extension is
listed as the next step in
[`common-mode-resilience.md`](common-mode-resilience.md), not claimed here.

## 7. Rules

- Freeze predictions before running a new arm, event or scenario.
- Use `build_seed_inputs()`; never give arms different seeds or events.
- Report refutations and deviations, not only passes.
- Do not describe the flow-level result as a measurement of a production network.
