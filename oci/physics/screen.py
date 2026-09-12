"""M3 — Conjunction screening: the filter chain (SPEC §10.3), as measured, not as assumed.

Stage 1  apogee/perigee radial-range overlap (pure algebra) — removes most pairs for free
Stage 2  spatial index per time sample (cKDTree over all positions, query_pairs within the
         approach radius). This is the orbit-path geometric filter evaluated exactly, with
         time included. The mean-element Keplerian path the spec describes was measured to
         be 30+ km from the SGP4 path (J2 short-period terms and nodal precession over a
         multi-day window) and rejected a real 200 m conjunction; the index has no such error.
Stage 3  local minima of the sampled separation, gated on the parabolic estimate of the dip.
         Sample step is seconds, not 15 minutes: at 14 km/s relative speed a 15-min step is
         6,000 km, and every crossing conjunction whose TCA fell between samples was missed
         in tests. The parabolic-estimate error is ½·a_rel·Δt² (measured 7 km @30 s,
         29 km @60 s, 117 km @120 s), so the gate is d + that margin.
Stage 4  fine TCA refinement (bounded scalar minimisation on minutes-offset, ~1 s resolution)
Stage 5  risk annotation (covariance → Pc, or N/A with reason)
Stage 6  classification (ACTIVE_ACTIVE / ACTIVE_DEAD / DEAD_DEAD, intra-constellation)

Never O(N²) per time step. Pair counts at every stage are reported so blow-ups are visible.
"""
from __future__ import annotations

import hashlib
import itertools
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional, Sequence

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.spatial import cKDTree

from oci.config import CONFIG, MU_EARTH_KM3_S2, R_EARTH_KM
from oci.data.objects import SpaceObject
from oci.labels import Traced, traced
from oci.physics.geometry import covariance_inertial, encounter_plane
from oci.physics.pc import PcResult, compute_pc
from oci.physics.propagate import PropagationError, jd_of, propagate, propagate_batch, satrec_from_elements, time_grid

PairClass = Literal["ACTIVE_ACTIVE", "ACTIVE_DEAD", "DEAD_DEAD"]
STAGE2_MARGIN_KM = 25.0
SMALL_SET = 64          # below this, direct pairwise distances beat building a tree per sample


@dataclass(frozen=True)
class Conjunction:
    conj_id: str
    primary_id: int
    secondary_id: int
    tca: datetime
    miss_distance_m: Traced
    rel_speed_mps: Traced
    rel_r_km: np.ndarray            # secondary − primary at TCA, TEME
    rel_v_kmps: np.ndarray
    pc: Traced
    pc_max: Traced
    pc_method: str
    covariance_source: str
    sigma_rtn_combined_m: Optional[tuple[float, float, float]]
    mahalanobis: Optional[float]
    dilution: bool
    pair_class: PairClass
    intra_constellation: bool
    screening_run_id: str
    computed_by: str = "physics.screen@0.1.0"

    @property
    def miss_m(self) -> float:
        return float(self.miss_distance_m.value)

    @property
    def pc_value(self) -> Optional[float]:
        return self.pc.value

    def key(self) -> tuple[int, int]:
        return (min(self.primary_id, self.secondary_id), max(self.primary_id, self.secondary_id))


@dataclass
class ScreeningRun:
    run_id: str
    window_start: datetime
    window_end: datetime
    n_objects: int
    n_pairs_total: int
    n_pairs_after_stage1: int
    n_pairs_after_stage2: int
    n_candidates_stage3: int
    n_conjunctions: int
    screening_volume_m: float
    coarse_step_min: float
    gate_k: float
    propagator: str
    config_hash: str
    runtime_s: float
    excluded: dict[int, str] = field(default_factory=dict)


@dataclass
class ScreeningResult:
    conjunctions: list[Conjunction]
    run: ScreeningRun


# ── stage helpers ─────────────────────────────────────────────────────────────────────────

def dip_margin_km(step_s: float) -> float:
    """Worst-case error of the parabolic dip estimate: ½·a_rel·Δt² with a_rel = 2·g_LEO
    (opposite gravity directions), ×1.1 safety. Matches measurement (29 km at 60 s)."""
    return 0.5 * (2.0 * 8.7e-3) * step_s ** 2 * 1.1


