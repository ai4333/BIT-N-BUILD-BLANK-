"""M8 Part C — Value of information (SPEC §10.8, §11.11).

cost_now  = c_f·Δv(Pc(σ(τ))) + c_r·P_residual
cost_wait = c_f·E[Δv(Pc')] + c_r·E[P_residual'] + c_l·P(window closes) + c_u·P(risk grows)
VoI = cost_now − cost_wait. Both penalty terms are nonzero by construction — a VoI module
that always says "wait" is broken (§10.8 failure modes).

The shrinkage model σ(τ) is declared from config until the Kelvins fit (block 4) replaces it;
`covariance_source` on the result says which.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Sequence

import numpy as np

from oci.config import CONFIG
from oci.data.objects import SpaceObject
from oci.labels import Traced, na, traced
from oci.physics.geometry import covariance_inertial, encounter_plane
from oci.physics.maneuver import dv_to_clear
from oci.physics.pc import foster_2d
from oci.physics.propagate import propagate
from oci.physics.screen import Conjunction
from oci.sim.simulate import shrink_sigma

_FN = "decide.voi@0.1.0"


@dataclass
class VoIOption:
    wait_min: float
    expected_sigma_reduction: Traced
    expected_pc: Traced
    expected_dv_mps: Traced
    risk_of_delay: Traced
    voi_net: Traced
    feasible: bool


@dataclass
class VoIResult:
    conj_id: str
    cost_now: Traced
    dv_now_mps: Traced
    options: list[VoIOption]
    recommended_wait_min: Optional[float]
    covariance_source: str


def _expected_dv_after_wait(primary: SpaceObject, secondary: SpaceObject, c: Conjunction, wait_h: float,
                            pc_star: float, n_samples: int, rng: np.random.Generator) -> tuple[float, float, float]:
    """E[Δv], E[Pc'], P(Pc' grows beyond dv_max clearance) after waiting, by sampling the refined
    miss vector from the *current* covariance and evaluating Pc under the *shrunk* covariance."""
    sa, sb = propagate(primary, c.tca), propagate(secondary, c.tca)
    cov_now = covariance_inertial(primary.sigma_rtn_m, sa.r_km, sa.v_kmps) + covariance_inertial(secondary.sigma_rtn_m, sb.r_km, sb.v_kmps)
    plane_now = encounter_plane(c.rel_r_km, c.rel_v_kmps, cov_now)
    s_a = shrink_sigma(primary.sigma_rtn_m, wait_h + 1.0, 1.0)
    s_b = shrink_sigma(secondary.sigma_rtn_m, wait_h + 1.0, 1.0)
    cov_later = covariance_inertial(s_a, sa.r_km, sa.v_kmps) + covariance_inertial(s_b, sb.r_km, sb.v_kmps)
    plane_later = encounter_plane(c.rel_r_km, c.rel_v_kmps, cov_later)
    hbr = primary.hard_body_radius_m + secondary.hard_body_radius_m
    pcs, dvs, grow = [], [], 0
    residuals = []
    # Δv scales ~ with the along-track clearance needed; calibrate once from the nominal case
    nominal = dv_to_clear(primary, secondary, c.tca, pc_star)
    dv_nom = nominal.dv_mps.value if nominal.dv_mps.value is not None else CONFIG.maneuver.dv_max_mps
    pc_nom = c.pc.value or 0.0
    for _ in range(n_samples):
        miss = rng.multivariate_normal(plane_now.miss_xy_m, plane_now.cov_xy_m2)
        p = foster_2d(miss, plane_later.cov_xy_m2, hbr)
        pcs.append(p)
        if p < pc_star / CONFIG.maneuver.pc_margin:
            dvs.append(0.0)
            residuals.append(p / pc_star)                       # no burn needed; residual is the raw Pc
        else:
            residuals.append(1.0 / CONFIG.maneuver.pc_margin)    # cleared to Pc*/margin by construction
            # first-order: required clearance grows with log(Pc/Pc*) — proportional to the
            # Mahalanobis shift needed; scale the nominal Δv by that ratio, capped at dv_max
            scale = max(0.2, math.log10(p / (pc_star / CONFIG.maneuver.pc_margin)) / max(math.log10(max(pc_nom, 1e-12) / (pc_star / CONFIG.maneuver.pc_margin)), 0.3))
            dv = min(dv_nom * scale, CONFIG.maneuver.dv_max_mps)
            dvs.append(dv)
            if dv >= CONFIG.maneuver.dv_max_mps:
                grow += 1
    return float(np.mean(dvs)), float(np.mean(pcs)), grow / n_samples, float(np.mean(residuals))


def compute_voi(c: Conjunction, objects: dict[int, SpaceObject], decision_epoch,
                wait_options_min: Sequence[float] | None = None, n_samples: int = 200, seed: int = 42,
                pc_threshold: float | None = None) -> VoIResult:
    vc = CONFIG.voi
    pc_star = float(pc_threshold if pc_threshold is not None else CONFIG.thresholds.declared_pc_threshold)
    waits = list(wait_options_min or CONFIG.decision.wait_options_min)
    a, b = objects[c.primary_id], objects[c.secondary_id]
    src = a.covariance_source if a.covariance_source == b.covariance_source else "mixed"
    if a.sigma_rtn_m is None or b.sigma_rtn_m is None or c.pc.value is None:
        reason = "no covariance → Pc undefined → VoI undefined"
        return VoIResult(c.conj_id, na("cost", "MODELLED", _FN, reason), na("m/s", "MODELLED", _FN, reason), [], None, "none")
    primary, secondary = (a, b) if a.is_maneuverable else (b, a)
    if not primary.is_maneuverable:
        reason = "neither object is maneuverable"
        return VoIResult(c.conj_id, na("cost", "MODELLED", _FN, reason), na("m/s", "MODELLED", _FN, reason), [], None, src)
    now = dv_to_clear(primary, secondary, c.tca, pc_star)
    dv_now = now.dv_mps.value if now.dv_mps.value is not None else CONFIG.maneuver.dv_max_mps
    residual_now = (now.pc_after.value or 0.0) / pc_star
    cost_now = vc.c_fuel * dv_now + vc.c_risk * residual_now
    lead_available_min = (c.tca - decision_epoch).total_seconds() / 60.0
    min_lead = CONFIG.validator.min_maneuver_lead_min + CONFIG.validator.uplink_lead_min + primary.orbit.period_min
    rng = np.random.default_rng(seed)
    options: list[VoIOption] = []
    best: Optional[VoIOption] = None
    for w in waits:
        remaining = lead_available_min - w
        feasible = remaining >= min_lead
        # P(window closes): logistic in how close `remaining` is to the minimum lead, never zero
        p_late = 1.0 / (1.0 + math.exp((remaining - min_lead) / max(min_lead * 0.25, 1.0)))
        e_dv, e_pc, p_grow, e_resid = _expected_dv_after_wait(primary, secondary, c, w / 60.0, pc_star, n_samples, rng)
        s_before = sum(primary.sigma_rtn_m) + sum(secondary.sigma_rtn_m)
        s_after = sum(shrink_sigma(primary.sigma_rtn_m, w / 60.0 + 1, 1)) + sum(shrink_sigma(secondary.sigma_rtn_m, w / 60.0 + 1, 1))
        cost_wait = vc.c_fuel * e_dv + vc.c_risk * e_resid + vc.c_late * p_late + vc.c_growth * p_grow
        voi = cost_now - cost_wait
        opt = VoIOption(
            wait_min=w,
            expected_sigma_reduction=traced(1.0 - s_after / s_before, "fraction", "MODELLED", _FN, shrinkage=vc.source),
            expected_pc=traced(e_pc, "probability", "MODELLED", _FN, n_samples=n_samples),
            expected_dv_mps=traced(e_dv, "m/s", "MODELLED", _FN, n_samples=n_samples),
            risk_of_delay=traced(p_late + p_grow, "cost", "MODELLED", _FN, p_window_closes=p_late, p_risk_grows=p_grow),
            voi_net=traced(voi, "cost", "MODELLED", _FN, c_fuel=vc.c_fuel, c_risk=vc.c_risk, c_late=vc.c_late, c_growth=vc.c_growth),
            feasible=feasible,
        )
        options.append(opt)
        if feasible and voi > 0 and (best is None or voi > float(best.voi_net.value)):
            best = opt
    return VoIResult(
        conj_id=c.conj_id,
        cost_now=traced(cost_now, "cost", "MODELLED", _FN, dv_now=dv_now, residual=residual_now),
        dv_now_mps=traced(dv_now, "m/s", "MODELLED", _FN),
        options=options, recommended_wait_min=best.wait_min if best else None, covariance_source=src,
    )
