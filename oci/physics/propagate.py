"""M2 — Propagator (SPEC §10.2).

SGP4 over mean elements, single and batched. Frame is TEME throughout the pipeline; screening,
Pc and manoeuvre geometry all stay in TEME, which is consistent and documented (§10.2 step 3).
The SGP4 error code is never ignored.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

import numpy as np
from sgp4.api import SGP4_ERRORS, Satrec, SatrecArray, WGS72, jday

from oci.data.objects import Elements, SpaceObject

_SGP4_EPOCH_JD = 2433281.5  # 1949 December 31 00:00 UT


class PropagationError(RuntimeError):
    def __init__(self, norad_id: int, code: int, message: str):
        super().__init__(f"NORAD {norad_id}: SGP4 error {code}: {message}")
        self.norad_id, self.code = norad_id, code


@dataclass(frozen=True)
class State:
    r_km: np.ndarray      # (3,)
    v_kmps: np.ndarray    # (3,)
    epoch: datetime
    frame: str = "TEME"


def jd_of(t: datetime) -> tuple[float, float]:
    t = t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond * 1e-6)


def satrec_from_elements(norad_id: int, el: Elements) -> Satrec:
    """Build an SGP4 record directly from mean elements (no TLE string round-trip)."""
    jd, fr = jd_of(el.epoch)
    sat = Satrec()
    sat.sgp4init(
        WGS72, "i", int(norad_id) % 100000,
        (jd + fr) - _SGP4_EPOCH_JD,
        el.bstar,
        el.mean_motion_dot, el.mean_motion_ddot,
        el.eccentricity,
        math.radians(el.argp_deg),
        math.radians(el.inclination_deg),
        math.radians(el.mean_anomaly_deg),
        el.mean_motion_rev_day * 2.0 * math.pi / 1440.0,   # rad/min
        math.radians(el.raan_deg),
    )
    return sat


def propagate(obj: SpaceObject, t: datetime) -> State:
    sat = satrec_from_elements(obj.norad_id, obj.elements)
    jd, fr = jd_of(t)
    e, r, v = sat.sgp4(jd, fr)
    if e != 0:
        raise PropagationError(obj.norad_id, e, SGP4_ERRORS.get(e, "unknown"))
    return State(np.asarray(r, dtype=float), np.asarray(v, dtype=float), t)


def propagate_batch(objs: Sequence[SpaceObject], times: Sequence[datetime]
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised SGP4. Returns (r[n_obj, n_t, 3] km, v[n_obj, n_t, 3] km/s, err[n_obj, n_t])."""
    if not objs:
        return np.zeros((0, len(times), 3)), np.zeros((0, len(times), 3)), np.zeros((0, len(times)), dtype=int)
    arr = SatrecArray([satrec_from_elements(o.norad_id, o.elements) for o in objs])
    jds = np.empty(len(times)); frs = np.empty(len(times))
    for i, t in enumerate(times):
        jds[i], frs[i] = jd_of(t)
    e, r, v = arr.sgp4(jds, frs)
    return r, v, e


def time_grid(t0: datetime, t1: datetime, step_min: float) -> list[datetime]:
    n = int(math.floor((t1 - t0).total_seconds() / (step_min * 60.0))) + 1
    return [t0 + timedelta(minutes=step_min * k) for k in range(n)]


def specific_energy(r_km: np.ndarray, v_kmps: np.ndarray) -> float:
    from oci.config import MU_EARTH_KM3_S2
    return 0.5 * float(np.dot(v_kmps, v_kmps)) - MU_EARTH_KM3_S2 / float(np.linalg.norm(r_km))