def gate_radius_km(d_screen_m: float, coarse_step_min: float, v_rel_max_kmps: float | None = None,
                   k: float | None = None) -> float:
    """Stage-3 gate on the parabolic dip estimate: max(k·d, d + dip margin)."""
    d_km = d_screen_m / 1000.0
    k_conf = k if k is not None else CONFIG.screening.gate_k
    return max(k_conf * d_km, d_km + dip_margin_km(coarse_step_min * 60.0))


def query_radius_km(d_screen_m: float, coarse_step_min: float) -> float:
    """Stage-2 spatial-index radius: a pair with a true minimum inside the gate must be
    caught at the sample nearest TCA, which is at most Δt/2 away → v_rel_max·Δt/2 + gate."""
    step_s = coarse_step_min * 60.0
    return CONFIG.screening.v_rel_max_kmps * step_s / 2.0 + gate_radius_km(d_screen_m, coarse_step_min)


def _parabolic_min(d2_left: float, d2_mid: float, d2_right: float) -> float:
    """Minimum of the parabola through three equally spaced samples of d² (returns d, km)."""
    denom = d2_left - 2.0 * d2_mid + d2_right
    if denom <= 0:
        return math.sqrt(max(d2_mid, 0.0))
    x = 0.5 * (d2_left - d2_right) / denom          # offset of the vertex in step units
    x = max(-1.0, min(1.0, x))
    val = d2_mid - 0.25 * (d2_left - d2_right) * x
    return math.sqrt(max(val, 0.0))


def radial_ranges_overlap(a: SpaceObject, b: SpaceObject, d_screen_m: float) -> bool:
    oa, ob = a.orbit, b.orbit
    d = d_screen_m / 1000.0
    return not (oa.perigee_alt_km - ob.apogee_alt_km > d or ob.perigee_alt_km - oa.apogee_alt_km > d)


def _orbit_path_points(obj: SpaceObject, n: int = 90) -> np.ndarray:
    """Points along the (Keplerian) orbit path in the orbital frame, ignoring timing."""
    el = obj.elements
    a = obj.orbit.sma_km
    e = el.eccentricity
    i, O, w = map(math.radians, (el.inclination_deg, el.raan_deg, el.argp_deg))
    nu = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    p = a * (1.0 - e * e)
    r = p / (1.0 + e * np.cos(nu))
    x_p, y_p = r * np.cos(nu), r * np.sin(nu)
    cO, sO, ci, si, cw, sw = math.cos(O), math.sin(O), math.cos(i), math.sin(i), math.cos(w), math.sin(w)
    R = np.array([
        [cO * cw - sO * sw * ci, -cO * sw - sO * cw * ci],
        [sO * cw + cO * sw * ci, -sO * sw + cO * cw * ci],
        [sw * si, cw * si],
    ])
    return (R @ np.vstack([x_p, y_p])).T   # (n,3)


def min_orbit_path_distance_km(a: SpaceObject, b: SpaceObject) -> float:
    """Stage 2: min distance between the two orbit *paths* (timing ignored), sampled then
    refined near the best sample. A loose lower bound — the refinement makes it tight enough
    that a rejection is safe (verified by test_filter_chain_no_false_negatives)."""
    pa, pb = _orbit_path_points(a), _orbit_path_points(b)
    d = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=2)
    ia, ib = np.unravel_index(np.argmin(d), d.shape)
    # local refinement with a finer sampling around the best pair of true anomalies
    best = float(d[ia, ib])
    n = pa.shape[0]
    fine_a = _orbit_path_points(a, n * 8)
    fine_b = _orbit_path_points(b, n * 8)
    wa = slice(max(0, ia * 8 - 12), min(n * 8, ia * 8 + 12))
    wb = slice(max(0, ib * 8 - 12), min(n * 8, ib * 8 + 12))
    d2 = np.linalg.norm(fine_a[wa][:, None, :] - fine_b[wb][None, :, :], axis=2)
    return min(best, float(d2.min()))


def _separation_fn(sat_a, sat_b):
    def f(t_jd: float) -> float:
        ea, ra, _ = sat_a.sgp4(math.floor(t_jd - 0.5) + 0.5, t_jd - (math.floor(t_jd - 0.5) + 0.5))
        eb, rb, _ = sat_b.sgp4(math.floor(t_jd - 0.5) + 0.5, t_jd - (math.floor(t_jd - 0.5) + 0.5))
        if ea or eb:
            return 1e9
        return float(np.linalg.norm(np.subtract(ra, rb)))
    return f


