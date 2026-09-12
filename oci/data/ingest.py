"""M1 — Ingest & normalise (SPEC §10.1).

CelesTrak GP records + public SATCAT + operator map → normalised `SpaceObject`s with explicit
provenance and explicit MODELLED fields. Bad element sets are rejected and logged, never
coerced. Stale element sets (> 7 d) are flagged and excluded from live screening. Unmatched
operators become UNKNOWN-OPERATOR, never dropped.

Covariance: TLEs carry none. Until the Kelvins fit (M8 part A) is wired in, every real
object gets a class-based RTN σ labelled `assumed`, from config, shown in the assumptions
panel. Pc computed from it is MODELLED and the source is stated on every conjunction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from oci.config import CONFIG
from oci.data.celestrak import SatcatRow, fetch_gp_group, load_satcat
from oci.data.objects import Elements, SpaceObject, derive_orbit, mass_model
from oci.data.operators import match_operator

REQUIRED = ("NORAD_CAT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION",
            "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY")


class BadElementSet(ValueError):
    pass


@dataclass
class IngestReport:
    group: str
    source: str
    n_raw: int
    n_ingested: int
    n_rejected: int
    n_stale: int
    n_satcat_miss: int
    n_unknown_operator: int
    by_type: dict[str, int] = field(default_factory=dict)
    by_operator_top: list[tuple[str, int]] = field(default_factory=list)
    rejects: list[tuple[Optional[int], str]] = field(default_factory=list)
    cached_at: Optional[str] = None
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def parse_elements(rec: dict) -> Elements:
    for k in REQUIRED:
        if k not in rec or rec[k] in (None, ""):
            raise BadElementSet(f"missing {k}")
    try:
        epoch = datetime.fromisoformat(str(rec["EPOCH"]).replace("Z", "")).replace(tzinfo=timezone.utc)
        vals = [float(rec[k]) for k in ("MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY")]
    except (TypeError, ValueError) as e:
        raise BadElementSet(f"unparseable field: {e}")
    if not all(math.isfinite(v) for v in vals):
        raise BadElementSet("non-finite element")
    n, e, inc, raan, argp, ma = vals
    if n <= 0 or not (0 <= e < 1) or not (0 <= inc <= 180):
        raise BadElementSet(f"out of range: n={n} e={e} i={inc}")
    return Elements(epoch=epoch, mean_motion_rev_day=n, eccentricity=e, inclination_deg=inc, raan_deg=raan,
                    argp_deg=argp, mean_anomaly_deg=ma, bstar=float(rec.get("BSTAR") or 0.0),
                    mean_motion_dot=float(rec.get("MEAN_MOTION_DOT") or 0.0), mean_motion_ddot=float(rec.get("MEAN_MOTION_DDOT") or 0.0))


def infer_active(sat: Optional[SatcatRow], group: str) -> bool:
    """Payload, not decayed, and operationally active per SATCAT status (+ P B S X)."""
    if sat is None:
        return group == "active"
    if sat.decay_date:
        return False
    if sat.object_type != "PAYLOAD":
        return False
    return sat.ops_status in ("+", "P", "B", "S", "X") or (sat.ops_status == "" and group == "active")


def infer_maneuverable(active: bool, sat: Optional[SatcatRow], operator: str) -> bool:
    """Conservative (§10.1 step 7): active payload AND an operator known to manoeuvre.
    Unknown active payloads default to False — assume it cannot move."""
    if not active or (sat is not None and sat.object_type != "PAYLOAD"):
        return False
    return operator.split(":")[0] in CONFIG.ingest.maneuvering_operators


_FIT = None


def covariance_model():
    """The Kelvins-fitted covariance model if models/covariance_fit.json exists, else None."""
    global _FIT
    if _FIT is None:
        from oci.data.kelvins import load_models
        m = load_models()
        _FIT = m if m is not None else False
    return _FIT or None


def assumed_sigma(object_type: str, active: bool) -> tuple[float, float, float]:
    key = "PAYLOAD_ACTIVE" if (object_type == "PAYLOAD" and active) else object_type
    return CONFIG.ingest.assumed_sigma_rtn_m.get(key, CONFIG.ingest.assumed_sigma_rtn_m["DEFAULT"])


def object_sigma(object_type: str, active: bool, alt_km: float) -> tuple[tuple[float, float, float], str]:
    """Object-level σ (used by the simulator and VoI): Kelvins-fitted at τ = 1 d if the model is
    present, else the class-based assumption. Screening re-evaluates the fit at each
    conjunction's actual time-to-TCA (§10.8 step 5)."""
    m = covariance_model()
    if m is not None:
        cov, _ = m
        return cov.sigma_rtn_m(1.0, object_type, alt_km), "kelvins_fitted"
    return assumed_sigma(object_type, active), "assumed"


