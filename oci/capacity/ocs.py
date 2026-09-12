"""M10 part 3 — Orbital Capacity Score, hazard index, regime indicator κ, and the two peaks
(SPEC §11.8, §11.10).

    OCS_s      = 100 · clamp(1 − M_s / M_viability, 0, 1)      M_viability = 120/sat-yr, published (config)
    hazard_s   = Σ_i m_i · w_state(i) · min(lifetime_i, 100) / normaliser
    κ_s        = E[new conjunctions above Pc* created per executed clearing manoeuvre]   (by simulation)

The two currencies are never blended (§11.10.4). The disagreement is the result.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from oci.capacity.flux import Calibration, ShellFlux, calibrate, shell_flux
from oci.capacity.shells import Shell, partition
from oci.config import CONFIG
from oci.data.objects import SpaceObject
from oci.labels import Traced, na, traced
from oci.physics.decay import decay_lifetime_years
from oci.physics.maneuver import Burn, dv_to_clear
from oci.physics.screen import Conjunction
from oci.sim.simulate import Action, OrbitalState, simulate

_FN = "capacity.ocs@0.1.0"


def ocs_from_burden(m_per_sat_yr: Optional[float]) -> Traced:
    cap = CONFIG.capacity
    if m_per_sat_yr is None:
        return na("score", "MODELLED", _FN, "manoeuvre burden unavailable")
    v = 100.0 * min(1.0, max(0.0, 1.0 - m_per_sat_yr / cap.m_viability_per_sat_yr))
    return traced(v, "score", "MODELLED", _FN, m_viability_per_sat_yr=cap.m_viability_per_sat_yr,
                  anchor=cap.m_viability_source, form="100·clamp(1 − M/M_viability, 0, 1)")


def hazard_raw(objects: Sequence[SpaceObject]) -> float:
    """Σ m·w_state·persistence, un-normalised. Lifetime via the decay model per object."""
    cap = CONFIG.capacity
    total = 0.0
    for o in objects:
        life = decay_lifetime_years(o.orbit.mean_alt_km, o.area_to_mass_m2_kg, cap_yr=cap.persistence_cap_yr).value
        w = cap.w_active_hazard if o.is_active else 1.0
        total += o.mass_kg_est * w * min(life, cap.persistence_cap_yr)
    return total


def _lifetime_cache_key(o: SpaceObject) -> tuple[int, float]:
    return (int(o.orbit.mean_alt_km // 5) * 5, round(o.area_to_mass_m2_kg, 4))


def hazard_raw_fast(objects: Sequence[SpaceObject], cache: dict) -> float:
    """Same as hazard_raw, with lifetimes cached on (5 km altitude bin, A/m)."""
    cap = CONFIG.capacity
    total = 0.0
    for o in objects:
        k = _lifetime_cache_key(o)
        if k not in cache:
            cache[k] = decay_lifetime_years(k[0] + 2.5, k[1], cap_yr=cap.persistence_cap_yr).value
        w = cap.w_active_hazard if o.is_active else 1.0
        total += o.mass_kg_est * w * min(cache[k], cap.persistence_cap_yr)
    return total


@dataclass
class KappaEstimate:
    kappa: Traced
    ci_low: Optional[float]
    ci_high: Optional[float]
    regime: str                       # SUBSTITUTES | INDETERMINATE | COMPLEMENTS | N/A
    n_samples: int
    samples: list[int] = field(default_factory=list)


def estimate_kappa(shell: Shell, state: OrbitalState, conjunctions: Sequence[Conjunction], pc_threshold: float,
                   k_samples: int = 8, seed: int = 42) -> KappaEstimate:
    """§11.8 by simulation: sample conjunctions above Pc* inside the shell whose primary can
    manoeuvre, apply the clearing Δv, re-screen the neighbourhood, count NEW conjunctions above
    Pc*. κ = mean, CI = ±1.96·σ/√K. Labelled MODELLED; N/A when nothing in the shell can move."""
    members = set(shell.members)
    cands = [c for c in conjunctions if c.primary_id in members and c.secondary_id in members
             and c.pc.value is not None and c.pc.value >= pc_threshold]
    events = []
    for c in cands:
        for mover, other in ((c.primary_id, c.secondary_id), (c.secondary_id, c.primary_id)):
            if state.objects[mover].is_maneuverable:
                events.append((c, mover, other))
                break
    if not events:
        return KappaEstimate(na("ratio", "MODELLED", _FN, "no conjunction above Pc* with a manoeuvrable member in this shell"),
                             None, None, "N/A", 0)
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(events), size=min(k_samples, len(events)), replace=False)
    counts: list[int] = []
    for i in idx:
        c, mover, other = events[i]
        d = dv_to_clear(state.objects[mover], state.objects[other], c.tca, pc_threshold)
        if d.direction is None or d.t_burn is None or d.dv_mps.value is None:
            continue
        vec = {"R": (d.dv_mps.value, 0.0, 0.0), "T": (0.0, d.dv_mps.value, 0.0), "N": (0.0, 0.0, d.dv_mps.value)}[d.direction]
        sim = simulate(state, Action("MANEUVER", burn=Burn(mover, vec, d.t_burn)), list(conjunctions))
        new_above = sum(1 for x in sim.conjunctions if x.conj_id in set(sim.new_conj_ids)
                        and x.pc.value is not None and x.pc.value >= pc_threshold)
        counts.append(new_above)
    if not counts:
        return KappaEstimate(na("ratio", "MODELLED", _FN, "clearing burn could not be found for the sampled events"), None, None, "N/A", 0)
    m = float(np.mean(counts))
    sd = float(np.std(counts, ddof=1)) if len(counts) > 1 else 0.0
    half = 1.96 * sd / math.sqrt(len(counts))
    lo, hi = max(0.0, m - half), m + half
    if hi < 1.0:
        regime = "SUBSTITUTES"
    elif lo > 1.0:
        regime = "COMPLEMENTS"
    else:
        regime = "INDETERMINATE"
    return KappaEstimate(traced(m, "ratio", "MODELLED", _FN, n_samples=len(counts), ci95=(round(lo, 2), round(hi, 2)),
                                method="clearing Δv on sampled events, re-screen, count new conjunctions above Pc*"),
                         lo, hi, regime, len(counts), counts)


@dataclass
class ShellCapacity:
    shell: Shell
    flux: ShellFlux
    ocs: Traced
    hazard_index: Traced
    hazard_raw_kg_yr: float
    decay_lifetime_yr: Traced         # for a reference payload at the shell midpoint
    kappa: Optional[KappaEstimate]

    def row(self) -> dict:
        s = self.shell
        return {"shell_id": s.shell_id, "alt_low_km": s.alt_low_km, "alt_high_km": s.alt_high_km,
                "n_objects": s.n_objects, "n_active": s.n_active, "n_dead": s.n_dead, "n_debris": s.n_debris,
                "n_rocket_bodies": s.n_rocket_bodies,
                "spatial_density": self.flux.spatial_density_per_km3, "v_rel_mean_kms": self.flux.v_rel_mean_kms,
                "conjunctions_per_sat_yr": self.flux.conjunctions_per_sat_yr, "q_above_threshold": self.flux.q_above_threshold,
                "maneuver_burden_per_sat_yr": self.flux.maneuvers_per_sat_yr, "calibration_factor": self.flux.calibration_factor,
                "kappa": self.kappa.kappa if self.kappa else na("ratio", "MODELLED", _FN, "κ not estimated for this shell"),
                "regime": self.kappa.regime if self.kappa else "N/A",
                "ocs": self.ocs, "hazard_index": self.hazard_index, "decay_lifetime_yr": self.decay_lifetime_yr}


@dataclass
class CapacityResult:
    shells: list[ShellCapacity]
    pc_threshold: float
    c_intra: float
    workload_peak_alt_km: Optional[float]
    hazard_peak_alt_km: Optional[float]
    peaks_differ: Optional[bool]
    calibration_shells: list[str]
    notes: list[str] = field(default_factory=list)

    def by_alt(self, alt_km: float) -> Optional[ShellCapacity]:
        return next((s for s in self.shells if s.shell.contains_alt(alt_km)), None)


def compute_capacity(objects: Sequence[SpaceObject], conjunctions: Sequence[Conjunction] = (),
                     screened_ids: Optional[set[int]] = None, window_days: float = 0.0,
                     pc_threshold: Optional[float] = None, width_km: Optional[float] = None,
                     alt_min_km: Optional[float] = None, alt_max_km: Optional[float] = None,
                     kappa_state: Optional[OrbitalState] = None, kappa_samples: int = 6,
                     reference_area_to_mass: float = 0.04, seed: int = 42, c_intra: Optional[float] = None) -> CapacityResult:
    """Shell-by-shell capacity for the catalogue. `conjunctions`/`screened_ids` come from an M3
    run covering some shells; q is calibrated there and carried (MODELLED) elsewhere."""
    pc_star = pc_threshold if pc_threshold is not None else CONFIG.thresholds.declared_pc_threshold
    shells = partition(objects, width_km, alt_min_km, alt_max_km)
    by_id = {o.norad_id: o for o in objects}
    screened = screened_ids or set()
    cals: dict[str, Calibration] = {}
    for s in shells:
        if screened and sum(1 for m in s.members if m in screened) >= max(2, 0.5 * s.n_objects) and s.n_objects:
            cal = calibrate(s, conjunctions, {i: by_id[i] for i in s.members if i in screened}, window_days, pc_star)
            if cal.n_conjunctions >= 20:            # enough events to estimate the rate
                cals[s.shell_id] = cal
    # q: pooled over all calibrated shells — per-shell counts above Pc* are single digits at 1e-4,
    # so the pooled estimate is used everywhere and its event count is stated; config prior if none
    pooled_n = sum(c.n_conjunctions for c in cals.values())
    pooled_above = sum(c.n_above_threshold for c in cals.values())
    if pooled_n and pooled_above >= CONFIG.capacity.min_events_for_q:
        q_fb = pooled_above / pooled_n
        q_note = f"pooled over screened shells {sorted(cals)}: {pooled_above}/{pooled_n} conjunctions above Pc*"
    else:
        q_fb = CONFIG.capacity.q_prior_by_threshold.get(pc_star, 1e-3)
        q_note = (f"config prior — screening run has only {pooled_above} conjunction(s) above Pc* (< {CONFIG.capacity.min_events_for_q})"
                  if pooled_n else "config prior (no screening run supplied)")
    for c in cals.values():                         # per-shell q only when the shell itself has enough events
        if c.n_above_threshold < CONFIG.capacity.min_events_for_q:
            c.n_above_threshold = -1                # sentinel: q property → None → fallback used, rate calibration kept
    life_cache: dict = {}
    out: list[ShellCapacity] = []
    raw_h: list[float] = []
    for s in shells:
        fl = shell_flux(s, pc_star, cals.get(s.shell_id), q_fb, q_note, seed=seed, c_intra=c_intra)
        members = [by_id[i] for i in s.members]
        h = hazard_raw_fast(members, life_cache)
        raw_h.append(h)
        life = decay_lifetime_years(s.alt_mid_km, reference_area_to_mass)
        kap = None
        if kappa_state is not None and s.shell_id in cals:
            kap = estimate_kappa(s, kappa_state, conjunctions, pc_star, k_samples=kappa_samples, seed=seed)
        out.append(ShellCapacity(s, fl, ocs_from_burden(fl.maneuvers_per_sat_yr.value), traced(0.0, "index", "MODELLED", _FN), h, life, kap))
    norm = max(raw_h) if raw_h and max(raw_h) > 0 else 1.0
    for sc, h in zip(out, raw_h):
        sc.hazard_index = traced(h / norm, "index", "MODELLED", _FN, normaliser="max over shells (index ∈ [0,1])",
                                 w_active=CONFIG.capacity.w_active_hazard, persistence_cap_yr=CONFIG.capacity.persistence_cap_yr,
                                 raw_kg_yr=round(h), masses="MODELLED from RCS class (§11.9)")
    populated = [sc for sc in out if sc.shell.n_objects > 0 and sc.flux.maneuvers_per_sat_yr.value is not None]
    wl = max(populated, key=lambda sc: sc.flux.maneuvers_per_sat_yr.value).shell.alt_mid_km if populated else None
    hz = max(out, key=lambda sc: sc.hazard_raw_kg_yr).shell.alt_mid_km if out and max(raw_h) > 0 else None
    return CapacityResult(out, pc_star, CONFIG.capacity.c_intra if c_intra is None else c_intra, wl, hz, (wl != hz) if (wl is not None and hz is not None) else None,
                          sorted(cals), notes=[f"q fallback: {q_note} = {q_fb:.2e}"])
