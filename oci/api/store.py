"""Run registry (SPEC §12). One process, no database — the anti-overengineering rule (§16.7).

A "run" is either a cached screening run on a real altitude shell (a pickle written by
`python -m oci screen`, under `data/cache/runs/`) or a synthetic scenario from D8 addressed as
`scenario:<name>`. Both expose the same bundle, so every endpoint works against either and the
demo can fall back to a scenario with the cable pulled.

Derived products — the graph, a ledger at a given threshold, the capacity map — are computed on
first request and cached on the bundle. `GET /ledger` on a warm bundle is a dict lookup, which is
what keeps it inside the 200 ms budget of §12.6.
"""
from __future__ import annotations

import hashlib
import pickle
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from oci.config import CONFIG
from oci.data.objects import SpaceObject
from oci.graph.build import Cluster, GraphResult, build_graph
from oci.ledger.compute import LedgerResult, compute_ledger
from oci.physics.screen import ScreeningResult
from oci.sim.simulate import OrbitalState

RUNS_DIR = Path("data/cache/runs")
SCENARIO_PREFIX = "scenario:"
_LOCK = threading.RLock()


@dataclass
class RunBundle:
    """Everything the API can serve for one screening run, computed lazily and kept warm."""

    run_id: str
    objects: dict[int, SpaceObject]
    screening: ScreeningResult
    shell: tuple[float, float]
    source: str                                   # "cached_run" | "scenario"
    _graphs: dict[float, GraphResult] = field(default_factory=dict)
    _ledgers: dict[float, LedgerResult] = field(default_factory=dict)
    _capacity: object = None
    _pipelines: dict = field(default_factory=dict)

    # -- derived, lazily ------------------------------------------------------------------
    @property
    def window_days(self) -> float:
        r = self.screening.run
        return (r.window_end - r.window_start).total_seconds() / 86400.0

    def graph(self, pc_threshold: Optional[float] = None) -> GraphResult:
        """Risk clusters depend on the declared threshold (edge floor = Pc*/100, critical count
        = edges ≥ Pc*), so one graph is kept per threshold."""
        key = float(pc_threshold if pc_threshold is not None else CONFIG.thresholds.declared_pc_threshold)
        with _LOCK:
            if key not in self._graphs:
                self._graphs[key] = build_graph(self.screening.conjunctions, self.objects, pc_threshold=key)
            return self._graphs[key]

    def ledger(self, pc_threshold: float) -> LedgerResult:
        key = float(pc_threshold)
        with _LOCK:
            if key not in self._ledgers:
                disk = RUNS_DIR / f"{self.run_id}_ledger_{key:g}.pkl"
                if disk.exists():
                    try:
                        self._ledgers[key] = pickle.load(open(disk, "rb"))
                        return self._ledgers[key]
                    except Exception:
                        pass
                self._ledgers[key] = compute_ledger(self.screening.conjunctions, self.objects,
                                                    self.window_days, pc_threshold=key)
            return self._ledgers[key]

    def clusters(self, pc_threshold: Optional[float] = None) -> list[Cluster]:
        return self.graph(pc_threshold).clusters

    def cluster(self, cluster_id: str, pc_threshold: Optional[float] = None) -> Optional[Cluster]:
        for th in ([pc_threshold] if pc_threshold is not None else []) + list(self._graphs) + [None]:
            c = next((c for c in self.clusters(th) if c.cluster_id == cluster_id), None)
            if c is not None:
                return c
        return None

    def state(self) -> OrbitalState:
        r = self.screening.run
        return OrbitalState(self.objects, r.window_start,
                            frozenset(c.conj_id for c in self.screening.conjunctions),
                            horizon_h=min(CONFIG.decision.horizon_h, self.window_days * 24.0))

    def window_end(self) -> datetime:
        return self.screening.run.window_end

    def config_hash(self) -> str:
        return self.screening.run.config_hash


_BUNDLES: dict[str, RunBundle] = {}


def _run_paths() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted(p for p in RUNS_DIR.glob("run_*.pkl") if "_ledger_" not in p.name)


def list_run_ids() -> list[str]:
    """Cached shell runs, newest last, followed by the synthetic scenarios."""
    from oci.data.synthetic import SCENARIOS
    return [p.stem for p in _run_paths()] + [SCENARIO_PREFIX + n for n in SCENARIOS]


def default_run_id() -> Optional[str]:
    """The run the UI opens on: the largest cached real run, else a scenario."""
    paths = _run_paths()
    if paths:
        return max(paths, key=lambda p: p.stat().st_size).stem
    from oci.data.synthetic import SCENARIOS
    return (SCENARIO_PREFIX + "dead_rocket_body") if "dead_rocket_body" in SCENARIOS else None


def _load_scenario(name: str) -> RunBundle:
    from oci.data.synthetic import load
    from oci.physics.screen import screen
    sc = load(name)
    objs = {o.norad_id: o for o in sc.objects}
    res = screen(list(objs.values()), sc.window_start, sc.window_end)
    alts = [o.orbit.mean_alt_km for o in objs.values()]
    return RunBundle(run_id=SCENARIO_PREFIX + name, objects=objs, screening=res,
                     shell=(min(alts), max(alts)), source="scenario")


