"""SPEC §10.1 M1 ingest acceptance tests and §17.3 SOCRATES cross-validation.

Tests that need the network are skipped when it is unavailable; everything else runs from
the committed fixtures in data/fixtures so the suite passes with the cable pulled (§17.6)."""
import csv
import io
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from oci.config import CONFIG
from oci.data import celestrak
from oci.data.celestrak import SatcatRow, fetch_socrates, load_satcat
from oci.data.ingest import BadElementSet, ingest, normalise, parse_elements, shell_filter
from oci.data.operators import coordinated_constellations, match_operator
from oci.physics.screen import screen

FIX = Path("data/fixtures")


def _online() -> bool:
    try:
        socket.create_connection(("celestrak.org", 443), timeout=3).close()
        return True
    except OSError:
        return False


def _satcat_fixture() -> dict[int, SatcatRow]:
    text = (FIX / "satcat_sample.csv").read_text()
    # reuse the real parser by pointing the cache at the fixture
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        rcs = float(row["RCS"]) if row.get("RCS") else None
        out[int(row["NORAD_CAT_ID"])] = SatcatRow(int(row["NORAD_CAT_ID"]), row["OBJECT_NAME"], row["OBJECT_ID"],
                                                  celestrak._TYPE.get(row["OBJECT_TYPE"], "UNKNOWN"), row["OPS_STATUS_CODE"],
                                                  row["OWNER"], row["LAUNCH_DATE"] or None, row["DECAY_DATE"] or None,
                                                  rcs, celestrak._rcs_bucket(rcs), row["ORBIT_TYPE"])
    return out


NOW = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def sample_objects():
    recs = json.load(open(FIX / "gp_sample.json"))
    satcat = _satcat_fixture()
    return [normalise(r, satcat, "active", NOW) for r in recs]


# ── parsing and normalisation ────────────────────────────────────────────────────────────
def test_derived_orbit_matches_known_iss(sample_objects):
    iss = next(o for o in sample_objects if o.norad_id == 25544)
    assert abs(iss.orbit.mean_alt_km - 420.0) < 15.0
    assert iss.is_active and iss.operator == "ISS"


def test_no_silent_nulls(sample_objects):
    for o in sample_objects:
        assert o.object_name and o.object_type in ("PAYLOAD", "ROCKET_BODY", "DEBRIS", "UNKNOWN")
        assert o.operator and o.mass_kg_est > 0 and o.hard_body_radius_m > 0
        assert o.sigma_rtn_m is not None and o.covariance_source in ("assumed", "kelvins_fitted")


def test_modelled_fields_labelled(sample_objects):
    for o in sample_objects:
        assert o.mass_kg_low <= o.mass_kg_est <= o.mass_kg_high


def test_bad_element_set_rejected_not_coerced():
    with pytest.raises(BadElementSet):
        parse_elements({"NORAD_CAT_ID": 1, "EPOCH": "2026-09-12T00:00:00", "MEAN_MOTION": "nan", "ECCENTRICITY": 0,
                        "INCLINATION": 50, "RA_OF_ASC_NODE": 0, "ARG_OF_PERICENTER": 0, "MEAN_ANOMALY": 0})
    with pytest.raises(BadElementSet):
        parse_elements({"NORAD_CAT_ID": 1, "EPOCH": "2026-09-12T00:00:00", "MEAN_MOTION": 15.0, "ECCENTRICITY": 1.2,
                        "INCLINATION": 50, "RA_OF_ASC_NODE": 0, "ARG_OF_PERICENTER": 0, "MEAN_ANOMALY": 0})


def test_unmatched_operator_not_dropped():
    satcat = _satcat_fixture()
    rec = json.load(open(FIX / "gp_sample.json"))[0] | {"OBJECT_NAME": "ZORBLAX-7", "NORAD_CAT_ID": 999999}
    o = normalise(rec, satcat, "active", NOW)
    assert o.operator.startswith("UNKNOWN-OPERATOR")
    assert o.is_maneuverable is False        # conservative default


def test_stale_flagged(sample_objects):
    old = next(iter(json.load(open(FIX / "gp_sample.json"))))
    o = normalise(old, _satcat_fixture(), "active", NOW + timedelta(days=30))
    assert o.stale


