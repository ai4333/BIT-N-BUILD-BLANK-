"""Terminal / Markdown rendering of the capacity result and the deployment table (S5, S6)."""
from __future__ import annotations

from datetime import datetime, timezone

from oci.capacity.deployment import DeploymentResult
from oci.capacity.ocs import CapacityResult
from oci.config import CONFIG


def _f(t, fmt=".2f"):
    return format(t.value, fmt) if t is not None and t.value is not None else "N/A"


def render_shells(cap: CapacityResult, min_objects: int = 1) -> str:
    out = [f"SHELL MAP  Pc* {cap.pc_threshold:g} · c_intra {cap.c_intra} · calibrated shells {', '.join(cap.calibration_shells) or 'none'}",
           f"  {cap.notes[0] if cap.notes else ''}",
           f"  {'shell km':>10} {'N':>6} {'active':>6} {'dead':>6} {'D obj/km³':>10} {'v_rel':>6} {'conj/yr':>8} {'q':>8} {'M/yr':>6} {'OCS':>5} {'hazard':>6} {'life yr':>7} {'κ':>6} {'regime':>13} {'calib':>6}"]
    for s in cap.shells:
        if s.shell.n_objects < min_objects:
            continue
        f = s.flux
        q = f"{f.q_above_threshold.value:.1e}{'*' if f.q_above_threshold.label == 'MODELLED' else ''}" if f.q_above_threshold.value is not None else "N/A"
        kap = _f(s.kappa.kappa) if s.kappa else "—"
        out.append(f"  {s.shell.alt_low_km:>5.0f}-{s.shell.alt_high_km:<4.0f} {s.shell.n_objects:>6} {s.shell.n_active:>6} {s.shell.n_dead:>6} "
                   f"{f.spatial_density_per_km3.value:>10.2e} {_f(f.v_rel_mean_kms, '.1f'):>6} {_f(f.conjunctions_per_sat_yr, '.1f'):>8} {q:>8} "
                   f"{_f(f.maneuvers_per_sat_yr):>6} {_f(s.ocs, '.1f'):>5} {_f(s.hazard_index):>6} {_f(s.decay_lifetime_yr, '.1f'):>7} {kap:>6} "
                   f"{(s.kappa.regime if s.kappa else '—'):>13} {_f(f.calibration_factor):>6}")
    out.append(f"  * q carried from the pooled screening calibration (MODELLED); unstarred q is calibrated in that shell (COMPUTED)")
    out.append(f"  TWO PEAKS: workload peak {cap.workload_peak_alt_km} km · hazard peak {cap.hazard_peak_alt_km} km · "
               f"{'DIFFER' if cap.peaks_differ else 'coincide'} (OCS anchored to M_viability = {CONFIG.capacity.m_viability_per_sat_yr:g}/sat-yr: {CONFIG.capacity.m_viability_source})")
    return "\n".join(out)


def render_deployment(d: DeploymentResult) -> str:
    r = d.request
    out = [f"DEPLOYMENT  {r.n_satellites} satellites · {r.inclination_deg:g}° · target {r.target_alt_km:g} km · c_intra {d.c_intra_used} · Pc* as above",
           f"  {'alt':>6} {'OCS before':>10} {'OCS after':>9} {'M/sat/yr':>9} {'imposed m/s/yr':>14} {'hazard →':>14} {'decay yr':>8} {'WORKLOAD':>8} {'HAZARD':>6}"]
    for a in sorted([d.baseline] + d.alternatives, key=lambda x: x.alt_km):
        tag = " ◀" if a.alt_km == r.target_alt_km else ""
        out.append(f"  {a.alt_km:>5.0f}{'*' if a.alt_km == r.target_alt_km else ' '} {_f(a.ocs_before, '.1f'):>10} {_f(a.ocs, '.1f'):>9} {_f(a.maneuver_burden_per_sat_yr):>9} "
                   f"{_f(a.burden_imposed_on_incumbents_mps_yr, '.0f'):>14} {_f(a.hazard_index_before):>6} → {_f(a.hazard_index):>5} {_f(a.decay_lifetime_yr, '.1f'):>8} "
                   f"{a.workload_rank:>8} {a.hazard_rank:>6}{tag}")
    flag = "⚠  WORKLOAD-OPTIMAL and HAZARD-OPTIMAL altitudes DIFFER." if d.optima_disagree else "Both optima coincide on this range."
    out += [f"  {flag}", f"  workload-optimal {d.workload_optimal_alt_km:g} km · hazard-optimal {d.hazard_optimal_alt_km:g} km · "
            f"balanced under stated weights {CONFIG.capacity.balanced_weights} → {d.balanced_alt_km:g} km",
            f"  {d.explanation}", f"  {d.honest_note}"]
    u = d.uncoordinated_comparison
    if u:
        out.append(f"  if the constellation were NOT coordinated (c_intra = 1.0): {_f(u['maneuver_burden_per_sat_yr'])} manoeuvres/sat-yr, OCS {_f(u['ocs'], '.1f')} "
                   f"vs {_f(d.baseline.maneuver_burden_per_sat_yr)} and {_f(d.baseline.ocs, '.1f')} coordinated")
    return "\n".join(out)


def write_doc(cap: CapacityResult, deployments: list[DeploymentResult], path: str = "docs/CAPACITY.md",
              catalogue_note: str = "") -> None:
    lines = ["# Capacity engine — measured output", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%MZ} by `python -m oci capacity`. {catalogue_note}", "",
             "Every figure is MODELLED (kinetic-gas flux, §11.13) except the spatial density, the mean relative speed, and the",
             "shells where `q` is calibrated from the pairwise screener (COMPUTED). The calibration factor column is the",
             "pairwise conjunction rate divided by the flux-model rate in the same shell — reported, never used to tune.", "",
             "```", render_shells(cap, min_objects=20), "```", ""]
    for d in deployments:
        lines += ["```", render_deployment(d), "```", ""]
    lines += ["## Reading it", "",
              "- OCS is anchored to the published viability threshold (10 manoeuvres/month = 120 per satellite-year); it is not a composite.",
              "- Workload follows traffic density; hazard follows inactive mass × decay lifetime. They peak at different altitudes",
              "  — the two-peaks structure of the literature (§2.6) reproduced from the public catalogue.",
              "- The catalogue is the public CelesTrak groups (active + four debris groups). Most tracked debris and rocket bodies",
              "  are absent until Space-Track is wired in, so absolute burdens are lower bounds; the shape is what is measured.",
              "- κ is estimated by simulation in the shells covered by a screening run only; elsewhere it is N/A with the reason.", ""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
