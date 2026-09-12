"""Impulsive manoeuvres and element-set rebuild (SPEC §11.2), Δv-to-clear (§11.5).

Rebuilding mean elements after a burn: the spec allows a first-order osculating→mean
approximation. We do better and more simply — a numerical fit: starting from the osculating
elements of the post-burn state, solve for the mean element set whose SGP4 propagation at
`t_burn` reproduces the post-burn (r, v). With Δv = 0 the round trip returns the original
state to solver tolerance, which is the mandatory validation test.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal, Optional

import numpy as np
from scipy.optimize import least_squares

from oci.config import CONFIG, MU_EARTH_KM3_S2
from oci.data.objects import Elements, SpaceObject
from oci.labels import Traced, na, traced
from oci.physics.geometry import rtn_to_inertial
from oci.physics.propagate import State, jd_of, propagate, satrec_from_elements

Direction = Literal["R", "T", "N"]


def rv2coe(r: np.ndarray, v: np.ndarray, mu: float = MU_EARTH_KM3_S2) -> dict[str, float]:
    """Osculating classical elements from a state vector. Angles in degrees."""
    rn = np.linalg.norm(r)
    h = np.cross(r, v); hn = np.linalg.norm(h)
    n_vec = np.cross([0.0, 0.0, 1.0], h); nn = np.linalg.norm(n_vec)
    e_vec = ((np.dot(v, v) - mu / rn) * r - np.dot(r, v) * v) / mu
    e = float(np.linalg.norm(e_vec))
    energy = np.dot(v, v) / 2.0 - mu / rn
    a = -mu / (2.0 * energy)
    inc = math.degrees(math.acos(np.clip(h[2] / hn, -1, 1)))
    raan = math.degrees(math.atan2(n_vec[1], n_vec[0])) % 360.0 if nn > 1e-12 else 0.0
    if e > 1e-9 and nn > 1e-12:
        argp = math.degrees(math.acos(np.clip(np.dot(n_vec, e_vec) / (nn * e), -1, 1)))
        if e_vec[2] < 0:
            argp = 360.0 - argp
        nu = math.degrees(math.acos(np.clip(np.dot(e_vec, r) / (e * rn), -1, 1)))
        if np.dot(r, v) < 0:
            nu = 360.0 - nu
    else:
        # circular: measure argument of latitude from the node
        argp = 0.0
        if nn > 1e-12:
            nu = math.degrees(math.acos(np.clip(np.dot(n_vec, r) / (nn * rn), -1, 1)))
            if r[2] < 0:
                nu = 360.0 - nu
        else:
            nu = math.degrees(math.atan2(r[1], r[0])) % 360.0
    E = 2.0 * math.atan2(math.sqrt(1 - e) * math.sin(math.radians(nu) / 2), math.sqrt(1 + e) * math.cos(math.radians(nu) / 2))
    M = math.degrees(E - e * math.sin(E)) % 360.0
    n_rev_day = math.sqrt(mu / a ** 3) * 86400.0 / (2.0 * math.pi)
    return {"a_km": a, "e": e, "inc_deg": inc, "raan_deg": raan, "argp_deg": argp, "nu_deg": nu,
            "M_deg": M, "n_rev_day": n_rev_day}


def fit_mean_elements(norad_id: int, r_km: np.ndarray, v_kmps: np.ndarray, epoch: datetime,
                      bstar: float = 0.0, seed: Optional[Elements] = None) -> Elements:
    """Find mean elements whose SGP4 state at `epoch` equals (r, v).

    Least squares in an equinoctial-style parameterisation (n, e·cos ω, i, Ω, e·sin ω, ω+M):
    the classical (e, ω, M) set is degenerate for near-circular orbits and was measured to
    stall at ~2 km residual on a real e = 1e-4 Sentinel element set; this form converges in a
    handful of evaluations. Starting point: the osculating elements of (r, v)."""
    coe = rv2coe(r_km, v_kmps)
    if seed is not None:
        n0, e0, i0, O0, w0, M0 = (seed.mean_motion_rev_day, seed.eccentricity, seed.inclination_deg,
                                  seed.raan_deg, seed.argp_deg, seed.mean_anomaly_deg)
    else:
        n0, e0, i0, O0, w0, M0 = coe["n_rev_day"], coe["e"], coe["inc_deg"], coe["raan_deg"], coe["argp_deg"], coe["M_deg"]
    w_rad = math.radians(w0)
    y0 = np.array([n0, e0 * math.cos(w_rad), i0, O0, e0 * math.sin(w_rad), (w0 + M0) % 360.0])
    jd, fr = jd_of(epoch)
    target = np.concatenate([r_km, v_kmps * 1000.0])   # scale v so residuals are comparable

    def unpack(y) -> Elements:
        e = float(math.hypot(y[1], y[4]))
        w = math.degrees(math.atan2(y[4], y[1])) % 360.0
        return Elements(epoch=epoch, mean_motion_rev_day=float(y[0]), eccentricity=e, inclination_deg=float(y[2]),
                        raan_deg=float(y[3] % 360.0), argp_deg=w, mean_anomaly_deg=float((y[5] - w) % 360.0), bstar=bstar)

    def resid(y):
        sat = satrec_from_elements(norad_id, unpack(y))
        e, rr, vv = sat.sgp4(jd, fr)
        if e:
            return np.full(6, 1e6)
        return np.concatenate([np.asarray(rr), np.asarray(vv) * 1000.0]) - target

    res = least_squares(resid, y0, xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=400, x_scale="jac")
    if np.linalg.norm(res.fun[:3]) > 1e-3:   # > 1 m position residual is a failed fit
        raise RuntimeError(f"mean-element fit did not converge for NORAD {norad_id}: |Δr|={np.linalg.norm(res.fun[:3])*1000:.1f} m")
    return unpack(res.x)


@dataclass(frozen=True)
class Burn:
    target_id: int
    dv_rtn_mps: tuple[float, float, float]
    t_burn: datetime

    @property
    def magnitude_mps(self) -> float:
        return float(np.linalg.norm(self.dv_rtn_mps))


def apply_maneuver(obj: SpaceObject, burn: Burn) -> SpaceObject:
    """§11.2 — propagate to t_burn, add Δv (RTN → inertial), rebuild mean elements. Pure."""
    st = propagate(obj, burn.t_burn)
    dv_i = rtn_to_inertial(np.asarray(burn.dv_rtn_mps, dtype=float) / 1000.0, st.r_km, st.v_kmps)
    v_after = st.v_kmps + dv_i
    el = fit_mean_elements(obj.norad_id, st.r_km, v_after, burn.t_burn, bstar=obj.elements.bstar)
    return obj.with_elements(el)


def delta_sma_analytic_km(a_km: float, dv_alongtrack_mps: float) -> float:
    """§11.2: Δa ≈ 2a²v/μ · Δv (circular). Sanity anchor: ~few hundred m per 1 m/s at 550 km."""
    v = math.sqrt(MU_EARTH_KM3_S2 / a_km)
    return 2.0 * a_km * a_km * v / MU_EARTH_KM3_S2 * (dv_alongtrack_mps / 1000.0)


@dataclass(frozen=True)
class DvToClear:
    dv_mps: Traced
    direction: Optional[Direction]
    t_burn: Optional[datetime]
    pc_after: Traced
    miss_after_m: Traced
    iterations: int
    per_direction: dict[str, Optional[float]]


def _pc_after_burn(obj: SpaceObject, other: SpaceObject, burn: Burn, tca: datetime, horizon_min: float):
    from oci.physics.screen import screen_pair
    moved = apply_maneuver(obj, burn)
    t0 = tca - timedelta(minutes=horizon_min)
    t1 = tca + timedelta(minutes=horizon_min)
    cs = screen_pair(moved, other, t0, t1, coarse_min=5.0, d_screen_m=max(CONFIG.screening.screening_volume_m, 50_000.0))
    if not cs:
        return None, None, moved   # no approach inside 50 km anymore
    c = min(cs, key=lambda c: c.miss_m)
    return c.pc.value, c.miss_m, moved


def dv_to_clear(primary: SpaceObject, secondary: SpaceObject, tca: datetime, pc_threshold: float,
                lead_orbits: float | None = None, directions: tuple[str, ...] | None = None) -> DvToClear:
    """§11.5 — minimal |Δv| at t_burn = tca − lead such that post-burn Pc < Pc*/margin.
    Bisection on magnitude, evaluated along T, R and N; the cheapest direction is reported."""
    mc = CONFIG.maneuver
    lead = lead_orbits if lead_orbits is not None else mc.lead_time_orbits
    dirs = directions or mc.directions
    t_burn = tca - timedelta(minutes=primary.orbit.period_min * lead)
    goal = pc_threshold / mc.pc_margin
    fn = "ledger.dv_to_clear@0.1.0"
    if primary.sigma_rtn_m is None or secondary.sigma_rtn_m is None:
        return DvToClear(na("m/s", "MODELLED", fn, "no covariance → Pc undefined → clearance undefined"),
                         None, None, na("probability", "MODELLED", fn, "no covariance"),
                         na("m", "COMPUTED", fn, "not evaluated"), 0, {})
    per: dict[str, Optional[float]] = {}
    best: Optional[tuple[float, str, float, float]] = None
    total_iter = 0
    for d in dirs:
        unit = {"R": (1.0, 0.0, 0.0), "T": (0.0, 1.0, 0.0), "N": (0.0, 0.0, 1.0)}[d]
        lo, hi = 0.0, mc.dv_max_mps
        pc_hi, miss_hi, _ = _pc_after_burn(primary, secondary, Burn(primary.norad_id, tuple(u * hi for u in unit), t_burn), tca, 30.0)
        if pc_hi is not None and pc_hi >= goal:
            per[d] = None   # even dv_max does not clear along this axis
            continue
        it = 0
        pc_mid, miss_mid = pc_hi, miss_hi
        while hi - lo > mc.dv_tolerance_mps and it < mc.max_bisection_iter:
            mid = 0.5 * (lo + hi)
            pc_mid, miss_mid, _ = _pc_after_burn(primary, secondary, Burn(primary.norad_id, tuple(u * mid for u in unit), t_burn), tca, 30.0)
            if pc_mid is None or pc_mid < goal:
                hi = mid
            else:
                lo = mid
            it += 1
        total_iter += it
        per[d] = hi
        if best is None or hi < best[0]:
            best = (hi, d, pc_mid if pc_mid is not None else 0.0, miss_mid if miss_mid is not None else float("nan"))
    if best is None:
        return DvToClear(na("m/s", "MODELLED", fn, f"bisection did not clear Pc*/{mc.pc_margin} within dv_max={mc.dv_max_mps} m/s"),
                         None, t_burn, na("probability", "MODELLED", fn, "not cleared"),
                         na("m", "COMPUTED", fn, "not cleared"), total_iter, per)
    dv, d, pc_after, miss_after = best
    assumptions = {"pc_threshold": pc_threshold, "margin": mc.pc_margin, "lead_orbits": lead,
                   "direction": d, "method": "bisection_on_magnitude"}
    return DvToClear(
        dv_mps=traced(dv, "m/s", "MODELLED", fn, **assumptions),
        direction=d, t_burn=t_burn,   # type: ignore[arg-type]
        pc_after=traced(pc_after, "probability", "MODELLED", fn, **assumptions),
        miss_after_m=traced(miss_after, "m", "COMPUTED", fn),
        iterations=total_iter, per_direction=per,
    )