def test_operator_map():
    assert match_operator("STARLINK-31084") == "SPACEX"
    assert match_operator("ONEWEB-0442") == "ONEWEB"
    assert match_operator("FENGYUN 1C DEB", "PRC", "DEBRIS") == "DEBRIS:PRC"
    assert match_operator("SL-16 R/B", "CIS", "ROCKET_BODY") == "ROCKET-BODY:CIS"
    assert "SPACEX" in coordinated_constellations()
    for c in coordinated_constellations():
        assert c in CONFIG.attribution.coordinated_constellations


def test_dead_objects_are_not_maneuverable(sample_objects):
    for o in sample_objects:
        if o.object_type in ("DEBRIS", "ROCKET_BODY"):
            assert not o.is_active and not o.is_maneuverable


def test_shell_filter(sample_objects):
    inside = shell_filter(sample_objects, 700, 900)
    assert inside and all(o.orbit.apogee_alt_km >= 700 and o.orbit.perigee_alt_km <= 900 for o in inside)


def test_real_elements_screen_and_maneuver(sample_objects):
    """Real element sets go through the whole chain: screen, then a burn rebuilds mean elements."""
    from oci.physics.maneuver import Burn, apply_maneuver
    from oci.physics.propagate import propagate
    objs = shell_filter(sample_objects, 700, 900)[:40]
    res = screen(objs, NOW, NOW + timedelta(hours=12))
    assert res.run.n_objects == len(objs)
    o = next(x for x in objs if x.is_maneuverable) if any(x.is_maneuverable for x in objs) else objs[0]
    tb = NOW + timedelta(hours=1)
    for dv in (0.0, 0.5, 5.0):
        m = apply_maneuver(o, Burn(o.norad_id, (0.0, dv, 0.0), tb))
        if dv == 0.0:
            import numpy as np
            assert np.linalg.norm(propagate(m, tb + timedelta(hours=6)).r_km - propagate(o, tb + timedelta(hours=6)).r_km) * 1000 < 0.05


# ── SOCRATES cross-validation, from fixtures (no network) ──────────────────────────────
def test_socrates_same_elements_recall():
    from oci.data.socrates import CrossValidation
    from oci.data.celestrak import SocratesReport
    import oci.data.socrates as S
    rep = celestrak.fetch_socrates.__wrapped__("MINRANGE", 1000) if hasattr(celestrak.fetch_socrates, "__wrapped__") else None
    # parse the fixture HTML through the real parser by temporarily pointing the cache at fixtures
    old_cache, celestrak.CACHE_DIR = celestrak.CACHE_DIR, FIX
    S.GP_DIR = FIX / "socrates_gp"
    try:
        rep = fetch_socrates("MINRANGE", 1000, offline=True)
        assert len(rep.rows) == 1000 and rep.interval_start is not None
        pairs = [r for r in rep.rows if (FIX / "socrates_gp" / f"{r.norad_1}_{r.norad_2}.csv").exists()]
        assert len(pairs) >= 40
        satcat = _satcat_fixture()
        celestrak.load_satcat = lambda offline=False: satcat  # type: ignore[assignment]
        S.load_satcat = lambda offline=False: satcat           # type: ignore[assignment]
        cv = S.cross_validate_same_elements(pairs, rep, offline=True)
    finally:
        celestrak.CACHE_DIR = old_cache
    assert cv.recall_on_encounters >= 0.85, cv.summary()
    assert max(cv.tca_abs_err_s) < 1.0 and max(abs(x) for x in cv.miss_err_m) < 5.0


# ── network-dependent ─────────────────────────────────────────────────────────────────────
@pytest.mark.skipif(not _online(), reason="network unavailable")
def test_ingest_active_group_nonempty():
    objs, rep = ingest("active")
    assert rep.n_ingested >= 5000
    assert rep.n_rejected == 0 or rep.n_rejected < 0.01 * rep.n_raw


def test_offline_mode_works_from_cache_or_fails_loudly(tmp_path):
    old, celestrak.CACHE_DIR = celestrak.CACHE_DIR, tmp_path
    try:
        with pytest.raises(celestrak.OfflineCacheMiss):
            celestrak.fetch_gp_group("active", offline=True)
        (tmp_path / "gp_active.json").write_text(json.dumps(json.load(open(FIX / "gp_sample.json"))))
        recs, meta = celestrak.fetch_gp_group("active", offline=True)
        assert meta["source"] == "cache" and len(recs) > 0
    finally:
        celestrak.CACHE_DIR = old
