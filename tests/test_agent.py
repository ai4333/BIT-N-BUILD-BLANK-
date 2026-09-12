"""SPEC §10.11 M11 planner acceptance tests (deterministic driver — no LLM credentials needed).

The planner must (a) reach its recommendation only through the tool registry, (b) never state a
number that no tool returned, (c) show validator rejections that were not scripted, and (d) fall
back to a HOLD it can defend when nothing better is approved."""
import pytest

from oci.agent.guard import check_no_fabricated_numbers
from oci.agent.planner import DeterministicPlanner, plan
from oci.agent.tools import TOOLS, ToolContext, call_tool
from oci.data.synthetic import load
from oci.graph.build import build_graph
from oci.ledger.compute import compute_ledger
from oci.physics.screen import screen
from oci.sim.simulate import OrbitalState


def _ctx(name: str) -> ToolContext:
    sc = load(name)
    objs = {o.norad_id: o for o in sc.objects}
    res = screen(sc.objects, sc.window_start, sc.window_end)
    g = build_graph(res.conjunctions, objs)
    led = compute_ledger(res.conjunctions, objs, (sc.window_end - sc.window_start).total_seconds() / 86400.0)
    state = OrbitalState(objs, sc.window_start, frozenset(c.conj_id for c in res.conjunctions))
    return ToolContext(state, res.conjunctions, g, led)


@pytest.fixture(scope="module")
def keystone_trace():
    ctx = _ctx("keystone_cluster")
    return ctx, plan(ctx, ctx.graph.clusters[0].cluster_id, prefer_llm=False)


def test_eight_tools_registered():
    assert set(TOOLS) >= {"get_cluster", "get_ledger_entry", "get_conjunction", "simulate_action", "run_uncertainty_analysis",
                          "compute_voi", "rank_strategies", "validate_action"}
    assert len(TOOLS) in (8, 9)   # + evaluate_deployment once the capacity engine exists


def test_agent_cannot_fabricate_numbers(keystone_trace):
    ctx, tr = keystone_trace
    assert tr.guard_passed, tr.guard_violations
    # an invented figure in the same explanation is caught
    forged = tr.explanation + "\nFUN FACT: this manoeuvre saves 42.7 m/s of fuel and lowers Pc to 3.3e-09."
    bad = check_no_fabricated_numbers(forged, ctx.calls)
    assert bad and any(x in bad for x in ("42.7", "3.3e-09"))


def test_recommendation_traces_to_tool_calls(keystone_trace):
    ctx, tr = keystone_trace
    names = [c["tool"] for c in tr.tool_calls]
    for required in ("get_cluster", "get_conjunction", "compute_voi", "simulate_action", "run_uncertainty_analysis", "rank_strategies", "validate_action"):
        assert required in names
    assert tr.recommendation and tr.explanation.startswith("RECOMMENDATION:")
    assert "[source:" in tr.explanation and "NOT a prediction accuracy" in tr.explanation
    assert tr.driver == "deterministic"


def test_rejection_is_unscripted_and_visible(keystone_trace):
    """The late 'instinct' burn (TCA − 40 min) is proposed like any other candidate and the
    validator — not the planner — rejects it on C4. The rejection is in the trace with its reason."""
    ctx, tr = keystone_trace
    assert tr.rejections, "expected at least one validator rejection on keystone_cluster"
    assert any("C4" in r["violated"] for r in tr.rejections)
    verdicts = [c["result"]["verdict"] for c in tr.tool_calls if c["tool"] == "validate_action"]
    assert "REJECTED" in verdicts and "APPROVED" in verdicts
    # the recommended action is one the validator approved
    rec_ids = [c["args"] for c in tr.tool_calls if c["tool"] == "validate_action" and c["result"]["verdict"] == "APPROVED"]
    assert rec_ids


def test_hold_when_nothing_exceeds_threshold():
    ctx = _ctx("voi_event")           # Pc ≈ 7e-5 < Pc* = 1e-4
    tr = plan(ctx, ctx.graph.clusters[0].cluster_id, prefer_llm=False)
    assert tr.guard_passed and tr.recommendation and tr.recommendation.startswith("HOLD")


def test_tool_errors_are_surfaced_not_hidden():
    ctx = _ctx("two_body_head_on")
    out = call_tool(ctx, "get_cluster", {"cluster_id": "clu_does_not_exist"})
    assert "error" in out and ctx.calls[-1]["ok"] is False
