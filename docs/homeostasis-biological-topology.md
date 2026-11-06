# Theoretical Cross-Correlation: Network Homeostasis and Biological Topology

**Document Status:** Motivation and analogy, not derivation
**Target Reference:** *"Homeostasis in Networks with Multiple Input Nodes and Robustness in Bacterial Chemotaxis"* (arXiv:2011.04415)
**Project Context:** 7G-Backhaul-Simulation (Surgical, Rate-Controlled Multicooperative Backhauls)

## 1. Purpose and Disclaimer
This document records the biological *analogy* that motivated the OEF and MKB controllers. It is not a derivation, and it transfers no theorem.

arXiv:2011.04415 is a theoretical-biology paper about homeostasis in ordinary-differential-equation network structures. It classifies homeostatic mechanisms by network topology and characterises their robustness in dynamical-systems terms, but it contains **no routing algorithms, no congestion-control law, and no queueing model**. Its results concern how multiple input nodes combine to regulate a scalar variable, not how packets behave in a finite-buffer network.

A shared vocabulary ("homeostasis", "multiple input nodes", "counterweight") does not transfer a theorem. Nothing in the reference constrains, validates or predicts the behaviour of the controllers in `simulation/`. The mapping below is a research-organising analogy: it names a family of control designs and suggests why a designer might try them, and that is all.

## 2. Core Concepts from the Reference Paper
The paper defines **homeostasis** as a network's ability to maintain a regulated variable within a tight range despite external perturbations. Its key contributions are, in its own terms:
*   **Model-Independent Classification:** Homeostasis mechanisms can be classified based solely on network topology, independent of the specific differential equations.
*   **Input Counterweight Homeostasis:** In networks with multiple input nodes, homeostasis is achieved through the dynamic balance of these multiple inputs.
*   **Robustness:** The formalization of how stable the homeostatic mechanism is under varying conditions (derived from dynamical systems theory).

## 3. Direct Conceptual Mapping (analogy, not proof)

### 3.1. OEF (Fick Principle) as Metabolic Homeostasis
*   **Biological Analog:** A cell maintaining its metabolic rate (CMRO₂) despite reduced blood flow (CBF).
*   **Analogy:** The paper's core definition of homeostasis — maintaining a regulated variable despite perturbation.
*   **Network Implementation:** The OEF controller raises the legitimate class's queue weight when the CBF monitor sees delivered throughput fall. The mapping is suggestive: a regulated output (goodput) paired with an adjustable extraction fraction. **The M4 benchmark does not support the analogy empirically.** OEF does not beat `static_isolation` on legitimate goodput (0.8465 vs 0.8648, paired p = 0.53) and never reaches its 92 % target, because the CBF-drop trigger does not fire during the flood: a DDoS *raises* total delivered throughput rather than lowering it. The analogy motivated the test; the test refuted the mechanism.

### 3.2. MKB as "Input Counterweight Homeostasis"
*   **Biological Analog:** Balancing multiple inputs to maintain stability.
*   **Analogy:** The paper introduces *Input Counterweight Homeostasis* for networks with multiple input nodes.
*   **Network Implementation:** Our MKB controller defines the state as a 4-D vector `S(t) = [CBF, OEF, Queue_Depth, Drop_Rate]` and thresholds on the vector acceleration. The "multiple inputs" language is a loose analogy: the four dimensions are telemetry channels, not independent input nodes with a physical regulatory weight. The M4 benchmark also refutes the mechanism: the peak burst speed is statistically unchanged relative to the 1D limiter (218.4 vs 222.0 units/s, paired p = 0.89), and coupling OEF into the vector drive produces ~175 false-positive edits and roughly halves goodput.

### 3.3. Savant Hyper-Specialization and the Limits of Robustness
*   **Biological Analog:** The fragility of homeostasis; when a system breaks its normal balance to survive.
*   **Analogy:** The paper discusses robustness and dishomeostasis.
*   **Network Implementation:** The Savant mechanism trades global transit delivery for a local circuit. The measured cost — negative neighbour spillover and a cascading failure of neighbours — resembles the paper's dishomeostasis in spirit, but no quantity in the paper corresponds to the network's measured starvation threshold.

## 4. What This Does and Does Not Establish
1.  **Motivation, not validation.** The analogy suggests a class of control designs. It does not establish that they work; the M4 benchmark tests them and finds no goodput benefit under a DDoS shockwave.
2.  **A shared name is not a theorem.** The reference classifies ODE network structures regulating a scalar variable; it makes no prediction about a finite-buffer queueing network with a rate limiter.
3.  **Classical scope, on the network side.** The controllers are classical control laws (EMA baseline, double integrator, Euclidean acceleration norm). The biological mapping is a naming convention, not physics. It requires no speculative quantum or multidimensional physics.

## 5. Scope and Limitations
arXiv:2011.04415 is a theoretical biology paper analysing topological structures. It does **not** provide routing algorithms, congestion control mechanisms, or network protocols.

Our contribution — if any — is the **translation of a homeostatic control *idea* into executable, rate-controlled network actuators, and an honest empirical test of that idea**. The reference supplies the *motivation* (topological stability); the simulation supplies the *measurement* (Surgical, OEF and MKB controllers), and the measurement is largely negative.

---
*Document generated for the 7G-Backhaul-Simulation repository. These mappings are analogies, not results. The intended empirical validation has been run, and it largely refutes the OEF and MKB mechanisms (see `results/m4/m4_summary.md`).*
