"""SPEC §10.13 M14 chaos mode acceptance tests. The pipeline is a pure function of state, so an
injection is a new state and a replan — no hidden caches to invalidate."""
import time

import pytest

from oci.pipeline import run_pipeline
from oci.sim.chaos import KINDS, Injection, chaos, replan


@pytest.fixture(scope="module")
def base():
    return run_pipeline("keystone_cluster", n_mc=25, seed=42)


def test_chaos_is_pure(base):
    before = (len(base.state.objects), base.state.epoch, dict(base.state.policy))
    new_state, applied = chaos(base.state, base, Injection("NEW_OBJECT"))
    assert len(new_state.objects) == before[0] + 1 and applied["norad_id"] in new_state.objects
    assert (len(base.state.objects), base.state.epoch, dict(base.state.policy)) == before   # untouched


def test_chaos_invalidates_previous(base):
    res = replan(base, Injection("NEW_OBJECT"), n_mc=25)
    assert res.invalidated == [base.recommendation.strategy_id]
    assert res.invalidation_reason and ("C7" in res.invalidation_reason or "Pc" in res.invalidation_reason)
    assert res.diff["was"] == base.recommendation.action.describe()


def test_chaos_produces_new_recommendation(base):
    res = replan(base, Injection("NEW_OBJECT"), n_mc=25)
    assert res.new.recommendation is not None
    assert res.diff["now"] != res.diff["was"] and res.diff["changed"]
    assert res.new.verdicts[res.new.recommendation.strategy_id].status == "APPROVED"


def test_chaos_deterministic_with_seed(base):
    a = replan(base, Injection("COVARIANCE_SPIKE", {"factor": 4.0}, seed=7), n_mc=25)
    b = replan(base, Injection("COVARIANCE_SPIKE", {"factor": 4.0}, seed=7), n_mc=25)
    assert a.diff["now"] == b.diff["now"] and a.applied == b.applied
    assert a.new.recommendation.expected_cost.value == pytest.approx(b.new.recommendation.expected_cost.value)


def test_chaos_end_to_end_under_10s(base):
    t = time.perf_counter()
    res = replan(base, Injection("NEW_OBJECT"), n_mc=25)
    assert time.perf_counter() - t < 10.0, res.elapsed_s


def test_every_injection_kind_runs(base):
    for kind in KINDS:
        res = replan(base, Injection(kind), n_mc=10)
        assert res.new.screening is not None and res.diff["why"]
        assert res.elapsed_s < 20.0


def test_uplink_delay_and_refusal_change_the_action_space(base):
    up = replan(base, Injection("UPLINK_DELAY", {"uplink_lead_min": 180.0}), n_mc=10)
    assert up.new.state.policy["uplink_lead_min"] == 180.0
    assert any("uplink delay" in c.detail for s in up.new.optimisation.strategies for c in up.new.verdicts[s.strategy_id].checks
               if s.kind == "MANEUVER") or up.new.rejected
    ref = replan(base, Injection("REFUSE_COORDINATION"), n_mc=10)
    assert all(s.kind != "COORDINATE" for s in ref.new.optimisation.strategies)
