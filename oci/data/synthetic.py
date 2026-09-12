"""D8 — Synthetic scenario generator (SPEC §6.7). Deterministic, seeded, reproducible.

Every scenario is built geometrically: we choose the encounter point and the relative
velocity at TCA, offset the secondary by the desired miss vector (⟂ v_rel), and fit mean
elements to each state. So the designed TCA and miss distance are exact by construction and
the screening engine has a known answer to find (used by its acceptance tests).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from oci.config import MU_EARTH_KM3_S2, R_EARTH_KM
from oci.data.objects import SpaceObject, mass_model
from oci.physics.maneuver import fit_mean_elements
from oci.physics.propagate import propagate

T0 = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)

# Declared RTN 1σ position uncertainties (m) for synthetic objects — MODELLED, stated.
SIGMA_ACTIVE = (40.0, 250.0, 35.0)
SIGMA_DEBRIS = (120.0, 900.0, 90.0)
SIGMA_RB = (90.0, 650.0, 70.0)
SIGMA_HIGH = (400.0, 3000.0, 300.0)     # for the VoI event: fresh, poorly tracked


@dataclass
class Scenario:
    name: str
    objects: list[SpaceObject]
    window_start: datetime
    window_end: datetime
    designed: list[dict] = field(default_factory=list)   # (primary, secondary, tca, miss_m)
    notes: str = ""
    seed: int = 42
    expected: dict = field(default_factory=dict)         # what tests assert


# ── geometric helpers ─────────────────────────────────────────────────────────────────────

def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def _tangent_basis(r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rhat = _unit(r)
    z = np.array([0.0, 0.0, 1.0])
    e1 = _unit(np.cross(z, rhat))       # "east"
    e2 = np.cross(rhat, e1)             # "north"
    return e1, e2


def circular_state(alt_km: float, lat_deg: float, lon_deg: float, heading_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Position on the sphere at (lat, lon, alt) and circular velocity along `heading`
    measured from east toward north in the local tangent plane."""
    rad = R_EARTH_KM + alt_km
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    r = rad * np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])
    e1, e2 = _tangent_basis(r)
    h = math.radians(heading_deg)
    v = math.sqrt(MU_EARTH_KM3_S2 / rad) * (math.cos(h) * e1 + math.sin(h) * e2)
    return r, v


def crossing_state(r_primary: np.ndarray, v_primary: np.ndarray, crossing_angle_deg: float,
                   miss_m: float, miss_dir_deg: float = 0.0, radial_offset_km: float = 0.0
                   ) -> tuple[np.ndarray, np.ndarray]:
    """A secondary that passes the primary's TCA point with its velocity rotated by
    `crossing_angle_deg` in the tangent plane, displaced by `miss_m` ⟂ v_rel. `miss_dir_deg`
    rotates the miss vector within the plane ⟂ v_rel (0 = along the radial-ish axis)."""
    rhat = _unit(r_primary)
    speed = np.linalg.norm(v_primary)
    vhat = _unit(v_primary)
    side = _unit(np.cross(rhat, vhat))
    a = math.radians(crossing_angle_deg)
    v2 = speed * (math.cos(a) * vhat + math.sin(a) * side)
    v2 = v2 * (math.sqrt(MU_EARTH_KM3_S2 / (np.linalg.norm(r_primary) + radial_offset_km)) / speed)
    v_rel = v2 - v_primary
    if np.linalg.norm(v_rel) < 1e-6:
        v_rel = side
    uz = _unit(v_rel)
    ux = _unit(rhat - np.dot(rhat, uz) * uz)
    uy = np.cross(uz, ux)
    d = math.radians(miss_dir_deg)
    m = (miss_m / 1000.0) * (math.cos(d) * ux + math.sin(d) * uy)
    r2 = r_primary + m + radial_offset_km * rhat
    return r2, v2


def object_from_state(norad_id: int, name: str, r: np.ndarray, v: np.ndarray, epoch: datetime, *,
                      object_type: str, operator: str, is_active: bool, is_maneuverable: bool,
                      sigma: Optional[tuple[float, float, float]], rcs: str = "MEDIUM",
                      launch_date: str = "2020-01-01", country: str = "XX") -> SpaceObject:
    el = fit_mean_elements(norad_id, r, v, epoch)
    mm = mass_model(object_type, rcs)
    return SpaceObject(
        norad_id=norad_id, object_name=name, object_type=object_type,  # type: ignore[arg-type]
        is_active=is_active, is_maneuverable=is_maneuverable, operator=operator, elements=el,
        country=country, launch_date=launch_date, rcs_size=rcs, source="synthetic",
        sigma_rtn_m=sigma, covariance_source="declared" if sigma else "none", **mm,
    )


def _designed(a: SpaceObject, b: SpaceObject, tca: datetime, miss_m: float) -> dict:
    return {"primary": a.norad_id, "secondary": b.norad_id, "tca": tca, "miss_m": miss_m}


# ── scenarios ─────────────────────────────────────────────────────────────────────────────

