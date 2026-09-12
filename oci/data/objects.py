"""The normalised catalogue object (SPEC §9.1 `objects` table) and derived orbit quantities (§11.1).

An `SpaceObject` carries mean elements exactly as SGP4 wants them, plus the metadata the
ledger needs (active? maneuverable? operator? mass?). Everything MODELLED is stored with its
range so the assumptions panel can show it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from oci.config import CONFIG, MU_EARTH_KM3_S2, R_EARTH_KM

ObjectType = Literal["PAYLOAD", "ROCKET_BODY", "DEBRIS", "UNKNOWN"]


@dataclass(frozen=True)
class Elements:
    """Mean elements at `epoch`, in the units SGP4's `sgp4init` expects."""
    epoch: datetime                 # UTC
    mean_motion_rev_day: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float
    argp_deg: float
    mean_anomaly_deg: float
    bstar: float = 0.0
    mean_motion_dot: float = 0.0    # rev/day²  (ndot/2 in TLE convention handled by caller)
    mean_motion_ddot: float = 0.0

    @property
    def n_rad_s(self) -> float:
        return self.mean_motion_rev_day * 2.0 * math.pi / 86400.0


@dataclass(frozen=True)
class DerivedOrbit:
    sma_km: float
    perigee_alt_km: float
    apogee_alt_km: float
    mean_alt_km: float
    period_min: float


def derive_orbit(el: Elements) -> DerivedOrbit:
    """§11.1 — semi-major axis, apsides, mean altitude, period from mean motion."""
    n = el.n_rad_s
    if n <= 0:
        raise ValueError("mean motion must be positive")
    a = (MU_EARTH_KM3_S2 / (n * n)) ** (1.0 / 3.0)
    rp = a * (1.0 - el.eccentricity)
    ra = a * (1.0 + el.eccentricity)
    return DerivedOrbit(
        sma_km=a,
        perigee_alt_km=rp - R_EARTH_KM,
        apogee_alt_km=ra - R_EARTH_KM,
        mean_alt_km=((rp - R_EARTH_KM) + (ra - R_EARTH_KM)) / 2.0,
        period_min=1440.0 / el.mean_motion_rev_day,
    )


@dataclass(frozen=True)
class SpaceObject:
    norad_id: int
    object_name: str
    object_type: ObjectType
    is_active: bool
    is_maneuverable: bool
    operator: str
    elements: Elements
    international_id: Optional[str] = None
    country: Optional[str] = None
    launch_date: Optional[str] = None
    rcs_size: Optional[str] = None
    mass_kg_est: float = 50.0            # MODELLED
    mass_kg_low: float = 0.01            # MODELLED
    mass_kg_high: float = 9000.0         # MODELLED
    hard_body_radius_m: float = CONFIG.pc.hard_body_radius_m   # MODELLED
    area_to_mass_m2_kg: float = 0.02     # MODELLED
    source: str = "synthetic"
    stale: bool = False
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Declared RTN position sigmas (m). Synthetic scenarios set these explicitly; real data gets
    # them from the Kelvins-fitted model (M8). None → covariance unavailable → Pc is N/A.
    sigma_rtn_m: Optional[tuple[float, float, float]] = None
    covariance_source: str = "none"

    @property
    def orbit(self) -> DerivedOrbit:
        return derive_orbit(self.elements)

    @property
    def shell_id(self) -> int:
        cap = CONFIG.capacity
        return int((self.orbit.mean_alt_km - cap.shell_min_km) // cap.shell_width_km)

    def with_elements(self, el: Elements) -> "SpaceObject":
        return replace(self, elements=el)

    def with_sigma(self, sigma_rtn_m: tuple[float, float, float], source: str) -> "SpaceObject":
        return replace(self, sigma_rtn_m=sigma_rtn_m, covariance_source=source)

    def summary(self) -> dict[str, Any]:
        o = self.orbit
        return {
            "norad_id": self.norad_id, "object_name": self.object_name,
            "object_type": self.object_type, "is_active": self.is_active,
            "is_maneuverable": self.is_maneuverable, "operator": self.operator,
            "mean_alt_km": round(o.mean_alt_km, 1), "inclination_deg": self.elements.inclination_deg,
            "shell_id": self.shell_id,
        }


def mass_model(object_type: str, rcs_size: Optional[str]) -> dict[str, float]:
    """§6.5 — MODELLED mass and area-to-mass by class and RCS bucket."""
    m = CONFIG.mass
    est, low, high = m.table.get((object_type, rcs_size or ""), m.default)
    return {
        "mass_kg_est": est, "mass_kg_low": low, "mass_kg_high": high,
        "area_to_mass_m2_kg": m.area_to_mass_by_type.get(object_type, m.area_to_mass_by_type["UNKNOWN"]),
    }
