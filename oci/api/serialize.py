"""Wire format (SPEC §12.1): Traced objects keep their five fields, datetimes are ISO-8601 with
Z, numpy is unwrapped, dataclasses become dicts. Nothing destined for display is a bare float
unless it is a count, id, coordinate or config value — the test suite walks every response."""
from __future__ import annotations

import dataclasses
import hashlib
import math
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import numpy as np

from oci.labels import Traced

_SKIP_TYPES = ("Graph",)                      # networkx graphs are exposed through /graph, not dumped


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# §10.14/§13.8: the provenance panel keys on a trace_id. `Traced` itself carries no id (it is a
# value object shared across responses), so the id is derived from the value's own identity —
# function + unit + value — and registered here as each response is serialised. Deterministic,
# so the same number always opens the same panel.
_PROVENANCE: dict[str, dict] = {}
_PROVENANCE_MAX = 50_000


def provenance_get(trace_id: str) -> dict | None:
    return _PROVENANCE.get(trace_id)


def traced_wire(t: Traced) -> dict:
    v = t.value
    if isinstance(v, float) and not math.isfinite(v):
        v = None
    d = {"value": v, "unit": t.unit, "label": t.label, "function": t.function,
         "assumptions": wire(t.assumptions) if t.assumptions else {}, "na_reason": t.na_reason}
    d["trace_id"] = "prov_" + hashlib.sha1(f"{t.function}|{t.unit}|{v}".encode()).hexdigest()[:12]
    if len(_PROVENANCE) < _PROVENANCE_MAX:
        _PROVENANCE.setdefault(d["trace_id"], d)
    return d


def wire(x: Any, depth: int = 0) -> Any:
    if depth > 12:
        return str(x)
    if x is None or isinstance(x, (bool, int, str)):
        return x
    if isinstance(x, float):
        return None if not math.isfinite(x) else x
    if isinstance(x, Traced):
        return traced_wire(x)
    if isinstance(x, datetime):
        return iso(x)
    if isinstance(x, Enum):
        return x.value
    if isinstance(x, np.generic):
        return wire(x.item(), depth)
    if isinstance(x, np.ndarray):
        return [wire(v, depth + 1) for v in x.tolist()]
    if isinstance(x, dict):
        return {str(k): wire(v, depth + 1) for k, v in x.items()}
    if isinstance(x, (list, tuple, set, frozenset)):
        return [wire(v, depth + 1) for v in x]
    if type(x).__name__ in _SKIP_TYPES:
        return None
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        out = {}
        for f in dataclasses.fields(x):
            v = getattr(x, f.name)
            if type(v).__name__ in _SKIP_TYPES:
                continue
            out[f.name] = wire(v, depth + 1)
        return out
    if hasattr(x, "__dict__"):
        return {k: wire(v, depth + 1) for k, v in vars(x).items() if not k.startswith("_")}
    return str(x)


def object_summary(o) -> dict:
    orb = o.orbit
    return {"norad_id": o.norad_id, "object_name": o.object_name, "object_type": o.object_type, "operator": o.operator,
            "country": o.country, "launch_date": o.launch_date, "is_active": o.is_active, "is_maneuverable": o.is_maneuverable,
            "rcs_size": o.rcs_size, "source": o.source, "stale": o.stale, "covariance_source": o.covariance_source,
            "mean_alt_km": round(orb.mean_alt_km, 1), "perigee_alt_km": round(orb.perigee_alt_km, 1), "apogee_alt_km": round(orb.apogee_alt_km, 1),
            "inclination_deg": round(o.elements.inclination_deg, 3), "period_min": round(orb.period_min, 2),
            "shell_id": o.shell_id if hasattr(o, "shell_id") else None,
            "mass_kg_est": {"value": o.mass_kg_est, "unit": "kg", "label": "MODELLED", "function": "data.mass_model@0.1.0",
                            "assumptions": {"low": o.mass_kg_low, "high": o.mass_kg_high, "from": "RCS class"}, "na_reason": None},
            "sigma_rtn_m": list(o.sigma_rtn_m) if o.sigma_rtn_m else None, "epoch": iso(o.elements.epoch)}


def conjunction_wire(c, objects: dict | None = None) -> dict:
    d = {"conj_id": c.conj_id, "primary_id": c.primary_id, "secondary_id": c.secondary_id, "tca": iso(c.tca),
         "miss_distance_m": traced_wire(c.miss_distance_m), "rel_speed_mps": traced_wire(c.rel_speed_mps),
         "pc": traced_wire(c.pc), "pc_max": traced_wire(c.pc_max), "pc_method": c.pc_method, "covariance_source": c.covariance_source,
         "sigma_rtn_combined_m": list(c.sigma_rtn_combined_m) if c.sigma_rtn_combined_m else None,
         "mahalanobis": c.mahalanobis, "dilution": c.dilution, "pair_class": wire(c.pair_class), "intra_constellation": c.intra_constellation,
         "screening_run_id": c.screening_run_id}
    if objects:
        for k in ("primary", "secondary"):
            o = objects.get(d[f"{k}_id"])
            d[f"{k}_name"] = o.object_name if o else None
            d[f"{k}_operator"] = o.operator if o else None
    return d


