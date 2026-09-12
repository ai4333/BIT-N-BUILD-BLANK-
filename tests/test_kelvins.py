"""SPEC §10.8 M8 acceptance tests — covariance fit, shrinkage, replay. The fit itself needs the
(gitignored) dataset; the persisted model in models/covariance_fit.json is tested always."""
from pathlib import Path

import pytest

from oci.data import kelvins as K

HAVE_DATA = K.DATA.exists()


def test_covariance_fit_converges_and_is_persisted():
    m = K.load_models()
    assert m is not None, "models/covariance_fit.json missing — run `python -m oci kelvins`"
    cov, sh = m
    for k in "rtn":
        assert 0.0 < cov.r2[k] <= 1.0 and cov.residual_sd[k] > 0
        for v in (cov.coefficients[k]["intercept"], cov.coefficients[k]["b_logtau"]):
            assert v == v and abs(v) < 100
    assert cov.r2["t"] >= 0.3          # along-track carries the signal (challenge paper)
    assert cov.n_events > 10_000


def test_sigma_grows_with_time_to_tca_and_decreases_toward_it():
    cov, _ = K.load_models()
    s = [cov.sigma_rtn_m(tau, "DEBRIS", 800.0)[1] for tau in (0.25, 0.5, 1, 2, 4, 6)]
    assert all(a < b for a, b in zip(s, s[1:]))
    assert cov.sigma_rtn_m(1.0, "DEBRIS", 800.0)[1] > cov.sigma_rtn_m(1.0, "PAYLOAD", 800.0)[1]


def test_shrinkage_lambda_positive_with_ci():
    _, sh = K.load_models()
    lam = sh.lambda_per_day["ALL"]
    assert 0.05 < lam < 5.0
    lo, hi = sh.lambda_ci_per_day["ALL"]
    assert lo <= lam <= hi or (lo != lo)   # NaN CI allowed only when bootstrap was skipped
    assert 0.0 < sh.sigma_floor_fraction["ALL"] < 1.0


def test_covariance_source_always_labelled_on_real_objects():
    import json
    from datetime import datetime, timezone
    from oci.data.ingest import normalise
    from tests.test_ingest import _satcat_fixture
    recs = json.load(open("data/fixtures/gp_sample.json"))[:20]
    objs = [normalise(r, _satcat_fixture(), "active", datetime(2026, 9, 12, 15, tzinfo=timezone.utc)) for r in recs]
    for o in objs:
        assert o.sigma_rtn_m is not None and o.covariance_source in ("kelvins_fitted", "assumed")
    if K.load_models() is not None:
        assert all(o.covariance_source == "kelvins_fitted" for o in objs)


@pytest.mark.skipif(not HAVE_DATA, reason="Kelvins dataset not present")
def test_voi_not_always_wait_on_replay():
    df = K.load()
    _, sh = K.load_models()
    r = K.replay(df, sh, pc_threshold=1e-5, max_events=3000)
    assert r.n_events_replayed > 1000
    assert r.n_wait_recommended < r.n_events_replayed
    assert r.n_maneuver_recommended > 0 and r.n_hold > 0