def two_body_head_on(seed: int = 42) -> Scenario:
    """Simplest conjunction: active payload vs debris, near head-on, 120 m miss at T0+6h."""
    tca = T0 + timedelta(hours=6)
    r1, v1 = circular_state(550.0, 20.0, 40.0, 60.0)
    a = object_from_state(90001, "SYN-PAYLOAD-A", r1, v1, tca, object_type="PAYLOAD", operator="OPERATOR-A",
                          is_active=True, is_maneuverable=True, sigma=SIGMA_ACTIVE)
    r2, v2 = crossing_state(r1, v1, 160.0, 120.0, miss_dir_deg=30.0)
    b = object_from_state(90002, "SYN-DEBRIS-B", r2, v2, tca, object_type="DEBRIS", operator="UNKNOWN-OPERATOR",
                          is_active=False, is_maneuverable=False, sigma=SIGMA_DEBRIS, rcs="SMALL")
    sc = Scenario("two_body_head_on", [a, b], T0, T0 + timedelta(hours=24), seed=seed,
                  notes="one designed conjunction; verifies TCA/miss/Pc code")
    sc.designed.append(_designed(a, b, tca, 120.0))
    sc.expected = {"n_conjunctions": 1, "tca": tca, "miss_m": 120.0}
    return sc


def keystone_cluster(seed: int = 42) -> Scenario:
    """Six objects. A–C is the single highest-Pc edge (150 m). B has three moderate
    conjunctions (D, E, F) so its risk-weighted degree is highest: keystone ≠ max-Pc object.
    This is the demo's core moment and must exist by construction."""
    win = (T0, T0 + timedelta(hours=36))
    # B: the keystone — an active maneuverable satellite crossed three times
    tB = T0 + timedelta(hours=8)
    rB, vB = circular_state(560.0, -10.0, 100.0, 55.0)
    B = object_from_state(91002, "SYN-SAT-B", rB, vB, tB, object_type="PAYLOAD", operator="OPERATOR-B",
                          is_active=True, is_maneuverable=True, sigma=SIGMA_ACTIVE)
    partners = []
    for k, (norad, name, typ, op, active, man, sig, rcs, cross, miss, mdir) in enumerate([
        (91004, "SYN-SAT-D", "PAYLOAD", "OPERATOR-C", True, True, SIGMA_ACTIVE, "MEDIUM", 95.0, 260.0, 20.0),
        (91005, "SYN-RB-E", "ROCKET_BODY", "UNKNOWN-OPERATOR", False, False, SIGMA_RB, "LARGE", 140.0, 320.0, 60.0),
        (91006, "SYN-SAT-F", "PAYLOAD", "OPERATOR-D", True, True, SIGMA_ACTIVE, "MEDIUM", 70.0, 300.0, 100.0),
    ]):
        tk = tB + timedelta(hours=3.0 * (k + 1))
        stB = propagate(B, tk)
        rk, vk = crossing_state(stB.r_km, stB.v_kmps, cross, miss, miss_dir_deg=mdir)
        partners.append((object_from_state(norad, name, rk, vk, tk, object_type=typ, operator=op, is_active=active,
                                           is_maneuverable=man, sigma=sig, rcs=rcs), tk, miss))
    # A: crosses B once (moderate, 420 m) so the cluster is connected, and is then crossed by
    # C at 150 m — the single highest-Pc edge. B still has the highest risk-weighted degree.
    tAB = tB + timedelta(hours=1.5)
    stB = propagate(B, tAB)
    rA, vA = crossing_state(stB.r_km, stB.v_kmps, 115.0, 420.0, miss_dir_deg=80.0)
    A = object_from_state(91001, "SYN-SAT-A", rA, vA, tAB, object_type="PAYLOAD", operator="OPERATOR-A",
                          is_active=True, is_maneuverable=True, sigma=SIGMA_ACTIVE)
    tA = T0 + timedelta(hours=20)
    stA = propagate(A, tA)
    rC, vC = crossing_state(stA.r_km, stA.v_kmps, 165.0, 150.0, miss_dir_deg=15.0)
    C = object_from_state(91003, "SYN-DEB-C", rC, vC, tA, object_type="DEBRIS", operator="UNKNOWN-OPERATOR",
                          is_active=False, is_maneuverable=False, sigma=SIGMA_DEBRIS, rcs="SMALL")
    objs = [A, B, C] + [p[0] for p in partners]
    sc = Scenario("keystone_cluster", objs, *win, seed=seed,
                  notes="A–C highest Pc; B highest risk-weighted degree → disagreement=True")
    sc.designed.append(_designed(A, C, tA, 150.0))
    sc.designed.append(_designed(B, A, tAB, 420.0))
    for p, tk, miss in partners:
        sc.designed.append(_designed(B, p, tk, miss))
    sc.expected = {"keystone_id": 91002, "max_pc_edge": (91001, 91003), "disagreement": True, "n_conjunctions": 5}
    return sc


