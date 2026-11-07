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

"""Run one scenario and reduce it to the metrics the hypotheses need."""
from __future__ import annotations

import numpy as np

from .config import SHOCK_WINDOW, STEADY_WINDOW
from .network import SimRun

WINDOWS = {
    "exp1_ddos": (STEADY_WINDOW, SHOCK_WINDOW),
    "exp2_churn": ((10.0, 23.0), (50.0, 60.0)),
    "exp3_boundary": ((8.0, 25.0), (26.0, 40.0)),
    "exp4_savant": ((10.0, 30.0), (30.0, 41.0)),
}


def offered_legit(sim, t0, t1, step=0.05):
    """Offered legitimate requests in [t0, t1), from the demand model."""
    tot = 0.0
    t = t0
    while t < t1:
        m = sim.demand.multiplier(t)
        for f in sim.flows:
            if f.kind != "legit" or not f.active(t):
                continue
            tot += f.rate * m * step
        t += step
    return tot


def _p95(x):
    if len(x) == 0:
        return float("nan")
    return float(np.percentile(x, 95))


def _cbf_mean(res, window):
    """Mean total delivered throughput (CBF) over a window, from oef_series."""
    series = res.get("oef_series")
    if series is None or len(series) == 0:
        return 0.0
    mask = (series[:, 0] >= window[0]) & (series[:, 0] < window[1])
    if not mask.any():
        return 0.0
    return float(np.mean(series[mask, 2]))


def window_stats(sim, res, t0, t1, deadline):
    t = res["done_t"]
    kind = res["done_kind"]
    lat = res["done_lat"]
    cnt = res["done_cnt"]
    m = (kind == 0) & (t >= t0) & (t < t1)
    lat_w = lat[m]
    cnt_w = cnt[m]
    delivered = float(cnt_w.sum())
    # offered == what the generator actually dispatched, so goodput cannot
    # exceed 1 through a mismatch between the demand model and the RNG.
    mo = (res["disp_t"] >= t0) & (res["disp_t"] < t1)
    offered = float(res["disp_cnt"][mo].sum())
    # Border effects: a batch dispatched just before the window completes
    # inside it, so offered and delivered are the same units but not the same
    # cohorts.  Clip at 1.0 rather than report a physically impossible ratio.
    goodput = min(1.0, delivered / offered) if offered > 0 else 0.0
    p95 = _p95(lat_w)
    # loss-aware p95: a dropped request is censored at the deadline.  A
    # controller that simply drops everything must not look good here.
    lost = max(0.0, offered - delivered)
    if offered > 0 and len(lat_w):
        eff = np.concatenate([np.minimum(lat_w, deadline),
                              np.full(int(min(lost, 400_000)), deadline)])
        p95_eff = _p95(eff)
    else:
        p95_eff = deadline
    return {"p95": p95, "p95_eff": p95_eff, "goodput": goodput,
            "delivered": delivered, "offered": offered,
            "loss": 1.0 - goodput, "n": int(len(lat_w)),
            "mean_lat": float(np.mean(lat_w)) if len(lat_w) else float("nan")}


def rolling_series(res, t0, t1, win=2.0, step=0.5):
    t = res["done_t"]
    kind = res["done_kind"]
    lat = res["done_lat"]
    m = kind == 0
    t, lat = t[m], lat[m]
    order = np.argsort(t)
    t, lat = t[order], lat[order]
    ts, p95s, means, cnts = [], [], [], []
    tt = t0
    while tt < t1:
        a = np.searchsorted(t, tt - win, "left")
        b = np.searchsorted(t, tt, "left")
        seg = lat[a:b]
        ts.append(tt)
        p95s.append(_p95(seg) if len(seg) else np.nan)
        means.append(float(seg.mean()) if len(seg) else np.nan)
        cnts.append(len(seg))
        tt += step
    return np.array(ts), np.array(p95s), np.array(means), np.array(cnts)


