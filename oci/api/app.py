"""M12 — the REST API (SPEC §12).

One FastAPI process, no database, no auth (§12.1, §16.7). Every 200 carries the universal
envelope, so an exported response is self-describing and cannot be quoted out of context:

    {data, assumptions, run_id, computed_at, meta}

Every number destined for display crosses the wire as a `Traced` (§9.3) — `tests/test_api.py`
walks each response tree and fails on a bare float in a display field. Errors are RFC 7807
problem+json (§12.5). Long operations return 202 + a job id (§12.1).

Run with `make api`. `OCI_DEMO_SAFE=1` refuses any route that would touch the network, so the
whole demo runs from committed fixtures and cached runs with the cable pulled (§17.6).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from oci.api import errors as err
from oci.api import jobs, store
from oci.api.schemas import (AgentRequest, BenchRequest, ChaosRequest, DeploymentRequestBody,
                             IngestRequest, LedgerComputeRequest, ScreenRequest, StrategiesRequest,
                             ValidateRequest, VoIRequest)
from oci.api.serialize import (conjunction_wire, iso, ledger_entry_wire, object_summary,
                               provenance_get, strategy_wire, traced_wire, verdict_wire, wire)
from oci.config import CONFIG

API = "/api/v1"
VERSION = "0.1.0"
DEBRIS_GROUPS = ("cosmos-1408-debris", "fengyun-1c-debris", "iridium-33-debris", "cosmos-2251-debris")

app = FastAPI(title="Orbital Capacity Intelligence", version=VERSION,
              description="Per-object operational externality ledger over public orbital data. "
                          "Research prototype — decision support, not a flight command.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(err.Problem, err.problem_response)

# in-memory caches for things addressed by their own id
_STRATEGIES: dict[str, dict] = {}
_TRACES: dict[str, Any] = {}
_PIPELINES: dict[str, Any] = {}          # run_id/cluster_id → PipelineResult, for chaos replans


def demo_safe() -> bool:
    return os.environ.get("OCI_DEMO_SAFE", "").lower() in ("1", "true", "yes")


def envelope(data: Any, run_id: Optional[str] = None, **meta: Any) -> dict:
    """§12.1 — the universal envelope. The assumption block travels with every payload."""
    return {"data": data, "assumptions": CONFIG.assumptions_block(), "run_id": run_id,
            "computed_at": iso(datetime.now(timezone.utc)), "meta": meta or {}}


def _bundle(run_id: Optional[str]) -> store.RunBundle:
    b = store.get_bundle(run_id)
    if b is None:
        raise err.run_not_found(run_id or "(default)")
    return b


def _threshold(pc_threshold: Optional[float]) -> float:
    if pc_threshold is None:
        raise err.threshold_not_declared()
    return float(pc_threshold)


# ── health, assumptions, provenance ──────────────────────────────────────────────────────
@app.get(API + "/health")
def health() -> dict:
    import sgp4
    b = store.get_bundle(None)
    return envelope({"status": "ok", "version": VERSION, "propagator": f"sgp4-{sgp4.__version__}",
                     "demo_safe": demo_safe(), "runs_available": store.list_run_ids(),
                     "data_freshness": store.catalogue_freshness(b)},
                    run_id=b.run_id if b else None)


@app.get(API + "/assumptions")
def assumptions() -> dict:
    from oci.assumptions_doc import REGISTER
    return envelope({"block": CONFIG.assumptions_block(),
                     "register": [{"n": i + 1, "id": a[0], "assumption": a[1], "label": a[2], "impact": a[3]}
                                  for i, a in enumerate(REGISTER)],
                     "config_hash": _config_hash()})


@app.get(API + "/provenance/{trace_id}")
def provenance(trace_id: str) -> dict:
    d = provenance_get(trace_id)
    if d is None:
        raise err.Problem("provenance-not-found", "No such traced value", 404,
                          f"trace_id '{trace_id}' has not been served in this process. "
                          "Provenance ids are minted as responses are serialised; fetch the parent resource first.")
    return envelope(d)


# ── jobs ──────────────────────────────────────────────────────────────────────────────────
@app.get(API + "/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    j = jobs.get(job_id)
    if j is None:
        raise err.Problem("job-not-found", "Job not found", 404, f"No job '{job_id}'.")
    return envelope(j.wire(), run_id=j.run_id)


@app.get(API + "/jobs")
def job_list() -> dict:
    return envelope({"jobs": [j.wire() for j in jobs.all_jobs()]})


# ── ingest / screen (202 + poll) ──────────────────────────────────────────────────────────
@app.post(API + "/ingest", status_code=202)
def ingest(req: IngestRequest) -> JSONResponse:
    if req.source == "spacetrack":
        raise err.Problem("source-unavailable", "Space-Track ingest is not built", 501,
                          "D4 requires credentials that are not present. Use source='celestrak'.")
    offline = req.offline or demo_safe()

    def run(job: jobs.Job) -> dict:
        from oci.data.ingest import ingest as do_ingest
        job.stage = "fetching catalogue"
        objs, rep = do_ingest(req.group, offline=offline,
                              extra_groups=DEBRIS_GROUPS if req.include_debris else ())
        job.progress = 1.0
        return {"n_ingested": rep.n_ingested, "n_raw": rep.n_raw, "source": rep.source,
                "n_rejected": rep.n_rejected, "n_stale": rep.n_stale,
                "by_type": rep.by_type, "top_operators": rep.by_operator_top[:10]}

    j = jobs.submit("ingest", run)
    return JSONResponse(status_code=202, content=envelope(j.wire()))


@app.post(API + "/screen", status_code=202)
def screen_endpoint(req: ScreenRequest) -> JSONResponse:
    offline = req.offline or demo_safe()
    if req.window_hours > 24 * 14:
        raise err.Problem("window-too-large", "Screening window too large", 422,
                          "Element sets are stale beyond 7 days; a window over 14 days is refused.")

    def run(job: jobs.Job) -> dict:
        from oci.data.ingest import ingest as do_ingest, shell_filter
        from oci.physics.screen import screen as do_screen
        job.stage = "ingest"
        objs, _ = do_ingest("active", offline=offline, extra_groups=DEBRIS_GROUPS)
        shell = (shell_filter(objs, req.alt_low_km, req.alt_high_km) if req.object_ids is None
                 else [o for o in objs if o.norad_id in set(req.object_ids)])
        job.stage = f"screening {len(shell)} objects"
        job.progress = 0.1
        t0 = req.window_start or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        res = do_screen(shell, t0, t0 + timedelta(hours=req.window_hours),
                        volume_m=req.screening_volume_m, step_min=req.coarse_step_min, gate_k=req.gate_k)
        job.stage = "caching run"
        job.progress = 0.95
        b = store.save_run({o.norad_id: o for o in shell}, res, (req.alt_low_km, req.alt_high_km))
        job.run_id = b.run_id
        return {"run_id": b.run_id, "n_conjunctions": res.run.n_conjunctions, "n_objects": len(shell)}

    j = jobs.submit("screen", run)
    return JSONResponse(status_code=202, content=envelope(j.wire()))


# ── screening runs, conjunctions, objects ────────────────────────────────────────────────
@app.get(API + "/screening-runs")
def screening_runs() -> dict:
    out = []
    for rid in store.list_run_ids():
        b = store.get_bundle(rid) if rid.startswith("run_") else None
        if b is None:
            out.append({"run_id": rid, "source": "scenario", "loaded": False})
        else:
            r = b.screening.run
            out.append({"run_id": rid, "source": b.source, "loaded": True,
                        "window_start": iso(r.window_start), "window_end": iso(r.window_end),
                        "window_days": round(b.window_days, 3), "n_objects": r.n_objects,
                        "n_conjunctions": r.n_conjunctions, "shell_km": list(b.shell)})
    return envelope({"runs": out, "default": store.default_run_id()})


@app.get(API + "/screening-runs/{run_id}")
def screening_run(run_id: str) -> dict:
    b = _bundle(run_id)
    r = b.screening.run
    from collections import Counter
    cls = Counter(str(c.pair_class) for c in b.screening.conjunctions)
    return envelope({"run_id": r.run_id, "window_start": iso(r.window_start), "window_end": iso(r.window_end),
                     "window_days": round(b.window_days, 3), "shell_km": list(b.shell),
                     "n_objects": r.n_objects, "n_pairs_total": r.n_pairs_total,
                     "n_conjunctions": r.n_conjunctions, "screening_volume_m": r.screening_volume_m,
                     "coarse_step_min": r.coarse_step_min, "gate_k": r.gate_k, "propagator": r.propagator,
                     "config_hash": r.config_hash, "runtime_s": r.runtime_s,
                     "n_formation_pairs_dropped": r.n_formation_pairs_dropped,
                     "n_excluded": len(r.excluded), "pair_classes": dict(cls)}, run_id=b.run_id)


@app.get(API + "/objects")
def objects(run_id: Optional[str] = None, q: Optional[str] = None, object_type: Optional[str] = None,
            operator: Optional[str] = None, is_active: Optional[bool] = None,
            alt_min_km: Optional[float] = None, alt_max_km: Optional[float] = None,
            limit: int = Query(50, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    b = _bundle(run_id)
    rows = list(b.objects.values())
    if q:
        ql = q.lower()
        rows = [o for o in rows if ql in o.object_name.lower() or ql == str(o.norad_id)]
    if object_type:
        rows = [o for o in rows if o.object_type == object_type]
    if operator:
        rows = [o for o in rows if o.operator == operator]
    if is_active is not None:
        rows = [o for o in rows if o.is_active is is_active]
    if alt_min_km is not None:
        rows = [o for o in rows if o.orbit.mean_alt_km >= alt_min_km]
    if alt_max_km is not None:
        rows = [o for o in rows if o.orbit.mean_alt_km <= alt_max_km]
    total = len(rows)
    rows.sort(key=lambda o: o.norad_id)
    return envelope({"total": total, "limit": limit, "offset": offset,
                     "objects": [object_summary(o) for o in rows[offset:offset + limit]]}, run_id=b.run_id)


@app.get(API + "/objects/{norad_id}")
def object_detail(norad_id: int, run_id: Optional[str] = None,
                  pc_threshold: Optional[float] = None) -> dict:
    b = _bundle(run_id)
    o = b.objects.get(norad_id)
    if o is None:
        raise err.object_not_found(norad_id)
    thr = _threshold(pc_threshold if pc_threshold is not None else CONFIG.thresholds.declared_pc_threshold)
    led = b.ledger(thr)
    entry = next((e for e in led.entries if e.norad_id == norad_id), None)
    conjs = [c for c in b.screening.conjunctions if norad_id in (c.primary_id, c.secondary_id)]
    conjs.sort(key=lambda c: -(c.pc.value or 0.0))
    from oci.physics.decay import decay_lifetime_years
    return envelope({"object": object_summary(o),
                     "ledger_entry": ledger_entry_wire(entry, full=True) if entry else None,
                     "decay_lifetime_yr": traced_wire(decay_lifetime_years(o.orbit.mean_alt_km, o.area_to_mass_m2_kg)),
                     "n_conjunctions": len(conjs),
                     "conjunctions": [conjunction_wire(c, b.objects) for c in conjs[:100]],
                     "pc_threshold": thr}, run_id=b.run_id)


@app.get(API + "/conjunctions")
def conjunctions(run_id: Optional[str] = None, primary_id: Optional[int] = None,
                 min_pc: Optional[float] = None, max_miss_m: Optional[float] = None,
                 pair_class: Optional[str] = None, exclude_intra: bool = True,
                 limit: int = Query(100, ge=1, le=2000), offset: int = Query(0, ge=0)) -> dict:
    b = _bundle(run_id)
    rows = list(b.screening.conjunctions)
    if primary_id is not None:
        rows = [c for c in rows if primary_id in (c.primary_id, c.secondary_id)]
    if min_pc is not None:
        rows = [c for c in rows if c.pc.value is not None and c.pc.value >= min_pc]
    if max_miss_m is not None:
        rows = [c for c in rows if (c.miss_distance_m.value or 1e18) <= max_miss_m]
    if pair_class:
        rows = [c for c in rows if str(c.pair_class) == pair_class]
    if exclude_intra:
        rows = [c for c in rows if not c.intra_constellation]
    rows.sort(key=lambda c: -(c.pc.value or 0.0))
    return envelope({"total": len(rows), "limit": limit, "offset": offset,
                     "conjunctions": [conjunction_wire(c, b.objects) for c in rows[offset:offset + limit]]},
                    run_id=b.run_id)


@app.get(API + "/conjunctions/{conj_id}")
def conjunction_detail(conj_id: str, run_id: Optional[str] = None) -> dict:
    b = _bundle(run_id)
    c = next((x for x in b.screening.conjunctions if x.conj_id == conj_id), None)
    if c is None:
        raise err.Problem("conjunction-not-found", "Conjunction not found", 404,
                          f"No conjunction '{conj_id}' in run {b.run_id}.")
    if c.pc.value is None and c.covariance_source in (None, "none"):
        raise err.insufficient_covariance(c.primary_id, c.secondary_id)
    d = conjunction_wire(c, b.objects)
    d["encounter_plane"] = _encounter_plane(c, b)
    return envelope(d, run_id=b.run_id)


def _encounter_plane(c, b: store.RunBundle) -> dict:
    """S4 — the 2D B-plane view (§13.5): miss vector, projected covariance, HBR, dilution flag."""
    import numpy as np
    from oci.physics.geometry import covariance_inertial, encounter_plane
    from oci.physics.propagate import propagate
    if not c.sigma_rtn_combined_m:
        return {"available": False,
                "na_reason": "no covariance for this pair; the encounter plane would be a point estimate"}
    try:
        st = propagate(b.objects[c.primary_id], c.tca)
        cov = covariance_inertial(c.sigma_rtn_combined_m, st.r_km, st.v_kmps)
        ep = encounter_plane(np.asarray(c.rel_r_km, float), np.asarray(c.rel_v_kmps, float), cov)
    except Exception as e:
        return {"available": False, "na_reason": f"{type(e).__name__}: {e}"}
    evals, evecs = np.linalg.eigh(ep.cov_xy_m2)
    order = np.argsort(evals)[::-1]
    evals, evecs = evals[order], evecs[:, order]
    return {"available": True,
            "miss_xy_m": [float(x) for x in ep.miss_xy_m],
            "miss_m": float(ep.miss_m), "v_rel_mps": float(ep.v_rel_mps),
            "cov_xy_m2": [[float(x) for x in row] for row in ep.cov_xy_m2],
            "sigma_major_m": float(np.sqrt(max(evals[0], 0.0))),
            "sigma_minor_m": float(np.sqrt(max(evals[1], 0.0))),
            "orientation_deg": float(np.degrees(np.arctan2(evecs[1, 0], evecs[0, 0]))),
            "sigma_rtn_combined_m": list(c.sigma_rtn_combined_m),
            "hard_body_radius_m": CONFIG.pc.hard_body_radius_m,
            "hard_body_radius_label": "MODELLED",
            "dilution": c.dilution, "mahalanobis": c.mahalanobis,
            "covariance_source": c.covariance_source}


def _config_hash() -> str:
    """A stable fingerprint of the assumption set, shown in the provenance panel (§13.8)."""
    import hashlib
    import json
    blk = CONFIG.assumptions_block()
    return hashlib.sha1(json.dumps(blk, sort_keys=True, default=str).encode()).hexdigest()[:12]


# ── graph ─────────────────────────────────────────────────────────────────────────────────
@app.get(API + "/graph")
def graph(run_id: Optional[str] = None, min_pc: float = 0.0,
          limit_edges: int = Query(2000, ge=1, le=20000)) -> dict:
    b = _bundle(run_id)
    g = b.graph()
    edges = [c for c in b.screening.conjunctions if (c.pc.value or 0.0) >= min_pc]
    edges.sort(key=lambda c: -(c.pc.value or 0.0))
    edges = edges[:limit_edges]
    ids = {i for c in edges for i in (c.primary_id, c.secondary_id)}
    cen = g.centrality
    nodes = []
    for nid in sorted(ids):
        o = b.objects.get(nid)
        nodes.append({"norad_id": nid, "label": o.object_name if o else str(nid),
                      "operator": o.operator if o else None, "is_active": o.is_active if o else None,
                      "degree": cen.get("degree", {}).get(nid),
                      "risk_weighted_degree": cen.get("risk_weighted_degree", {}).get(nid),
                      "betweenness": cen.get("betweenness", {}).get(nid),
                      "eigenvector": cen.get("eigenvector", {}).get(nid)})
    return envelope({"nodes": nodes,
                     "edges": [{"source": c.primary_id, "target": c.secondary_id,
                                "conj_id": c.conj_id, "pc": traced_wire(c.pc),
                                "miss_distance_m": traced_wire(c.miss_distance_m),
                                "rel_speed_mps": traced_wire(c.rel_speed_mps), "tca": iso(c.tca)}
                               for c in edges],
                     "metrics": {"n_nodes": len(nodes), "n_edges": len(edges),
                                 "weight_rule": g.weight_rule,
                                 "n_clusters": len(g.clusters),
                                 "betweenness_exact": g.betweenness_exact,
                                 "betweenness_note": ("exact" if g.betweenness_exact else
                                                      f"estimated from {CONFIG.graph.betweenness_samples} pivots — "
                                                      "display only; keystone selection uses risk-weighted degree"),
                                 "disagreement_clusters": g.disagreement_clusters}}, run_id=b.run_id)


@app.get(API + "/graph/clusters")
def clusters(run_id: Optional[str] = None, min_size: int = Query(2, ge=1),
             pc_threshold: Optional[float] = Query(None, gt=0, lt=1)) -> dict:
    """Risk clusters at the declared threshold: edges below Pc*/100 do not join objects into a
    cluster (a raw 5-km conjunction graph of a real shell is one giant component), and
    `critical_conjunctions` counts edges at or above Pc*. Ordered most actionable first."""
    b = _bundle(run_id)
    th = pc_threshold if pc_threshold is not None else CONFIG.thresholds.declared_pc_threshold
    cs = [c for c in b.clusters(th) if len(c.members) >= min_size]
    from oci.labels import traced
    return envelope({"clusters": [_cluster_wire(c, b) for c in cs], "pc_threshold": th,
                     "edge_floor_pc": traced(th * CONFIG.graph.w_min_fraction_of_threshold, "probability", "MODELLED", "graph.build@0.1.0",
                                             fraction_of_threshold=CONFIG.graph.w_min_fraction_of_threshold,
                                             meaning="edges with summed Pc below this do not join objects into a cluster"),
                     "n_disagreement": sum(1 for c in cs if c.disagreement)}, run_id=b.run_id)


def _cluster_wire(c, b: store.RunBundle) -> dict:
    return {"cluster_id": c.cluster_id, "members": list(c.members), "n_objects": len(c.members),
            "n_edges": c.n_edges, "total_weight": c.total_weight,
            "keystone_id": c.keystone_id, "keystone_selected_by": c.keystone_selected_by,
            "keystone_score": c.keystone_score, "max_pc_object_id": c.max_pc_object_id,
            "max_pc_edge": list(c.max_pc_edge) if c.max_pc_edge else None, "max_pc": c.max_pc,
            "keystone_differs_from_max_pc": c.disagreement,
            "critical_conjunctions": c.critical_conjunctions,
            "member_names": {str(m): (b.objects[m].object_name if m in b.objects else None) for m in c.members}}


# ── ledger — the headline (§12.3) ────────────────────────────────────────────────────────
@app.post(API + "/ledger/compute")
def ledger_compute(req: LedgerComputeRequest) -> dict:
    b = _bundle(req.run_id)
    thr = _threshold(req.pc_threshold)
    led = b.ledger(thr)
    return envelope({"run_id": b.run_id, "pc_threshold": thr, "window_days": led.window_days,
                     "n_entries": len(led.entries),
                     "n_conjunctions_used": led.n_conjunctions_used,
                     "n_conjunctions_intra_excluded": led.n_conjunctions_intra_excluded,
                     "share_of_dv_from_dead": traced_wire(led.share_of_dv_from_dead)}, run_id=b.run_id)


@app.get(API + "/ledger")
def ledger(run_id: Optional[str] = None, pc_threshold: Optional[float] = None,
           sort: str = "dv_imposed_mps", order: str = "desc",
           object_type: Optional[str] = None, is_active: Optional[bool] = None,
           operator: Optional[str] = None, nonzero_only: bool = False,
           limit: int = Query(50, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    b = _bundle(run_id)
    thr = _threshold(pc_threshold)
    led = b.ledger(thr)
    rows = list(led.entries)
    if object_type:
        rows = [e for e in rows if e.object_type == object_type]
    if is_active is not None:
        rows = [e for e in rows if e.is_active is is_active]
    if operator:
        rows = [e for e in rows if e.operator == operator]
    if nonzero_only:
        rows = [e for e in rows if (e.dv_imposed_mps.value or 0.0) > 0.0]
    keys = {"dv_imposed_mps": lambda e: e.dv_imposed_mps.value or 0.0,
            "cab": lambda e: e.cab.value or 0.0,
            "maneuvers_forced": lambda e: e.maneuvers_forced.value or 0.0,
            "operators_affected": lambda e: e.operators_affected.value or 0.0,
            "conjunctions_generated": lambda e: e.conjunctions_generated.value or 0.0,
            "dv_spent_mps": lambda e: e.dv_spent_mps.value or 0.0,
            "implied_fee_usd_yr": lambda e: e.implied_fee_usd_yr.value or 0.0}
    if sort not in keys:
        raise err.Problem("bad-sort-key", "Unknown sort key", 422,
                          f"sort must be one of {', '.join(sorted(keys))}.")
    rows.sort(key=keys[sort], reverse=(order != "asc"))
    total_imposed = sum(e.dv_imposed_mps.value or 0.0 for e in led.entries)
    return envelope({"total": len(rows), "total_all": len(led.entries), "limit": limit, "offset": offset,
                     "window_days": led.window_days, "pc_threshold": thr, "sort": sort, "order": order,
                     "share_of_dv_from_dead": traced_wire(led.share_of_dv_from_dead),
                     "total_dv_imposed_mps": traced_wire(
                         __import__("oci.labels", fromlist=["traced"]).traced(
                             total_imposed, "m/s", "MODELLED", "ledger.total_imposed@0.4.1",
                             pc_threshold=thr, window_days=led.window_days)),
                     "n_entries_nonzero": sum(1 for e in led.entries if (e.dv_imposed_mps.value or 0.0) > 0),
                     "entries": [ledger_entry_wire(e) for e in rows[offset:offset + limit]]},
                    run_id=b.run_id)


@app.get(API + "/ledger/by-operator")
def ledger_by_operator(run_id: Optional[str] = None, pc_threshold: Optional[float] = None) -> dict:
    b = _bundle(run_id)
    thr = _threshold(pc_threshold)
    led = b.ledger(thr)
    imposed: dict[str, float] = {}
    borne: dict[str, float] = {}
    for e in led.entries:
        imposed[e.operator] = imposed.get(e.operator, 0.0) + (e.dv_imposed_mps.value or 0.0)
        borne[e.operator] = borne.get(e.operator, 0.0) + (e.dv_spent_mps.value or 0.0)
    ops = sorted(set(imposed) | set(borne), key=lambda o: -(imposed.get(o, 0.0) + borne.get(o, 0.0)))
    from oci.labels import traced
    asm = {"pc_threshold": thr, "window_days": led.window_days, "attribution_rule": "R1"}
    return envelope({"pc_threshold": thr, "window_days": led.window_days,
                     "operators": [{"operator": o,
                                    "dv_imposed_mps": traced_wire(traced(
                                        imposed.get(o, 0.0), "m/s", "MODELLED",
                                        "ledger.by_operator_imposed@0.4.1", **asm)),
                                    "dv_borne_mps": traced_wire(traced(
                                        borne.get(o, 0.0), "m/s", "MODELLED",
                                        "ledger.by_operator_borne@0.4.1", **asm)),
                                    "net_mps": traced_wire(traced(
                                        imposed.get(o, 0.0) - borne.get(o, 0.0), "m/s", "MODELLED",
                                        "ledger.by_operator_net@0.4.1", **asm))} for o in ops]},
                    run_id=b.run_id)


@app.get(API + "/ledger/{norad_id}")
def ledger_entry(norad_id: int, run_id: Optional[str] = None, pc_threshold: Optional[float] = None) -> dict:
    b = _bundle(run_id)
    thr = _threshold(pc_threshold)
    e = next((x for x in b.ledger(thr).entries if x.norad_id == norad_id), None)
    if e is None:
        raise err.object_not_found(norad_id)
    return envelope(ledger_entry_wire(e, full=True), run_id=b.run_id)


@app.get(API + "/ledger/{norad_id}/bearers")
def ledger_bearers(norad_id: int, run_id: Optional[str] = None, pc_threshold: Optional[float] = None) -> dict:
    b = _bundle(run_id)
    thr = _threshold(pc_threshold)
    led = b.ledger(thr)
    flows = [f for f in led.flows if f.imposer_id == norad_id]
    by_op: dict[str, dict] = {}
    for f in flows:
        d = by_op.setdefault(f.bearer_operator, {"operator": f.bearer_operator, "n_maneuvers": 0.0,
                                                 "dv_mps": 0.0, "bearers": []})
        d["n_maneuvers"] += f.n_maneuvers
        d["dv_mps"] += f.dv_mps or 0.0
        d["bearers"].append(f.bearer_id)
    rows = sorted(by_op.values(), key=lambda d: -d["dv_mps"])
    return envelope({"norad_id": norad_id, "pc_threshold": thr, "n_flows": len(flows),
                     "by_operator": rows, "flows": [wire(f) for f in flows]}, run_id=b.run_id)


# ── strategies, VoI, validate ─────────────────────────────────────────────────────────────
@app.post(API + "/clusters/{cluster_id}/strategies")
def cluster_strategies(cluster_id: str, req: StrategiesRequest) -> dict:
    from oci.decide.optimize import cluster_conjunctions, evaluate, generate_strategies
    from oci.decide.validate import validate as do_validate
    b, cluster = store.find_cluster(cluster_id)
    if b is None or cluster is None:
        raise err.Problem("cluster-not-found", "Cluster not found", 404,
                          f"No cluster '{cluster_id}'. GET /graph/clusters lists them.")
    state = b.state()
    conjs = b.screening.conjunctions
    kinds = tuple(req.include_kinds or ("HOLD", "MANEUVER", "WAIT", "OBSERVE", "COORDINATE"))
    strategies = generate_strategies(cluster, state, conjs, include=kinds)
    opt = evaluate(strategies, cluster, state, conjs, weights=req.weights,
                   n_mc=req.mc_samples, seed=req.seed)
    approved, rejected = [], []
    for s in opt.strategies:
        if req.validate_all or s.action.kind != "HOLD":
            v = do_validate(s.action, state, conjs, sim=s.sim)
            s.validator_verdict, s.validator_reason = v.status, v.reason
        _STRATEGIES[s.strategy_id] = {"strategy": s, "run_id": b.run_id, "cluster_id": cluster_id}
        (approved if s.validator_verdict != "REJECTED" else rejected).append(s)
    ev = next((s for s in opt.by_expected if s.validator_verdict != "REJECTED"), None)
    rg = next((s for s in opt.by_regret if s.validator_verdict != "REJECTED"), None)
    return envelope({"cluster_id": cluster_id, "cluster": _cluster_wire(cluster, b),
                     "strategies": [strategy_wire(s) for s in approved],
                     "rejected": [strategy_wire(s) for s in rejected],
                     "recommendation": {
                         "expected_value_optimum": ev.strategy_id if ev else None,
                         "minimax_regret_optimum": rg.strategy_id if rg else None,
                         "optima_agree": bool(ev and rg and ev.strategy_id == rg.strategy_id),
                         "note": "When optima disagree, surface both. A single-satellite operator and a "
                                 "300-satellite operator should not choose the same strategy."},
                     "weights_used": opt.weights_used, "mc_samples": req.mc_samples},
                    run_id=b.run_id)


@app.get(API + "/strategies/{strategy_id}")
def strategy_detail(strategy_id: str) -> dict:
    rec = _STRATEGIES.get(strategy_id)
    if rec is None:
        raise err.Problem("strategy-not-found", "Strategy not found", 404,
                          f"No strategy '{strategy_id}' in this process. "
                          "POST /clusters/{cluster_id}/strategies mints them.")
    d = strategy_wire(rec["strategy"])
    d["cluster_id"] = rec["cluster_id"]
    return envelope(d, run_id=rec["run_id"])


@app.post(API + "/voi")
def voi(req: VoIRequest) -> dict:
    from oci.decide.voi import compute_voi
    b = _bundle(req.run_id)
    c = next((x for x in b.screening.conjunctions if x.conj_id == req.conj_id), None)
    if c is None:
        raise err.Problem("conjunction-not-found", "Conjunction not found", 404,
                          f"No conjunction '{req.conj_id}' in run {b.run_id}.")
    res = compute_voi(c, b.objects, b.screening.run.window_start, wait_options_min=req.wait_options_min)
    return envelope({"conj_id": res.conj_id, "covariance_source": res.covariance_source,
                     "cost_now": traced_wire(res.cost_now), "dv_now_mps": traced_wire(res.dv_now_mps),
                     "recommended_wait_min": res.recommended_wait_min,
                     "options": [{"wait_min": o.wait_min, "feasible": o.feasible,
                                  "expected_sigma_reduction": traced_wire(o.expected_sigma_reduction),
                                  "expected_pc": traced_wire(o.expected_pc),
                                  "expected_dv_mps": traced_wire(o.expected_dv_mps),
                                  "risk_of_delay": traced_wire(o.risk_of_delay),
                                  "voi_net": traced_wire(o.voi_net)} for o in res.options]},
                    run_id=b.run_id)


@app.post(API + "/validate")
def validate_endpoint(req: ValidateRequest) -> dict:
    from oci.decide.validate import validate as do_validate
    from oci.physics.maneuver import Burn
    from oci.sim.simulate import Action
    b = _bundle(req.run_id)
    if req.target_id not in b.objects:
        raise err.object_not_found(req.target_id)
    t = req.t_burn if req.t_burn.tzinfo else req.t_burn.replace(tzinfo=timezone.utc)
    burn = Burn(target_id=req.target_id, dv_rtn_mps=tuple(float(x) for x in req.dv_vector_mps), t_burn=t)
    action = Action(kind="MANEUVER", target_id=req.target_id, burn=burn)
    v = do_validate(action, b.state(), b.screening.conjunctions)
    return envelope(verdict_wire(v), run_id=b.run_id)


# ── capacity (§12.3 deployment) ──────────────────────────────────────────────────────────
def _capacity(b: store.RunBundle, pc_threshold: Optional[float] = None, c_intra: Optional[float] = None):
    """The shell map is a property of the whole catalogue, not of one screened shell — the two
    peaks only exist if 450 km and 800 km are both in scope (§11.13). The run supplies the
    conjunctions that calibrate q in the shells it covers; everywhere else q is MODELLED and
    labelled so. Matches what `python -m oci capacity` prints."""
    from oci.capacity.ocs import compute_capacity
    if b._capacity is None:
        thr = pc_threshold or CONFIG.thresholds.declared_pc_threshold
        b._capacity = compute_capacity(store.catalogue(), b.screening.conjunctions,
                                       set(b.objects), window_days=b.window_days,
                                       pc_threshold=thr, c_intra=c_intra)
    return b._capacity


@app.get(API + "/shells")
def shells(run_id: Optional[str] = None, pc_threshold: Optional[float] = None,
           min_objects: int = Query(1, ge=0)) -> dict:
    b = _bundle(run_id)
    cap = _capacity(b, pc_threshold)
    rows = [s for s in cap.shells if s.shell.n_objects >= min_objects]
    return envelope({"pc_threshold": cap.pc_threshold, "c_intra": cap.c_intra,
                     "workload_peak_alt_km": cap.workload_peak_alt_km,
                     "hazard_peak_alt_km": cap.hazard_peak_alt_km,
                     "peaks_differ": cap.peaks_differ,
                     "calibration_shells": cap.calibration_shells, "notes": cap.notes,
                     "shells": [wire(s.row()) if hasattr(s, "row") else wire(s) for s in rows]},
                    run_id=b.run_id)


@app.get(API + "/shells/{shell_id}")
def shell_detail(shell_id: str, run_id: Optional[str] = None, pc_threshold: Optional[float] = None) -> dict:
    b = _bundle(run_id)
    cap = _capacity(b, pc_threshold)
    s = next((x for x in cap.shells if x.shell.shell_id == shell_id), None)
    if s is None:
        raise err.Problem("shell-not-found", "Shell not found", 404,
                          f"No shell '{shell_id}'. GET /shells lists them.")
    return envelope(wire(s), run_id=b.run_id)


@app.post(API + "/deployment/evaluate")
def deployment(req: DeploymentRequestBody) -> dict:
    from oci.capacity.deployment import DeploymentRequest, evaluate_deployment
    b = _bundle(req.run_id)
    cap = _capacity(b, c_intra=req.c_intra)
    dr = DeploymentRequest(n_satellites=req.n_satellites, target_alt_km=req.target_alt_km,
                           inclination_deg=req.inclination_deg, sat_mass_kg=req.sat_mass_kg,
                           sat_area_m2=req.sat_area_m2, pmd_success_rate=req.pmd_success_rate,
                           mission_life_yr=req.mission_life_yr,
                           alternatives_km=tuple(req.alternatives_km) if req.alternatives_km
                           else DeploymentRequest.alternatives_km,
                           horizon_yr=req.horizon_yr, c_intra=req.c_intra)
    res = evaluate_deployment(cap, dr)
    return envelope(wire(res.as_dict()), run_id=b.run_id)


# ── agent (M11) ───────────────────────────────────────────────────────────────────────────
@app.post(API + "/agent/analyse")
def agent_analyse(req: AgentRequest) -> dict:
    from oci.agent.planner import plan
    from oci.agent.tools import ToolContext
    if req.scenario:
        b = _bundle(store.SCENARIO_PREFIX + req.scenario)
    else:
        b = _bundle(req.run_id)
    cluster_id = req.cluster_id
    if cluster_id is None:
        cs = b.clusters()
        if not cs:
            raise err.Problem("no-cluster", "No risk cluster in this run", 422,
                              f"Run {b.run_id} produced no cluster to plan on.")
        cluster_id = cs[0].cluster_id
    cluster = b.cluster(cluster_id)
    if cluster is None:
        raise err.Problem("cluster-not-found", "Cluster not found", 404, f"No cluster '{cluster_id}'.")
    from oci.decide.optimize import generate_strategies
    state = b.state()
    conjs = b.screening.conjunctions
    ctx = ToolContext(state=state, conjunctions=conjs, graph=b.graph(),
                      ledger=b.ledger(CONFIG.thresholds.declared_pc_threshold),
                      strategies={})
    trace = plan(ctx, cluster_id, prefer_llm=False)
    _TRACES[trace.trace_id] = trace
    return envelope(_trace_wire(trace), run_id=b.run_id)


def _trace_wire(t) -> dict:
    return {"trace_id": t.trace_id, "driver": t.driver, "cluster_id": t.cluster_id,
            "recommendation": t.recommendation, "explanation": t.explanation,
            "guard_passed": t.guard_passed, "guard_violations": t.guard_violations,
            "fell_back_to_template": t.fell_back_to_template, "n_llm_calls": t.n_llm_calls,
            "elapsed_s": t.elapsed_s, "error": t.error,
            "n_tool_calls": len(t.tool_calls),
            "tool_calls": [{"tool": c["tool"], "args": wire(c["args"]), "ok": c["ok"],
                            "summary": c["summary"], "elapsed_s": c["elapsed_s"]} for c in t.tool_calls],
            "rejections": [wire(r) for r in t.rejections]}


@app.get(API + "/agent/trace/{trace_id}")
def agent_trace(trace_id: str) -> dict:
    t = _TRACES.get(trace_id)
    if t is None:
        raise err.Problem("trace-not-found", "Agent trace not found", 404,
                          f"No trace '{trace_id}' in this process.")
    d = _trace_wire(t)
    d["tool_calls_full"] = [wire(c) for c in t.tool_calls]
    return envelope(d)


# ── chaos (M14) ───────────────────────────────────────────────────────────────────────────
@app.post(API + "/chaos")
def chaos_endpoint(req: ChaosRequest) -> dict:
    from oci.pipeline import run_on_state, run_pipeline
    from oci.sim.chaos import KINDS, Injection, replan
    from oci.sim.simulate import OrbitalState
    if req.injection not in KINDS:
        raise err.Problem("unknown-injection", "Unknown injection kind", 422,
                          f"injection must be one of {', '.join(KINDS)}.")
    key = req.scenario or req.run_id or "(default)"
    prev = _PIPELINES.get(key)
    if prev is None:
        if req.scenario:
            prev = run_pipeline(req.scenario, n_mc=req.mc_samples, seed=req.seed)
        else:
            # §12.6 — replan the affected neighbourhood, never the full catalogue. A full
            # re-screen of the demo run is 677 s against a 10 s budget; the neighbourhood of the
            # cluster being replanned is the only set a burn there can newly conflict with.
            b = _bundle(req.run_id)
            cs = b.clusters()
            if not cs:
                raise err.Problem("no-cluster", "Nothing to replan", 422,
                                  f"Run {b.run_id} produced no risk cluster, so there is no "
                                  "standing recommendation for an injection to invalidate.")
            cluster = max(cs, key=lambda c: (c.critical_conjunctions, len(c.members)))
            objs, conjs = store.neighbourhood(b, cluster, hops=1)
            state = OrbitalState(objs, b.screening.run.window_start,
                                 frozenset(c.conj_id for c in conjs),
                                 horizon_h=min(CONFIG.decision.horizon_h, b.window_days * 24.0))
            prev = run_on_state(state, b.window_end(), scenario_name=b.run_id,
                                n_mc=req.mc_samples, seed=req.seed,
                                focus_cluster_member=cluster.keystone_id)
        _PIPELINES[key] = prev
    res = replan(prev, Injection(kind=req.injection, params=req.params, seed=req.seed),
                 n_mc=req.mc_samples)
    _PIPELINES[key] = res.new
    return envelope({"injection": {"kind": res.injection.kind, "params": wire(res.injection.params),
                                   "seed": res.injection.seed},
                     "applied": wire(res.applied),
                     "invalidated": res.invalidated, "invalidation_reason": res.invalidation_reason,
                     "still_valid": res.still_valid,
                     "new_recommendation": (strategy_wire(res.new.recommendation)
                                            if res.new.recommendation else None),
                     "diff": wire(res.diff), "elapsed_s": res.elapsed_s,
                     "new_run_id": res.new.screening.run.run_id}, run_id=key)


@app.get(API + "/chaos/kinds")
def chaos_kinds() -> dict:
    from oci.sim.chaos import KINDS
    return envelope({"kinds": list(KINDS)})


# ── benchmark (M15) ───────────────────────────────────────────────────────────────────────
@app.post(API + "/bench/run")
def bench_run(req: BenchRequest) -> dict:
    from oci.bench.harness import SCENARIO_SET, run_scenario
    ids = [req.scenario_id] if req.scenario_id else list(SCENARIO_SET)
    for sid in ids:
        if sid not in SCENARIO_SET:
            raise err.Problem("scenario-not-found", "Unknown benchmark scenario", 404,
                              f"scenario_id must be one of {', '.join(SCENARIO_SET)}.")
    out = []
    for sid in ids:
        r = run_scenario(sid, seed=req.seed, n_mc=req.mc_samples)
        out.append(wire(r.as_dict()) if hasattr(r, "as_dict") else wire(r))
    return envelope({"results": out, "scenario_set": {k: v[1] for k, v in SCENARIO_SET.items()}})


@app.get(API + "/bench")
def bench_cached() -> dict:
    """The committed benchmark fixtures — instant, and what `--demo-safe` serves (§17.6)."""
    import json
    from pathlib import Path
    d = Path("data/fixtures/bench")
    rows = []
    for p in sorted(d.glob("bench_*.json")):
        try:
            rows.append(json.loads(p.read_text()))
        except Exception:
            continue
    if not rows:
        raise err.Problem("no-bench-fixtures", "No benchmark fixtures committed", 404,
                          "Run POST /bench/run, or `python -m oci bench`, to generate them.")
    return envelope({"results": rows, "source": "committed fixtures (data/fixtures/bench)"})