def ledger_entry_wire(e, full: bool = False) -> dict:
    """One §12.3 ledger row. `full=True` adds the bearer breakdown (the object card, S2)."""
    d = {"norad_id": e.norad_id, "object_name": e.object_name, "object_type": e.object_type,
         "operator": e.operator, "is_active": e.is_active, "is_maneuverable": e.is_maneuverable,
         "mean_alt_km": round(e.mean_alt_km, 1), "shell_id": e.shell_id,
         "window_days": e.window_days, "pc_threshold": e.pc_threshold,
         "conjunctions_generated": traced_wire(e.conjunctions_generated),
         "maneuvers_forced": traced_wire(e.maneuvers_forced),
         "maneuvers_forced_soft": traced_wire(e.maneuvers_forced_soft),
         "dv_imposed_mps": traced_wire(e.dv_imposed_mps),
         "mission_days_imposed": traced_wire(e.mission_days_imposed),
         "operators_affected": traced_wire(e.operators_affected),
         "top_bearer": e.top_bearer, "bearer_gini": traced_wire(e.bearer_gini),
         "maneuvers_performed": traced_wire(e.maneuvers_performed),
         "dv_spent_mps": traced_wire(e.dv_spent_mps),
         "cab": traced_wire(e.cab), "cab_normalised": traced_wire(e.cab_normalised),
         "decay_lifetime_yr_est": traced_wire(e.decay_lifetime_yr_est),
         "projected_lifetime_dv": traced_wire(e.projected_lifetime_dv),
         "implied_fee_usd_yr": traced_wire(e.implied_fee_usd_yr),
         "n_dv_unresolved": e.n_dv_unresolved,
         "rank_by_dv_imposed": e.rank_by_dv_imposed,
         "on_published_top50": getattr(e, "on_published_top50", False)}
    if full:
        d["bearers"] = [wire(b) for b in e.bearers]
    return d


def strategy_wire(s) -> dict:
    """A strategy without its simulator payload — `SimResult.objects_after` is the whole
    catalogue and has no business on the wire."""
    a = s.action
    burn = None
    if a.burn is not None:
        burn = {"target_id": a.burn.target_id, "dv_vector_mps": [float(x) for x in a.burn.dv_rtn_mps],
                "t_burn": iso(a.burn.t_burn)}
    d = {"strategy_id": s.strategy_id, "kind": a.kind, "proposed_by": s.proposed_by,
         "params": {"target_id": a.target_id, "wait_min": a.wait_min, "burn": burn,
                    "then": (a.then.kind if a.then else None),
                    "expected_dv_mps": a.expected_dv_mps, "delay_risk": a.delay_risk},
         "label": describe_action(a),
         "pc_after": traced_wire(s.pc_after) if s.pc_after else None,
         "future_conjunctions": traced_wire(s.future_conjunctions) if s.future_conjunctions else None,
         "dv_mps": traced_wire(s.dv_mps) if s.dv_mps else None,
         "mission_impact": traced_wire(s.mission_impact) if s.mission_impact else None,
         "systemic_cost": traced_wire(s.systemic_cost) if s.systemic_cost else None,
         "expected_cost": traced_wire(s.expected_cost) if s.expected_cost else None,
         "p95_cost": traced_wire(s.p95_cost) if getattr(s, "p95_cost", None) else None,
         "max_regret": traced_wire(s.max_regret) if s.max_regret else None,
         "mc_safe_fraction": traced_wire(s.mc_safe_fraction) if s.mc_safe_fraction else None,
         "validator_verdict": s.validator_verdict, "validator_reason": s.validator_reason}
    if s.sim is not None:
        d["new_conj_ids"] = list(s.sim.new_conj_ids)
        d["removed_conj_ids"] = list(s.sim.removed_conj_ids)
    return d


def describe_action(a) -> str:
    if a.kind == "HOLD":
        return "HOLD"
    if a.kind == "OBSERVE":
        return "OBSERVE (request tracking)"
    if a.kind == "WAIT":
        then = f", then clear {a.then.target_id}" if a.then and a.then.target_id else ""
        return f"WAIT {a.wait_min:.0f} min{then}"
    if a.kind == "COORDINATE":
        return f"COORDINATE — joint burn on {a.target_id} and partner"
    if a.burn is not None:
        v = a.burn.dv_rtn_mps
        return (f"MANEUVER {a.burn.target_id} Δv=({v[0]:+.3f},{v[1]:+.3f},{v[2]:+.3f}) m/s RTN "
                f"at {a.burn.t_burn:%Y-%m-%dT%H:%MZ}")
    return a.kind


def verdict_wire(v) -> dict:
    return {"verdict": v.status, "reason": v.reason, "violated": list(v.violated),
            "checks": [{"id": c.id, "name": c.name, "passed": c.passed, "detail": c.detail} for c in v.checks]}
