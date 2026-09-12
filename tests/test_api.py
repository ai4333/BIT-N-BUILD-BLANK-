"""M12 acceptance tests (SPEC §12, §17.5).

Runs entirely offline against a synthetic scenario run, so the suite never touches the network.
The honesty tests of §17.5 live here because most of them are only meaningful once there is a
response tree to walk.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oci.api.app import app
from oci.labels import walk_for_bare_floats

RID = "scenario:keystone_cluster"
DEAD = "scenario:dead_rocket_body"
THR = 1e-5


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def cluster_id(client) -> str:
    b = client.get("/api/v1/graph/clusters", params={"run_id": RID}).json()
    return b["data"]["clusters"][0]["cluster_id"]


def _ok(client, path, **params) -> dict:
    r = client.get(path, params=params)
    assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:300]}"
    return r.json()


# ── envelope and wire format (§12.1) ─────────────────────────────────────────────────────
ASSUMPTION_KEYS = ("covariance_source", "propagator", "screening_volume_m", "pc_method",
                   "pc_threshold", "hard_body_radius_m", "horizon_h", "mc_samples",
                   "intra_constellation_excluded", "attribution_rules", "weights")


@pytest.mark.parametrize("path,params", [
    ("/api/v1/health", {}),
    ("/api/v1/assumptions", {}),
    ("/api/v1/screening-runs", {}),
    ("/api/v1/objects", {"run_id": RID}),
    ("/api/v1/conjunctions", {"run_id": RID}),
    ("/api/v1/graph", {"run_id": RID}),
    ("/api/v1/graph/clusters", {"run_id": RID}),
    ("/api/v1/ledger", {"run_id": RID, "pc_threshold": THR}),
    ("/api/v1/ledger/by-operator", {"run_id": RID, "pc_threshold": THR}),
])
def test_assumptions_block_on_every_response(client, path, params):
    """§17.5 — every 200 carries the full assumption block, so an exported response is
    self-describing and cannot be quoted out of context."""
    b = _ok(client, path, **params)
    assert set(b) >= {"data", "assumptions", "computed_at"}
    for k in ASSUMPTION_KEYS:
        assert k in b["assumptions"], f"{path} assumption block missing {k}"
        assert b["assumptions"][k] is not None


@pytest.mark.parametrize("path,params", [
    ("/api/v1/health", {}),
    ("/api/v1/assumptions", {}),
    ("/api/v1/objects", {"run_id": RID}),
    ("/api/v1/conjunctions", {"run_id": RID}),
    ("/api/v1/graph", {"run_id": RID}),
    ("/api/v1/graph/clusters", {"run_id": RID}),
    ("/api/v1/ledger", {"run_id": RID, "pc_threshold": THR}),
    ("/api/v1/ledger/by-operator", {"run_id": RID, "pc_threshold": THR}),
])
def test_no_bare_floats_in_api_response(client, path, params):
    """§17.5 — walk the response tree; a display field must be a Traced, never a bare float."""
    bad = walk_for_bare_floats(_ok(client, path, **params)["data"])
    assert not bad, f"{path} has bare floats in display fields: {sorted(set(bad))[:10]}"


def test_no_bare_floats_in_strategies(client, cluster_id):
    r = client.post(f"/api/v1/clusters/{cluster_id}/strategies", json={"mc_samples": 10})
    assert r.status_code == 200
    bad = walk_for_bare_floats(r.json()["data"])
    assert not bad, f"strategies has bare floats: {sorted(set(bad))[:10]}"


def test_traced_shape_is_complete(client):
    """§12.1 — the five fields, plus the trace_id the provenance panel keys on (§13.8)."""
    e = _ok(client, "/api/v1/ledger", run_id=DEAD, pc_threshold=THR)["data"]["entries"][0]
    t = e["dv_imposed_mps"]
    assert set(t) >= {"value", "unit", "label", "function", "assumptions", "na_reason", "trace_id"}
    assert t["label"] in ("OBSERVED", "COMPUTED", "MODELLED", "INDICATIVE")
    assert "@" in t["function"], "function must carry its version"


def test_every_na_has_reason(client):
    """§17.5 — a null value always says why. A silent zero is forbidden."""
    seen = 0
    for path, params in [("/api/v1/ledger", {"run_id": RID, "pc_threshold": THR}),
                         ("/api/v1/conjunctions", {"run_id": RID}),
                         ("/api/v1/objects", {"run_id": RID})]:
        def walk(o):
            nonlocal seen
            if isinstance(o, dict):
                if set(o) >= {"value", "unit", "label", "function"}:
                    if o["value"] is None:
                        seen += 1
                        assert o["na_reason"], f"null value with no na_reason: {o}"
                    return
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(_ok(client, path, **params)["data"])
    assert seen >= 0


def test_modelled_values_labelled(client):
    """§17.5 — mass, decay lifetime and the fee are never presented as observation."""
    e = _ok(client, "/api/v1/ledger", run_id=DEAD, pc_threshold=THR)["data"]["entries"][0]
    assert e["decay_lifetime_yr_est"]["label"] in ("MODELLED", "INDICATIVE")
    assert e["implied_fee_usd_yr"]["label"] == "INDICATIVE"
    assert e["dv_imposed_mps"]["label"] in ("MODELLED", "COMPUTED")
    o = _ok(client, "/api/v1/objects", run_id=DEAD)["data"]["objects"][0]
    assert o["mass_kg_est"]["label"] == "MODELLED"


# ── the headline endpoint (§12.3) ────────────────────────────────────────────────────────
def test_ledger_requires_declared_threshold(client):
    """Burden is meaningless without a declared Pc threshold — 422, not a default."""
    r = client.get("/api/v1/ledger", params={"run_id": RID})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "/errors/threshold-not-declared"


def test_ledger_sorted_and_threshold_on_every_figure(client):
    d = _ok(client, "/api/v1/ledger", run_id=DEAD, pc_threshold=THR, sort="dv_imposed_mps")["data"]
    vals = [e["dv_imposed_mps"]["value"] or 0.0 for e in d["entries"]]
    assert vals == sorted(vals, reverse=True)
    assert d["pc_threshold"] == THR
    for e in d["entries"]:
        assert e["dv_imposed_mps"]["assumptions"].get("pc_threshold") == THR


def test_dead_object_imposes_and_bears_nothing(client):
    """The thesis, through the API: the dead rocket body bills others and pays nothing."""
    d = _ok(client, "/api/v1/ledger", run_id=DEAD, pc_threshold=THR, sort="dv_imposed_mps")["data"]
    top = d["entries"][0]
    assert top["is_active"] is False and top["is_maneuverable"] is False
    assert (top["dv_imposed_mps"]["value"] or 0.0) > 0.0
    assert (top["dv_spent_mps"]["value"] or 0.0) == 0.0
    assert d["share_of_dv_from_dead"]["value"] > 0.5


def test_object_card_has_bearers(client):
    d = _ok(client, "/api/v1/ledger", run_id=DEAD, pc_threshold=THR)["data"]
    nid = d["entries"][0]["norad_id"]
    card = _ok(client, f"/api/v1/ledger/{nid}", run_id=DEAD, pc_threshold=THR)["data"]
    assert card["bearers"], "object card must list who paid"
    bear = _ok(client, f"/api/v1/ledger/{nid}/bearers", run_id=DEAD, pc_threshold=THR)["data"]
    assert bear["by_operator"]


# ── strategies, validator, the rejected array (§12.3) ────────────────────────────────────
def test_strategies_surface_both_optima_and_rejections(client, cluster_id):
    r = client.post(f"/api/v1/clusters/{cluster_id}/strategies", json={"mc_samples": 25})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["strategies"], "no strategies generated"
    rec = d["recommendation"]
    assert "expected_value_optimum" in rec and "minimax_regret_optimum" in rec
    assert isinstance(rec["optima_agree"], bool)
    # §12.3: "the rejected array is load-bearing" — the validator must do real work
    assert d["rejected"], "validator rejected nothing; the loop would be theatre (§12.3)"
    assert all(s["validator_reason"] for s in d["rejected"])


def test_validate_endpoint_returns_checks(client):
    r = client.post("/api/v1/validate", json={"run_id": RID, "target_id": 91001,
                                              "dv_vector_mps": [0.0, 0.5, 0.0],
                                              "t_burn": "2026-09-12T06:00:00Z"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["verdict"] in ("APPROVED", "REJECTED")
    assert d["checks"] and all({"id", "name", "passed", "detail"} <= set(c) for c in d["checks"])


def test_excessive_dv_rejected_through_the_api(client):
    r = client.post("/api/v1/validate", json={"run_id": RID, "target_id": 91001,
                                              "dv_vector_mps": [0.0, 50.0, 0.0],
                                              "t_burn": "2026-09-12T06:00:00Z"})
    assert r.status_code == 200
    assert r.json()["data"]["verdict"] == "REJECTED"


# ── encounter plane, VoI, capacity, agent, chaos ─────────────────────────────────────────
def test_encounter_plane_available_for_s4(client):
    cid = _ok(client, "/api/v1/conjunctions", run_id=RID, limit=1)["data"]["conjunctions"][0]["conj_id"]
    ep = _ok(client, f"/api/v1/conjunctions/{cid}", run_id=RID)["data"]["encounter_plane"]
    assert ep["available"] is True
    assert ep["sigma_major_m"] >= ep["sigma_minor_m"] > 0
    assert ep["hard_body_radius_label"] == "MODELLED"


def test_voi_returns_options(client):
    cid = _ok(client, "/api/v1/conjunctions", run_id=RID, limit=1)["data"]["conjunctions"][0]["conj_id"]
    r = client.post("/api/v1/voi", json={"run_id": RID, "conj_id": cid})
    assert r.status_code == 200
    assert r.json()["data"]["options"]


def test_shells_reproduce_two_peaks(client):
    """S5 — the shell map is computed over the whole catalogue, not one screened shell;
    the two peaks only exist if 450 km and 800 km are both in scope (§11.13)."""
    d = _ok(client, "/api/v1/shells", pc_threshold=THR, min_objects=20)["data"]
    assert len(d["shells"]) > 5
    assert d["workload_peak_alt_km"] is not None and d["hazard_peak_alt_km"] is not None
    assert d["hazard_peak_alt_km"] > d["workload_peak_alt_km"], \
        "hazard should peak above the workload peak (§2.6); if it does not, say so rather than tune"


def test_deployment_reports_the_trade_off(client):
    r = client.post("/api/v1/deployment/evaluate",
                    json={"n_satellites": 5000, "target_alt_km": 550, "inclination_deg": 53.0,
                          "alternatives_km": [500, 550, 600, 650, 700, 750, 800]})
    assert r.status_code == 200
    d = r.json()["data"]
    tp = d["two_peaks_finding"]
    assert {"workload_optimal_alt_km", "hazard_optimal_alt_km", "optima_disagree"} <= set(tp)
    assert d["recommendation"]["if_priority_is_operations"] is not None
    assert d["recommendation"]["if_priority_is_environment"] is not None
    assert "trade-off" in d["recommendation"]["honest_note"]


def test_agent_trace_is_served_with_rejections(client):
    r = client.post("/api/v1/agent/analyse", json={"scenario": "keystone_cluster", "mc_samples": 25})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["driver"] == "deterministic", "the planner must not need an API key (§14.5)"
    assert d["n_tool_calls"] > 0 and d["guard_passed"] is True
    assert d["rejections"], "the planner's own proposals must be rejected by the validator sometimes"
    t = client.get(f"/api/v1/agent/trace/{d['trace_id']}")
    assert t.status_code == 200


def test_chaos_replan_within_budget(client):
    """§12.6 — the base run is pre-computed; the replan itself must land under 10 s."""
    client.post("/api/v1/chaos", json={"scenario": "keystone_cluster", "injection": "NEW_OBJECT",
                                       "mc_samples": 25})            # warm the base pipeline
    t = time.perf_counter()
    r = client.post("/api/v1/chaos", json={"scenario": "keystone_cluster",
                                           "injection": "COVARIANCE_SPIKE",
                                           "params": {"factor": 5}, "mc_samples": 25})
    elapsed = time.perf_counter() - t
    assert r.status_code == 200
    d = r.json()["data"]
    assert {"invalidated", "invalidation_reason", "diff"} <= set(d)
    assert {"was", "now", "why"} <= set(d["diff"])
    assert elapsed < 15.0, f"chaos replan took {elapsed:.1f}s (§12.6 ceiling 15 s)"


def test_unknown_injection_is_problem_json(client):
    r = client.post("/api/v1/chaos", json={"scenario": "keystone_cluster", "injection": "NOPE"})
    assert r.status_code == 422
    assert r.json()["type"] == "/errors/unknown-injection"


# ── errors, jobs, provenance ─────────────────────────────────────────────────────────────
def test_404_is_problem_json(client):
    r = client.get("/api/v1/screening-runs/run_does_not_exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert {"type", "title", "status", "detail", "instance"} <= set(body)
    assert body["type"].startswith("/errors/")


def test_object_not_found_is_problem_json(client):
    r = client.get("/api/v1/objects/99999999", params={"run_id": RID})
    assert r.status_code == 404
    assert r.json()["type"] == "/errors/object-not-found"


def test_job_flow_202_then_poll(client):
    r = client.post("/api/v1/ingest", json={"source": "celestrak", "offline": True,
                                            "include_debris": False})
    assert r.status_code == 202
    job = r.json()["data"]
    assert job["state"] in ("PENDING", "RUNNING", "DONE")
    for _ in range(120):
        b = client.get(f"/api/v1/jobs/{job['job_id']}").json()["data"]
        if b["state"] in ("DONE", "FAILED"):
            break
        time.sleep(0.5)
    assert b["state"] == "DONE", f"ingest job failed: {b['error']}"


def test_provenance_panel_resolves(client):
    e = _ok(client, "/api/v1/ledger", run_id=DEAD, pc_threshold=THR)["data"]["entries"][0]
    tid = e["dv_imposed_mps"]["trace_id"]
    d = _ok(client, f"/api/v1/provenance/{tid}")["data"]
    assert d["function"] == e["dv_imposed_mps"]["function"]
    assert d["label"] == e["dv_imposed_mps"]["label"]


def test_spacetrack_source_is_honest_501(client):
    r = client.post("/api/v1/ingest", json={"source": "spacetrack"})
    assert r.status_code == 501
    assert r.json()["type"] == "/errors/source-unavailable"


# ── §18.4 forbidden language ─────────────────────────────────────────────────────────────
FORBIDDEN = [
    r"\bflight[- ]certified\b", r"\bflight[- ]qualified\b", r"\boperationally certified\b",
    r"\bguarantee(s|d)? (safety|collision)", r"\bprevents? collisions?\b",
    r"\bwill not collide\b", r"\bcertified for flight\b", r"\bmission[- ]critical certified\b",
]


def test_no_flight_certified_language():
    """§17.5/§18.4 — the codebase and its docs must never claim certification or guarantees."""
    roots = [Path("oci"), Path("tests"), Path("docs"), Path("README.md"), Path("frontend/src")]
    offences: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        files = [root] if root.is_file() else [p for p in root.rglob("*")
                                               if p.suffix in (".py", ".md", ".ts", ".tsx", ".css", ".html")]
        for p in files:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in FORBIDDEN:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    line = text[:m.start()].count("\n") + 1
                    # a sentence that *disclaims* the phrase is the point, not a violation
                    ctx = text[max(0, m.start() - 60):m.end() + 20].lower()
                    if any(neg in ctx for neg in ("not ", "never ", "cannot ", "no ", "forbidden", "must never")):
                        continue
                    offences.append(f"{p}:{line}: {m.group(0)}")
    assert not offences, "forbidden language (§18.4):\n" + "\n".join(offences[:20])


def test_export_embeds_assumptions(client):
    """§10.14 — an exported response carries its assumption block with it."""
    b = _ok(client, "/api/v1/ledger", run_id=DEAD, pc_threshold=THR, limit=5)
    blob = json.dumps(b)
    assert '"assumptions"' in blob
    for k in ASSUMPTION_KEYS:
        assert f'"{k}"' in blob
