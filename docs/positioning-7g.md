# Where the "7G" label stands, and where this project sits among post-6G research

This note exists because of a specific review criticism: the project's name and
framing invite the reader to treat it as a 7G architecture proposal, while the
dominant research directions associated with post-6G work are largely absent
from it. That criticism is accepted. This document records the correction:
what the label means here, which research directions the project does and does
not address, and what claims are therefore unsupported.

## 1. What the label means in this repository

"7G" is a **project codename**, chosen when the code base was started. It is
not a standardized generation, not a claim to implement IMT-2030, and not a
prediction about what a future generation will contain.

The repository name is kept for continuity (links, citations, package name).
Every user-facing document now states the codename status and points here.

The defensible description of the work is:

> An early-stage research prototype exploring **multi-medium backhaul
> continuity, predictive multipath scheduling and self-scaling content
> distribution** as candidate components of a post-6G network architecture.

## 2. The directions that dominate post-6G research

IMT-2030 framing (ITU-R, 2023) and the 6G literature that surrounds it
concentrate on a set of directions that are, at heart, *physical-layer and
air-interface* programmes:

1. **THz and sub-THz communication** — spectrum above 100 GHz, with the
   associated channel, beam, blockage, and device-electronics problems.
2. **Light-wave backhaul** — free-space optical and fibre-based backhaul,
   including optical satellite cross-links and optical switching, with link
   budgets dominated by pointing, weather and optical component limits.
3. **AI-native air interface and AI-native RAN** — learned channel estimation,
   beam management, scheduling and control, with the associated data
   collection, model-lifecycle, verification and over-the-air monitoring
   problems.
4. **Integrated sensing and communication (ISAC)**, **non-terrestrial
   networks**, **deterministic and time-sensitive networking**, and
   **native security/privacy** as cross-cutting requirements.

These are not the same questions as "how should a session survive a medium
change and how should caches scale with demand". The mismatch is real, and
the project should not be read as covering the four directions above.

## 3. Alignment and divergence, item by item

| Direction | Present in this project? | Honest description |
| --- | --- | --- |
| THz communication | No | Links have stipulated rates/latency/loss. There is no THz channel, beam, blockage, or device model. A "thz"-labelled link in the scenario data is a label on a rate/latency tuple. |
| Light-wave backhaul | No | No optical link budget, pointing, weather attenuation or optical switching model. Fibre links are rate/latency tuples. |
| AI-native air interface | No | No air-interface learning. The learned components here are a telemetry forecaster, a tabular Q-learning router and a cache/anomaly score — control-plane toys, not AI-RAN. |
| Integrated sensing | No | Not modelled in any form. |
| Non-terrestrial integration | Partially, as scheduling | Satellite and drone relays exist as paths with contact windows; there is no orbit, link-budget or spacecraft model. |
| Multi-medium session continuity | Yes | This is the project's actual subject: stable session identity across changing media, variable MTU, reassembly and handover hysteresis. |
| Multipath scheduling and congestion control | Yes, at model level | Capacity/latency/loss-based scheduling, per-path AIMD, and (added after review) LIA and OLIA coupled congestion control, all in a simulator. |
| Predictive (forecast-driven) control | Yes, with a negative result | The controlled benchmark finds no goodput advantage from pressure prediction; the benefit measured comes from cache prediction (see README and the paper). |
| Edge/CDN self-scaling | Yes, at model level | Demand-driven cache placement, replica targets and cloud placement ranking, all simulated. |
| Quantum resources | No, and explicitly not | A key-buffer abstraction only; no QKD, no quantum channel, no security proof. |

## 4. Claims that are therefore unsupported

- That the project implements, represents, or predicts 7G.
- That its architecture is aligned with the dominant post-6G research
  programmes, or that it covers their central problems.
- That its modelled numbers say anything about THz, optical, or AI-native air
  interface performance.
- That a simulated goodput or cost difference demonstrates deployed-system
  superiority.

## 5. What would move the work toward the dominant directions

In descending order of effort-to-relevance:

1. **Replace one point-to-point link with a real wireless model.** ns-3's
   Wi-Fi or a mmWave module, or Sionna for a channel/PHY question, would test
   whether the scheduling and continuity logic survives a medium with fading,
   contention and rate adaptation rather than a rate/latency/loss tuple.
2. **Add an optical or free-space-optical link budget** for the backhaul path,
   so that availability is derived from physics (weather, pointing) rather than
   a stipulated outage schedule.
3. **Model AI-native control honestly.** Any learned controller should be
   trained on traces, evaluated against persistence and classical baselines,
   and reported with data-collection and model-lifecycle costs — the existing
   finite-difference forecaster is a placeholder, not a contribution.
4. **Keep the scope statement attached to every result.** The paper's
   limitations section and this note are the boundary conditions for reading
   any number produced by the simulator.

## 6. Status of this correction

- README, the vision paper and the package metadata describe "7G" as a
  codename and point to this note.
- The abstract and introduction of the vision paper state the divergence from
  THz, light-wave and AI-native research explicitly.
- Nothing in the repository now claims coverage of those directions.