def rolling_goodput(res, t0, t1, win=2.0, step=0.5, content=None, target=0):
    """Rolling legitimate goodput (delivered / offered) over [t0, t1).

    ``content`` selects which legitimate requests count: ``None`` counts every
    legitimate request, ``"transit"`` counts every legitimate request whose
    content differs from ``target`` (the attack target).  This is the raw,
    unsmoothed delivered/offered ratio -- the CMRO2 proxy for H5.
    """
    t = res["done_t"]
    kind = res["done_kind"]
    cnt = res["done_cnt"]
    c_arr = res["done_content"]
    m = kind == 0
    if content == "transit":
        m = m & (c_arr != target)
    elif content is not None:
        m = m & (c_arr == content)
    dt_, dc = t[m], cnt[m]
    order = np.argsort(dt_)
    dt_, dc = dt_[order], dc[order]

    ot = res["disp_t"]
    oc = res["disp_cnt"]
    o_arr = res["disp_content"]
    om = np.ones(len(ot), dtype=bool)
    if content == "transit":
        om = o_arr != target
    elif content is not None:
        om = o_arr == content
    ot_, oc_ = ot[om], oc[om]
    order2 = np.argsort(ot_)
    ot_, oc_ = ot_[order2], oc_[order2]

    ts, gps = [], []
    tt = t0
    while tt < t1:
        a = np.searchsorted(dt_, tt - win, "left")
        b = np.searchsorted(dt_, tt, "left")
        delivered = float(dc[a:b].sum())
        a2 = np.searchsorted(ot_, tt - win, "left")
        b2 = np.searchsorted(ot_, tt, "left")
        offered = float(oc_[a2:b2].sum())
        ts.append(tt)
        gps.append(min(1.0, delivered / offered) if offered > 0 else float("nan"))
        tt += step
    return np.array(ts), np.array(gps)


