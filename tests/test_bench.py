"""SPEC §15 benchmark harness: baselines exist, OCI never worse than B2 on its own objective
beyond the 5 % tie band, and the losing rows are reported, not hidden."""
import json
from pathlib import Path

import pytest

from oci.bench.harness import SCENARIO_SET, render, run_scenario


@pytest.mark.parametrize("sid", ["S1", "S2", "S5"])
def test_bench_scenario_runs_and_reports_losses(sid):
    r = run_scenario(sid, seed=42, n_mc=40)
    assert {m.policy for m in r.rows} == {"B1", "B2", "B3", "B4", "OCI"}
    assert r.verdict in ("OCI_BETTER", "NEUTRAL", "OCI_WORSE")
    text = render(r)
    assert "VERDICT" in text
    if any(v == "worse" for v in r.verdict_detail.values()):
        assert "reported, not hidden" in text
    json.loads(r.to_json())


def test_oci_contains_standard_practice():
    """OCI's candidate set includes B2's iterated plan, so it cannot lose to B2 on expected cost
    by more than Monte-Carlo noise (the 5 % tie band)."""
    r = run_scenario("S2", seed=42, n_mc=60)
    b2 = next(m for m in r.rows if m.policy == "B2"); oci = r.rows[-1]
    assert oci.expected_cost <= b2.expected_cost * 1.05
    assert r.verdict != "OCI_WORSE"


def test_bench_fixtures_committed():
    assert list(Path("data/fixtures/bench").glob("bench_S*_seed42.json"))