def refine_tca(a: SpaceObject, b: SpaceObject, t_guess: datetime, bracket_min: float | None = None
               ) -> tuple[datetime, float, float, np.ndarray, np.ndarray]:
    """Stage 4: bounded minimisation of separation around a coarse dip.
    Returns (tca, miss_km, v_rel_kmps, rel_r_km, rel_v_kmps)."""
    half = (bracket_min if bracket_min is not None else CONFIG.screening.coarse_step_min) / 1440.0
    sat_a = satrec_from_elements(a.norad_id, a.elements)
    sat_b = satrec_from_elements(b.norad_id, b.elements)
    jd, fr = jd_of(t_guess)
    t0 = jd + fr
    f = _separation_fn(sat_a, sat_b)
    # Minimise over the offset in minutes, not absolute JD: a bounded scalar minimiser at
    # x ≈ 2.46e6 with a 1e-5 tolerance never moves (float scaling), and returns the bracket edge.
    half_min = half * 1440.0
    res = minimize_scalar(lambda m: f(t0 + m / 1440.0), bounds=(-half_min, half_min), method="bounded",
                          options={"xatol": CONFIG.screening.refine_tolerance_s / 60.0})
    t_star = t0 + float(res.x) / 1440.0
    tca = t_guess + timedelta(days=t_star - t0)
    jd_i = math.floor(t_star - 0.5) + 0.5
    ea, ra, va = sat_a.sgp4(jd_i, t_star - jd_i)
    eb, rb, vb = sat_b.sgp4(jd_i, t_star - jd_i)
    if ea or eb:
        raise PropagationError(a.norad_id if ea else b.norad_id, ea or eb, "refinement propagation failed")
    rel_r = np.subtract(rb, ra)
    rel_v = np.subtract(vb, va)
    return tca, float(np.linalg.norm(rel_r)), float(np.linalg.norm(rel_v)), np.asarray(rel_r), np.asarray(rel_v)


def classify(a: SpaceObject, b: SpaceObject) -> tuple[PairClass, bool]:
    if a.is_active and b.is_active:
        pc: PairClass = "ACTIVE_ACTIVE"
    elif not a.is_active and not b.is_active:
        pc = "DEAD_DEAD"
    else:
        pc = "ACTIVE_DEAD"
    intra = (a.operator == b.operator and a.operator in CONFIG.attribution.coordinated_constellations)
    return pc, intra


def annotate_risk(a: SpaceObject, b: SpaceObject, rel_r_km: np.ndarray, rel_v_kmps: np.ndarray,
                  r_a_km: np.ndarray, v_a_kmps: np.ndarray, r_b_km: np.ndarray, v_b_kmps: np.ndarray) -> PcResult:
    """Stage 5. Combined covariance = Σ_a + Σ_b (independence), projected into the B-plane."""
    if a.sigma_rtn_m is None or b.sigma_rtn_m is None:
        return compute_pc(None, None, "none")
    cov = covariance_inertial(a.sigma_rtn_m, r_a_km, v_a_kmps) + covariance_inertial(b.sigma_rtn_m, r_b_km, v_b_kmps)
    plane = encounter_plane(rel_r_km, rel_v_kmps, cov)
    src = a.covariance_source if a.covariance_source == b.covariance_source else "mixed"
    sig = tuple(math.sqrt(sa * sa + sb * sb) for sa, sb in zip(a.sigma_rtn_m, b.sigma_rtn_m))
    hbr = a.hard_body_radius_m + b.hard_body_radius_m if (a.hard_body_radius_m + b.hard_body_radius_m) > 0 else CONFIG.pc.hard_body_radius_m
    return compute_pc(plane.miss_xy_m, plane.cov_xy_m2, src, hbr_m=hbr, sigma_rtn_combined_m=sig)  # type: ignore[arg-type]


def _run_id(t0: datetime, cfg_hash: str) -> str:
    return f"run_{t0.strftime('%Y%m%dT%H%MZ')}_{cfg_hash[:4]}"


def _config_hash(d_screen_m: float, coarse_min: float, gate_k: float) -> str:
    s = f"{d_screen_m}|{coarse_min}|{gate_k}|{CONFIG.pc.method}|{CONFIG.pc.hard_body_radius_m}"
    return hashlib.sha1(s.encode()).hexdigest()


# ── the chain ─────────────────────────────────────────────────────────────────────────────

