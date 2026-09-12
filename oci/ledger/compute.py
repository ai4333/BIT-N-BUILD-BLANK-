"""M5 — THE EXTERNALITY LEDGER (SPEC §10.5, §11.7). The project's novel artifact.

For every object: what it imposes on other operators (manoeuvres forced, Δv extracted,
mission-days consumed, operators affected, concentration), what it bears itself, its net
position, a lifetime projection and an INDICATIVE fee. Every figure carries the declared Pc
threshold. Attribution starts with R1 (dead → active), where causation is unambiguous.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Sequence

import numpy as np

from oci.config import CONFIG, SECONDS_PER_DAY
from oci.data.objects import SpaceObject
from oci.labels import Traced, na, traced
from oci.ledger.attribution import attribute
from oci.physics.decay import decay_lifetime_years
from oci.physics.maneuver import DvToClear, dv_to_clear
from oci.physics.screen import Conjunction

V = "0.1.0"


@dataclass
class BurdenFlow:
    flow_id: str
    imposer_id: int
    bearer_id: int
    bearer_operator: str
    conj_id: str
    n_conjunctions: int
    n_maneuvers: float
    n_maneuvers_soft: float
    dv_mps: Optional[float]
    dv_na_reason: Optional[str]
    mission_days: Optional[float]
    attribution_rule: str
    contested: bool
    pc: Optional[float]
    pc_threshold: float
    forced_by: str                  # "pc" | "geometric_surrogate"


@dataclass
class LedgerEntry:
    norad_id: int
    object_name: str
    object_type: str
    operator: str
    is_active: bool
    is_maneuverable: bool
    mean_alt_km: float
    shell_id: int
    window_days: float
    pc_threshold: float
    conjunctions_generated: Traced
    maneuvers_forced: Traced
    maneuvers_forced_soft: Traced
    dv_imposed_mps: Traced
    mission_days_imposed: Traced
    operators_affected: Traced
    top_bearer: Optional[str]
    bearer_gini: Traced
    maneuvers_performed: Traced
    dv_spent_mps: Traced
    cab: Traced
    cab_normalised: Traced
    decay_lifetime_yr_est: Traced
    projected_lifetime_dv: Traced
    implied_fee_usd_yr: Traced
    n_dv_unresolved: int
    bearers: list[BurdenFlow] = field(default_factory=list)
    rank_by_dv_imposed: Optional[int] = None
    assumptions: dict = field(default_factory=dict)

    @property
    def field_name_maneuvers(self) -> str:
        return f"maneuvers_forced_at_Pc_{self.pc_threshold:g}"


@dataclass
class LedgerResult:
    entries: list[LedgerEntry]
    flows: list[BurdenFlow]
    pc_threshold: float
    window_days: float
    share_of_dv_from_dead: Traced
    n_conjunctions_used: int
    n_conjunctions_intra_excluded: int
    computed_at: datetime


def sk_budget_mps_per_day(alt_km: float) -> float:
    for lo, hi, b in CONFIG.mission.sk_budget_mps_per_day:
        if lo <= alt_km < hi:
            return b
    return CONFIG.mission.sk_budget_mps_per_day[-1][2]


def gini(values: Sequence[float]) -> Optional[float]:
    x = np.sort(np.asarray([v for v in values if v is not None and v > 0], dtype=float))
    if x.size == 0 or x.sum() == 0:
        return None
    n = x.size
    return float((2.0 * np.sum((np.arange(1, n + 1)) * x) / (n * x.sum())) - (n + 1) / n)


def forced(c: Conjunction, pc_threshold: float) -> tuple[float, float, str]:
    """§10.5 step 2 — hard count, soft count, and which rule decided."""
    th = CONFIG.thresholds
    if c.pc.value is not None:
        hard = 1.0 if c.pc.value >= pc_threshold else 0.0
        z = (math.log10(max(c.pc.value, 1e-300)) - math.log10(pc_threshold)) / th.soft_count_scale
        soft = 1.0 / (1.0 + math.exp(-z))
        return hard, soft, "pc"
    hard = 1.0 if (c.miss_m <= th.surrogate_d_trigger_m and float(c.rel_speed_mps.value) >= th.surrogate_v_min_mps) else 0.0
    return hard, hard, "geometric_surrogate"


def compute_ledger(conjs: Sequence[Conjunction], objects: dict[int, SpaceObject],
                   window_days: float, pc_threshold: float | None = None,
                   rules: tuple[str, ...] | None = None, dv_cache: Optional[dict] = None) -> LedgerResult:
    pc_star = pc_threshold if pc_threshold is not None else CONFIG.thresholds.declared_pc_threshold
    rules = rules or CONFIG.attribution.rules
    dv_cache = dv_cache if dv_cache is not None else {}
    flows: list[BurdenFlow] = []
    n_intra = 0
    for c in conjs:
        if c.intra_constellation and CONFIG.attribution.exclude_intra_constellation:
            n_intra += 1
            continue
        for att in attribute(c, objects, rules):
            hard, soft, by = forced(c, pc_star)
            dv: Optional[float] = None
            dv_reason: Optional[str] = None
            days: Optional[float] = None
            if not att.bearer.is_maneuverable:
                hard, soft, dv, days = 0.0, 0.0, 0.0, 0.0
                dv_reason = None
            elif hard > 0:
                key = (att.bearer.norad_id, att.imposer.norad_id, c.conj_id, pc_star)
                res: DvToClear = dv_cache.get(key) or dv_to_clear(att.bearer, att.imposer, c.tca, pc_star)
                dv_cache[key] = res
                if res.dv_mps.value is None:
                    dv_reason = res.dv_mps.na_reason
                else:
                    dv = res.dv_mps.value * att.share
                    days = dv / sk_budget_mps_per_day(att.bearer.orbit.mean_alt_km)
            else:
                dv, days = 0.0, 0.0
            flows.append(BurdenFlow(
                flow_id=f"fl_{c.conj_id}_{att.imposer.norad_id}_{att.bearer.norad_id}",
                imposer_id=att.imposer.norad_id, bearer_id=att.bearer.norad_id,
                bearer_operator=att.bearer.operator, conj_id=c.conj_id, n_conjunctions=1,
                n_maneuvers=hard * att.share, n_maneuvers_soft=soft * att.share,
                dv_mps=dv, dv_na_reason=dv_reason, mission_days=days,
                attribution_rule=att.rule, contested=att.contested, pc=c.pc.value,
                pc_threshold=pc_star, forced_by=by,
            ))

    # conjunctions generated per object (excluding intra-constellation)
    conj_count: dict[int, int] = {}
    for c in conjs:
        if c.intra_constellation and CONFIG.attribution.exclude_intra_constellation:
            continue
        for nid in (c.primary_id, c.secondary_id):
            conj_count[nid] = conj_count.get(nid, 0) + 1

    # per-object aggregates: imposed (as imposer) and borne (as bearer)
    imposed: dict[int, list[BurdenFlow]] = {}
    borne: dict[int, list[BurdenFlow]] = {}
    for f in flows:
        imposed.setdefault(f.imposer_id, []).append(f)
        borne.setdefault(f.bearer_id, []).append(f)

    entries: list[LedgerEntry] = []
    fn = f"ledger.compute@{V}"
    base_assumptions = {"pc_threshold": pc_star, "threshold_source": "IADC" if pc_star == 1e-4 else "declared",
                        "attribution_rules": list(rules), "intra_constellation_excluded": CONFIG.attribution.exclude_intra_constellation,
                        "window_days": window_days}
    for nid, obj in objects.items():
        fl = imposed.get(nid, [])
        bf = borne.get(nid, [])
        if not fl and not bf and nid not in conj_count:
            continue
        n_mnvr = sum(f.n_maneuvers for f in fl)
        n_soft = sum(f.n_maneuvers_soft for f in fl)
        resolved = [f for f in fl if f.dv_mps is not None]
        unresolved = [f for f in fl if f.dv_mps is None and f.n_maneuvers > 0]
        dv_sum = sum(f.dv_mps for f in resolved)
        days_sum = sum(f.mission_days for f in resolved if f.mission_days is not None)
        ops = {f.bearer_operator for f in fl if f.n_maneuvers > 0}
        dv_by_op: dict[str, float] = {}
        for f in resolved:
            dv_by_op[f.bearer_operator] = dv_by_op.get(f.bearer_operator, 0.0) + (f.dv_mps or 0.0)
        top = max(dv_by_op, key=dv_by_op.get) if dv_by_op else None
        g = gini(list(dv_by_op.values()))
        # borne by self
        if not obj.is_maneuverable:
            m_perf = traced(0.0, "count", "OBSERVED", f"ledger.borne@{V}", reason="object is non-maneuverable")
            dv_spent = traced(0.0, "m/s", "OBSERVED", f"ledger.borne@{V}", reason="object is non-maneuverable")
        else:
            m_perf = traced(sum(f.n_maneuvers for f in bf), "count", "MODELLED", f"ledger.borne@{V}", **base_assumptions)
            dv_spent = traced(sum(f.dv_mps or 0.0 for f in bf), "m/s", "MODELLED", f"ledger.borne@{V}", **base_assumptions)
        cab = dv_sum                                    # α = (0,1,0): CAB reported in m/s (§11.7.1)
        per_year = window_days / 365.25
        cab_norm = cab / per_year if per_year > 0 else 0.0
        life = decay_lifetime_years(obj.orbit.mean_alt_km, obj.area_to_mass_m2_kg)
        horizon = min(life.value or 0.0, CONFIG.attribution.horizon_cap_yr)
        proj = cab_norm * horizon
        entries.append(LedgerEntry(
            norad_id=nid, object_name=obj.object_name, object_type=obj.object_type, operator=obj.operator,
            is_active=obj.is_active, is_maneuverable=obj.is_maneuverable, mean_alt_km=obj.orbit.mean_alt_km,
            shell_id=obj.shell_id, window_days=window_days, pc_threshold=pc_star,
            conjunctions_generated=traced(conj_count.get(nid, 0), "count", "COMPUTED", f"ledger.count_conj@{V}"),
            maneuvers_forced=traced(n_mnvr, "count", "MODELLED", f"ledger.maneuvers_forced@{V}", **base_assumptions),
            maneuvers_forced_soft=traced(n_soft, "count", "MODELLED", f"ledger.maneuvers_forced_soft@{V}", **base_assumptions),
            dv_imposed_mps=(traced(dv_sum, "m/s", "MODELLED", f"ledger.dv_imposed@{V}", n_unresolved=len(unresolved), **base_assumptions)
                            if resolved or not unresolved else
                            na("m/s", "MODELLED", f"ledger.dv_imposed@{V}", "; ".join({f.dv_na_reason or "" for f in unresolved}), **base_assumptions)),
            mission_days_imposed=traced(days_sum, "days", "MODELLED", f"ledger.mission_days@{V}", sk_budget="config/mission_model", **base_assumptions),
            operators_affected=traced(len(ops), "count", "COMPUTED", f"ledger.operators@{V}"),
            top_bearer=top,
            bearer_gini=(traced(g, "ratio", "COMPUTED", f"ledger.gini@{V}") if g is not None
                         else na("ratio", "COMPUTED", f"ledger.gini@{V}", "fewer than one bearer with Δv > 0")),
            maneuvers_performed=m_perf, dv_spent_mps=dv_spent,
            cab=traced(cab, "m/s", "MODELLED", f"ledger.cab@{V}", alpha=(0, 1, 0), **base_assumptions),
            cab_normalised=traced(cab_norm, "m/s per yr", "MODELLED", f"ledger.cab_norm@{V}", **base_assumptions),
            decay_lifetime_yr_est=life,
            projected_lifetime_dv=traced(proj, "m/s", "MODELLED", f"ledger.project@{V}", decay_model="exponential_atmosphere",
                                         burden_decay="constant over horizon", horizon_yr=horizon, **base_assumptions),
            implied_fee_usd_yr=na("USD/yr", "INDICATIVE", f"ledger.fee@{V}", "computed after shell reference is known"),
            n_dv_unresolved=len(unresolved), bearers=sorted(fl, key=lambda f: -(f.dv_mps or 0.0)),
            assumptions=base_assumptions,
        ))

    # Indicative fee (§11.9.2). Reference = mean Δv BORNE per active satellite-year in the same
    # shell (the average bill an active satellite pays); the spec's literal "CAB per active
    # satellite" is identically zero under R1 because active objects never impose. Fallback to
    # the global mean when the shell has no active bearers.
    per_year = window_days / 365.25
    borne_by_shell: dict[int, list[float]] = {}
    for e in entries:
        if e.is_active and e.is_maneuverable:
            borne_by_shell.setdefault(e.shell_id, []).append((e.dv_spent_mps.value or 0.0) / per_year)
    global_ref = float(np.mean([v for vs in borne_by_shell.values() for v in vs])) if borne_by_shell else 0.0
    for e in entries:
        vals = borne_by_shell.get(e.shell_id)
        ref, ref_scope = (float(np.mean(vals)), "shell") if vals else (global_ref, "global")
        if ref > 0 and e.cab_normalised.value:
            e.implied_fee_usd_yr = traced(e.cab_normalised.value / ref * CONFIG.fee.fee_reference_usd_per_sat_yr,
                                          "USD/yr", "INDICATIVE", f"ledger.fee@{V}",
                                          calibration=CONFIG.fee.calibration, caveat=CONFIG.fee.caveat,
                                          reference_borne_dv_per_sat_yr=ref, reference_scope=ref_scope)
        else:
            e.implied_fee_usd_yr = na("USD/yr", "INDICATIVE", f"ledger.fee@{V}",
                                      "no active bearer reference available" if ref <= 0 else "zero burden imposed",
                                      caveat=CONFIG.fee.caveat)

    entries.sort(key=lambda e: -(e.dv_imposed_mps.value or 0.0))
    for i, e in enumerate(entries, 1):
        e.rank_by_dv_imposed = i
    total_dv = sum(e.dv_imposed_mps.value or 0.0 for e in entries)
    dead_dv = sum(e.dv_imposed_mps.value or 0.0 for e in entries if not e.is_active)
    share = (traced(dead_dv / total_dv, "ratio", "MODELLED", f"ledger.share_dead@{V}", **base_assumptions)
             if total_dv > 0 else na("ratio", "MODELLED", f"ledger.share_dead@{V}", "no Δv imposed in window"))
    return LedgerResult(entries=entries, flows=flows, pc_threshold=pc_star, window_days=window_days,
                        share_of_dv_from_dead=share, n_conjunctions_used=len(conjs) - n_intra,
                        n_conjunctions_intra_excluded=n_intra, computed_at=datetime.now(timezone.utc))
