"""Decay lifetime estimate (SPEC §11.9.1). MODELLED: static exponential atmosphere, stated
solar condition, circular-orbit approximation. Solar-cycle variation is not modelled (A8)."""
from __future__ import annotations

import math

from oci.config import CONFIG, MU_EARTH_KM3_S2, R_EARTH_KM, SECONDS_PER_YEAR
from oci.labels import Traced, traced

_FN = "physics.decay.lifetime@0.1.0"


def density_kg_m3(alt_km: float) -> float:
    layers = CONFIG.atmosphere.layers
    if alt_km < layers[0][0]:
        return layers[0][1]
    for h0, rho0, H in reversed(layers):
        if alt_km >= h0:
            return rho0 * math.exp(-(alt_km - h0) / H)
    return layers[-1][1]


def decay_lifetime_years(alt_km: float, area_to_mass_m2_kg: float, cap_yr: float | None = None) -> Traced:
    """Integrate da/dt = -(A/m)·ρ·√(μ a) (circular) from `alt_km` down to re-entry."""
    cap = cap_yr if cap_yr is not None else CONFIG.atmosphere.lifetime_cap_yr
    a = R_EARTH_KM + alt_km
    a_end = R_EARTH_KM + CONFIG.atmosphere.reentry_alt_km
    t = 0.0
    dt = 86400.0 * 5      # 5-day steps; adaptive near the end
    while a > a_end and t < cap * SECONDS_PER_YEAR:
        h = a - R_EARTH_KM
        rho = density_kg_m3(h) * 1e9                       # kg/km³
        dadt = -(area_to_mass_m2_kg * 1e-6) * rho * math.sqrt(MU_EARTH_KM3_S2 * a)   # km/s (A/m in km²/kg)
        step = dt if h > 250 else 86400.0
        a += dadt * step
        t += step
    years = min(t / SECONDS_PER_YEAR, cap)
    return traced(years, "yr", "MODELLED", _FN, area_to_mass_m2_kg=area_to_mass_m2_kg,
                  atmosphere="static exponential, " + CONFIG.atmosphere.solar_condition,
                  capped=(t >= cap * SECONDS_PER_YEAR))
