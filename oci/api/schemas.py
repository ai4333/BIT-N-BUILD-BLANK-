"""Request bodies (SPEC §9.2, §12). Responses are not modelled as pydantic types on purpose:
they carry `Traced` objects through `oci.api.serialize.wire`, and a second schema layer would
be one more place for a bare float to sneak in."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from oci.config import CONFIG


class IngestRequest(BaseModel):
    source: Literal["celestrak", "spacetrack", "synthetic"] = "celestrak"
    group: str = "active"
    include_debris: bool = True
    force_refresh: bool = False
    offline: bool = True


class ScreenRequest(BaseModel):
    window_start: Optional[datetime] = None
    window_hours: float = Field(default=72.0, gt=0, le=24 * 14)
    alt_low_km: float = 500.0
    alt_high_km: float = 1000.0
    object_ids: Optional[list[int]] = None
    screening_volume_m: Optional[float] = None
    coarse_step_min: Optional[float] = None
    gate_k: Optional[float] = None
    offline: bool = True


class LedgerComputeRequest(BaseModel):
    run_id: Optional[str] = None
    pc_threshold: float = CONFIG.thresholds.declared_pc_threshold


class StrategiesRequest(BaseModel):
    horizon_h: float = CONFIG.decision.horizon_h
    include_kinds: Optional[list[str]] = None
    mc_samples: int = Field(default=CONFIG.decision.mc_samples_interactive, ge=0, le=1000)
    weights: Optional[dict[str, float]] = None
    seed: int = 42
    validate_all: bool = True
    pc_threshold: Optional[float] = Field(default=None, gt=0, lt=1)   # the declared Pc* the decision is made at
    neighbourhood_hops: int = Field(default=1, ge=0, le=3)


class VoIRequest(BaseModel):
    run_id: Optional[str] = None
    conj_id: str
    wait_options_min: Optional[list[float]] = None


class ValidateRequest(BaseModel):
    run_id: Optional[str] = None
    target_id: int
    dv_vector_mps: list[float] = Field(min_length=3, max_length=3)
    t_burn: datetime


class DeploymentRequestBody(BaseModel):
    run_id: Optional[str] = None
    n_satellites: int = Field(default=5000, gt=0)
    target_alt_km: float = 550.0
    inclination_deg: float = 53.0
    sat_mass_kg: float = 300.0
    sat_area_m2: float = 12.0
    pmd_success_rate: float = Field(default=0.9, ge=0.0, le=1.0)
    mission_life_yr: float = 5.0
    alternatives_km: Optional[list[float]] = None
    horizon_yr: float = 15.0
    c_intra: Optional[float] = None


class AgentRequest(BaseModel):
    run_id: Optional[str] = None
    cluster_id: Optional[str] = None
    scenario: Optional[str] = None
    max_tool_calls: int = CONFIG.agent.max_tool_calls
    seed: int = 42
    mc_samples: int = 25
    pc_threshold: Optional[float] = Field(default=None, gt=0, lt=1)


class ChaosRequest(BaseModel):
    run_id: Optional[str] = None
    scenario: Optional[str] = None
    cluster_id: Optional[str] = None       # which standing recommendation to perturb (default: most critical)
    pc_threshold: Optional[float] = None
    injection: str
    params: dict = Field(default_factory=dict)
    seed: int = 42
    mc_samples: int = 25


class BenchRequest(BaseModel):
    scenario_id: Optional[str] = None
    mc_samples: int = 100
    seed: int = 42
