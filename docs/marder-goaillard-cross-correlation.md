# Theoretical Cross-Correlation: Neuronal Degeneracy and Network Homeostasis

**Document Status:** Motivation and analogy, not derivation
**Target Reference:** Marder, E., & Goaillard, J. M. (2006). *Variability, compensation and homeostasis in neuron and network function.* Nature Reviews Neuroscience, 7(7), 563-574.
**Project Context:** 7G-Backhaul-Simulation (Surgical, Rate-Controlled Multicooperative Backhauls)

## 1. Purpose and Disclaimer
This document records the neuroscience analogy that motivated the MKB/OEF framing and the two metrics we derived from it. It is not a derivation, and it transfers no theorem.

Marder & Goaillard (2006) is a **review** of neuronal variability, compensation and homeostasis. It synthesises electrophysiology and modelling results about ion-channel densities and firing patterns; it is not a control-theory result and it says nothing about packet networks, queues or congestion. No quantity in the review corresponds to a network state vector, and nothing in it predicts how a queueing controller will behave.

What follows is therefore an analogy. It suggests *what to measure* (degeneracy and compensatory distance) and *why a designer might try* multidimensional compensation. The measurements are reported honestly and do not confirm the analogy.

## 2. Core Concepts from Marder & Goaillard (2006)
The review addresses how biological neurons maintain stable function despite continuous turnover and external perturbation:
*   **Degeneracy:** Multiple combinations of underlying parameters (for example ion-channel densities) can produce the same functional output (a firing pattern). There is no single "correct" parameter set.
*   **Compensation:** When a parameter is artificially altered, the system invokes slow compensatory mechanisms to restore normal function.
*   **Multidimensional parameter spaces:** The system operates within a high-dimensional space of possible states, and homeostasis keeps it within a stable region of that space.

## 3. Direct Conceptual Mapping (analogy, not equivalence)

### 3.1. MKB as "Multidimensional Parameter Space" Navigation
*   **Biological analog:** The neuron operates in a multidimensional parameter space (conductances, time constants).
*   **Network implementation:** Our MKB controller tracks a 4-D telemetry vector (`CBF, OEF, Queue_Depth, Drop_Rate`) and thresholds on its acceleration. The analogy is that a neuron navigates a parameter space while a switch navigates a telemetry space; the two spaces are only structurally similar. The M4 benchmark refutes the mechanism: the peak burst speed is statistically unchanged relative to the 1D limiter (218.4 vs 222.0 units/s, paired p = 0.89).

### 3.2. OEF as "Compensatory Homeostasis" and "Degeneracy"
*   **Biological analog:** When a neuron's primary conductance is blocked, it may upregulate other channels to maintain activity — degeneracy in action.
*   **Network implementation:** When CBF (throughput) falls, the OEF controller raises the legitimate class's queue weight instead of dropping packets. That is the intended "degenerate solution". The M4 benchmark does not confirm it: OEF does not beat `static_isolation` on goodput (0.8465 vs 0.8648, paired p = 0.53).

### 3.3. Savant as Extreme "Compensation"
*   **Biological analog:** Systems can exhibit "multiple solutions to the production of similar behaviour".
*   **Network implementation:** The Savant mechanism saves a critical local circuit by sacrificing global transit. The measured cost is negative neighbour spillover and neighbour cascading failure — a biological trade-off in spirit, but not a quantity the review defines.

## 4. Metrics Derived from the Analogy
The analogy suggested two measurements, which the M4 runner implements. They are derived *from* the analogy, not validated by it, and the measured values do not support a "degenerate" or "homeostatic" claim.

1.  **Degeneracy Index** — a 10×10 grid over `(Path_Utilization, OEF)`; the count of occupied bins whose mean goodput exceeds 90 %. Measured: **5 of 37 occupied bins** (13.5 %), with the grid only partially populated along the OEF axis (6 of 10 OEF bins) because the actuator barely moves off `OEF = 0`.
2.  **Compensatory Distance** — the Euclidean distance the mean 4-D state travels from its steady baseline during the shockwave. Measured: `m4_oef` 0.0343, `m4_combined` 0.0389, `m4_mkb` 0.0149. The OEF actuator moves the state *farther* from baseline than the no-OEF trigger — the opposite of what the homeostatic analogy predicts.

## 5. Conclusion
Marder & Goaillard (2006) motivates a multidimensional, compensatory view of a neuron. It does **not** prove that a network controller should behave the same way, and the M4 measurements do not confirm that it does. The analogy is useful for organising hypotheses and for defining two honest metrics; it is not evidence that the OEF or MKB mechanisms work. The intended empirical validation has been run and is largely negative (see `results/m4/m4_summary.md`).
