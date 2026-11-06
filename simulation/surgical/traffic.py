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

"""Traffic generation: legitimate demand, DDoS shockwave, fluctuating load."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Flow:
    fid: int
    content: int
    src: int
    region: int
    kind: str            # "legit" | "attack"
    rate: float          # requests/s nominal
    payload: int         # bytes per request
    batch: int           # requests coalesced into one simulated event
    t_on: float = 0.0
    t_off: float = 1e9

    @property
    def cls_id(self) -> int:
        return 1 + self.content * 8 + self.region

    def active(self, t: float) -> bool:
        return self.t_on <= t < self.t_off


@dataclass
class Demand:
    flows: list
    wave_amp: float = 0.0
    wave_period: float = 12.0
    steps: tuple = ()

    def multiplier(self, t: float) -> float:
        m = 1.0
        if self.wave_amp:
            m += self.wave_amp * math.sin(2.0 * math.pi * t / self.wave_period)
        for (ts, mag) in self.steps:
            if t >= ts:
                m += mag
        return max(0.02, m)

    def rate(self, flow: Flow, t: float) -> float:
        if not flow.active(t):
            return 0.0
        if flow.kind == "attack":
            return flow.rate
        return flow.rate * self.multiplier(t)


def build_flows(cfg, topo, rng):
    """Legitimate flows plus, where applicable, the attack.

    Legit sources are drawn from rows 2..9; the botnet occupies rows 0..1.
    That separation is an explicit, disclosed assumption: the surgical
    controller is granted clean flow attribution.  Real DDoS attribution is a
    research problem in its own right, and spoofed sources would defeat this
    controller exactly as they defeat FlowSpec.  The attack still shares the
    *bottleneck links* with legitimate traffic, which is what the experiment
    actually tests.  See results.md, "Threats to validity".
    """
    flows = []
    fid = 0
    pop = topo.content_pop
    if cfg.src_pool:
        legit_srcs = list(cfg.src_pool)
    else:
        legit_srcs = [x for x in range(topo.n_nodes) if (x // 10) >= 2]
    if cfg.attack_src_pool:
        bot_nodes = list(cfg.attack_src_pool)
    else:
        # Compromised CPEs inside the aggregation ring, adjacent to the origin
        # uplink over fiber.  This is the adversarial case: the flood reaches
        # the shared bottleneck at line rate instead of being throttled by the
        # 100 Mbps access hops first, so the controller cannot win by geography.
        bot_nodes = [40, 41, 44, 45, 50, 51, 54, 55]

    for _ in range(cfg.n_flows):
        content = int(rng.choice(topo.n_content, p=pop))
        src = legit_srcs[int(rng.integers(len(legit_srcs)))]
        region = min(7, (src // 10) // 2 + 1)
        flows.append(Flow(fid, content, src, region, "legit", cfg.legit_rate,
                          cfg.payload_b, cfg.batch_legit))
        fid += 1

    target = 0
    if cfg.attack_rate > 0 and cfg.attack_start < cfg.duration:
        target = 0 if cfg.attack_target == "auto" else int(cfg.attack_target)
        n_att = 8
        for k in range(n_att):
            src = bot_nodes[(k * 3) % len(bot_nodes)]
            flows.append(Flow(fid, target, src, 0, "attack",
                              cfg.attack_rate / n_att, cfg.attack_payload_b,
                              cfg.batch_attack, cfg.attack_start,
                              cfg.attack_start + cfg.attack_dur))
            fid += 1
    return flows, target
