"""All tunables in one place (SPEC §20.1: "No magic numbers anywhere else").

Every constant here is either a physical constant, a published figure with its citation, or
a MODELLED assumption that the assumptions panel (§10.14) renders. If you find yourself
typing a number in another module, it belongs here.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# ── physical constants (§11) ─────────────────────────────────────────────────────────────
MU_EARTH_KM3_S2 = 398600.4418
R_EARTH_KM = 6378.137
J2 = 1.08262668e-3
OMEGA_EARTH_RAD_S = 7.2921159e-5
SECONDS_PER_YEAR = 3.15576e7
SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class ScreeningConfig:
    screening_volume_m: float = 5000.0        # §4: 5 km spherical, configurable
    coarse_step_min: float = 0.25             # 15 s. §10.3's 15 min misses crossing pairs — see screen.py docstring
    block_hours: float = 1.0                  # stage-2/3 time block for memory bounding
    gate_k: float = 4.0                       # gate = k × d_screen; documented in gate_radius()
    v_rel_max_kmps: float = 15.5              # bound used to derive the gate
    refine_tolerance_s: float = 1.0           # stage 4 effective resolution
    max_alt_km: float = 2000.0                # LEO scope
    stale_after_days: float = 7.0             # §10.1 failure modes
    dedupe_tca_s: float = 60.0                # §10.3 failure modes
    stage1_margin_km: float = 30.0            # mean-vs-osculating apsis margin (measured; see screen.py)
    formation_v_rel_floor_mps: float = 50.0   # below this the pair co-orbits (docked/formation/duplicate); not a conjunction


@dataclass(frozen=True)
class PcConfig:
    method: str = "foster_2d"                 # foster_2d | maximum
    hard_body_radius_m: float = 5.0           # MODELLED, combined (A2)
    quadrature_n_r: int = 48
    quadrature_n_theta: int = 96
    max_pc_scaling_grid: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
    dilution_check_scales: tuple[float, ...] = (1.0, 2.0, 4.0)


@dataclass(frozen=True)
class ThresholdConfig:
    """D6 — operator manoeuvre thresholds, with their sources (§6.6)."""
    declared_pc_threshold: float = 1e-4       # IADC-aligned default; ALWAYS reported with burden
    per_operator: dict[str, float] = field(default_factory=lambda: {
        "SPACEX": 3e-7,       # reported "1 in 3.3 million"
        "PLANET": 1e-4,       # publicly stated automated threshold
        "NASA": 1e-4,         # red threshold
        "IADC": 1e-4,
    })
    sources: dict[str, str] = field(default_factory=lambda: {
        "IADC": "IADC Space Debris Mitigation Guidelines",
        "NASA": "NASA CARA red/yellow thresholds",
        "PLANET": "Planet public statements",
        "SPACEX": "SpaceX FCC semiannual filings / public statements",
    })
    # geometric surrogate when Pc is unavailable (§10.5 step 2)
    surrogate_d_trigger_m: float = 1000.0
    surrogate_v_min_mps: float = 100.0
    soft_count_scale: float = 0.5             # sigmoid width in log10(Pc)


@dataclass(frozen=True)
class ManeuverConfig:
    lead_time_orbits: float = 1.0             # §10.5 step 3 default
    pc_margin: float = 2.0                    # clear to Pc*/margin (§11.5)
    dv_max_mps: float = 5.0                   # bisection upper bound
    dv_tolerance_mps: float = 1e-3
    max_bisection_iter: int = 40
    directions: tuple[str, ...] = ("T", "R", "N")   # §11.5: evaluate all, report best


@dataclass(frozen=True)
class MissionModelConfig:
    """§11.6 station-keeping budgets by altitude band, m/s per day. MODELLED."""
    sk_budget_mps_per_day: tuple[tuple[float, float, float], ...] = (
        (400.0, 500.0, 0.15),
        (500.0, 600.0, 0.05),
        (600.0, 700.0, 0.02),
        (700.0, 900.0, 0.005),
        (900.0, 2000.0, 0.003),
    )
    sk_budget_ranges_note: str = "order-of-magnitude station-keeping budgets; ±50% plausible"


@dataclass(frozen=True)
class MassModelConfig:
    """§6.5 mass lookup by (object_type, rcs_size) → (est, low, high) kg. MODELLED."""
    table: dict[tuple[str, str], tuple[float, float, float]] = field(default_factory=lambda: {
        ("ROCKET_BODY", "LARGE"): (3000.0, 1500.0, 9000.0),
        ("ROCKET_BODY", "MEDIUM"): (1000.0, 300.0, 1500.0),
        ("ROCKET_BODY", "SMALL"): (200.0, 50.0, 300.0),
        ("PAYLOAD", "LARGE"): (1200.0, 500.0, 3000.0),
        ("PAYLOAD", "MEDIUM"): (250.0, 100.0, 500.0),
        ("PAYLOAD", "SMALL"): (20.0, 1.0, 100.0),
        ("DEBRIS", "LARGE"): (5.0, 1.0, 10.0),
        ("DEBRIS", "MEDIUM"): (1.0, 0.1, 10.0),
        ("DEBRIS", "SMALL"): (0.1, 0.01, 1.0),
    })
    default: tuple[float, float, float] = (50.0, 0.01, 9000.0)
    area_to_mass_by_type: dict[str, float] = field(default_factory=lambda: {
        "PAYLOAD": 0.01, "ROCKET_BODY": 0.012, "DEBRIS": 0.05, "UNKNOWN": 0.02,
    })


@dataclass(frozen=True)
class AtmosphereConfig:
    """§11.9.1 simplified exponential atmosphere. MODELLED; solar condition stated."""
    solar_condition: str = "moderate (F10.7 ≈ 150)"
    reentry_alt_km: float = 100.0
    lifetime_cap_yr: float = 100.0
    # piecewise exponential table (h_km, rho kg/m^3, scale height km), Vallado Table 8-4 style
    layers: tuple[tuple[float, float, float], ...] = (
        (100.0, 5.297e-7, 5.877), (150.0, 2.070e-9, 22.523), (200.0, 2.789e-10, 37.105),
        (250.0, 7.248e-11, 45.546), (300.0, 2.418e-11, 53.628), (350.0, 9.518e-12, 53.298),
        (400.0, 3.725e-12, 58.515), (450.0, 1.585e-12, 60.828), (500.0, 6.967e-13, 63.822),
        (600.0, 1.454e-13, 71.835), (700.0, 3.614e-14, 88.667), (800.0, 1.170e-14, 124.64),
        (900.0, 5.245e-15, 181.05), (1000.0, 3.019e-15, 268.00),
    )


@dataclass(frozen=True)
class IngestConfig:
    """M1 — who is assumed able to manoeuvre, and the ASSUMED RTN σ (m) used until the Kelvins
    fit is wired in. Both MODELLED, both shown in the assumptions panel."""
    maneuvering_operators: tuple[str, ...] = (
        "SPACEX", "ONEWEB", "AMAZON", "PLANET", "IRIDIUM", "GLOBALSTAR", "ORBCOMM", "SPIRE", "ICEYE",
        "CAPELLA", "BLACKSKY", "UMBRA", "ASTROCAST", "KEPLER", "HAWKEYE360", "ESA-COPERNICUS", "ISS",
        "CMSA", "NASA-NOAA", "EUMETSAT", "ISRO", "USSF-GPS", "EUSPA", "CNSA-BEIDOU", "ROSCOSMOS",
        "SSST", "CHINA-SATNET", "PRC-YAOGAN", "CHANGGUANG",
    )
    # (R, T, N) 1σ position uncertainty in metres. Order-of-magnitude values for public GP data at
    # ~1 day from epoch; along-track dominates. Replaced by Kelvins-fitted σ(τ, type, alt) in M8.
    assumed_sigma_rtn_m: dict[str, tuple[float, float, float]] = field(default_factory=lambda: {
        "PAYLOAD_ACTIVE": (100.0, 800.0, 80.0),
        "PAYLOAD": (150.0, 1500.0, 120.0),
        "ROCKET_BODY": (150.0, 1500.0, 120.0),
        "DEBRIS": (250.0, 3000.0, 200.0),
        "UNKNOWN": (250.0, 3000.0, 200.0),
        "DEFAULT": (250.0, 3000.0, 200.0),
    })
    assumed_sigma_source: str = "assumed (class-based, order of magnitude; Kelvins fit pending)"


@dataclass(frozen=True)
class AttributionConfig:
    rules: tuple[str, ...] = ("R1",)          # §10.5 step 1: start with R1 only
    exclude_intra_constellation: bool = True
    coordinated_constellations: tuple[str, ...] = ("SPACEX", "ONEWEB", "AMAZON", "PLANET", "IRIDIUM", "SSST", "CHINA-SATNET")
    horizon_cap_yr: float = 25.0              # §10.5 step 7


@dataclass(frozen=True)
class FeeConfig:
    """§11.9.2 indicative fee calibration — INDICATIVE only."""
    fee_reference_usd_per_sat_yr: float = 235_000.0
    calibration: str = "Rao, Burgess & Kaffine (2020), PNAS — optimal orbital-use fee ~$235k/sat-yr by 2040"
    caveat: str = ("Scaling of a published aggregate fee estimate onto our per-object burden measure; "
                   "not a price, not a legal assessment, not calibrated to any regulatory instrument.")


@dataclass(frozen=True)
class GraphConfig:
    weight_rule: str = "pc"                   # pc | inv_miss
    w_min: float = 0.0


@dataclass(frozen=True)
class DecisionConfig:
    """§11.12 systemic cost weights (defaults) and strategy generation caps."""
    weights: dict[str, float] = field(default_factory=lambda: {
        "safety": 0.40, "future": 0.20, "fuel": 0.15, "mission": 0.15, "network": 0.10,
    })
    horizon_h: float = 72.0
    max_strategies: int = 40
    dv_grid_mps: tuple[float, ...] = (0.05, 0.15, 0.5, 1.0)
    burn_lead_orbits: tuple[float, ...] = (1.0, 2.0)
    wait_options_min: tuple[float, ...] = (30.0, 120.0, 360.0)
    mc_samples_interactive: int = 100
    mc_samples_reported: int = 1000
    # normalisation references for the cost vector (§11.12.1) — scenario-specific overrides allowed
    dv_reference_mps: float = 1.0
    days_reference: float = 20.0
    observe_cost_days: float = 0.5           # tasking a refined tracking pass, in mission-day equivalents (MODELLED)
    future_pc_reference: float = 1e-3
    network_reference: float = 1e-3


@dataclass(frozen=True)
class VoIConfig:
    """§10.8 Part B/C. Until the Kelvins fit lands these are DECLARED placeholders, labelled so."""
    lambda_per_h: float = 0.035               # shrinkage rate; Kelvins fit will replace (block 4)
    sigma_floor_fraction: float = 0.25        # σ∞ / σ0
    observe_shrink: float = 0.5               # OBSERVE action: one refined tracking pass
    c_fuel: float = 1.0
    c_risk: float = 1.0
    c_late: float = 1.0                       # P(window closes) weight — must be nonzero
    c_growth: float = 1.0                     # P(risk grows beyond recoverable) weight — must be nonzero
    source: str = "declared (Kelvins fit pending)"


@dataclass(frozen=True)
class ValidatorConfig:
    """§10.9 constraints C1–C10 defaults."""
    dv_max_per_burn_mps: float = 2.0
    remaining_dv_mps: float = 15.0
    uplink_lead_min: float = 30.0
    min_maneuver_lead_min: float = 45.0
    min_alt_km: float = 300.0
    mission_alt_band_km: float = 25.0         # C6: stay within ± this of nominal mean altitude
    mission_inc_band_deg: float = 0.5
    min_miss_floor_m: float = 500.0           # §14.3 geometric floor
    slew_time_min: float = 10.0               # C9
    eclipse_burn_allowed: bool = True         # C8 (True unless power-constrained platform)


@dataclass(frozen=True)
class CapacityConfig:
    """§11.10 / §11.13."""
    m_viability_per_sat_yr: float = 120.0     # 10 manoeuvres/month, published viability threshold
    m_viability_source: str = "2025 study: 10 CAMs/month = operationally unviable (SPEC §2.2)"
    c_intra: float = 0.05
    w_active_hazard: float = 0.1              # §11.10.3 w_a
    persistence_cap_yr: float = 100.0
    shell_width_km: float = 50.0              # aligned with pySSEM discretisation
    shell_min_km: float = 200.0
    shell_max_km: float = 2000.0


@dataclass(frozen=True)
class AgentConfig:
    temperature: float = 0.0
    seed: int = 42
    max_tool_calls: int = 25
    timeout_s: float = 60.0
    model: str = "claude-sonnet-5"


@dataclass(frozen=True)
class Config:
    screening: ScreeningConfig = ScreeningConfig()
    pc: PcConfig = PcConfig()
    thresholds: ThresholdConfig = ThresholdConfig()
    maneuver: ManeuverConfig = ManeuverConfig()
    mission: MissionModelConfig = MissionModelConfig()
    mass: MassModelConfig = MassModelConfig()
    atmosphere: AtmosphereConfig = AtmosphereConfig()
    attribution: AttributionConfig = AttributionConfig()
    ingest: IngestConfig = IngestConfig()
    fee: FeeConfig = FeeConfig()
    graph: GraphConfig = GraphConfig()
    decision: DecisionConfig = DecisionConfig()
    voi: VoIConfig = VoIConfig()
    validator: ValidatorConfig = ValidatorConfig()
    capacity: CapacityConfig = CapacityConfig()
    agent: AgentConfig = AgentConfig()
    propagator: str = "sgp4"

    def assumptions_block(self) -> dict[str, Any]:
        """The universal envelope block (§12.1) and the persistent panel (§10.14)."""
        import sgp4
        return {
            "covariance_source": "assumed",   # overwritten by the run once Kelvins fit is wired
            "propagator": f"sgp4-{sgp4.__version__}",
            "screening_volume_m": self.screening.screening_volume_m,
            "coarse_step_min": self.screening.coarse_step_min,
            "gate_k": self.screening.gate_k,
            "pc_method": self.pc.method,
            "pc_threshold": self.thresholds.declared_pc_threshold,
            "pc_threshold_source": "IADC",
            "hard_body_radius_m": self.pc.hard_body_radius_m,
            "mass_model": "class×RCS lookup (MODELLED, ranges shown)",
            "horizon_h": self.decision.horizon_h,
            "mc_samples": self.decision.mc_samples_interactive,
            "intra_constellation_excluded": self.attribution.exclude_intra_constellation,
            "c_intra": self.capacity.c_intra,
            "attribution_rules": list(self.attribution.rules),
            "weights": dict(self.decision.weights),
            "m_viability_per_sat_yr": self.capacity.m_viability_per_sat_yr,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CONFIG = Config()
