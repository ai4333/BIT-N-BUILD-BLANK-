"""S10 — the globe's data (SPEC §13.2, cut-first but built last).

The browser propagates every object itself (SGP4 in a worker, from the same mean elements the
backend uses), so what the API serves is the catalogue as OMM JSON, the cluster geometry, and
the post-burn elements of any strategy so a manoeuvre can be drawn as before/after orbits."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from oci.api.serialize import iso, traced_wire
from oci.config import CONFIG, R_EARTH_KM
from oci.data.objects import SpaceObject
from oci.physics.propagate import propagate


def omm(o: SpaceObject) -> dict:
    """CCSDS OMM JSON, the shape satellite.js `json2satrec` reads — identical fields to the
    CelesTrak GP record the object was ingested from."""
    e = o.elements
    return {"OBJECT_NAME": o.object_name, "OBJECT_ID": o.international_id or "", "EPOCH": e.epoch.strftime("%Y-%m-%dT%H:%M:%S.%f"),
            "MEAN_MOTION": e.mean_motion_rev_day, "ECCENTRICITY": e.eccentricity, "INCLINATION": e.inclination_deg,
            "RA_OF_ASC_NODE": e.raan_deg, "ARG_OF_PERICENTER": e.argp_deg, "MEAN_ANOMALY": e.mean_anomaly_deg,
            "EPHEMERIS_TYPE": 0, "CLASSIFICATION_TYPE": "U", "NORAD_CAT_ID": o.norad_id, "ELEMENT_SET_NO": 999,
            "BSTAR": e.bstar, "MEAN_MOTION_DOT": e.mean_motion_dot, "MEAN_MOTION_DDOT": e.mean_motion_ddot}


def role(o: SpaceObject) -> str:
    if o.object_type == "DEBRIS":
        return "debris"
    if o.object_type == "ROCKET_BODY":
        return "rocket_body"
    return "active" if o.is_active else "dead"


def catalogue(objects: dict[int, SpaceObject], ledger=None) -> list[dict]:
    billed: dict[int, float] = {}
    borne: dict[int, float] = {}
    if ledger is not None:
        for e in ledger.entries:
            if e.dv_imposed_mps.value:
                billed[e.norad_id] = float(e.dv_imposed_mps.value)
            if e.dv_spent_mps.value:
                borne[e.norad_id] = float(e.dv_spent_mps.value)
    out = []
    for o in objects.values():
        out.append({"id": o.norad_id, "name": o.object_name, "role": role(o), "operator": o.operator,
                    "maneuverable": o.is_maneuverable, "alt_km": round(o.orbit.mean_alt_km, 1),
                    "inc_deg": round(o.elements.inclination_deg, 2), "period_min": round(o.orbit.period_min, 2),
                    "dv_imposed_mps": billed.get(o.norad_id, 0.0), "dv_borne_mps": borne.get(o.norad_id, 0.0),
                    "omm": omm(o)})
    return out


def _teme(o: SpaceObject, t: datetime) -> list[float]:
    st = propagate(o, t)
    return [float(x) for x in st.r_km]


def cluster_geometry(cluster, objects: dict[int, SpaceObject], conjunctions, pc_threshold: float) -> dict:
    members = set(cluster.members)
    edges = []
    for c in conjunctions:
        if c.primary_id in members and c.secondary_id in members:
            edges.append({"conj_id": c.conj_id, "primary_id": c.primary_id, "secondary_id": c.secondary_id, "tca": iso(c.tca),
                          "miss_m": c.miss_m, "pc": c.pc.value, "critical": bool(c.pc.value is not None and c.pc.value >= pc_threshold),
                          "rel_speed_mps": float(c.rel_speed_mps.value), "r_teme_km": _teme(objects[c.primary_id], c.tca)})
    edges.sort(key=lambda e: -(e["pc"] or 0.0))
    return {"cluster_id": cluster.cluster_id, "members": sorted(members), "keystone_id": cluster.keystone_id,
            "max_pc_object_id": cluster.max_pc_object_id, "edges": edges, "pc_threshold": pc_threshold}


def strategy_geometry(s, state_objects: dict[int, SpaceObject]) -> dict:
    """What a strategy does to the picture: the burns (time, target, Δv), the post-burn OMM of
    every object it moved, and the conjunctions that remain / appear afterwards."""
    burns = []
    for b in s.action.burns() if hasattr(s.action, "burns") else []:
        burns.append({"target_id": b.target_id, "t_burn": iso(b.t_burn), "dv_rtn_mps": [float(x) for x in b.dv_rtn_mps],
                      "magnitude_mps": float(b.magnitude_mps), "r_teme_km": _teme(state_objects[b.target_id], b.t_burn)})
    moved = {}
    if s.sim is not None:
        for nid, o in s.sim.objects_after.items():
            if nid in state_objects and o.elements != state_objects[nid].elements:
                moved[str(nid)] = omm(o)
    after = []
    if s.sim is not None:
        for c in s.sim.conjunctions:
            after.append({"conj_id": c.conj_id, "primary_id": c.primary_id, "secondary_id": c.secondary_id, "tca": iso(c.tca),
                          "miss_m": c.miss_m, "pc": c.pc.value, "new": c.conj_id in set(s.sim.new_conj_ids)})
        after.sort(key=lambda e: -(e["pc"] or 0.0))
    return {"strategy_id": s.strategy_id, "kind": s.action.kind, "label": s.action.describe(), "burns": burns,
            "omm_after": moved, "conjunctions_after": after[:40],
            "pc_after": traced_wire(s.pc_after) if s.pc_after else None,
            "wait_min": s.action.wait_min, "epoch_after": iso(s.sim.epoch_after) if s.sim is not None else None}
