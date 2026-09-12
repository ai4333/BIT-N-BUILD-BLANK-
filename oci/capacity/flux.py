"""M10 part 2 — kinetic-gas / spatial-density flux model (SPEC §11.13) and its calibration
against the pairwise screener (M3) in the same shell.

    R_s  = D_s · σ_c · v_rel_mean_s          conjunctions per object per second
    C_s  = R_s · seconds_per_year            conjunctions per satellite-year
    M_s  = C_s · q_s(Pc*)                    manoeuvres per satellite-year
    q_s  = P(Pc > Pc* | conjunction in s)    CALIBRATED from M3 where screened, else carried
                                             from the nearest screened shell and labelled MODELLED

The two engines cross-check each other: `calibration_factor` = pairwise C_s / flux C_s. It is
reported, never used to silently tune either side (§10.10 failure modes).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from oci.capacity.shells import Shell, mean_relative_speed_kms
from oci.config import CONFIG, SECONDS_PER_YEAR
from oci.labels import Traced, na, traced
from oci.physics.screen import Conjunction

_FN = "capacity.flux@0.1.0"


@dataclass
class Calibration:
    """What the pairwise screener saw inside one shell over its window."""
    shell_id: str
    n_objects_screened: int
    window_days: float
    n_conjunctions: int
    n_above_threshold: int
    pc_threshold: float

    @property
    def q(self) -> Optional[float]:
        if not self.n_conjunctions or self.n_above_threshold < 0:
            return None
        return self.n_above_threshold / self.n_conjunctions

    member_conjunctions: int = 0        # Σ over members of the conjunctions they were in

    @property
    def conjunctions_per_object_year(self) -> Optional[float]:
        if not self.n_objects_screened or not self.window_days:
            return None
        return self.member_conjunctions / self.n_objects_screened / self.window_days * 365.25


@dataclass
class ShellFlux:
    shell_id: str
    spatial_density_per_km3: Traced
    v_rel_mean_kms: Traced
    cross_section_km2: Traced
    conjunctions_per_sat_yr: Traced
    q_above_threshold: Traced
    maneuvers_per_sat_yr: Traced
    calibration_factor: Traced          # pairwise / flux conjunction rate, where screened
    pc_threshold: float


def calibrate(shell: Shell, conjunctions: Sequence[Conjunction], objects_by_id: dict, window_days: float,
              pc_threshold: float) -> Calibration:
    """What an object in this shell experienced in the screening run: every conjunction with at
    least one member in the shell counts (cross-shell pairs included — the other object is what
    the member met), so the per-object rate is Σ member conjunctions / members / window."""
    members = set(shell.members) & set(objects_by_id)
    n = n_above = 0
    per_member = 0
    for c in conjunctions:
        if c.intra_constellation:
            continue
        hits = (c.primary_id in members) + (c.secondary_id in members)
        if hits:
            n += 1
            per_member += hits
            if c.pc.value is not None and c.pc.value >= pc_threshold:
                n_above += 1
    cal = Calibration(shell.shell_id, len(members), window_days, n, n_above, pc_threshold)
    cal.member_conjunctions = per_member
    return cal


def cross_section_km2() -> float:
    d = CONFIG.screening.screening_volume_m / 1000.0
    return math.pi * d * d


def shell_flux(shell: Shell, pc_threshold: float, calibration: Optional[Calibration] = None,
               q_fallback: Optional[float] = None, q_fallback_note: str = "", seed: int = 0,
               c_intra: Optional[float] = None) -> ShellFlux:
    D = shell.spatial_density_per_km3
    v = mean_relative_speed_kms(shell.inclinations_deg, shell.alt_mid_km, seed=seed)
    sig = cross_section_km2()
    # existing coordinated constellations: their members meet same-constellation traffic with the
    # coordination factor, everything else at full weight (§10.10 "intra-constellation handling")
    c_intra = CONFIG.capacity.c_intra if c_intra is None else c_intra
    D_int = shell.coordinated_internal_density_per_km3
    D_ext = max(D - D_int, 0.0)
    R = (D_ext + c_intra * D_int) * sig * v           # per second (km⁻³ · km² · km/s)
    C = R * SECONDS_PER_YEAR
    C_uncoordinated = D * sig * v * SECONDS_PER_YEAR
    if calibration is not None and calibration.q is not None:
        q_val, q_label, q_ass = calibration.q, "COMPUTED", {"calibrated_from": "M3 pairwise screening in this shell",
                                                            "n_conjunctions": calibration.n_conjunctions,
                                                            "n_above_threshold": calibration.n_above_threshold}
    elif q_fallback is not None:
        q_val, q_label, q_ass = q_fallback, "MODELLED", {"carried_from": q_fallback_note or "nearest screened shell"}
    else:
        q_val, q_label, q_ass = None, "MODELLED", {}
    q = traced(q_val, "probability", q_label, _FN, pc_threshold=pc_threshold, **q_ass) if q_val is not None \
        else na("probability", "MODELLED", _FN, "no screening run covers this shell and no fallback q was supplied")
    M = traced(C * q_val, "maneuvers/sat-yr", "MODELLED", _FN, pc_threshold=pc_threshold,
               q_source=q_label) if q_val is not None else na("maneuvers/sat-yr", "MODELLED", _FN, "q unavailable")
    if calibration is not None and calibration.conjunctions_per_object_year is not None and C > 0:
        cf = traced(calibration.conjunctions_per_object_year / C, "ratio", "COMPUTED", _FN,
                    pairwise_conj_per_obj_yr=round(calibration.conjunctions_per_object_year, 2), flux_conj_per_obj_yr=round(C, 2),
                    meaning="pairwise M3 rate ÷ flux-model rate in this shell; reported, not used to tune")
    else:
        cf = na("ratio", "MODELLED", _FN, "shell not covered by a pairwise screening run")
    return ShellFlux(
        shell_id=shell.shell_id,
        spatial_density_per_km3=traced(D, "objects/km³", "COMPUTED", _FN, n_objects=shell.n_objects, volume_km3=round(shell.volume_km3),
                                       catalogue="public CelesTrak groups (active + four debris groups); Space-Track pending"),
        v_rel_mean_kms=traced(v, "km/s", "COMPUTED", _FN, method="E[2 v_orb sin(θ/2)] over empirical inclinations, uniform ΔΩ"),
        cross_section_km2=traced(sig, "km²", "MODELLED", _FN, screening_diameter_km=CONFIG.screening.screening_volume_m / 1000.0),
        conjunctions_per_sat_yr=traced(C, "conjunctions/sat-yr", "MODELLED", _FN, model="kinetic gas §11.13", c_intra=c_intra,
                                       coordinated_share=round(D_int / D, 3) if D else 0.0, uncoordinated_value=round(C_uncoordinated, 1),
                                       constellations={k: v for k, v in sorted(shell.constellation_counts.items(), key=lambda kv: -kv[1])[:3]}),
        q_above_threshold=q, maneuvers_per_sat_yr=M, calibration_factor=cf, pc_threshold=pc_threshold,
    )


def deployment_flux(shell: Shell, n_new: int, inclination_deg: float, c_intra: float, q: float,
                    pc_threshold: float, seed: int = 0) -> dict[str, Traced]:
    """Conjunction and manoeuvre rates for ONE new satellite of a coordinated constellation of
    `n_new` at `inclination_deg` added to `shell`, split into the external component (against
    incumbents, full weight) and the internal component (scaled by c_intra), plus the extra
    conjunction rate each incumbent sees from the newcomers."""
    sig = cross_section_km2()
    V = shell.volume_km3
    D_ext = shell.n_objects / V
    D_int = n_new / V
    v_ext = mean_relative_speed_kms(shell.inclinations_deg, shell.alt_mid_km, seed=seed, second_population_deg=[inclination_deg]) \
        if shell.inclinations_deg else 0.0
    v_int = mean_relative_speed_kms([inclination_deg, inclination_deg], shell.alt_mid_km, seed=seed)
    C_ext = D_ext * sig * v_ext * SECONDS_PER_YEAR
    C_int_raw = D_int * sig * v_int * SECONDS_PER_YEAR
    C_int = C_int_raw * c_intra
    C_new = C_ext + C_int
    C_on_incumbent = D_int * sig * v_ext * SECONDS_PER_YEAR      # each incumbent's extra rate from the newcomers
    return {
        "conjunctions_per_sat_yr_external": traced(C_ext, "conjunctions/sat-yr", "MODELLED", _FN, against="incumbents"),
        "conjunctions_per_sat_yr_internal": traced(C_int, "conjunctions/sat-yr", "MODELLED", _FN, c_intra=c_intra, uncoordinated_value=round(C_int_raw, 2)),
        "conjunctions_per_sat_yr": traced(C_new, "conjunctions/sat-yr", "MODELLED", _FN),
        "maneuvers_per_sat_yr": traced(C_new * q, "maneuvers/sat-yr", "MODELLED", _FN, pc_threshold=pc_threshold, q=q),
        "extra_conjunctions_per_incumbent_yr": traced(C_on_incumbent, "conjunctions/sat-yr", "MODELLED", _FN),
        "extra_maneuvers_per_incumbent_yr": traced(C_on_incumbent * q, "maneuvers/sat-yr", "MODELLED", _FN, pc_threshold=pc_threshold),
        "v_rel_external_kms": traced(v_ext, "km/s", "COMPUTED", _FN), "v_rel_internal_kms": traced(v_int, "km/s", "COMPUTED", _FN),
    }