def run_and_score(cfg):
    sim = SimRun(cfg)
    res = sim.run()
    name = cfg.name
    base_w, shock_w = WINDOWS.get(name, (STEADY_WINDOW, SHOCK_WINDOW))
    deadline = cfg.deadline
    base = window_stats(sim, res, base_w[0], base_w[1], deadline)
    shock = window_stats(sim, res, shock_w[0], shock_w[1], deadline)

    s = res["series"]
    churn_rate = None
    if len(res["churn_mag"]):
        cm = res["churn_mag"]
        dt = 0.1
        churn_rate = cm / dt          # normalised state units per second

    gov = res["governor"]
    ts, p95s, means, cnts = rolling_series(res, base_w[0], min(cfg.duration, 60.0))

    reasm = s[:, 3] if len(s) else np.zeros(1)
    reasm_cap = 262_144.0
    deadlock_frac = float(np.mean(reasm > 0.8 * reasm_cap)) if len(reasm) else 0.0

    # H4: delivery of the affected name vs everything else, in the shock window
    tgt = res.get("attack_target", 0)
    g_t, g_goodput = rolling_goodput(res, 2.0, min(cfg.duration, 60.0))
    _, g_transit = rolling_goodput(res, 2.0, min(cfg.duration, 60.0),
                                   content="transit", target=tgt)

    # Marder & Goaillard metric: compensatory distance = ||S_shock - S_steady||
    # over the mean 4-D state vector [CBF, Queue, Drop, OEF] (Euclidean norm).
    ss = res.get("state_series", np.zeros((0, 5)))
    compensatory_distance = float("nan")
    if len(ss):
        steady_m = (ss[:, 0] >= base_w[0]) & (ss[:, 0] < base_w[1])
        shock_m = (ss[:, 0] >= shock_w[0]) & (ss[:, 0] < shock_w[1])
        base_state = ss[steady_m, 1:].mean(axis=0) if steady_m.any() else np.zeros(4)
        shock_state = ss[shock_m, 1:].mean(axis=0) if shock_m.any() else np.zeros(4)
        compensatory_distance = float(np.linalg.norm(shock_state - base_state))

    # Grid-bin degeneracy inputs: mean path utilization (all arms) and mean OEF
    # (OEF/MKB arms only; 0 otherwise), plus the raw per-tick 4-D state.
    series_arr = res.get("series", np.zeros((0, 7)))
    mean_util = float(np.mean(series_arr[:, 1])) if len(series_arr) else 0.0
    mean_oef = float(np.mean(ss[:, 4])) if len(ss) else 0.0

    mw = (res["done_t"] >= shock_w[0]) & (res["done_t"] < shock_w[1]) & (res["done_kind"] == 0)
    ow = (res["disp_t"] >= shock_w[0]) & (res["disp_t"] < shock_w[1])
    dc = res["done_content"]
    ddc = res["disp_content"]
    aff_del = float(res["done_cnt"][mw & (dc == tgt)].sum())
    aff_off = float(res["disp_cnt"][ow & (ddc == tgt)].sum())
    oth_del = float(res["done_cnt"][mw & (dc != tgt)].sum())
    oth_off = float(res["disp_cnt"][ow & (ddc != tgt)].sum())
    gp_aff = min(1.0, aff_del / aff_off) if aff_off > 0 else float("nan")
    gp_oth = min(1.0, oth_del / oth_off) if oth_off > 0 else float("nan")

    # Spillover: when a node sheds transit, its neighbours must absorb the
    # load.  Compare neighbour throughput per second during the shock with the
    # steady window, over the neighbours of every alpha-edited node.
    spill, spill_nodes = float("nan"), 0
    cascading_failure_rate = float("nan")
    snaps = res.get("snapshots", {})
    edited = res.get("alpha_nodes", np.zeros(0, dtype=np.int32))
    shock_span = shock_w[1] - shock_w[0]
    base_span = shock_w[0] - 20.0
    if (20.0 in snaps and 30.0 in snaps and shock_w[1] in snaps
            and len(edited) and base_span > 0):
        neighbours = set()
        for n in edited:
            neighbours.update(sim.topo.adj[int(n)])
        neighbours -= set(int(n) for n in edited)
        if neighbours:
            base_rate = sum(snaps[30.0][m] - snaps[20.0][m]
                            for m in neighbours) / base_span
            shock_rate = sum(snaps[shock_w[1]][m] - snaps[30.0][m]
                             for m in neighbours) / shock_span
            if base_rate > 0:
                spill = shock_rate / base_rate - 1.0
            spill_nodes = len(neighbours)
            # cascading-failure rate: the fraction of neighbours whose own
            # throughput fell below their steady-window rate.
            failing = 0
            for m in neighbours:
                base_thru = snaps[30.0][m] - snaps[20.0][m]
                shock_thru = snaps[shock_w[1]][m] - snaps[30.0][m]
                if base_thru > 0 and shock_thru < base_thru:
                    failing += 1
            cascading_failure_rate = failing / len(neighbours)

    out = {
        "name": name,
        "controller": cfg.arm or cfg.controller,
        "seed": cfg.seed,
        "gp_affected": gp_aff,
        "gp_other": gp_oth,
        "spillover": spill,
        "spillover_nodes": spill_nodes,
        "cascading_failure_rate": cascading_failure_rate,
        "savant_other_drops": res.get("savant_other_drops", 0),
        "savant_affected_drops": res.get("savant_affected_drops", 0),
        "alpha_edited_nodes": int(len(edited)),
        "base": base,
        "shock": shock,
        "ratio_p95": shock["p95"] / base["p95"] if base["p95"] and base["p95"] > 0 else np.nan,
        "ratio_p95_eff": (shock["p95_eff"] / base["p95_eff"]
                          if base["p95_eff"] and base["p95_eff"] > 0 else np.nan),
        "goodput_shock": shock["goodput"],
        "goodput_loss": shock["loss"],
        "goodput_base": base["goodput"],
        "edits": res["edits"],
        "ns_classes_peak": res["ns_classes_peak"],
        # OEF / MKB (homeostasis) metrics
        "oef_peak": res.get("oef_peak", 0.0),
        "oef_limit_hit": res.get("oef_limit_hit", False),
        "oef_speed_max": (float(np.max(res["oef_log"][:, 3]))
                          if len(res["oef_log"]) else 0.0),
        "oef_accel_max": (float(np.max(res["oef_log"][:, 4]))
                          if len(res["oef_log"]) else 0.0),
        "oef_series": res.get("oef_series", np.zeros((0, 3))),
        "mkb_spike_count": int(len(res.get("mkb_spikes", []))),
        "rer_event_count": int(len(res.get("rer_events", []))),
        "mkb_first_trigger": (float(np.min(res["mkb_spikes"][:, 0]))
                              if len(res.get("mkb_spikes", [])) else float("nan")),
        "cbf_base": _cbf_mean(res, base_w),
        "cbf_shock": _cbf_mean(res, shock_w),
        "compensatory_distance": compensatory_distance,
        "state_series": ss,
        "mean_util": mean_util,
        "mean_oef": mean_oef,
        "edit_times": res.get("edit_times", np.zeros(0)),
        "total_served_bytes": res.get("total_served_bytes", 0.0),
        "mkb_spikes": res.get("mkb_spikes", np.zeros((0, 2))),
        "dual_band_first_trigger": (float(np.min(res["detections"][:, 0]))
                                    if len(res.get("detections", [])) else float("nan")),
        "dual_band_spike_count": int(len(res.get("dual_band_spikes", []))),
        "detection_count": int(len(res.get("detections", []))),
        "detections": res.get("detections", np.zeros((0, 2))),
        "filter_series": res.get("filter_series", np.zeros((0, 4))),
        "reasm_peak": float(np.max(reasm)) if len(reasm) else 0.0,
        "reasm_deadlock_frac": deadlock_frac,
        "reasm_drops": int((res["drop_reason"] == "reorder_overflow").sum()),
        "reorder_drops": int((res["drop_reason"] == "reorder_overflow").sum()),
        "loop_drops": int((res["drop_reason"] == "routing_loop").sum()),
        "buffer_drops": int((res["drop_reason"] == "buffer_full").sum()),
        "loss_drops": int((res["drop_reason"] == "link_loss").sum()),
        "churn_max": float(np.max(churn_rate)) if churn_rate is not None else 0.0,
        "churn_mean": float(np.mean(churn_rate)) if churn_rate is not None else 0.0,
        "churn_total": float(np.sum(res["churn_mag"])),
        "churn_accel_max": float(np.max(res["churn_accel"])) if len(res["churn_accel"]) else 0.0,
        "churn_accel_mean": float(np.mean(res["churn_accel"])) if len(res["churn_accel"]) else 0.0,
        "gov_max_speed": float(gov[:, 2].max()) if len(gov) else 0.0,
        "gov_max_accel": float(gov[:, 3].max()) if len(gov) else 0.0,
        "gov_edges": int(len(gov)),
        "util_max_series": s[:, 1] if len(s) else np.zeros(1),
        "qmax_series": s[:, 2] if len(s) else np.zeros(1),
        "pmax_series": s[:, 4] if len(s) else np.zeros(1),
        "nclass_series": s[:, 6] if len(s) else np.zeros(1),
        "series_t": s[:, 0] if len(s) else np.zeros(1),
        "churn_rate": churn_rate if churn_rate is not None else np.zeros(1),
        "churn_accel": res["churn_accel"],
        "churn_speed": res["churn_speed"],
        "churn_t": res["churn_t"],
        "roll_t": ts, "roll_p95": p95s, "roll_mean": means, "roll_n": cnts,
        "roll_goodput_t": g_t,
        "roll_goodput": g_goodput,
        "roll_transit_goodput": g_transit,
        "alpha_final": res["alpha_final"],
        "attack_target": res["attack_target"],
        "base_window": base_w,
        "shock_window": shock_w,
    }
    return out