def screen(objects: Sequence[SpaceObject], t0: datetime, t1: datetime,
           d_screen_m: float | None = None, coarse_min: float | None = None,
           gate_k: float | None = None, run_id: str | None = None,
           pairs_override: Optional[list[tuple[int, int]]] = None) -> ScreeningResult:
    started = time.perf_counter()
    d_screen_m = d_screen_m if d_screen_m is not None else CONFIG.screening.screening_volume_m
    coarse_min = coarse_min if coarse_min is not None else CONFIG.screening.coarse_step_min
    gate_k = gate_k if gate_k is not None else CONFIG.screening.gate_k
    cfg_hash = _config_hash(d_screen_m, coarse_min, gate_k)
    run_id = run_id or _run_id(t0, cfg_hash)

    excluded: dict[int, str] = {}
    objs = []
    for o in objects:
        if o.stale:
            excluded[o.norad_id] = "stale element set"
        elif o.orbit.mean_alt_km >= CONFIG.screening.max_alt_km:
            excluded[o.norad_id] = "outside LEO scope"
        else:
            objs.append(o)
    n = len(objs)
    idx = {o.norad_id: i for i, o in enumerate(objs)}

    # Stage 1
    all_pairs = list(itertools.combinations(range(n), 2)) if pairs_override is None else \
        [(idx[a], idx[b]) for a, b in pairs_override if a in idx and b in idx]
    s1 = [(i, j) for i, j in all_pairs if radial_ranges_overlap(objs[i], objs[j], d_screen_m)]
    # Stage 2 + 3 — per-sample spatial index, then local minima gated on the parabolic dip
    s1_set = set(s1)
    gate_km = gate_radius_km(d_screen_m, coarse_min, k=gate_k)
    r_query = query_radius_km(d_screen_m, coarse_min)
    times = time_grid(t0, t1, coarse_min)
    n_t = len(times)
    step_per_block = max(int(CONFIG.screening.block_hours * 60.0 / coarse_min), 3)
    # separations per pair are kept only around index-hits: {pair: {k: sep_km}}
    hits: dict[tuple[int, int], dict[int, float]] = {}
    n_index_pairs = 0
    start = 0
    while start < n_t:
        k_lo, k_hi = max(0, start - 1), min(n_t, start + step_per_block + 1)
        chunk = times[k_lo:k_hi]
        r, _, err = propagate_batch(objs, chunk)
        for i, o in enumerate(objs):
            if o.norad_id not in excluded and np.any(err[i] != 0):
                excluded[o.norad_id] = f"SGP4 error during coarse grid ({int(err[i][err[i] != 0][0])})"
        ok = np.array([o.norad_id not in excluded for o in objs])
        for kk, t in enumerate(chunk):
            k = k_lo + kk
            pts = r[:, kk, :]
            valid = ok & np.all(np.isfinite(pts), axis=1)
            idx_valid = np.nonzero(valid)[0]
            if len(idx_valid) < 2:
                continue
            if len(idx_valid) <= SMALL_SET:
                sub = pts[idx_valid]
                dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
                ia, ib = np.nonzero(np.triu(dm <= r_query, k=1))
                pair_iter = zip(ia.tolist(), ib.tolist())
            else:
                pair_iter = cKDTree(pts[idx_valid]).query_pairs(r_query)
            for a, b in pair_iter:
                i, j = int(idx_valid[a]), int(idx_valid[b])
                if i > j:
                    i, j = j, i
                if (i, j) not in s1_set:
                    continue
                n_index_pairs += 1
                d = hits.setdefault((i, j), {})
                # store this sample and its neighbours so a dip at k has both sides available
                for kn in (k - 1, k, k + 1):
                    if k_lo <= kn < k_hi and kn not in d:
                        d[kn] = float(np.linalg.norm(r[i, kn - k_lo] - r[j, kn - k_lo]))
        start += step_per_block
    cands: list[tuple[int, int, datetime]] = []
    for (i, j), d in hits.items():
        for k, sk in d.items():
            left, right = d.get(k - 1), d.get(k + 1)
            if left is None and k > 0:
                continue         # not a complete local-min triple (the neighbour was outside the query radius)
            if right is None and k + 1 < n_t:
                continue
            if left is not None and sk > left:
                continue
            if right is not None and sk > right:
                continue
            if left is None or right is None:
                est = sk         # window edge
            else:
                est = _parabolic_min(left * left, sk * sk, right * right)
            if est <= gate_km:
                cands.append((i, j, times[k]))
    s2 = sorted(hits.keys())
    # Stage 4–6
    conjs: list[Conjunction] = []
    seen: set[tuple[int, int, int]] = set()
    for i, j, tg in cands:
        a, b = objs[i], objs[j]
        try:
            tca, miss_km, vrel, rel_r, rel_v = refine_tca(a, b, tg, bracket_min=coarse_min)
        except PropagationError as e:
            excluded[e.norad_id] = str(e)
            continue
        if tca < t0 or tca > t1 or miss_km * 1000.0 > d_screen_m:
            continue
        dedupe = (a.norad_id, b.norad_id, int(round(tca.timestamp() / CONFIG.screening.dedupe_tca_s)))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        st_a, st_b = propagate(a, tca), propagate(b, tca)
        risk = annotate_risk(a, b, rel_r, rel_v, st_a.r_km, st_a.v_kmps, st_b.r_km, st_b.v_kmps)
        pair_class, intra = classify(a, b)
        conj_id = "cj_" + hashlib.sha1(f"{a.norad_id}|{b.norad_id}|{tca.isoformat()}".encode()).hexdigest()[:10]
        conjs.append(Conjunction(
            conj_id=conj_id, primary_id=a.norad_id, secondary_id=b.norad_id, tca=tca,
            miss_distance_m=traced(miss_km * 1000.0, "m", "COMPUTED", "physics.screen.refine_tca@0.1.0",
                                   propagator=CONFIG.propagator, frame="TEME"),
            rel_speed_mps=traced(vrel * 1000.0, "m/s", "COMPUTED", "physics.screen.refine_tca@0.1.0"),
            rel_r_km=rel_r, rel_v_kmps=rel_v,
            pc=risk.pc, pc_max=risk.pc_max, pc_method=risk.method, covariance_source=risk.covariance_source,
            sigma_rtn_combined_m=risk.sigma_rtn_combined_m, mahalanobis=risk.mahalanobis, dilution=risk.dilution,
            pair_class=pair_class, intra_constellation=intra, screening_run_id=run_id,
        ))
    conjs.sort(key=lambda c: c.tca)
    run = ScreeningRun(
        run_id=run_id, window_start=t0, window_end=t1, n_objects=n,
        n_pairs_total=len(all_pairs), n_pairs_after_stage1=len(s1), n_pairs_after_stage2=len(s2),
        n_candidates_stage3=len(cands), n_conjunctions=len(conjs),
        screening_volume_m=d_screen_m, coarse_step_min=coarse_min, gate_k=gate_km / (d_screen_m / 1000.0),
        propagator=CONFIG.propagator, config_hash=cfg_hash, runtime_s=time.perf_counter() - started,
        excluded=excluded,
    )
    return ScreeningResult(conjunctions=conjs, run=run)