def dead_rocket_body(seed: int = 42) -> Scenario:
    """One immovable SL-16-class rocket body at 846 km forcing manoeuvres on five active
    satellites from three operators. The ledger showcase: it imposes everything, bears nothing."""
    win = (T0, T0 + timedelta(hours=48))
    tRB = T0 + timedelta(hours=5)
    rRB, vRB = circular_state(846.0, 5.0, 10.0, 20.0)   # 71° inclination-ish crossing regime
    RB = object_from_state(92000, "SYN SL-16 R/B", rRB, vRB, tRB, object_type="ROCKET_BODY",
                           operator="UNKNOWN-OPERATOR", is_active=False, is_maneuverable=False,
                           sigma=SIGMA_RB, rcs="LARGE", launch_date="1987-05-19", country="CIS")
    victims = []
    plan = [
        (92001, "SYN-OPA-1", "OPERATOR-A", 110.0, 180.0, 10.0),
        (92002, "SYN-OPA-2", "OPERATOR-A", 130.0, 260.0, 50.0),
        (92003, "SYN-OPB-1", "OPERATOR-B", 75.0, 220.0, 90.0),
        (92004, "SYN-OPB-2", "OPERATOR-B", 150.0, 340.0, 130.0),
        (92005, "SYN-OPC-1", "OPERATOR-C", 100.0, 200.0, 170.0),
    ]
    for k, (norad, name, op, cross, miss, mdir) in enumerate(plan):
        tk = tRB + timedelta(hours=6.0 * k + 2.0)
        st = propagate(RB, tk)
        rk, vk = crossing_state(st.r_km, st.v_kmps, cross, miss, miss_dir_deg=mdir)
        victims.append((object_from_state(norad, name, rk, vk, tk, object_type="PAYLOAD", operator=op,
                                          is_active=True, is_maneuverable=True, sigma=SIGMA_ACTIVE), tk, miss))
    # two bystanders that never come close
    r1, v1 = circular_state(700.0, 60.0, 150.0, 80.0)
    by1 = object_from_state(92010, "SYN-BYSTANDER-1", r1, v1, T0, object_type="PAYLOAD", operator="OPERATOR-D",
                            is_active=True, is_maneuverable=True, sigma=SIGMA_ACTIVE)
    objs = [RB] + [v[0] for v in victims] + [by1]
    sc = Scenario("dead_rocket_body", objs, *win, seed=seed,
                  notes="R1 attribution: every forced manoeuvre is imposed by 92000; it bears zero")
    for v, tk, miss in victims:
        sc.designed.append(_designed(RB, v, tk, miss))
    sc.expected = {"imposer": 92000, "n_conjunctions": 5, "operators_affected": 3}
    return sc


def voi_event(seed: int = 42) -> Scenario:
    """High initial uncertainty (σ_T = 3 km) on a 700 m miss with TCA 60 h out. As the
    covariance shrinks, the expected Δv to clear drops: WAIT should beat MANEUVER-now."""
    tca = T0 + timedelta(hours=60)
    r1, v1 = circular_state(520.0, 15.0, 70.0, 50.0)
    a = object_from_state(93001, "SYN-SAT-VOI", r1, v1, tca, object_type="PAYLOAD", operator="OPERATOR-A",
                          is_active=True, is_maneuverable=True, sigma=SIGMA_ACTIVE)
    r2, v2 = crossing_state(r1, v1, 120.0, 700.0, miss_dir_deg=80.0)
    b = object_from_state(93002, "SYN-DEB-FRESH", r2, v2, tca, object_type="DEBRIS", operator="UNKNOWN-OPERATOR",
                          is_active=False, is_maneuverable=False, sigma=SIGMA_HIGH, rcs="SMALL")
    sc = Scenario("voi_event", [a, b], T0, T0 + timedelta(hours=72), seed=seed,
                  notes="uncertainty shrinks toward TCA; WAIT expected to dominate")
    sc.designed.append(_designed(a, b, tca, 700.0))
    sc.expected = {"wait_beats_maneuver": True}
    return sc


def chaos_new_object(scenario: Scenario, target_id: int, t_inject: datetime, miss_m: float = 180.0,
                     norad_id: int = 99999, crossing_angle_deg: float = 120.0) -> SpaceObject:
    """M14 injection: a new debris object on a trajectory that conjuncts with `target_id` at
    `t_inject`. Returns the object; the caller builds the new state (pure)."""
    tgt = next(o for o in scenario.objects if o.norad_id == target_id)
    st = propagate(tgt, t_inject)
    r, v = crossing_state(st.r_km, st.v_kmps, crossing_angle_deg, miss_m, miss_dir_deg=45.0)
    return object_from_state(norad_id, "SYN-CHAOS-NEW", r, v, t_inject, object_type="DEBRIS",
                             operator="UNKNOWN-OPERATOR", is_active=False, is_maneuverable=False,
                             sigma=SIGMA_HIGH, rcs="SMALL")


SCENARIOS = {
    "two_body_head_on": two_body_head_on,
    "keystone_cluster": keystone_cluster,
    "dead_rocket_body": dead_rocket_body,
    "voi_event": voi_event,
}


def load(name: str, seed: int = 42) -> Scenario:
    return SCENARIOS[name](seed)
