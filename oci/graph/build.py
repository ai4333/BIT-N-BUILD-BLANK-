"""M4 — Graph engine (SPEC §10.4).

Prior art, credited here as the spec requires: Lewis, Newland, Swinerd & Saunders (2010)
established the conjunction network and centrality-ranked removal; Rao (2023/24,
arXiv:2410.04599) computed it on real SOCRATES data. We reimplement it and add the
keystone-vs-max-Pc disagreement check and the feasibility-restricted keystone score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import networkx as nx

from oci.config import CONFIG
from oci.data.objects import SpaceObject
from oci.physics.screen import Conjunction


@dataclass
class Cluster:
    cluster_id: str
    members: list[int]
    n_edges: int
    total_weight: float
    keystone_id: Optional[int]
    keystone_selected_by: str
    keystone_score: float
    max_pc_object_id: Optional[int]
    max_pc_edge: Optional[tuple[int, int]]
    max_pc: Optional[float]
    disagreement: bool
    critical_conjunctions: int


@dataclass
class GraphResult:
    G: nx.Graph
    weight_rule: str
    clusters: list[Cluster]
    centrality: dict[str, dict[int, float]]
    disagreement_clusters: list[str] = field(default_factory=list)

    def cluster_of(self, norad_id: int) -> Optional[Cluster]:
        for c in self.clusters:
            if norad_id in c.members:
                return c
        return None


def _edge_default() -> dict:
    return {"n_conj": 0, "sum_pc": 0.0, "max_pc": None, "min_miss": float("inf"),
            "sum_inv_miss": 0.0, "mean_v_rel": 0.0, "pair_class": None, "conj_ids": []}


def build_graph(conjs: Sequence[Conjunction], objects: dict[int, SpaceObject],
                w_min: float | None = None, weight_rule: str | None = None,
                pc_threshold: float | None = None) -> GraphResult:
    w_min = CONFIG.graph.w_min if w_min is None else w_min
    rule = weight_rule or CONFIG.graph.weight_rule
    pc_star = pc_threshold if pc_threshold is not None else CONFIG.thresholds.declared_pc_threshold
    G = nx.Graph()
    usable = [c for c in conjs if not (c.intra_constellation and CONFIG.attribution.exclude_intra_constellation)]
    # Never mix weight rules: if any edge lacks Pc, the whole graph uses 1/d_miss.
    if rule == "pc" and any(c.pc.value is None for c in usable):
        rule = "inv_miss"
    for c in usable:
        for nid in (c.primary_id, c.secondary_id):
            if nid not in G:
                o = objects[nid]
                G.add_node(nid, name=o.object_name, type=o.object_type, active=o.is_active,
                           maneuverable=o.is_maneuverable, operator=o.operator, mass=o.mass_kg_est,
                           shell=o.shell_id)
        e = G.edges[c.primary_id, c.secondary_id] if G.has_edge(c.primary_id, c.secondary_id) else _edge_default()
        e["n_conj"] += 1
        if c.pc.value is not None:
            e["sum_pc"] += c.pc.value
            e["max_pc"] = c.pc.value if e["max_pc"] is None else max(e["max_pc"], c.pc.value)
        e["min_miss"] = min(e["min_miss"], c.miss_m)
        e["sum_inv_miss"] += 1.0 / max(c.miss_m, 1.0)
        e["mean_v_rel"] = ((e["mean_v_rel"] * (e["n_conj"] - 1)) + float(c.rel_speed_mps.value)) / e["n_conj"]
        e["pair_class"] = c.pair_class
        e["conj_ids"].append(c.conj_id)
        G.add_edge(c.primary_id, c.secondary_id, **e)
    for u, v, e in G.edges(data=True):
        e["w"] = e["sum_pc"] if rule == "pc" else e["sum_inv_miss"]
    G.graph["weight_rule"] = rule

    sub = G.edge_subgraph([e for e in G.edges if G.edges[e]["w"] >= w_min]).copy() if G.number_of_edges() else G
    components = list(nx.connected_components(sub)) if sub.number_of_nodes() else []

    cent: dict[str, dict[int, float]] = {
        "degree": dict(G.degree()),
        "wdegree": {n: float(sum(G.edges[n, m]["w"] for m in G[n])) for n in G},
        "betweenness": nx.betweenness_centrality(G, weight="w") if G.number_of_nodes() else {},
        "eigenvector": {},
    }
    for comp in components:
        H = G.subgraph(comp)
        try:
            if H.number_of_nodes() == 1:
                cent["eigenvector"].update({n: 1.0 for n in H})
            elif H.number_of_nodes() < 50:
                cent["eigenvector"].update(nx.eigenvector_centrality(H, weight="w", max_iter=2000))
            else:
                cent["eigenvector"].update(nx.eigenvector_centrality_numpy(H, weight="w"))
        except Exception:
            cent["eigenvector"].update({n: cent["wdegree"][n] for n in H})   # documented fallback

    clusters: list[Cluster] = []
    for comp in components:
        members = sorted(comp)
        H = G.subgraph(members)
        # keystone: feasibility-restricted risk-weighted degree. A manoeuvre keystone must be
        # maneuverable; a removal keystone must be inactive. We report the manoeuvre keystone
        # if any exists, else the removal keystone.
        def score(n: int, feasible) -> float:
            return float(sum(G.edges[n, m]["w"] for m in G[n] if m in comp)) if feasible(n) else -1.0
        man = {n: score(n, lambda x: G.nodes[x]["maneuverable"]) for n in members}
        rem = {n: score(n, lambda x: not G.nodes[x]["active"]) for n in members}
        if max(man.values()) > 0:
            key, sel, ks = max(man, key=man.get), "risk_weighted_degree (maneuverable)", max(man.values())
        elif max(rem.values()) > 0:
            key, sel, ks = max(rem, key=rem.get), "risk_weighted_degree (removal)", max(rem.values())
        else:
            key, sel, ks = None, "none feasible", 0.0
        # max-Pc edge and the object "in the worst conjunction" (its maneuverable end, else either)
        best_edge, best_pc = None, None
        for u, v, e in H.edges(data=True):
            val = e["max_pc"] if rule == "pc" else e["sum_inv_miss"]
            if val is not None and (best_pc is None or val > best_pc):
                best_edge, best_pc = (u, v), val
        max_pc_obj = None
        if best_edge:
            u, v = best_edge
            cands = [n for n in (u, v) if G.nodes[n]["maneuverable"]] or [u, v]
            max_pc_obj = max(cands, key=lambda n: cent["wdegree"][n]) if len(cands) > 1 else cands[0]
        critical = sum(1 for _, _, e in H.edges(data=True) if e["max_pc"] is not None and e["max_pc"] >= pc_star)
        cid = f"clu_{min(members)}_{len(members)}"
        clusters.append(Cluster(
            cluster_id=cid, members=members, n_edges=H.number_of_edges(),
            total_weight=float(sum(e["w"] for _, _, e in H.edges(data=True))),
            keystone_id=key, keystone_selected_by=sel, keystone_score=ks,
            max_pc_object_id=max_pc_obj, max_pc_edge=best_edge,
            max_pc=best_pc if rule == "pc" else None,
            disagreement=(key is not None and max_pc_obj is not None and key != max_pc_obj),
            critical_conjunctions=critical,
        ))
    clusters.sort(key=lambda c: (-int(c.disagreement), -c.total_weight))
    return GraphResult(G=G, weight_rule=rule, clusters=clusters, centrality=cent,
                       disagreement_clusters=[c.cluster_id for c in clusters if c.disagreement])