def get_bundle(run_id: Optional[str]) -> Optional[RunBundle]:
    """Load (and memoise) one run. `None` → the default run."""
    rid = run_id or default_run_id()
    if rid is None:
        return None
    with _LOCK:
        if rid in _BUNDLES:
            return _BUNDLES[rid]
    if rid.startswith(SCENARIO_PREFIX):
        from oci.data.synthetic import SCENARIOS
        name = rid[len(SCENARIO_PREFIX):]
        if name not in SCENARIOS:
            return None
        b = _load_scenario(name)
    else:
        path = RUNS_DIR / f"{rid}.pkl"
        if not path.exists():
            return None
        d = pickle.load(open(path, "rb"))
        b = RunBundle(run_id=rid, objects=d["objects"], screening=d["result"],
                      shell=tuple(d.get("shell", (0.0, 0.0))), source="cached_run")
    with _LOCK:
        _BUNDLES[rid] = b
    return b


def register(bundle: RunBundle) -> None:
    with _LOCK:
        _BUNDLES[bundle.run_id] = bundle


def save_run(objects: dict[int, SpaceObject], result: ScreeningResult, shell: tuple[float, float]) -> RunBundle:
    """Persist a screening run produced through the API, so it survives a restart."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    rid = result.run.run_id
    pickle.dump({"objects": objects, "result": result, "shell": shell}, open(RUNS_DIR / f"{rid}.pkl", "wb"))
    b = RunBundle(run_id=rid, objects=objects, screening=result, shell=shell, source="cached_run")
    register(b)
    return b


def find_cluster(cluster_id: str) -> tuple[Optional[RunBundle], Optional[Cluster]]:
    """Clusters are addressed globally; search warm bundles first, then every cached run."""
    with _LOCK:
        warm = list(_BUNDLES.values())
    for b in warm:
        c = b.cluster(cluster_id)
        if c:
            return b, c
    for rid in list_run_ids():
        b = get_bundle(rid)
        if b is None:
            continue
        c = b.cluster(cluster_id)
        if c:
            return b, c
    return None, None


def catalogue_freshness(b: Optional[RunBundle]) -> dict:
    if b is None:
        return {"catalogue_epoch_age_h": None, "last_screening_run": None, "n_objects": 0}
    epochs = [o.elements.epoch for o in b.objects.values()]
    now = datetime.now(timezone.utc)
    age = (now - max(epochs)).total_seconds() / 3600.0 if epochs else None
    return {"catalogue_epoch_age_h": round(age, 2) if age is not None else None,
            "last_screening_run": b.run_id, "n_objects": len(b.objects)}


def provenance_id(function: str, unit: str, value) -> str:
    """A stable id for one Traced value, so §13.8's provenance panel has something to key on
    without threading an id through every computation (§10.14 deviation, documented in the README)."""
    return "prov_" + hashlib.sha1(f"{function}|{unit}|{value}".encode()).hexdigest()[:12]


_CATALOGUE: Optional[list] = None
DEBRIS_GROUPS = ("cosmos-1408-debris", "fengyun-1c-debris", "iridium-33-debris", "cosmos-2251-debris")


def catalogue(offline: bool = True) -> list[SpaceObject]:
    """The whole public catalogue, ingested once per process. The capacity engine needs every
    shell (§11.13); a single screened shell cannot show the two peaks."""
    global _CATALOGUE
    with _LOCK:
        if _CATALOGUE is None:
            from oci.data.ingest import ingest
            objs, _ = ingest("active", offline=offline, extra_groups=DEBRIS_GROUPS)
            _CATALOGUE = list(objs)
        return _CATALOGUE


def neighbourhood(b: RunBundle, cluster, hops: int = 1) -> tuple[dict, list]:
    """The objects a replan can actually affect, and the conjunctions among them.

    SPEC §12.6: "chaos only re-runs the affected neighbourhood, never the full catalogue." A
    full re-screen of the demo run is 677 s; the budget is 10. The neighbourhood is the cluster's
    members plus everything within `hops` conjunction edges of them — which is exactly the set a
    burn on a cluster member can newly conflict with over one horizon, because anything further
    away has no edge to reach through.

    Returns (objects, conjunctions) ready for `run_on_state`.
    """
    members = set(cluster.members)
    adj: dict[int, set[int]] = {}
    for c in b.screening.conjunctions:
        adj.setdefault(c.primary_id, set()).add(c.secondary_id)
        adj.setdefault(c.secondary_id, set()).add(c.primary_id)
    frontier = set(members)
    for _ in range(max(0, hops)):
        nxt: set[int] = set()
        for n in frontier:
            nxt |= adj.get(n, set())
        frontier = nxt - members
        members |= nxt
    objs = {nid: o for nid, o in b.objects.items() if nid in members}
    conjs = [c for c in b.screening.conjunctions
             if c.primary_id in members and c.secondary_id in members]
    return objs, conjs