def screen_pair(a: SpaceObject, b: SpaceObject, t0: datetime, t1: datetime, **kw) -> list[Conjunction]:
    """Screen exactly one pair (used by the Δv-to-clear loop and the validator's re-screen)."""
    return screen([a, b], t0, t1, **kw).conjunctions


def brute_force_screen(objects: Sequence[SpaceObject], t0: datetime, t1: datetime,
                       d_screen_m: float, step_min: float = 1.0) -> set[tuple[int, int]]:
    """Reference all-pairs screen at fine resolution. Test-only: used to prove the filter chain
    has no false negatives (SPEC §17.3)."""
    times = time_grid(t0, t1, step_min)
    r, _, err = propagate_batch(objects, times)
    found: set[tuple[int, int]] = set()
    n = len(objects)
    for i in range(n):
        for j in range(i + 1, n):
            if np.any(err[i]) or np.any(err[j]):
                continue
            sep = np.linalg.norm(r[i] - r[j], axis=1)
            k = int(np.argmin(sep))
            if sep[k] * 1000.0 <= d_screen_m * 1.0:
                found.add((objects[i].norad_id, objects[j].norad_id))
            else:
                # refine the best dip to be fair to the reference
                try:
                    _, miss_km, *_ = refine_tca(objects[i], objects[j], times[k], bracket_min=step_min)
                    if miss_km * 1000.0 <= d_screen_m:
                        found.add((objects[i].norad_id, objects[j].norad_id))
                except PropagationError:
                    pass
    return found