def normalise(rec: dict, satcat: dict[int, SatcatRow], group: str, now: datetime) -> SpaceObject:
    el = parse_elements(rec)
    nid = int(rec["NORAD_CAT_ID"])
    sat = satcat.get(nid)
    name = str(rec.get("OBJECT_NAME") or (sat.object_name if sat else f"NORAD {nid}"))
    otype = sat.object_type if sat else "UNKNOWN"
    owner = sat.owner if sat else None
    operator = match_operator(name, owner, otype)
    active = infer_active(sat, group)
    man = infer_maneuverable(active, sat, operator)
    mm = mass_model(otype, sat.rcs_size if sat else None)
    stale = (now - el.epoch).total_seconds() / 86400.0 > CONFIG.screening.stale_after_days
    sigma, cov_src = object_sigma(otype, active, derive_orbit(el).mean_alt_km)
    return SpaceObject(
        norad_id=nid, object_name=name, object_type=otype, is_active=active, is_maneuverable=man,   # type: ignore[arg-type]
        operator=operator, elements=el, international_id=str(rec.get("OBJECT_ID") or (sat.object_id if sat else "")) or None,
        country=owner, launch_date=sat.launch_date if sat else None, rcs_size=sat.rcs_size if sat else None,
        hard_body_radius_m=CONFIG.pc.hard_body_radius_m / 2.0, source="celestrak", stale=stale,
        sigma_rtn_m=sigma, covariance_source=cov_src, **mm,
    )


def ingest(group: str = "active", offline: bool = False, extra_groups: Iterable[str] = (),
           now: Optional[datetime] = None) -> tuple[list[SpaceObject], IngestReport]:
    now = now or datetime.now(timezone.utc)
    recs, meta = fetch_gp_group(group, offline)
    for g in extra_groups:
        more, _ = fetch_gp_group(g, offline)
        seen = {r["NORAD_CAT_ID"] for r in recs}
        recs += [r for r in more if r["NORAD_CAT_ID"] not in seen]
    satcat = load_satcat(offline)
    objs: list[SpaceObject] = []
    rejects: list[tuple[Optional[int], str]] = []
    satcat_miss = 0
    for rec in recs:
        try:
            o = normalise(rec, satcat, group, now)
        except BadElementSet as e:
            nid = rec.get("NORAD_CAT_ID")
            rejects.append((int(nid) if nid else None, str(e)))
            continue
        if int(rec["NORAD_CAT_ID"]) not in satcat:
            satcat_miss += 1
        objs.append(o)
    by_type: dict[str, int] = {}
    by_op: dict[str, int] = {}
    for o in objs:
        by_type[o.object_type] = by_type.get(o.object_type, 0) + 1
        by_op[o.operator] = by_op.get(o.operator, 0) + 1
    report = IngestReport(
        group=group, source=meta["source"], n_raw=len(recs), n_ingested=len(objs), n_rejected=len(rejects),
        n_stale=sum(o.stale for o in objs), n_satcat_miss=satcat_miss,
        n_unknown_operator=sum(o.operator.startswith("UNKNOWN-OPERATOR") for o in objs),
        by_type=by_type, by_operator_top=sorted(by_op.items(), key=lambda kv: -kv[1])[:15],
        rejects=rejects, cached_at=meta.get("cached_at"), now=now,
    )
    return objs, report


def shell_filter(objs: Iterable[SpaceObject], alt_low_km: float, alt_high_km: float,
                 include_stale: bool = False) -> list[SpaceObject]:
    """Objects whose radial range overlaps [alt_low, alt_high] (an object can cross the shell)."""
    out = []
    for o in objs:
        if o.stale and not include_stale:
            continue
        orb = o.orbit
        if orb.perigee_alt_km <= alt_high_km and orb.apogee_alt_km >= alt_low_km:
            out.append(o)
    return out
