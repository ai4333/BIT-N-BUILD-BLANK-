"""M11 — the planner (SPEC §10.11, §14). ONE agent, a free-form action space, an authoritative
validator, and a fabrication guard. Two interchangeable drivers with the same trace format:

  * `LLMPlanner`          — an LLM via a function-calling SDK tool-use loop (needs LLM_API_KEY /
                             ANTHROPIC_API_KEY). Temperature is not exposed on the current model
                             generation; determinism comes from the deterministic tools, a fixed
                             Monte-Carlo seed, and the guard.
  * `DeterministicPlanner` — the spec's sanctioned fallback (§16.5): executes the §14.4 PROCEDURE
                             step by step with the same tools and writes the explanation from
                             computed values only. Used when no key is present and as the
                             demo-safe path.

Both produce an `AgentTrace`: every tool call, every rejection, the final text, and the guard's
verdict. The UI's agent-trace drawer (S7) renders that.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional

from oci.agent.guard import check_no_fabricated_numbers
from oci.agent.prompts import SYSTEM_PROMPT, USER_TEMPLATE
from oci.agent.tools import ToolContext, anthropic_tool_defs, call_tool
from oci.config import CONFIG


@dataclass
class AgentTrace:
    trace_id: str
    driver: str                      # "llm:<model>" | "deterministic"
    cluster_id: str
    tool_calls: list[dict] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    recommendation: Optional[str] = None
    explanation: str = ""
    guard_violations: list[str] = field(default_factory=list)
    guard_passed: bool = True
    fell_back_to_template: bool = False
    n_llm_calls: int = 0
    elapsed_s: float = 0.0
    error: Optional[str] = None


def _recommendation_line(text: str) -> Optional[str]:
    for line in text.splitlines():
        if line.strip().upper().startswith("RECOMMENDATION:"):
            return line.split(":", 1)[1].strip()
    return None


# ── deterministic driver ─────────────────────────────────────────────────────────────────
class DeterministicPlanner:
    """Runs the §14.4 PROCEDURE literally, through the tool registry, and templates the answer."""

    def run(self, ctx: ToolContext, cluster_id: str, trace_id: str = "trace_det") -> AgentTrace:
        t0 = time.perf_counter()
        tr = AgentTrace(trace_id, "deterministic", cluster_id)
        pc_star = CONFIG.thresholds.declared_pc_threshold
        # 1. structure
        cl = call_tool(ctx, "get_cluster", {"cluster_id": cluster_id})
        crit = sorted([c for c in cl["conjunctions"] if c["pc"]["value"] is not None and c["pc"]["value"] >= pc_star],
                      key=lambda c: -c["pc"]["value"])
        if not crit:
            text = (f"RECOMMENDATION: HOLD — no conjunction in cluster {cluster_id} exceeds the declared threshold [source: get_cluster]\n"
                    f"WHY:\n  1. critical_conjunctions = {cl['critical_conjunctions']} at Pc* = {pc_star:g} [source: get_cluster]\n"
                    f"TRADE-OFFS: none\nCONFIDENCE BASIS: not applicable\nASSUMPTIONS THAT MATTER: Pc threshold {pc_star:g}; covariance source per conjunction")
            return self._finish(tr, ctx, text, t0)
        top = crit[0]
        # 2. the critical edge
        cj = call_tool(ctx, "get_conjunction", {"conj_id": top["conj_id"]})
        # 3. VoI
        voi = call_tool(ctx, "compute_voi", {"conj_id": top["conj_id"]})
        # 4. candidates: HOLD, WAIT (if VoI suggests), clearing burns on keystone and max-Pc object
        ids = []
        ids.append(call_tool(ctx, "simulate_action", {"cluster_id": cluster_id, "action": "HOLD"})["strategy_id"])
        if voi.get("recommended_wait_min") is not None:
            bearer = top["primary_id"] if ctx.state.objects[top["primary_id"]].is_maneuverable else top["secondary_id"]
            ids.append(call_tool(ctx, "simulate_action", {"cluster_id": cluster_id, "action": "WAIT", "wait_min": voi["recommended_wait_min"], "target_id": bearer})["strategy_id"])
        candidates = []
        for nid in dict.fromkeys([cl["keystone_id"], cl["max_pc_object_id"]]):
            if nid is None or not ctx.state.objects[nid].is_maneuverable:
                continue
            burn = self._clearing_burn(ctx, nid, crit, pc_star)
            if burn:
                candidates.append(burn)
        # "operator instinct" candidates, proposed freely so the validator has real work (§14.3):
        # a big along-track burn on the max-Pc object one orbit out, and a late burn 40 min before TCA.
        mp = cl["max_pc_object_id"]
        if mp is not None and ctx.state.objects[mp].is_maneuverable:
            conj_top = next(x for x in ctx.conjunctions if x.conj_id == top["conj_id"])
            per = ctx.state.objects[mp].orbit.period_min
            candidates.append({"target_id": mp, "dv": [0.0, 1.0, 0.0], "t_burn": (conj_top.tca - timedelta(minutes=per)).isoformat(), "why": "instinct: 1 m/s along-track"})
            candidates.append({"target_id": mp, "dv": [0.0, 0.3, 0.0], "t_burn": (conj_top.tca - timedelta(minutes=40)).isoformat(), "why": "instinct: late burn"})
        for b in candidates:
            r = call_tool(ctx, "simulate_action", {"cluster_id": cluster_id, "action": "MANEUVER", "target_id": b["target_id"],
                                                   "dv_vector_mps": b["dv"], "t_burn": b["t_burn"]})
            ids.append(r["strategy_id"])
        # 5–6. uncertainty + rank
        for sid in ids:
            call_tool(ctx, "run_uncertainty_analysis", {"cluster_id": cluster_id, "strategy_id": sid, "n_samples": CONFIG.decision.mc_samples_interactive})
        rank = call_tool(ctx, "rank_strategies", {"cluster_id": cluster_id, "strategy_ids": ids})
        # 7. validate EVERY proposed burn (the operator wants to see what was infeasible and why);
        #    the recommendation is the best-ranked approved candidate. A rejected burn whose reason
        #    is timing (C3/C4) or a secondary conjunction (C7) is re-proposed once, one orbit earlier
        #    and at half the magnitude — the reason is incorporated, not retried verbatim.
        verdicts: dict[str, str] = {}
        for sid in list(ids):
            s = ctx.strategies[sid]
            if s.action.kind == "MANEUVER" and s.action.burn:
                v = call_tool(ctx, "validate_action", {"target_id": s.action.burn.target_id, "dv_vector_mps": list(s.action.burn.dv_rtn_mps),
                                                       "t_burn": s.action.burn.t_burn.isoformat()})
                verdicts[sid] = v["verdict"]
                if v["verdict"] == "REJECTED":
                    tr.rejections.append({"strategy_id": sid, "action": s.action.describe(), "reason": v["reason"], "violated": v["violated"]})
                    if any(x in v["violated"] for x in ("C3", "C4", "C7")):
                        alt = self._retry_burn(ctx, cluster_id, s, crit, pc_star)
                        if alt:
                            v2 = call_tool(ctx, "validate_action", alt)
                            if v2["verdict"] == "APPROVED":
                                r = call_tool(ctx, "simulate_action", {"cluster_id": cluster_id, "action": "MANEUVER", **alt})
                                call_tool(ctx, "run_uncertainty_analysis", {"cluster_id": cluster_id, "strategy_id": r["strategy_id"], "n_samples": CONFIG.decision.mc_samples_interactive})
                                ids.append(r["strategy_id"]); verdicts[r["strategy_id"]] = "APPROVED"
                            else:
                                tr.rejections.append({"strategy_id": sid + "_retry", "action": f"re-proposed: {alt['dv_vector_mps']} m/s at {alt['t_burn'][:16]}Z", "reason": v2["reason"], "violated": v2["violated"]})
            elif s.action.kind == "WAIT" and s.action.then is not None:
                b = s.action.then.burn
                v = call_tool(ctx, "validate_action", {"target_id": b.target_id, "dv_vector_mps": list(b.dv_rtn_mps), "t_burn": b.t_burn.isoformat()})
                verdicts[sid] = v["verdict"]
                if v["verdict"] == "REJECTED":
                    tr.rejections.append({"strategy_id": sid, "action": s.action.describe(), "reason": v["reason"], "violated": v["violated"]})
            else:
                verdicts[sid] = "APPROVED"
        if len(ids) > len(rank["by_expected"]):
            rank = call_tool(ctx, "rank_strategies", {"cluster_id": cluster_id, "strategy_ids": ids})
        approved = [ctx.strategies[r["strategy_id"]] for r in rank["by_expected"] if verdicts.get(r["strategy_id"]) == "APPROVED"]
        clearing_ok = [s for s in approved if s.pc_after is not None and s.pc_after.value is not None and s.pc_after.value < pc_star]
        chosen = (clearing_ok or approved or [ctx.strategies[ids[0]]])[0]     # operator's rule: clear Pc* if any approved plan can
        # 8. explanation from computed values only
        rr = next(r for r in rank["by_expected"] if r["strategy_id"] == chosen.strategy_id) if any(r["strategy_id"] == chosen.strategy_id for r in rank["by_expected"]) else None
        hold = next((r for r in rank["by_expected"] if ctx.strategies[r["strategy_id"]].action.kind == "HOLD"), None)
        regret_opt = rank["minimax_regret_optimum"]
        lines = [f"RECOMMENDATION: {chosen.action.describe()}", "WHY:"]
        lines.append(f"  1. Cluster {cluster_id}: keystone object {cl['keystone_id']} ({cl['keystone_selected_by']}), max-Pc object {cl['max_pc_object_id']}"
                     + (" — they differ" if cl["keystone_differs_from_max_pc"] else " — same object") + " [source: get_cluster]")
        lines.append(f"  2. Critical conjunction {top['conj_id']}: Pc {top['pc']['value']:.2e} ({top['pc']['label']}, covariance {cj['covariance_source']}), miss {top['miss_distance_m']['value']:.0f} m, TCA {top['tca']} [source: get_conjunction]")
        if voi.get("options"):
            best = max(voi["options"], key=lambda o: o["voi_net"]["value"] if o["voi_net"]["value"] is not None else -1e9)
            lines.append(f"  3. Value of information: acting now costs {voi['cost_now']['value']:.3f} (Δv {voi['dv_now_mps']['value']:.3f} m/s); best wait {best['wait_min']:.0f} min has VoI {best['voi_net']['value']:+.3f} → "
                         + ("waiting is recommended" if voi["recommended_wait_min"] is not None else "act now") + " [source: compute_voi]")
        if rr is not None:
            lines.append(f"  4. Expected systemic cost {rr['expected_cost']:.3f}" + (f" vs HOLD {hold['expected_cost']:.3f}" if hold else "")
                         + f"; post-action max Pc {rr['pc_after']:.2e}; Δv {rr['dv_mps']:.3f} m/s [source: rank_strategies]")
        if tr.rejections:
            lines.append(f"  5. {len(tr.rejections)} candidate burn(s) rejected by the validator: " + "; ".join(f"{x['action'][:44]} → {', '.join(x['violated'])}" for x in tr.rejections) + " [source: validate_action]")
        lines.append(f"TRADE-OFFS: Δv {chosen.action.total_dv_mps:.3f} m/s spent" + (f"; expected-value optimum and minimax-regret optimum differ ({regret_opt}) — a single-satellite operator may prefer the regret optimum" if regret_opt != chosen.strategy_id else "; expected-value and minimax-regret optima agree"))
        sf = rr["safe_fraction"] if rr is not None else None
        lines.append("CONFIDENCE BASIS: " + (f"{sf*100:.0f} of 100 sampled uncertainty scenarios remained below Pc* under the {cj['covariance_source']} covariance model (run_uncertainty_analysis) — NOT a prediction accuracy" if sf is not None else "Monte Carlo not run"))
        lines.append(f"ASSUMPTIONS THAT MATTER: Pc threshold {pc_star:g} (MODELLED trigger); covariance source {cj['covariance_source']} (A1); hard-body radius {CONFIG.pc.hard_body_radius_m} m (MODELLED)")
        return self._finish(tr, ctx, "\n".join(lines), t0)

    def _clearing_burn(self, ctx: ToolContext, nid: int, crit: list[dict], pc_star: float) -> Optional[dict]:
        from oci.physics.maneuver import dv_to_clear
        mine = [c for c in crit if nid in (c["primary_id"], c["secondary_id"])]
        if not mine:
            return None
        c = mine[0]
        other = ctx.state.objects[c["secondary_id"] if nid == c["primary_id"] else c["primary_id"]]
        conj = next(x for x in ctx.conjunctions if x.conj_id == c["conj_id"])
        r = dv_to_clear(ctx.state.objects[nid], other, conj.tca, pc_star)
        if r.dv_mps.value is None or r.t_burn is None:
            return None
        return {"target_id": nid, "dv": [r.dv_mps.value if d == r.direction else 0.0 for d in "RTN"], "t_burn": r.t_burn.isoformat()}

    def _retry_burn(self, ctx: ToolContext, cluster_id: str, s, crit, pc_star) -> Optional[dict]:
        b = s.action.burn
        obj = ctx.state.objects[b.target_id]
        earlier = b.t_burn - timedelta(minutes=obj.orbit.period_min)
        if earlier <= ctx.state.epoch + timedelta(minutes=CONFIG.validator.uplink_lead_min):
            return None
        return {"target_id": b.target_id, "dv_vector_mps": [x * 0.5 for x in b.dv_rtn_mps], "t_burn": earlier.isoformat()}

    def _finish(self, tr: AgentTrace, ctx: ToolContext, text: str, t0: float) -> AgentTrace:
        tr.tool_calls = list(ctx.calls)
        tr.explanation = text
        tr.recommendation = _recommendation_line(text)
        tr.guard_violations = check_no_fabricated_numbers(text, [c["result"] for c in ctx.calls] + [{"pc_threshold": CONFIG.thresholds.declared_pc_threshold, "hbr": CONFIG.pc.hard_body_radius_m}])
        tr.guard_passed = not tr.guard_violations
        tr.elapsed_s = time.perf_counter() - t0
        return tr


# ── LLM driver ───────────────────────────────────────────────────────────────────────────
class LLMPlanner:
    def __init__(self, model: str | None = None, max_tool_calls: int | None = None):
        import anthropic
        key = os.environ.get("LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        self.model = model or CONFIG.agent.model
        self.max_tool_calls = max_tool_calls or CONFIG.agent.max_tool_calls

    def run(self, ctx: ToolContext, cluster_id: str, trace_id: str = "trace_llm") -> AgentTrace:
        t0 = time.perf_counter()
        tr = AgentTrace(trace_id, f"llm:{self.model}", cluster_id)
        messages = [{"role": "user", "content": USER_TEMPLATE.format(cluster_id=cluster_id, epoch=ctx.state.epoch.isoformat(),
                                                                     pc_threshold=CONFIG.thresholds.declared_pc_threshold)}]
        tools = anthropic_tool_defs()
        n_calls = 0
        final_text = ""
        try:
            while True:
                resp = self.client.messages.create(
                    model=self.model, max_tokens=8000, system=SYSTEM_PROMPT, tools=tools, messages=messages,
                    thinking={"type": "adaptive"}, output_config={"effort": "medium"},
                )
                tr.n_llm_calls += 1
                messages.append({"role": "assistant", "content": resp.content})
                if resp.stop_reason != "tool_use":
                    final_text = "".join(b.text for b in resp.content if b.type == "text")
                    break
                results = []
                for block in resp.content:
                    if block.type != "tool_use":
                        continue
                    n_calls += 1
                    if n_calls > self.max_tool_calls:
                        tr.error = "agent-tool-limit-exceeded"
                        results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                        "content": f"tool call limit {self.max_tool_calls} exceeded — finish with what you have"})
                        continue
                    out = call_tool(ctx, block.name, dict(block.input))
                    if block.name == "validate_action" and out.get("verdict") == "REJECTED":
                        tr.rejections.append({"strategy_id": f"llm_{n_calls}", "action": json.dumps(block.input, default=str), "reason": out["reason"], "violated": out["violated"]})
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)[:12000]})
                messages.append({"role": "user", "content": results})
                if tr.error:
                    resp = self.client.messages.create(model=self.model, max_tokens=4000, system=SYSTEM_PROMPT, messages=messages,
                                                       thinking={"type": "adaptive"}, output_config={"effort": "low"})
                    final_text = "".join(b.text for b in resp.content if b.type == "text")
                    break
        except Exception as e:
            tr.error = f"{type(e).__name__}: {e}"
        tr.tool_calls = list(ctx.calls)
        tr.explanation = final_text
        tr.recommendation = _recommendation_line(final_text)
        tr.guard_violations = check_no_fabricated_numbers(final_text, [c["result"] for c in ctx.calls] + [{"pc_threshold": CONFIG.thresholds.declared_pc_threshold}])
        tr.guard_passed = not tr.guard_violations and not tr.error
        tr.elapsed_s = time.perf_counter() - t0
        return tr


def plan(ctx: ToolContext, cluster_id: str, prefer_llm: bool = True, trace_id: str | None = None) -> AgentTrace:
    """§14.6: LLM if available; if the guard fails, regenerate once, then fall back to the
    deterministic template. Log the incident on the trace."""
    have_key = bool(os.environ.get("LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    tid = trace_id or f"trace_{int(time.time())}"
    if prefer_llm and have_key:
        llm = LLMPlanner()
        tr = llm.run(ctx, cluster_id, tid)
        if tr.guard_passed:
            return tr
        ctx.calls.clear(); ctx.strategies.clear()
        tr2 = llm.run(ctx, cluster_id, tid + "_retry")
        if tr2.guard_passed:
            return tr2
        ctx.calls.clear(); ctx.strategies.clear()
        det = DeterministicPlanner().run(ctx, cluster_id, tid + "_fallback")
        det.fell_back_to_template = True
        det.guard_violations = tr2.guard_violations
        det.error = tr2.error or "LLM output failed the fabrication guard twice; template explanation used"
        return det
    return DeterministicPlanner().run(ctx, cluster_id, tid)
