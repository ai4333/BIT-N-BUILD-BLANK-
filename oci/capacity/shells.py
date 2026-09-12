"""M10 part 1 — shell partition and population statistics (SPEC §10.10, §11.13).

A shell is an altitude band [alt_low, alt_high). Objects are assigned by mean altitude.
Everything here is COMPUTED from the catalogue; the catalogue's own coverage (public CelesTrak
groups only, until Space-Track is wired in) is the assumption that travels with every figure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from oci.config import CONFIG, MU_EARTH_KM3_S2, R_EARTH_KM
from oci.data.objects import SpaceObject
from oci.data.operators import coordinated_constellations

_COORD = set(coordinated_constellations())

_FN = "capacity.shells@0.1.0"


@dataclass
class Shell:
    shell_id: str
    alt_low_km: float
    alt_high_km: float
    members: list[int] = field(default_factory=list)
    n_objects: int = 0
    n_active: int = 0
    n_dead: int = 0                      # inactive payloads + rocket bodies + debris
    n_debris: int = 0
    n_rocket_bodies: int = 0
    inclinations_deg: list[float] = field(default_factory=list)
    mass_active_kg: float = 0.0
    mass_inactive_kg: float = 0.0
    constellation_counts: dict[str, int] = field(default_factory=dict)   # coordinated constellations only (§10.10)

    @property
    def alt_mid_km(self) -> float:
        return 0.5 * (self.alt_low_km + self.alt_high_km)

    @property
    def volume_km3(self) -> float:
        r_lo, r_hi = R_EARTH_KM + self.alt_low_km, R_EARTH_KM + self.alt_high_km
        return 4.0 / 3.0 * math.pi * (r_hi ** 3 - r_lo ** 3)

    @property
    def spatial_density_per_km3(self) -> float:
        return self.n_objects / self.volume_km3

    @property
    def coordinated_internal_density_per_km3(self) -> float:
        """Population-averaged density of *same-constellation* neighbours: Σ_X N_X² / (N·V).
        This is the part of the flux each member meets with managed, phase-separated traffic."""
        if not self.n_objects:
            return 0.0
        return sum(n * n for n in self.constellation_counts.values()) / self.n_objects / self.volume_km3

    def contains_alt(self, alt_km: float) -> bool:
        return self.alt_low_km <= alt_km < self.alt_high_km


def shell_bounds(alt_km: float, width_km: float | None = None) -> tuple[float, float]:
    cap = CONFIG.capacity
    w = width_km or cap.shell_width_km
    lo = cap.shell_min_km + math.floor((alt_km - cap.shell_min_km) / w) * w
    return lo, lo + w


def partition(objects: Iterable[SpaceObject], width_km: float | None = None,
              alt_min_km: float | None = None, alt_max_km: float | None = None,
              include_stale: bool = False) -> list[Shell]:
    """Partition the catalogue into shells of `width_km` between alt_min and alt_max."""
    cap = CONFIG.capacity
    w = width_km or cap.shell_width_km
    lo0 = cap.shell_min_km if alt_min_km is None else alt_min_km
    hi0 = cap.shell_max_km if alt_max_km is None else alt_max_km
    n = int(math.ceil((hi0 - lo0) / w))
    shells = [Shell(f"shell_{int(lo0 + k * w):04d}", lo0 + k * w, lo0 + (k + 1) * w) for k in range(n)]
    for o in objects:
        if o.stale and not include_stale:
            continue
        h = o.orbit.mean_alt_km
        if not (lo0 <= h < hi0):
            continue
        s = shells[int((h - lo0) // w)]
        s.members.append(o.norad_id)
        s.n_objects += 1
        s.inclinations_deg.append(o.elements.inclination_deg)
        if o.is_active:
            s.n_active += 1
            s.mass_active_kg += o.mass_kg_est
            if o.operator in _COORD:
                s.constellation_counts[o.operator] = s.constellation_counts.get(o.operator, 0) + 1
        else:
            s.n_dead += 1
            s.mass_inactive_kg += o.mass_kg_est
            if o.object_type == "DEBRIS":
                s.n_debris += 1
            elif o.object_type == "ROCKET_BODY":
                s.n_rocket_bodies += 1
    return shells


# ── mean relative speed from the inclination distribution (§11.13) ──────────────────────────
def _plane_normal(inc_rad: np.ndarray, raan_rad: np.ndarray) -> np.ndarray:
    return np.stack([np.sin(inc_rad) * np.sin(raan_rad), -np.sin(inc_rad) * np.cos(raan_rad), np.cos(inc_rad)], axis=-1)


def mean_relative_speed_kms(inclinations_deg: Sequence[float], alt_km: float, n_pairs: int = 4000,
                            seed: int = 0, second_population_deg: Sequence[float] | None = None) -> float:
    """E[v_rel] over random pairs of the empirical inclination distribution with uniform
    relative node geometry. For two circular orbits of equal radius the encounter happens on
    their line of intersection, where |v_rel| = 2·v_orb·sin(θ/2) and θ is the dihedral angle
    between the planes (cos θ = n₁·n₂). Same-plane pairs contribute zero, as they should."""
    if len(inclinations_deg) < 2 and second_population_deg is None:
        return 0.0
    rng = np.random.default_rng(seed)
    v_orb = math.sqrt(MU_EARTH_KM3_S2 / (R_EARTH_KM + alt_km))
    a = np.radians(rng.choice(np.asarray(inclinations_deg, float), n_pairs))
    pool_b = np.asarray(second_population_deg if second_population_deg is not None else inclinations_deg, float)
    b = np.radians(rng.choice(pool_b, n_pairs))
    d_raan = rng.uniform(0.0, 2.0 * math.pi, n_pairs)
    cos_t = np.clip(np.sum(_plane_normal(a, np.zeros(n_pairs)) * _plane_normal(b, d_raan), axis=1), -1.0, 1.0)
    theta = np.arccos(cos_t)
    return float(np.mean(2.0 * v_orb * np.sin(theta / 2.0)))
