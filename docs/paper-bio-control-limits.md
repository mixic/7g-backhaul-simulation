# Why Fair-Queueing Beats the Fick Principle: An Empirical Refutation of Homeostatic Network Control in Discrete Packet Networks

**Milan Nikolic** · Independent Researcher · <m_nikolic@yahoo.com>

**Comments:** 11 tables, 6 figures. Part of a three-paper series on topological
routing (arXiv:XXXX.XXXXX), protocol layering (arXiv:ZZZZ.ZZZZZ), and
bio-inspired control limits (this paper).
**Primary:** cs.NI · **Cross-list:** cs.PF.

**Series note.** This paper is part of a three-paper series. The companion papers
are *Complex-Rotation Manifold Routing* (arXiv:XXXX.XXXXX) and *When Do Protocol
Layers Commute?* (arXiv:ZZZZ.ZZZZZ). The identifiers are placeholders until the
companion papers are posted.

**Status:** focused negative-result paper. The layering testbed of the companion
paper is cited here only as a methodological influence. Every figure is generated
from a committed CSV by `tools/generate_paper_figures.py`, and
`figures/figure-data-manifest.md` lists every plotted value with its source file.

## Abstract

Biologically inspired network control — homeostatic adaptation, metabolic
extraction (Fick's principle), and multidimensional kinematic baselining — is
mathematically elegant, but it is rarely measured against simple engineering
baselines. We close this gap with a pre-registered, 30-seed study in a 100-node SimPy testbed
under DDoS shockwaves: a five-arm main comparison against static per-flow
isolation, plus a smoothing arm, a stack compiler and a three-detector campaign. The arms are faithful implementations of *one* reading of
that analogy — a set-point metabolic law and a compensatory state-geometry law —
not re-implementations of a specific published controller, and §6.2.5 states the
claim that follows. The result is negative, and the negative result is the
contribution. Static isolation is not beaten on goodput under the DDoS
shockwave: the extraction-fraction (OEF) controller reaches 84.65 % legitimate
goodput against 86.48 % (paired p = 0.527); the four-dimensional kinematic trigger
shaves 218.4 against 222.0 units/s of peak burst speed without significance
(p = 0.891); the smoothed-trigger arm issues more edits than the raw trigger
(7.5 % more in the energy audit, 13 % more in its own campaign). Running the two biological actuators together cuts goodput to 48.2 %. The
one arm that does beat static isolation — a mocked LLM stack compiler that cuts
wire bytes by 42 % — returns $3.3\times10^{-6}$ on energy (60 J inference against
$2.0\times10^{-4}$ J of transmission savings).

We convert each verdict into a break-even threshold, so the conclusions do not
rest on stipulated constants. The compiler becomes viable only if inference falls
below 0.2 mJ per three-call transition (about 0.07 mJ per call). Static isolation
stays cheapest for any churn cost above about 0.19 J per edit, 27× below the 5 J
stipulation. The smoothing verdict is independent of the constant, because the arm
issues more edits, not fewer. The extraction verdict is a null result rather than
a threshold: its 1.83-point deficit is not significant (p = 0.527), and the
simulator prices per-flow isolation state at zero, so any real-hardware cost
advantage for static isolation is smaller than simulated.

The root cause is structural: discrete packet buffers are zero-sum and
time-quantised, so continuous biological compensation cannot beat fair-queueing.
We state the result as a boundary on these controllers and workloads, not a
general claim about bio-inspired control: it fails where the "blood" (traffic)
becomes toxic, because discrete queues cannot extract efficiency from a poisoned
flow. We release the testbed, the predictions, and the break-even calculations.

## 1. Introduction

The motivating idea is that the Fick principle — `CMRO2 = CBF · OEF · Ca` — maps
onto network metabolism: when delivered throughput (CBF) falls, an extraction
fraction (OEF) should rise to protect legitimate traffic (CMRO2). We test this
idea directly, alongside a multidimensional kinematic trigger that watches the
geometry of a 4-D state vector `[CBF, OEF, Queue, Drop]`.

The analogy is seductive because it is *quantitative*. Fick's principle is a
conservation law with three measurable terms; if a network can measure delivered
throughput and drop, it seems to have the two terms it needs to solve for the
third. The literature on bio-inspired networking has largely proceeded on that
intuition. What has not been done is the unglamorous thing: put the controller
next to the simplest engineering baseline that a competent operator would deploy
anyway — a static per-flow queue — on the same seeds, and count.

**Why the null result is worth a paper.** A controller that does not beat its
baseline is not merely unhelpful; it is *expensive*, and the expense is invisible
unless it is measured. The kinematic arm here costs 136× the per-tick CPU of the
1-D scalar-EMA limiter (813.4 µs against 6.0 µs) and buys a peak-burst difference
that is indistinguishable from noise. The compiler arm saves 42 % of wire bytes and
returns three parts in a million on energy. A field that reports only the elegant
mechanism and not its price accumulates a literature of mechanisms that no
operator can afford to run. We therefore report the prices, and we convert each
verdict into the threshold at which it would reverse, so a reader who disagrees
with our stipulated constants can see exactly how far they would have to move.

**Contributions.**

1. A pre-registered, 30-seed paired evaluation of five bio-inspired control arms
   against static per-flow isolation in a 100-node DDoS scenario, with the
   expectations frozen before the arms were run (§4.3) and every verdict reported:
   five refutations, one stipulation-dependent verdict and one confirmation (§5).
2. A measured mechanism for the failure: the Fick premise is wrong in a packet
   network. A DDoS flood *raises* total delivered throughput, so the CBF-drop
   trigger that drives the extraction fraction never fires; the actuator reaches
   1.0 only at end-of-run and is therefore indistinguishable from the stateless
   confound (§5.1).
3. A break-even analysis that replaces every stipulation-dependent verdict with a
   threshold: 0.2 mJ per three-call transition for the compiler arm, 0.19 J per
   edit for the churn-cost comparison, and a ratio argument that makes the
   smoothing verdict independent of the constant altogether (§5.4).
4. A structural explanation, stated as a bound rather than a slogan: a discrete
   buffer can only hold packets, so a continuous compensation signal has no
   representation it can act on at the granularity where the loss happens (§5.5,
   §6).

**What we do not show.** Not that bio-inspired control cannot work in general; not
that the Fick analogy is useless as a design intuition; not that these numbers
transfer to real hardware — the simulator baseline prices per-flow isolation state
at zero, which *favours* the biological arms, so the real margin is smaller than
the simulated one. §6.2 states these limits as threats to validity, and §6.3 says
what would change our mind.

## 2. Background and Related Work

### 2.1 The Fick principle in physiology

Fick's principle relates oxygen consumption to blood flow and extraction:
`CMRO2 = CBF · OEF · Ca`, where CBF is cerebral blood flow, OEF the oxygen
extraction fraction and `Ca` the arterial oxygen content (A. Fick, "Über
Diffusion", *Annalen der Physik* 94, 1855). The measurement tradition that made it
operational is Kety and Schmidt's nitrous-oxide method for cerebral blood flow in
man (*Journal of Clinical Investigation* 27(4), 1948). Homeostasis as a control
objective — the organism holds an internal variable near a set point by negative
feedback — is Cannon's formulation (*The Wisdom of the Body*, Norton, 1932). The
neurobiological version is more subtle than a set point: Marder and Goaillard show
that neurons and networks maintain function under parametric variation by
*compensation* across many parameters, not by restoring one variable (Nature
Reviews Neuroscience 7, 2006, DOI
[10.1038/nrn1949](https://doi.org/10.1038/nrn1949)). That distinction matters
here: our extraction arm implements the set-point version (restore CMRO2), and our
kinematic arm implements the compensatory version (watch the geometry of a state
vector). Both are faithful to one reading of the biology, and both fail for a
reason that the biology does not contain: the "blood" in a packet network is
quantised and zero-sum.

### 2.2 Bio-inspired networking

Dressler and Akan survey the field and classify its mechanisms — swarm
intelligence, artificial immune systems, cellular signalling, homeostasis
("A survey on bio-inspired networking", *Computer Networks* 54(6), 2010). The most
successful instances are *search* mechanisms rather than *control* mechanisms:
ant-colony routing (Di Caro and Dorigo, "AntNet: distributed stigmergetic control
for communications networks", *Journal of Artificial Intelligence Research* 9,
1998) explores paths, and the slime-mould experiments of Tero et al. ("Rules for
biologically inspired adaptive network design", *Science* 327, 2010, DOI
[10.1126/science.1177894](https://doi.org/10.1126/science.1177894)) produce
near-optimal transport networks by a local rule. Both are *allocation over
alternatives* — the network chooses among paths — which is a different problem
from the one we test, where the alternatives are queue shares on a congested link
and the loss is decided packet by packet. Our negative result is therefore not a
refutation of bio-inspired networking; it is a boundary on the subset that
attempts continuous metabolic control of a discrete queue.

**Whose controllers are under test.** They are ours. We surveyed the
homeostatic-control literature for a published Fick-principle network controller
with a fair-queueing comparison and did not find one that reports the comparison;
what we found were surveys, allocation mechanisms and design proposals. Rather
than construct a straw man from someone else's prose, we built two arms that are
faithful to two explicit readings of the biology — restore the set point (the
extraction fraction), and hold the geometry of the state vector (the kinematic
trigger) — and we test those. The result is therefore a complete statement about
*these* controllers and a bounded statement about the design pattern; §6.2.5 says
exactly how bounded.

### 2.3 Fair queueing and DDoS defence

The engineering baseline in this paper is classical: fair queueing
(Demers, Keshav and Shenker, SIGCOMM 1989, DOI
[10.1145/75246.75248](https://doi.org/10.1145/75246.75248)), deficit round-robin
as its practical implementation (Shreedhar and Varghese, *IEEE/ACM Transactions on
Networking* 4(3), 1996, DOI
[10.1109/90.502236](https://doi.org/10.1109/90.502236)), and core-stateless fair
queueing as its scalable variant (Stoica, Shenker and Zhang, SIGCOMM 1998, DOI
[10.1145/285237.285258](https://doi.org/10.1145/285237.285258)). Active queue
management (Floyd and Jacobson, "Random Early Detection gateways for congestion
avoidance", *IEEE/ACM Transactions on Networking* 1(4), 1993) and the
increase/decrease control laws analysed by Chiu and Jain (*Computer Networks and
ISDN Systems* 17, 1989) complete the picture: the baseline is not naive, it is the
accumulated answer to exactly the question the biological controllers re-ask.

The cost of that baseline matters for the paper's main caveat. Per-flow fair
queueing is cheap in hardware precisely because its state is a small per-flow
record and a deficit counter (DRR), or no per-flow state at all in the core (CSFQ
with edge-labelled flows); the simulator, by contrast, charges *nothing* for it.
That bias runs in the biological arms' favour, which is why we lean on it in §6.1
rather than hiding it: if the baseline were charged its real per-flow state, the
gap between the arms and the baseline would narrow, not widen.

The DDoS literature supplies the threat model (Mirkovic and Reiher, "A taxonomy of
DDoS attack and DDoS defense mechanisms", *ACM SIGCOMM Computer Communication
Review* 34(2), 2004, DOI
[10.1145/997150.997156](https://doi.org/10.1145/997150.997156)); our contribution
is to test whether *adding* a metabolic controller to that baseline helps, and to
report that it does not.

### 2.4 Energy cost of machine-learning control

The compiler arm prices inference against transmission. The magnitudes are well
documented: Strubell, Ganesh and McCallum quantify the energy and carbon cost of
training and inference in NLP (ACL 2019, DOI
[10.18653/v1/P19-1355](https://doi.org/10.18653/v1/P19-1355)); Patterson et al.
put large-model training in the megawatt-hour range ("Carbon Emissions and Large
Neural Network Training", arXiv:2104.10350, 2021); Luccioni, Viguier and Ligozat
estimate the lifecycle footprint of a 176-billion-parameter model (*Journal of
Machine Learning Research* 24, 2023); Dodge et al. measure the carbon intensity of
inference in cloud instances (ACM FAccT 2022). Our point is narrower and does not
depend on any of those numbers being exact: at *any* inference cost in the joule
range, a controller that saves two kilobytes per transition cannot repay it, and
§5.4 states the exact threshold at which the conclusion would reverse.

### 2.5 Fluid models and the discreteness of queues

Fluid approximations are the standard tool for queueing analysis: Anick, Mitra and
Sondhi model a data-handling system with multiple sources as a fluid queue (*Bell
System Technical Journal* 61(8), 1982). A fluid model is exactly what a continuous
controller assumes — the buffer level is a real number, the control signal is
continuous, and a proportional response moves the level smoothly. Real buffers are
not fluid: they hold an integer number of packets, and the arrival process is a
point process. §5.5 is a deliberately small figure about that gap, and §6.1 argues
that it is the reason the biological arms fail rather than a detail of their
tuning.

### 2.6 Pre-registration and negative results

We follow the pre-registration mechanism described by Nosek et al. ("The
preregistration revolution", *PNAS* 115(11), 2018, DOI
[10.1073/pnas.1708274114](https://doi.org/10.1073/pnas.1708274114)): the
expectation is frozen before the run and scored afterwards. The methodological
discipline of naming a cause gate and reporting INCONCLUSIVE rather than refuted
when the setup decides the outcome was developed in the layering testbed of the
companion paper ([`paper-layering-testbed.md`](paper-layering-testbed.md), §4.4).

### 2.7 The gap

Prior work assumes bio-inspiration is inherently beneficial and evaluates it
against weak or absent baselines. We locate the physical boundary where it fails:
against a static fair-queueing baseline, on the same seeds, with the expectations
frozen, under a workload where the biological premise (throughput falls, so
extract harder) is false. Frame the gap as: *prior work assumes bio-inspiration is
inherently beneficial; we empirically locate the physical boundary where it fails.*

## 3. Problem Statement: The Discrete Packet Bound

### 3.1 The continuous model the controllers assume

Let `q(t)` be a buffer occupancy, `c` the link capacity in bytes per second, `λ(t)`
the offered load, and `s(t)` the fraction of capacity allocated to legitimate
traffic by the controller. A fluid model writes

```text
dq/dt = λ(t) − c,        q(t) ≥ 0,        drop rate = max(0, λ(t) − c)
```

and a compensation law acts on `s(t)` to keep the legitimate goodput
`g(t) = min(s(t)·c, λ_legit(t))` near a target. In this model the controller's
action is a real number applied to a real-valued state: a small change in `s`
produces a small change in `q`, and the mapping from control to outcome is
continuous and invertible. Fick's principle is a law of exactly this shape.

### 3.2 What a packet buffer actually is

A buffer of `B` bytes holds `N = ⌊B/L⌋` packets of size `L`; the occupancy is an
integer, arrivals are a point process, and the service time of a packet is `L/c`.
Three consequences, each of which the fluid model erases:

1. **Quantisation of state.** `q(t)` can only take values in `{0, L, 2L, …}`. A
   controller that asks for a 3 % reduction in occupancy is asking for 37 packets
   when `N = 1250`, and for zero packets when `N = 30`.
2. **Quantisation of time.** The buffer can only change at arrival and departure
   instants, spaced at least `L/c` apart. A control decision is applied to a state
   that has already moved by one packet since it was measured.
3. **Zero-sum loss.** When `λ > c`, the bytes that are dropped are exactly the
   bytes that exceed `B`; a controller cannot create capacity, it can only choose
   *whose* packets are dropped. "Extraction" in a queue is a re-labelling of a
   fixed loss, not an increase in delivered goodput.

**Proposition (discrete packet bound).** For a buffer of depth `N` packets and
service time `τ = L/c`, a controller that observes the buffer at intervals `Δt`
and acts on a real-valued allocation `s` can change the *identity* of the packets
served within a window of length `W` by at most `⌈W/τ⌉` packets, independently of
`s`.

*Proof sketch.* The server removes packets, not bytes: at most `⌈W/τ⌉` departures
can occur in `W`, because each departure occupies the server for `τ`. Whatever `s`
is, it can only choose *which* of the arrivals in `W` receive those departures; it
cannot add departures. Hence any benefit that requires the buffer to sit between
two integer levels — for example, holding occupancy just below a threshold while
admitting one more legitimate packet — is unreachable for *any* continuous law,
however well tuned. ∎

**What the proposition is worth, and what it is not.** As mathematics it is close
to trivial, and a reviewer should say so: "you cannot create capacity" is not a
theorem. Its content is empirical, and it has two parts. First, the *operating
point*: the controllers in §5 are built to move a continuous signal precisely in
the regime where the bound binds — a buffer that is 12 % full of 1,250 packets, so
the quantisation step is 1/150 of the controllable range. Second, the *shared
actuator*: the kinematic trigger and its baseline issue the same discrete surgical
edit, so the bound is not something the trigger can route around; the only freedom
left is *when* to fire, and §5.2 measures that freedom to be within noise. The
bound does not say bio-inspired control is impossible. It says that in a packet
buffer the controller has to act on packet identity, and that is the thing fair
queueing already does.

Figure 5 draws the smallest possible instance of the argument.

### 3.3 Threat model

A 100-node mesh with fiber, microwave and satellite links serves mixed traffic;
a 10 s DDoS shockwave starts at t = 30 s and floods one content class at 300,000
requests/s with 1,000-byte requests. The adversary is not adaptive: it does not
observe the controller and does not change strategy. This is a *weak* adversary
and it is the point — a controller that cannot beat a static baseline against a
non-adaptive flood will not beat it against an adaptive one.

The controllers have full visibility of the 4-D state `[CBF, OEF, Queue, Drop]` and
may edit queue allocations across the fabric. What they do not have is any way to
change the arrival process, the service quantum, or the buffer's integer nature.

### 3.4 Out of scope

Real ISP traffic traces; real hardware energy measurement; adaptive or low-rate
DDoS; multi-tenant isolation on physical NICs; and any controller that acts on
admission control rather than queue allocation (which would attack the zero-sum
property directly rather than trying to compensate around it).

## 4. Methodology

### 4.1 Testbed and workload

The testbed is a discrete-event (SimPy) model of a 100-node mesh in which every
link is one of three channel types with its own capacity, propagation delay,
loss and buffer: fiber (1 Gbit/s, 2 ms, no loss, 9,000-byte MTU, 0.10 s of
buffering), microwave (100 Mbit/s, 10 ms, 1 % per-transmission loss, 1,500-byte
MTU, 0.15 s) and satellite (10 Mbit/s, 500 ms, no loss, 576-byte MTU, 2.0 s). A
byte that exceeds a link's buffer is dropped, so the loss the controllers fight is
drop-tail loss, not a modelled congestion signal.

**Table 1. Workload and control parameters.**

| Parameter | Value | Note |
|---|---|---|
| Topology | 100-node mesh, 3 link types | §4.1 values per link |
| Legitimate load | 40 flows, 4.8 requests/s each, 100 kB objects, Zipf `s = 0.9` | carries the shock |
| DDoS shockwave | one content class, 300,000 requests/s, 1,000-byte requests | 2.4 Gbit/s offered |
| Shock timing | starts t = 30 s, lasts 10 s | 60 s run, 20 s recovery |
| Control tick | 0.2 s | every controller's decision period |
| Warm-up | 8 s | triggers disarmed before this |
| Delivery deadline | 2 s | later arrivals count as loss |
| Baseline window | 10–30 s | reference for "normal" |
| Shock window | 30–41 s | where every reported metric is computed |
| Seeds | 30 paired seeds per campaign | the controller campaign draws from `default_rng(2026)`; the other campaigns use seeds 0–29 (§4.6) |

**Table 2. The four baselines of the reference campaign.** Thirty paired seeds,
same scenario, drawn with seeds 0–29; legitimate goodput and p95 latency over the
shock window (mean ± 95 % CI).

| Baseline | Mechanism | Legitimate goodput | p95 latency (s) |
|---|---|---|---|
| Static roles, slow central scaling | fixed role assignment, central step every 15 s | 0.5887 ± 0.0238 | 0.3510 ± 0.0080 |
| Spatial target field, instant install | full state vector installed in one control tick | 0.5887 ± 0.0238 | 0.3510 ± 0.0080 |
| Global pressure law | proportional controller on a global pressure signal, period 0.4 s | 0.7460 ± 0.0115 | 0.3343 ± 0.0114 |
| 1-D scalar-EMA limiter | kinematic trigger on one scalar, discrete isolation edit | 0.8576 ± 0.0573 | 0.2886 ± 0.0185 |

The campaign's purpose was to choose the reference against which any further
controller should be judged. Two of the four are indistinguishable *to four
decimal places* and we report the coincidence rather than explain it away; the
informative contrast is the global pressure law against the 1-D limiter, a
+11.2-point goodput difference with a lower p95 latency, which is why the limiter
is the reference in §5 and why an always-on per-flow isolation controller is added
as the confound control: if a biological trigger cannot beat an always-on
isolator, the trigger is not the source of the benefit. (The main campaign uses a
different seed set, so its limiter number, 0.8461, differs slightly from this
0.8576; the two campaigns are never mixed within a comparison.)

*One fidelity, not three.* Unlike the companion paper, this study runs a single
fidelity (SimPy). The 30-seed paired design is the substitute for cross-fidelity
replication: it quantifies sampling variability exactly and it cannot quantify
model error at all. §6.2.1 states what that costs and why the break-even analysis
in §5.4 is the mitigation.

### 4.2 The controllers, in full

Every controller below observes the same telemetry (per-node served bytes, drops,
queued bytes, capacity) and every one of them shares the same *actuator*: a
per-class fair-queueing isolation edit that grants the affected class a byte limit
of 12 % of the buffer and a weight of 0.05, holds the edit for a mandatory 3 s
hysteresis window, and allows one edit per node per 2.2 s burst. The controllers
differ only in *what fires the edit*, which is exactly the variable under test.

**(a) Static per-flow isolation (confound control).** No trigger. Each class gets
a fixed, generous per-class queue (50 % of the buffer) for the whole run. This is
the controller an operator already has; it is the thing to beat.

**(b) 1-D scalar-EMA limiter.** A scalar pressure signal is formed each tick as
`0.70·min(1, u) + 0.20·q/(d + q + 1) + 0.10·min(1, loss)`, where `u` is utilisation,
`q` the queued bytes expressed as seconds of link capacity and `d` the base delay.
Its first and second discrete differences,
smoothed by an EMA (`τ_v = τ_a = 1.0 s`), produce a velocity and an acceleration;
an edit fires when the acceleration residual exceeds
`max(2.0, 4 · EWMA(|residual|))` or when the velocity vector turns more than 45°
away from its own EMA (with floors `||v|| > 0.08`, `||a|| > 2.0`).

**(c) Extraction-fraction (OEF) actuator.** The Fick reading. Per node, `CBF` is
the delivered rate over a trailing 1 s window; an EMA with `τ = 2.0 s` is the
baseline; a Schmitt trigger engages after 3 consecutive ticks with
`CBF < 0.8 · EMA(CBF)` and releases after 5 ticks above the band. While engaged,
the target extraction fraction is `clip(2.0 · (1 − CBF/EMA), 0, 1)` and it is
applied to the bulk class as a WFQ weight `1 + 3 · OEF` (i.e. up to 4×). A double
integrator caps the OEF *speed* at 0.5/s and its *acceleration* at 0.4/s$^2$, so the
actuator cannot step. The OEF arm keeps the surgical isolation edit; OEF only
re-weights the legitimate class.

**(d) 4-D kinematic trigger.** The compensatory reading. The state is
`S = [utilisation, queue dimension, smoothed loss rate, OEF]`, where the queue
dimension is `q_sec / (base_delay + q_sec + 1)` (so it saturates instead of
sawtoothing) and the loss dimension is an EMA of `drops / (served + drops + 1)`.
Velocity and acceleration are the discrete derivatives of a short-window EMA of
`S` (`τ_s = 0.3 s`, `τ_v = 1.0 s`). An edit fires when
`||a − EMA(a)|| > max(2.0, 4 · EWMA(||a − EMA(a)||))` or when the velocity turns
more than 45° from its EMA with both norms above their floors. The actuator is the
shared isolation edit; the OEF actuator is disabled in this arm.

**(e) Smoothed trigger with early redirection.** Same state and same
velocity/acceleration as (d), but two separate EWMAs (`α` on velocity, `β` on
acceleration, both `τ = 1.0 s`) and a three-level decision: quiet; *band*
(`a_resid > 0.8 · floor`), where the controller redirects a single affected flow
to an alternate path with probability 0.05 and spends a quarter of the edit
budget; and *trigger*, where the full isolation edit fires. The intent is to break
up the all-nodes-at-once burst by pre-empting it.

**(f) LLM stack compiler (mocked oracle).** The only arm that changes the
*encapsulation* rather than the queue. An oracle proposes a `(layer order,
authenticate-outer)` pair for the current phase; three guardrails then check it
against the frozen commutation rules: encrypt-before-compress on compressible data
is rejected (it inflates the wire), fragment-before-compress is rejected (it
raises the fragment count), and authenticating the outer source is rejected
whenever a NAT is present (it breaks authentication). On a violation the guardrail
installs the canonical `C→E→F` order and logs the intervention. The oracle here is
a deterministic mock, not a language model: this arm measures the *guardrail and
the wire cost*, not the search quality of a real model (§6.2.6).

**(g) Dual-band detector.** A low-pass/high-pass pair per node. The LPF
(`τ = 2.0 s`) gives the utilisation baseline; the HPF residual is compared with
`max(0.02, 3σ)` where `σ` is the rolling standard deviation of the residual over
6 s. A crossing fires early redirection and then the shared isolation edit. The
single-LPF comparison arm uses the same actuator with a *fixed* residual threshold
of 0.10 instead of the adaptive one.

### 4.3 Expectations frozen before the run

**Table 3. Pre-registered expectations.** Written and committed before the arms
were executed. "Beats" always means a paired comparison on the same seed, 95 %
confidence interval on the paired difference, two-sided.

| ID | Expectation | Threshold for confirmation |
|---|---|---|
| E1 | The extraction fraction beats static isolation on legitimate goodput | > 0.92 and > the static baseline |
| E2 | The 4-D trigger caps the peak state-change speed below the 1-D limiter | significant reduction, zero false-positive edits |
| E3 | The smoothed trigger with early redirection is more energy-efficient than the 4-D trigger | fewer edits and lower churn energy |
| E4 | The LLM compiler repays its inference | energy return on investment > 1 |
| E5 | Static isolation is the cheapest arm | lowest total energy of all arms |
| E6 | The dual-band detector beats the single-LPF detector | higher true-positive rate at a lower false-positive rate, and more goodput per joule |
| E7 | The compiler beats a greedy heuristic | strictly lower wire cost than the canonical order |

E4 is the only expectation that cannot be scored as a binary: its outcome depends
on two stipulated constants, and §5.4 therefore reports it as a threshold rather
than a verdict.

### 4.4 Metrics

**Table 4. Metrics and their definitions.** Every metric is computed per run and
then averaged across the 30 paired seeds.

| Metric | Definition | Role in the paper |
|---|---|---|
| Legitimate goodput (CMRO2) | delivered legitimate bytes / offered legitimate bytes, shock window | primary outcome for every arm |
| Total throughput (CBF) | all delivered bytes, attack included | the mechanism check: does a flood lower it? |
| Peak state-change speed | max \|Δstate\| per control tick, summed over nodes | the burst the trigger is supposed to cap |
| Number of edits | control-plane edits issued in the run | the churn that energy is charged for |
| False-positive edits | edits issued before `t = 29.5 s`, i.e. in steady state | trigger selectivity (not defined for the triggerless baseline, whose isolation edits are by design) |
| Transit drop rate | 1 − goodput of non-target traffic | the price paid by innocent traffic |
| Compensatory distance | Euclidean displacement of the 4-D state from its baseline | how far the controller moves the state (Marder–Goaillard) |
| Degeneracy index | occupied (utilisation, extraction) bins with mean goodput > 90 % | whether many parameter settings work (Marder–Goaillard) |
| Total energy (J) | `E_tx + E_cpu + E_churn` from the stipulated model | energy comparisons; one-time `E_setup` is reported separately |
| Energy return (EROI) | `E_tx_saved / E_llm` | the compiler's repayment test |
| Detection latency | time from shock onset to the first edit | detector comparison |
| True/false-positive rate | detected seeds / 30; false edits per run | detector comparison |

### 4.5 The energy model, stated as stipulation

Every energy number in this paper comes from a stipulated accounting, not a
measurement:

```text
E_tx    = 1e-7 J/byte         transmission; scales with bytes actually sent
E_cpu   = 1e-9 J/cycle        processing; 100 cycles/byte encrypt+compress,
                              50 cycles/tick for an EWMA / redirect update
E_churn = 5.0 J per edit      queue flush + FIB update + context switch
E_setup = 5.0 J per setup edit, charged once per run (reported separately)
E_llm   = 20.0 J per call     local model inference
Total   = E_tx + E_cpu + E_churn          (E_setup excluded, §5.4)
```

The totals in every table are `E_tx + E_cpu + E_churn`. The one-time setup term is
charged to the static arm alone — 208 setup edits × 5 J, i.e. 1,071 ± 27 J over the
30 seeds — while the dynamic arms pay no setup because their first edit is already
counted as churn. §5.4 explains why that asymmetry is the point rather than a
bookkeeping detail.

The stipulation is the paper's largest soft spot, so §5.4 converts each
energy-based verdict into the value of the constant at which it would reverse. A
verdict whose break-even is far from the stipulation is robust; one whose
break-even is close is labelled fragile. This is the same discipline the companion
paper applies to its 56-byte composite overhead, and it is the reason the paper's
claims survive a reader who rejects 5 J/edit outright.

### 4.6 The campaigns behind the results

Four separate campaigns feed this paper, and they are never mixed within the same
comparison:

- **Reference campaign** (30 paired seeds, seeds 0–29): the four baselines of
  Table 2, run to choose the reference controller.
- **Controller campaign** (30 paired seeds, the shockwave scenario): five arms,
  the goodput and peak-burst outcomes of §5.1–§5.2, the starvation sweep, and the
  per-tick CPU measurement.
- **Energy audit** (30 paired seeds, same scenario): the three-term energy
  decomposition of §5.4 and Figure 4.
- **Smoothing and compiler campaign** (30 paired seeds): the smoothed trigger,
  the compiler experiment, and the guardrail accounting behind §5.3 and Figure 3.
- **Detector campaign** (30 paired seeds, same scenario): the dual-band detector,
  the single-LPF comparison and the 4-D trigger, reported in §5.6.

The controller campaign draws its 30 seeds from `default_rng(2026)`; the other
campaigns use seeds 0–29. Seed sets are therefore *not* shared between campaigns,
and no statistic in this paper pools runs from two campaigns: a number is always
computed inside one campaign, and where two campaigns measure the same arm (the
edit counts of §5.3, the peaks of §5.2) both are reported rather than averaged.

The committed artifacts keep the campaign keys in their directory names
(`results/m3/` … `results/m7/`); this table is the decoder ring, and it is the only
place in the paper where those keys appear:

| Campaign in this paper | Committed directory |
|---|---|
| Reference baselines (Table 2) | `results/m3/` |
| Controller campaign | `results/m4/` |
| Smoothing + compiler campaign | `results/m5/` |
| Energy audit | `results/m6/` |
| Detector campaign | `results/m7/` |

### 4.7 Reproducing the results

```powershell
py run_m3_experiments.py --seeds 30          # reference baselines (Table 2)
py run_m4_experiments.py --seeds 30          # E1, E2, starvation sweep, CPU cost
py run_m5_experiments.py --seeds 30          # E3, E7, the compiler arm
py run_m6_experiments.py --seeds 30          # the energy audit and energy return
py run_m7_experiments.py --seeds 30          # E6, the detector campaign
py tools\extract_arm_timeseries.py        # per-tick goodput trace (verified reproduction)
py tools\generate_paper_figures.py --output-dir figures
```

`tools/extract_arm_timeseries.py` exists because the controller-campaign runner
computes a per-tick goodput trace in memory and uses it only for a PNG. The
extractor re-runs the frozen harness with the same arms and the same seed set and
refuses to write the trace unless all 150 recomputed aggregate rows reproduce the
committed benchmark CSV exactly; the record is the reproduction note committed
beside it. Figure 1 is therefore drawn from the same model state that produced the
committed verdicts, not from new evidence.

## 5. Results

### 5.1 Static isolation is not beaten on goodput (E1)

Table 5 gives the shock-window goodput of every arm. The extraction-fraction
controller reaches 84.65 % against the baseline's 86.48 %; the paired difference is
−1.83 pp with p = 0.527, i.e. a null result rather than a demonstrated harm. The
4-D trigger is lower at 80.83 %, and running both actuators together collapses
goodput to 48.23 %.

**Table 5. Legitimate goodput over the shock window, 30 paired seeds (mean ± 95 %
CI).** From the controller campaign's committed per-seed benchmark.

| Arm | Legitimate goodput (CMRO2) | vs static isolation |
|---|---|---|
| Static per-flow isolation | 0.8648 ± 0.0177 | — |
| 1-D scalar-EMA limiter | 0.8461 ± 0.0541 | −1.87 pp (descriptive) |
| OEF actuator (Fick) | 0.8465 ± 0.0542 | −1.83 pp (paired p = 0.527) |
| 4-D kinematic trigger | 0.8083 ± 0.0467 | −5.65 pp (descriptive) |
| OEF + 4-D trigger (combined) | 0.4823 ± 0.0262 | −38.25 pp (vs 1-D limiter: p < 0.0001) |

Figure 1 shows why the extraction verdict is a *mechanism* result and not just a
number. Across the whole 60 s run the three arms track each other within the
confidence band until the shockwave, where all three dip; the kinematic arm dips
deepest and recovers latest. Nothing in the trace suggests that a better-tuned
trigger would separate them, because the quantity the extraction trigger watches —
total delivered throughput — *rises* during the flood.

![Figure 1](../figures/paperB_fig1_goodput_timeseries.pdf){width=100%}

**Figure 1.** Legitimate goodput over time for the three principal arms (mean of
30 seeds; the bands are 95 % confidence intervals across seeds, and the trace is a
2 s trailing window sampled every 0.5 s). (a) The full 60 s run: the three arms are
indistinguishable outside the shockwave, which is the null result stated as a
picture. (b) A zoom on the shock window, where the differences the text reports are
actually visible — the kinematic arm dips to about 58 % at t ≈ 32 s while static
isolation stays above 80 %, and the extraction arm sits between them, inside the
static confidence band for most of the window. The DDoS shockwave (30–40 s) is
shaded in both panels, and the annotation in (a) gives the shock-window means and
the paired difference. Data: the committed per-tick trace, produced by
`tools/extract_arm_timeseries.py` and verified against the benchmark CSV.

**The mechanism.** The extraction controller's CBF monitor tracks *total delivered
throughput*, which a DDoS flood does not lower — the attack's bytes are served
too — so the CBF-drop trigger never fires during the attack. The actuator reaches
1.0 only when traffic stops at end-of-run. Hence the extraction arm is
indistinguishable from the plain 1-D limiter (0.8465 vs 0.8461) and stays below
static isolation (0.8648). The Fick premise — that a DDoS lowers delivered CBF —
does not hold in this testbed, so the compensation has nothing to compensate. This
is the single most important sentence in the paper: the controller is not badly
tuned, its *input* is miscalibrated by a physical fact about floods.

The starvation sweep confirms the null and rules out the "it was tuned too
gently" objection: forcing the extraction fraction to its maximum across a 16×
weight range leaves goodput and transit drop flat (Table 6).

**Table 6. Extraction fraction forced to maximum, WFQ weight swept.**

| Weight multiplier | Legitimate goodput | Transit drop rate |
|---|---|---|
| 1 | 0.8461 ± 0.0541 | 0.0994 ± 0.0329 |
| 2 | 0.8528 ± 0.0550 | 0.0955 ± 0.0335 |
| 4 | 0.8515 ± 0.0543 | 0.0978 ± 0.0329 |
| 8 | 0.8521 ± 0.0544 | 0.0977 ± 0.0329 |
| 16 | 0.8521 ± 0.0544 | 0.0977 ± 0.0329 |

**Coupled actuators are worse than either alone.** The combined arm scores 0.4823.
The extraction actuator's weight changes feed back into the 4-D state vector and
trip the kinematic trigger about 175 times during steady traffic, isolating
innocent classes and roughly halving delivery (175.1 ± 10.5 steady-state edits,
against 0 for either arm alone). A negative result about one controller becomes a
*positive* result about decomposition: these two controllers are not composable,
and the interaction is measurable, not hypothetical.

### 5.2 The 4-D trigger does not cap the peak burst (E2)

**Table 7. Peak state-change speed, controller campaign (mean ± 95 % CI).**

| Arm | Peak state-change speed | vs 1-D limiter |
|---|---|---|
| Static per-flow isolation | 1072.83 ± 27.55 | +850.79 |
| 1-D scalar-EMA limiter | 222.04 ± 31.70 | — |
| OEF actuator (Fick) | 222.04 ± 31.70 | 0.00 |
| 4-D kinematic trigger | 218.38 ± 36.80 | −3.66 (p = 0.891) |
| OEF + 4-D trigger (combined) | 384.30 ± 41.38 | +162.26 |

The headline is in Figure 2, and it is deliberately unflattering to the paper's own
hypothesis. Panel (a) shows the 4.8× drop from static isolation to the two
kinematic arms — and the 1-D limiter and the 4-D trigger are *the same edit*, so
the drop is attributable to the discrete surgical edit, not to the biological
trigger. Panel (b) is the same 30 paired seeds, per seed: the 4-D mean is nominally
lower (218.4 against 222.0, p = 0.891) but its *worst* seed reaches 402.6 against
256.2 for the limiter, because it fires on fewer seeds and overshoots when it does.
The smoothing campaign, on a different seed set, shows the same shape (311.1 against
256.2). A controller whose tail is nearly twice its baseline's has not capped the
churn; it has moved it.

![Figure 2](../figures/paperB_fig2_peak_burst.pdf){width=100%}

**Figure 2.** Peak state-change speed. (a) Controller campaign: static isolation
1,072.8, 1-D limiter 222.0, 4-D trigger 218.4 (units/s; bars are means, whiskers
95 % CIs). The 4-D − 1-D difference is −3.7 with p = 0.891: no cap. (b) The 30
per-seed peaks of the same campaign and the same seeds; the tick labels give the
mean ± 95 % CI, the dashed line is the 1-D worst case (256.2), and three 4-D seeds
exceed it, the worst reaching 402.6. The smoothing campaign repeats the pattern on
its own seeds (worst case 311.1 against 256.2) and is quoted here rather than
plotted, so that panel (b) shares its seeds with panel (a). Data: the two committed
per-seed CSVs.

**The cost side.** The 4-D trigger keeps steady-state edits at exactly zero,
satisfying that clause of E2 (the triggerless baseline is exempt: its isolation
edits are by design). It also costs 813.4 µs per control tick against 6.0 µs for
the 1-D limiter — 136× the compute for a difference that is indistinguishable from
noise. On the data available, the correct engineering statement is that the vector
trigger is a more expensive way to compute the same edit.

**Table 8. Controller CPU cost per tick** (best of repeated runs, wrapping the
controller's `on_tick` so that only the control law is timed).

| Arm | µs/tick | vs 1-D limiter |
|---|---|---|
| Static per-flow isolation | 0.3 | 0.05× |
| 1-D scalar-EMA limiter | 6.0 | 1.00× |
| OEF actuator (Fick) | 214.2 | 35.89× |
| 4-D kinematic trigger | 813.4 | 136.29× |
| OEF + 4-D trigger (combined) | 686.6 | 115.04× |

**The homeostasis metrics do not rescue the hypothesis.** The Marder–Goaillard
apparatus was applied to both arms: the degeneracy index occupies 5 of 37 occupied
(utilisation, extraction) bins above 90 % goodput (13.5 % of occupied), and the
compensatory distance is *larger* with the extraction actuator (0.0343) than
without it (0.0149). The actuator moves the 4-D state farther from baseline without
improving goodput — the opposite of the homeostasis the analogy predicts. The grid
is only partially populated along the extraction axis because the actuator barely
moves off zero, so this metric mostly reflects routing variance; we report it for
completeness and do not rest a verdict on it.

### 5.3 The smoothed trigger and the compiler (E3, E7)

**E3: smoothing does not save churn.** The smoothed arm issues 1,614 edits against
1,428 for the 4-D trigger in its own campaign (13 % more, not fewer), and its mean
peak (223.9) is statistically indistinguishable from the 1-D limiter's (230.6). The
energy audit, on its own seed set, gives the same direction with different counts:
1,546 edits and 257.7 J of churn against 1,438 edits and 239.7 J (Figure 4). The
counts differ because the two campaigns use different seeds (§4.6); the *sign and
magnitude* do not, which is why we report both instead of choosing the flattering
one. Since churn energy scales linearly with its constant, the ratio
257.7/239.7 = 1.075 holds at *any* positive cost per edit. E3 is refuted
independently of the stipulation, which makes it the most robust verdict in the
paper.

Why it fails is visible in the mechanism: the peak burst is dominated by the
synchronous surgical edit — one class promoted across roughly 15 routers in a
single tick — and smoothing the *trigger* does not smooth the *edit*. Early
redirection engaged only 6 times in 30 seeds, because the shock is a step: the
pre-trigger band is crossed for almost no ticks. Detection latency (1.785 s) stays
inside the 15 % budget of the campaign (2.018 s), so the arm meets the part of its
goal it could meet and misses the part it could not.

**E7: the compiler does not beat greedy.** The compiler arm cuts wire bytes by
42 % against the static stack (4,650 B → 2,673.9 B, a paired difference of
−1,976.1 B, p = $1.1\times10^{-28}$). Against the *greedy* heuristic it is bit-identical:
2,673.9 B for both, 30/30 seeds, because the guardrail installs the canonical
`C→E→F` order on all 10 of the mock's hallucinated proposals and the greedy
heuristic already picks that order. E7 is therefore refuted, and the arm's positive
result is entirely attributable to the guardrail rather than to the oracle. That is
a property of the mock's policy, not of language models in general (§6.2.6), and we
do not claim otherwise.

### 5.4 Break-even: replacing stipulations with thresholds (E4, E5)

The energy verdicts depend on two constants, and a hostile reader is entitled to
reject both. Table 9 restates each verdict as the threshold at which it reverses.

**Table 9. Break-even thresholds.** Computed from the two committed energy CSVs
and the constants of §4.5.

| Verdict | Break-even | Distance from the stipulation | Robustness |
|---|---|---|---|
| E3 smoothing energy | any `E_churn > 0` (ratio) | the constant cancels | **robust** |
| E4 compiler repayment | `Δwire > 600 MB` per 3 calls, or inference < 0.198 mJ | ~5 orders of magnitude | robust to ordinary changes |
| E5 static cheapest | `E_churn > 0.186 J` | 27× below the 5 J stipulation | **robust** |
| E7 compiler vs greedy | must beat the canonical order | the mock never does | property of the mock |
| E6 detector | any churn cost | worse on both axes | **robust** |

**E5: static isolation is cheapest.** Per seed, static isolation transmits 918.2 J
and the 4-D trigger 909.3 J with 47.9 edits; static wins iff the churn cost
exceeds `(918.2 − 909.3)/47.9 = 0.186 J` per edit. The stipulation is 5 J, so the
verdict holds for any plausible edit cost — it would reverse only if a surgical
edit cost less than about a fifth of a joule. Figure 4 is the same statement as a
decomposition: the dynamic arms transmit *slightly fewer* bytes (the isolation
edit reduces attack delivery) and pay 211–258 J of churn to do it.

![Figure 4](../figures/paperB_fig6_energy_audit.pdf){width=100%}

**Figure 4.** Stipulated energy over the 60 s run, decomposed into transmission,
processing and churn, for the four arms of the energy audit. The static baseline's
entire cost is transmission: it pays no runtime churn, and that is the whole source
of its advantage. The bars show the summed `E_tx + E_cpu + E_churn`; the one-time
setup term is charged to the static arm only (1,071 ± 27 J, 208 setup edits × 5 J)
and is excluded from these totals, because the dynamic arms have no setup edits to
charge. This figure is drawn from a different seed set than Table 5 (§4.6); the two
are never combined into a single statistic. Data: the committed energy-audit CSV.

**E4: the compiler does not repay its inference.** The arm cuts wire bytes by 42 %
(4,650 B → 2,673.9 B), saving $1.976\times10^{-4}$ J of transmission energy per three-call
transition, against a stipulated `3 × 20 J = 60 J` of inference. The energy return
is $3.29\times10^{-6}$. Restated as a threshold, the compiler pays off iff it saves more
than 600 MB per three-call transition *or* inference falls below 0.2 mJ total
(0.066 mJ per call) — about five orders of magnitude away from the stipulation.
Figure 3 draws the curve: the break-even is at $E_{llm} = 1.976\times10^{-4}$ J, and the
stipulated operating point sits at the flat, hopeless end of the axis.

![Figure 3](../figures/paperB_fig3_breakeven.pdf){width=100%}

**Figure 3.** Net energy ROI of the stack compiler against inference cost, for one
three-call transition. The curve is `(E_tx,saved − E_llm)/E_llm` with
$E_{tx,saved} = 1.976\times10^{-4}$ J read from the committed compiler CSV; it crosses zero
at 0.198 mJ (the break-even) and the red dot is the stipulated operating point
(3 × 20 J = 60 J, net ROI −1.0000, EROI $3.29\times10^{-6}$). The shaded region is where
inference is cheaper than the transmission it saves. The x-axis is logarithmic and
the y-axis is symmetric-log, so both the crossing and the five-decade gap are
visible in one frame.

**The mocked oracle, stated plainly.** The compiler's installed stack is the
canonical `C→E→F`, forced by the guardrail on every hallucination; its
decision time is sub-millisecond because it is a policy table, not a model. The
arm therefore measures the guardrail and the wire cost, and E4's break-even is a
bound on what *any* model with that wire saving would need to be viable — it does
not depend on the mock being realistic, which is the point of stating it as a
threshold.

### 5.5 Why continuous compensation cannot win

Figure 5 is the smallest instance of §3.2. Two panels plot the same offered load
against the same buffer: on the left as a fluid, on the right as packets. The fluid
crosses the controller's isolation limit at 1.08 ms; the discrete buffer crosses it
at 1.20 ms, one packet service time later, and the crossing is not a point the
controller can aim at — it is a staircase edge that moved by a whole packet while
the decision was being applied.

![Figure 5](../figures/paperB_fig5_discrete_boundary.pdf){width=100%}

**Figure 5.** Schematic of the discrete packet bound, not a measurement. The same
offered load is drawn as a continuous fluid (a) and as packet arrivals into a real
buffer (b), using parameters imported from the simulation configuration: microwave
link, 100 Mbps, MTU 1,500 B (0.12 ms per packet), 0.15 s of buffering (1.88 MB =
1,250 packets), and a 12 % isolation limit (150 packets). The quantisation delays
the threshold crossing by 0.116 ms — small in isolation, decisive when every
control decision and every drop decision is quantised the same way.

The figure is not offered as evidence about the measured arms; it is offered as
the reason for the pattern they share. A controller can only act on the *identity*
of the packets that fill a quantised buffer, and the fair-queueing baseline already
acts on that identity with a smaller state and a simpler rule. The biological arms
add a continuous signal to a system whose state is not continuous; the signal
cannot be represented, so the arm collapses back to the edit it shares with its
own baseline.

### 5.6 The dual-band detector (E6)

The last expectation tests a different trigger: an LPF/HPF pair whose high-pass
band is meant to isolate attack energy from background jitter. It is refuted on
both axes, and the way it fails is instructive because the two axes point the same
way (Table 10 and Figure 6).

**Table 10. Detector campaign, 30 paired seeds (mean ± 95 % CI).**

| Detector | Detection latency (s) | False positives / 30 seeds | Legit goodput | Churn (J) | Peak state-change | Edits |
|---|---|---|---|---|---|---|
| 4-D kinematic trigger | 1.514 ± 0.300 | 0 | 0.870 ± 0.037 | 238.0 ± 24.0 | 239.73 ± 23.35 | 47.6 |
| Single-LPF (fixed 0.10) | 0.220 ± 0.022 | 6 | 0.915 ± 0.032 | 355.0 ± 41.7 | 258.03 ± 13.36 | 71.0 |
| Dual-band LPF/HPF | 0.200 ± 0.000 | 115 | 0.659 ± 0.057 | 988.0 ± 85.5 | 281.21 ± 26.11 | 197.6 |

![Figure 6](../figures/paperB_fig7_detector_tradeoff.pdf){width=100%}

**Figure 6.** Detection and protection cost of the three detectors. (a) Detection
cost: latency against false alarms over the 30 seeds (error bars are 95 % CIs on
latency); the 4-D trigger is quiet but slow, the dual-band detector is fast but
raises 115 alarms for 6 for the single-LPF arm. (b) Protection cost: legitimate
goodput against churn energy; down-and-right is better, and the dual-band arm is
up-and-right. Data: the committed detector-campaign CSVs.

**E6, detection.** The dual-band detector is faster by 20 ms (0.200 against
0.220 s) and costs 115 false positives against 6 — a 19× increase for a 9 %
latency improvement. The mechanism is a property of the design, not a tuning
error: the HPF's dynamic *k·σ* threshold adapts down during quiet periods and is
crossed by isolated batch arrivals, so the high-pass band does not separate attack
energy from Poisson jitter. The single-LPF comparison achieves essentially the same
latency with a fixed 0.10 utilisation threshold and an order of magnitude fewer
false alarms.

**E6, protection.** Dual-band goodput is 0.659 against 0.915 for the single-LPF
arm, and its churn energy is 988 J against 355 J. The arm is worse on *both* axes,
so no value of the churn constant rescues it: even at zero cost per edit it loses
on goodput, and at any positive cost it loses twice. This is why the verdict
belongs in the break-even table (§5.4) as robust — it is one of the two verdicts in
this paper that does not depend on a stipulation at all.

The pattern is the same one §5.1 and §5.2 report for the metabolic arms: an
additional continuous signal (here a high-pass band) is added to a controller whose
actuator is already discrete, the signal fires on noise, and the resulting extra
edits cost delivery rather than buying protection.

## 6. Discussion and Threats to Validity

### 6.1 What the results mean

For this fabric, these controllers and these loads, continuous bio-inspired
compensation did not beat static isolation, and lost once churn energy was
counted. Of the seven frozen expectations, five are refuted outright — E1 (the
extraction fraction on goodput), E2 (the peak-burst cap), E3 (smoothing on energy),
E6 (the dual-band detector) and E7 (the compiler against greedy) — one is
stipulation-dependent but five orders of magnitude from its threshold (E4), and one
is confirmed and uninteresting (E5: static isolation is cheapest). The negative result is not a tuning
failure: the extraction trigger's input is miscalibrated by a physical fact (a
flood raises total delivered throughput), and the 4-D trigger's actuator is the
same discrete edit as its baseline, so it has nothing left to vary.

**What the paper does not show.** Not that bio-inspired control cannot work in
general. Not that the Fick analogy is useless as a design intuition. Not that these
numbers transfer to real hardware: the SimPy baseline prices the per-flow WFQ
state that real hardware must pay — per-flow queues, hashing, decrementing timers
— at zero, which *favours* the biological arms, so the real margin is smaller than
the simulated one. The result bounds this model, not the paradigm.

**What would change our mind.** A controller that acts on admission (attacking the
zero-sum property directly), or one evaluated on a workload where a flood *does*
lower delivered throughput (a link whose capacity is shared with cross traffic), or
one whose actuator has a real degree of freedom that fair queueing lacks. None of
these is what the Fick-principle arms do.

### 6.2 Threats to validity

#### 6.2.1 Reliance on SimPy queue models

The entire quantitative result comes from a discrete-event simulator. SimPy is
faithful to the *queueing* semantics we model (integer occupancy, finite
drop-tail buffer, per-flow service), but it is not a kernel and not a NIC: there is
no offload, no interrupt coalescing, no driver queue, and no hardware pacing. The
baseline is therefore stronger than reality (its state is free) and weaker than
reality (it has no burst absorption), and we cannot say which effect dominates.
The mitigation is structural: every claim is a *comparison between arms inside the
same model*, so a systematic simulator bias would have to be arm-dependent to
change a verdict, and the one arm-dependent cost we can identify — free per-flow
state — is priced in favour of the arm that lost.

A second simulator threat is discrete-event ordering: ties between simultaneous
events are broken by insertion order, and the arms issue different numbers of
edits, so they perturb the event queue differently. We do not claim the simulator
is insensitive to that; we claim the 30 paired seeds make the *sampling* noise
visible, and the verdicts are nulls (p = 0.527, p = 0.891), which is the outcome
least likely to be manufactured by event-ordering artefacts.

#### 6.2.2 The stipulated energy constants

`E_TX_PER_BYTE = 1e-7 J`, `E_CHURN_PER_EDIT = 5 J`, `E_LLM_PER_CALL = 20 J` are
modelling choices, not measurements. Section 5.4 is the mitigation, and it is a
real one: the smoothing verdict is a *ratio* and cancels the constant entirely; the
static-isolation verdict survives down to 0.186 J/edit, 27× below the stipulation;
the compiler verdict is five orders of magnitude from its threshold. The verdict
that is *not* protected is any claim about absolute energy in joules — 918.2 J for
static isolation is a number produced by a formula, and a reader should treat it as
a comparison, not as a measurement of a deployed system.

#### 6.2.3 No real-world ISP traffic traces

The workload is synthetic: Poisson-ish request arrivals, a 1,000-byte request
size, a 10 s square-wave flood. Real ISP traffic has heavy-tailed flow sizes,
diurnal structure, and floods that ramp rather than switch on. A ramping flood
would delay the extraction trigger further (its input is even less likely to show
a drop) and would give the kinematic trigger more time to fire, so the *direction*
of the two verdicts is unlikely to reverse; the magnitudes certainly would. The
honest statement is that the workload is a lower bound on the controllers'
difficulty, not a representative sample of it.

#### 6.2.4 Statistical and multiplicity threats

Five arms × several metrics produce many pairwise tests; we report the
pre-registered comparisons and label the rest as descriptive. The two headline
nulls (p = 0.527, p = 0.891) are non-rejections, not equivalence tests with a
stated margin: we cannot say from these data that the extraction arm is
*equivalent* to static isolation, only that this experiment did not separate them.
With 30 seeds the CI on a paired goodput difference is about ±5.6 pp for the
extraction arm, which is wide; a true 2 pp advantage would have been missed. That
is a real limitation of the design and it is stated rather than hidden.

#### 6.2.5 Construct validity of "bio-inspired", and whose controller was tested

We test two specific readings of the biology — a set-point law (the extraction
fraction) and a compensatory state-geometry law (the 4-D trigger) — plus one
learning-based arm (the mocked compiler). A different reading (for example, an
immune-system-style detector) is outside the paper. The arms are ours (§2.2): we
found no published Fick-principle network controller that reports a fair-queueing
comparison, so we built faithful implementations of two readings rather than
re-implementing someone else's system. The claim is therefore about *these*
controllers, and the sentence "bio-inspired control does not beat fair queueing"
would be too broad. The sentence this paper supports is the one in the abstract,
with the boundary attached: in this fabric, under this workload, against this
baseline, two explicit readings of the metabolic analogy do not separate from fair
queueing, and the mechanism that stops them is the quantisation of the buffer.

#### 6.2.6 The mocked oracle

The compiler arm is a mock: a policy table with guardrails, not a language model.
Its wire-byte saving (42 %) is the *best case* the guardrail permits, and its
inference cost is a stipulated constant. The break-even is therefore a bound on
what any model with that saving would need to be viable, and it does not depend on
the mock being realistic — which is the point of stating it as a threshold.

### 6.3 Generality

The result bounds these controllers and this workload. What travels is the
mechanism: a flood raises total delivered throughput, so a drop-triggered
metabolic controller has no error signal to act on; a discrete buffer quantises the
state a continuous controller needs; and churn costs are paid per edit regardless of
whether the edit helped. Any of the three is checkable on another testbed in a day.

## 7. Conclusion

Static per-flow isolation is not beaten on goodput under a DDoS shockwave in this
testbed: the Fick-principle extraction arm reaches 84.65 % against 86.48 %
(p = 0.527), the four-dimensional kinematic trigger shaves 3.7 units/s of peak
burst speed without significance (p = 0.891), and the two actuators together halve
goodput. The one arm that does reduce wire bytes — the mocked stack compiler, by
42 % — returns three parts in a million on energy. The negative result is the
contribution, and it is a result about the *input* of the controllers, not their
tuning: a flood raises total delivered throughput, so the CBF-drop premise that
drives extraction never fires.

We state the boundary in the strongest form the data support. A discrete packet
buffer holds an integer number of packets, so a continuous compensation law has no
representation to act on at the granularity where loss happens; the best such a
law can do is re-label whose packets are dropped, which is exactly what the static
fair-queueing baseline already does at a fraction of the compute. The measured
consequence is 136× the per-tick CPU for no measurable burst reduction. We convert
each verdict into a threshold — 0.2 mJ per three-call transition for the compiler,
0.19 J per edit for the churn comparison, a constant-free ratio for the smoothing
arm — so that a reader who rejects our stipulated constants can still see how far
they would have to move to change the answer.

The boundary is where the paper stops and where the next experiment starts:
bio-inspired control may yet win where the actuator has a real degree of freedom
(admission, path selection, or a workload where a flood genuinely lowers delivered
throughput), and the three mechanisms above are the tests that would establish it.
What we can say with the evidence in hand is narrower and firmer: in a discrete
packet network, the fair-queueing baseline is the thing to beat, and the metabolic
analogy is not sufficient to beat it.

## 8. References

```bibtex
@article{fick1855diffusion,
  author  = {Fick, Adolf},
  title   = {{\"U}ber Diffusion},
  journal = {Annalen der Physik},
  volume  = {94},
  pages   = {59--86},
  year    = {1855}
}

@article{kety1948nitrous,
  author  = {Kety, Seymour S. and Schmidt, Carl F.},
  title   = {The Nitrous Oxide Method for the Quantitative Determination of
             Cerebral Blood Flow in Man: Theory, Procedure and Normal Values},
  journal = {Journal of Clinical Investigation},
  volume  = {27},
  number  = {4},
  pages   = {476--483},
  year    = {1948}
}

@book{cannon1932wisdom,
  author    = {Cannon, Walter B.},
  title     = {The Wisdom of the Body},
  publisher = {W. W. Norton},
  year      = {1932}
}

@article{marder2006variability,
  author  = {Marder, Eve and Goaillard, Jean-Marc},
  title   = {Variability, Compensation and Homeostasis in Neuron and Network
             Function},
  journal = {Nature Reviews Neuroscience},
  volume  = {7},
  number  = {7},
  pages   = {563--574},
  year    = {2006},
  doi     = {10.1038/nrn1949}
}

@article{dressler2010survey,
  author  = {Dressler, Falko and Akan, {\"O}zg{\"u}r B.},
  title   = {A Survey on Bio-inspired Networking},
  journal = {Computer Networks},
  volume  = {54},
  number  = {6},
  pages   = {881--900},
  year    = {2010}
}

@article{dicaro1998antnet,
  author  = {Di Caro, Gianni and Dorigo, Marco},
  title   = {{AntNet}: Distributed Stigmergetic Control for Communications
             Networks},
  journal = {Journal of Artificial Intelligence Research},
  volume  = {9},
  pages   = {317--365},
  year    = {1998}
}

@article{tero2010rules,
  author  = {Tero, Atsushi and Takagi, Seiji and Saigusa, Tetsu and Ito, Kentaro
             and Bebber, Daniel P. and Fricker, Mark D. and Yumiki, Kenji and
             Kobayashi, Ryo and Nakagaki, Toshiyuki},
  title   = {Rules for Biologically Inspired Adaptive Network Design},
  journal = {Science},
  volume  = {327},
  number  = {5964},
  pages   = {439--442},
  year    = {2010},
  doi     = {10.1126/science.1177894}
}

@inproceedings{demers1989fair,
  author    = {Demers, Alan and Keshav, Srinivasan and Shenker, Scott},
  title     = {Analysis and Simulation of a Fair Queueing Algorithm},
  booktitle = {Proceedings of ACM SIGCOMM 1989},
  year      = {1989},
  doi       = {10.1145/75246.75248}
}

@article{shreedhar1996drr,
  author  = {Shreedhar, M. and Varghese, George},
  title   = {Efficient Fair Queueing Using Deficit Round Robin},
  journal = {IEEE/ACM Transactions on Networking},
  volume  = {4},
  number  = {3},
  pages   = {375--385},
  year    = {1996},
  doi     = {10.1109/90.502236}
}

@inproceedings{stoica1998csfq,
  author    = {Stoica, Ion and Shenker, Scott and Zhang, Hui},
  title     = {Core-Stateless Fair Queueing: Achieving Approximately Fair
               Bandwidth Allocations in High Speed Networks},
  booktitle = {Proceedings of ACM SIGCOMM 1998},
  year      = {1998},
  doi       = {10.1145/285237.285258}
}

@article{floyd1993red,
  author  = {Floyd, Sally and Jacobson, Van},
  title   = {Random Early Detection Gateways for Congestion Avoidance},
  journal = {IEEE/ACM Transactions on Networking},
  volume  = {1},
  number  = {4},
  pages   = {397--413},
  year    = {1993}
}

@article{chiu1989analysis,
  author  = {Chiu, Dah-Ming and Jain, Raj},
  title   = {Analysis of the Increase and Decrease Algorithms for Congestion
             Avoidance in Computer Networks},
  journal = {Computer Networks and ISDN Systems},
  volume  = {17},
  number  = {1},
  pages   = {1--14},
  year    = {1989}
}

@article{mirkovic2004taxonomy,
  author  = {Mirkovic, Jelena and Reiher, Peter},
  title   = {A Taxonomy of {DDoS} Attack and {DDoS} Defense Mechanisms},
  journal = {ACM SIGCOMM Computer Communication Review},
  volume  = {34},
  number  = {2},
  pages   = {39--53},
  year    = {2004},
  doi     = {10.1145/997150.997156}
}

@article{anick1982fluid,
  author  = {Anick, David and Mitra, Debasis and Sondhi, Man M.},
  title   = {Stochastic Theory of a Data-Handling System with Multiple Sources},
  journal = {Bell System Technical Journal},
  volume  = {61},
  number  = {8},
  pages   = {1871--1894},
  year    = {1982}
}

@inproceedings{strubell2019energy,
  author    = {Strubell, Emma and Ganesh, Ananya and McCallum, Andrew},
  title     = {Energy and Policy Considerations for Deep Learning in {NLP}},
  booktitle = {Proceedings of the 57th Annual Meeting of the Association for
               Computational Linguistics (ACL)},
  year      = {2019},
  doi       = {10.18653/v1/P19-1355}
}

@misc{patterson2021carbon,
  author = {Patterson, David and Gonzalez, Joseph and Le, Quoc and Liang, Chen
            and Munguia, Lluis-Miquel and Rothchild, Daniel and So, David and
            Texier, Maud and Dean, Jeff},
  title  = {Carbon Emissions and Large Neural Network Training},
  howpublished = {arXiv:2104.10350},
  year   = {2021}
}

@article{luccioni2023bloom,
  author  = {Luccioni, Alexandra Sasha and Viguier, Sylvain and Ligozat, Anne-Laure},
  title   = {Estimating the Carbon Footprint of {BLOOM}, a 176B-Parameter
             Language Model},
  journal = {Journal of Machine Learning Research},
  volume  = {24},
  number  = {253},
  pages   = {1--15},
  year    = {2023}
}

@inproceedings{dodge2022measuring,
  author    = {Dodge, Jesse and Prewitt, Taylor and Tachet des Combes, Remi and
               Odmark, Erika and Schwartz, Roy and Strubell, Emma and
               Luccioni, Alexandra Sasha and Smith, Noah A. and DeCario, Nicole
               and Buchanan, Will},
  title     = {Measuring the Carbon Intensity of {AI} in Cloud Instances},
  booktitle = {Proceedings of the ACM Conference on Fairness, Accountability, and
               Transparency (FAccT)},
  year      = {2022}
}

@article{nosek2018preregistration,
  author  = {Nosek, Brian A. and Ebersole, Charles R. and DeHaven, Alexander C.
             and Mellor, David T.},
  title   = {The Preregistration Revolution},
  journal = {Proceedings of the National Academy of Sciences},
  volume  = {115},
  number  = {11},
  pages   = {2600--2606},
  year    = {2018},
  doi     = {10.1073/pnas.1708274114}
}
```





