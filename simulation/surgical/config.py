# 7g-backhaul-simulation
# Copyright (C) 2026 MILAN NIKOLIC
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

"""Configuration for the Surgical, Rate-Controlled 7G Backhaul Testbed.

Units: seconds, bits/s, bytes.  All rates in the simulator are *requests* per
second unless suffixed with _bps.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

# --------------------------------------------------------------------------
# Channel / link specifications  (the ns-3 attribute mapping is documented in
# topology.py -- these mirror ns-3 PointToPoint / Csma / Satellite channels)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkSpec:
    name: str
    capacity_bps: float      # ns-3 DataRate
    prop_s: float            # ns-3 Delay
    loss: float              # ns-3 packet error rate (per transmission)
    mtu: int                 # ns-3 MTU
    buffer_s: float          # drop-tail depth expressed in seconds of line rate
    jitter_s: float = 0.0

    @property
    def capacity_Bps(self) -> float:
        return self.capacity_bps / 8.0

    @property
    def buffer_bytes(self) -> float:
        return self.capacity_Bps * self.buffer_s


FIBER = LinkSpec("fiber",     1e9,   0.002, 0.000, 9000, 0.100)
MICRO = LinkSpec("microwave", 100e6, 0.010, 0.010, 1500, 0.150)
SAT   = LinkSpec("satellite", 10e6,  0.500, 0.000, 576,  2.000)

LINK_SPECS = {s.name: s for s in (FIBER, MICRO, SAT)}
# Wired links are lossless-ish; microwave has 1% PER by mandate of the spec.
LINK_SPECS["microwave"] = replace(MICRO, loss=0.01)


# --------------------------------------------------------------------------
# Controllers under test
# --------------------------------------------------------------------------
K8S              = "k8s"                # Baseline A: static roles, slow central scaling
PRESSURE         = "pressure"           # Baseline B: naive global pressure controller
SURGICAL         = "surgical"           # thesis: kinematic trigger + local edit + rate cap
SURGICAL_UNLIM   = "surgical_unlimited" # ablation: same, no rate limit / hysteresis
SURGICAL_AB      = "surgical_ab"        # ablation: alpha-beta filter trigger instead of EMA
SURGICAL_GLOBAL  = "surgical_global"    # ablation: kinematic trigger, but global edit
STATIC_ISO       = "static_isolation"   # CRITICAL control: per-flow isolation, always on,
                                        # zero kinematic trigger.  If the trigger does not
                                        # beat this, the paradigm adds nothing.
PRESSURE_TUNED   = "pressure_tuned"     # Baseline B given its best shot
VDR              = "vdr"                # spatial target field, installed instantly
VDR_SURGICAL     = "vdr_surgical"       # the SAME target field, rate-controlled
SAVANT           = "savant"             # compensatory hyper-specialisation (H4)
OEF              = "oef_surgical"       # M4: OEF-compensated surgical control
MKB              = "mkb"                # M4: multidimensional kinematic baselining
MKB_NO_OEF       = "mkb_no_oef"         # M4: MKB vector trigger, OEF actuator disabled

MAIN_CONTROLLERS = [K8S, PRESSURE, SURGICAL]
ALL_CONTROLLERS = [K8S, PRESSURE, PRESSURE_TUNED, SURGICAL, SURGICAL_UNLIM,
                   SURGICAL_AB, SURGICAL_GLOBAL, STATIC_ISO, VDR, VDR_SURGICAL,
                   SAVANT]
ABLATIONS = [SURGICAL_UNLIM, SURGICAL_AB, SURGICAL_GLOBAL, STATIC_ISO]

LABELS = {
    K8S: "Baseline A (Kubernetes-style)",
    PRESSURE: "Baseline B (global pressure)",
    SURGICAL: "Surgical (kinematic + rate-capped)",
    SURGICAL_UNLIM: "Ablation: surgical, no rate cap",
    SURGICAL_AB: "Ablation: alpha-beta filter trigger",
    SURGICAL_GLOBAL: "Ablation: kinematic trigger, global edit",
    STATIC_ISO: "Control: static per-flow isolation",
    PRESSURE_TUNED: "Baseline B (tuned best shot)",
    VDR: "Spatial target (VDR-like), instant install",
    VDR_SURGICAL: "Spatial target + rate governor",
    SAVANT: "Savant (compensatory hyper-specialisation)",
    OEF: "OEF-compensated surgical control",
    MKB: "Multidimensional kinematic baselining",
    MKB_NO_OEF: "MKB vector trigger (OEF actuator disabled)",
}


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------
@dataclass
class SimConfig:
    name: str = "base"
    duration: float = 60.0
    seed: int = 0
    controller: str = SURGICAL

    # control / logging cadence
    tick: float = 0.2          # control-plane period
    log_dt: float = 0.25       # metric sample period
    kin_tau_v: float = 1.0     # EMA time constant for velocity (s)
    kin_tau_a: float = 1.0     # EMA time constant for acceleration (s)
    kin_window: float = 0.5    # finite-difference window for dv/dt (s)

    # traffic
    n_flows: int = 40
    legit_rate: float = 4.8    # requests/s per flow
    payload_b: int = 100_000   # 100 kB objects (video segment / model shard)
    batch_legit: int = 4       # requests coalesced per simulated event
    zipf_s: float = 0.9
    n_content: int = 8
    src_pool: tuple = ()       # () -> rows 2..9 ; else explicit source nodes
    attack_src_pool: tuple = ()  # () -> rows 0..1

    # DDoS shockwave (exp1)
    attack_start: float = 30.0
    attack_dur: float = 10.0
    attack_rate: float = 300_000.0   # requests/s (2.4 Gbps of 1 kB requests)
    attack_payload_b: int = 1000
    batch_attack: int = 1000
    attack_target: str = "auto"      # "auto" -> hottest content

    # exp2 fluctuating load
    load_wave_amp: float = 0.45
    load_wave_period: float = 12.0
    load_step_times: tuple = ()      # extra step increases on top of the wave

    # exp3 heterogeneous boundary
    force_satellite: bool = False

    # exp4 savant sweep
    arm: str = ""              # result label when an arm carries a parameter
    snapshot_times: tuple = () # control times at which per-node byte counters
                               # are frozen, for the spillover measurement

    # deadline for "useful" delivery (s)
    deadline: float = 2.0

    # ---- M4: OEF compensation (Fick principle) ----
    oef_gain: float = 2.0             # OEF target = clip(gain * CBF deficit, 0, 1)
    oef_max: float = 4.0              # max WFQ weight multiplier for the legit class
    oef_speed_max: float = 0.5        # max OEF change speed (1/s)
    oef_accel_max: float = 0.4        # max OEF change acceleration (1/s^2)
    oef_cbf_tau: float = 2.0          # EMA time constant for the CBF baseline
    oef_trigger: float = 0.8          # act when CBF < trigger * EMA(CBF)
    oef_force_max: bool = False       # starvation-boundary experiment: pin OEF=1

    # ---- M4: multidimensional kinematic baselining (MKB) ----
    mkb_k: float = 4.0                # vector residual multiplier
    mkb_angle_deg: float = 45.0       # trajectory-deviation threshold (degrees)
    mkb_tau_v: float = 1.0            # EMA time constant for the velocity vector
    mkb_floor_a: float = 2.0          # absolute floor on ||a|| residual (1/s^2)
    mkb_floor_v: float = 0.08         # absolute floor on ||v|| for the angle test

    # ---- surgical controller ----
    spike_k: float = 4.0             # trigger: residual > k * EMA(|residual|)
    spike_floor_a: float = 2.0       # 1/s^2 floor on pressure-acceleration residual
    spike_floor_v: float = 0.08      # 1/s floor on pressure-velocity residual
    edit_hold: float = 3.0           # mandatory hysteresis duration (s)
    edit_speed_max: float = 0.35     # max normalised state units / s
    edit_accel_max: float = 0.60     # max normalised state units / s^2
    warmup: float = 8.0               # arm the trigger only after the baseline settles
    edit_burst: float = 2.2          # per-node burst allowance for one edit
    savant_alpha: float = 0.95       # H4: violence of the asymmetric alpha shift
    iso_weight: float = 0.05         # weight granted to an isolated flow class
    iso_limit_frac: float = 0.12     # per-class byte limit as fraction of buffer
    static_iso_limit: float = 0.50   # generous per-class limit for the control arm

    # ---- baseline B ----
    pressure_kp: float = 0.9
    pressure_period: float = 0.4
    pressure_target: float = 0.55
    pressure_alpha_gain: float = 1.0

    # ---- baseline A ----
    k8s_period: float = 15.0
    k8s_max_step: float = 0.25
    k8s_target_util: float = 0.70

    # ---- topology ----
    grid: int = 10

    def child(self, **kw) -> "SimConfig":
        return replace(self, **kw)


# Metric windows computed by the analysis layer.
STEADY_WINDOW = (10.0, 30.0)   # baseline reference window
SHOCK_WINDOW = (30.0, 41.0)    # DDoS shock window


def scenario_exp1(seed: int, controller: str) -> SimConfig:
    return SimConfig(name="exp1_ddos", seed=seed, controller=controller,
                     duration=60.0)


def scenario_exp2(seed: int, controller: str) -> SimConfig:
    return SimConfig(name="exp2_churn", seed=seed, controller=controller,
                     duration=60.0, load_step_times=((24.0, 0.35), (38.0, 0.45), (50.0, 0.30)))


def scenario_exp3(seed: int, controller: str) -> SimConfig:
    """Fiber -> satellite boundary: node 5 is a remote site whose only backhaul
    is the 10 Mbps / MTU 576 satellite hop to node 55."""
    return SimConfig(name="exp3_boundary", seed=seed, controller=controller,
                     duration=60.0, force_satellite=True,
                     attack_start=26.0, attack_dur=14.0,
                     src_pool=(5,), attack_src_pool=(5,),
                     n_flows=4, legit_rate=2.0, attack_rate=8000.0)


# --------------------------------------------------------------------------
# Experiment 4 - compensatory hyper-specialisation ("savant") gain sweep
#
# The claim is asymmetric, extreme compensation: shed general transit (raise
# alpha toward 1) at the injured node and give the affected circuit everything
# that remains.  A single gain cannot test a *threshold*, so the gain is swept
# and the crossover reported.
# --------------------------------------------------------------------------
SAVANT_GAINS = {
    "savant_a50": 0.50,
    "savant_a70": 0.70,
    "savant_a85": 0.85,
    "savant_a95": 0.95,
    "savant_a99": 0.99,
}


def parse_arm(arm: str) -> tuple[str, dict]:
    """Map an arm label onto (controller name, parameter overrides)."""
    if arm in SAVANT_GAINS:
        return SAVANT, {"savant_alpha": SAVANT_GAINS[arm]}
    return arm, {}


EXP4_ARMS = [K8S, PRESSURE, SURGICAL, VDR] + list(SAVANT_GAINS)

for _arm, _gain in SAVANT_GAINS.items():
    LABELS[_arm] = f"Savant alpha->{_gain:.2f}"


def scenario_exp4(seed: int, arm: str) -> SimConfig:
    """Localised extreme shockwave, savant gain swept."""
    controller, kwargs = parse_arm(arm)
    return SimConfig(name="exp4_savant", seed=seed, controller=controller,
                     arm=arm, snapshot_times=(20.0, 30.0, 41.0), **kwargs)
