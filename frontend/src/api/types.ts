/** The wire format of SPEC §12.1. `Traced` is the only way a number reaches the screen. */

export type Label = "OBSERVED" | "COMPUTED" | "MODELLED" | "INDICATIVE";

export interface Traced {
  value: number | null;
  unit: string;
  label: Label;
  function: string;
  assumptions: Record<string, unknown>;
  na_reason: string | null;
  trace_id: string;
}

export interface Envelope<T> {
  data: T;
  assumptions: Assumptions;
  run_id: string | null;
  computed_at: string;
  meta: Record<string, unknown>;
}

export interface Assumptions {
  covariance_source: string;
  covariance_note: string;
  propagator: string;
  screening_volume_m: number;
  coarse_step_min: number;
  gate_k: number;
  pc_method: string;
  pc_threshold: number;
  pc_threshold_source: string;
  hard_body_radius_m: number;
  mass_model: string;
  horizon_h: number;
  mc_samples: number;
  intra_constellation_excluded: boolean;
  c_intra: number;
  attribution_rules: string[];
  weights: Record<string, number>;
  m_viability_per_sat_yr: number;
}

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
}

export interface LedgerEntry {
  norad_id: number;
  object_name: string;
  object_type: string;
  operator: string;
  is_active: boolean;
  is_maneuverable: boolean;
  mean_alt_km: number;
  shell_id: number;
  window_days: number;
  pc_threshold: number;
  conjunctions_generated: Traced;
  maneuvers_forced: Traced;
  maneuvers_forced_soft: Traced;
  dv_imposed_mps: Traced;
  mission_days_imposed: Traced;
  operators_affected: Traced;
  top_bearer: string | null;
  bearer_gini: Traced;
  maneuvers_performed: Traced;
  dv_spent_mps: Traced;
  cab: Traced;
  cab_normalised: Traced;
  decay_lifetime_yr_est: Traced;
  projected_lifetime_dv: Traced;
  implied_fee_usd_yr: Traced;
  n_dv_unresolved: number;
  rank_by_dv_imposed: number | null;
  on_published_top50: boolean;
  bearers?: BurdenFlow[];
}

export interface BurdenFlow {
  flow_id: string;
  imposer_id: number;
  bearer_id: number;
  bearer_operator: string;
  conj_id: string;
  n_conjunctions: number;
  n_maneuvers: number;
  dv_mps: number | null;
  dv_na_reason: string | null;
  mission_days: number | null;
  attribution_rule: string;
  contested: boolean;
  pc: number | null;
  pc_threshold: number;
  forced_by: string;
}

export interface LedgerPage {
  total: number;
  total_all: number;
  limit: number;
  offset: number;
  window_days: number;
  pc_threshold: number;
  sort: string;
  order: string;
  share_of_dv_from_dead: Traced;
  total_dv_imposed_mps: Traced;
  n_entries_nonzero: number;
  entries: LedgerEntry[];
}

export interface Conjunction {
  conj_id: string;
  primary_id: number;
  secondary_id: number;
  primary_name?: string | null;
  secondary_name?: string | null;
  primary_operator?: string | null;
  secondary_operator?: string | null;
  tca: string;
  miss_distance_m: Traced;
  rel_speed_mps: Traced;
  pc: Traced;
  pc_max: Traced;
  pc_method: string;
  covariance_source: string;
  sigma_rtn_combined_m: number[] | null;
  mahalanobis: number | null;
  dilution: boolean;
  pair_class: string;
  intra_constellation: boolean;
  encounter_plane?: EncounterPlane;
}

export interface EncounterPlane {
  available: boolean;
  na_reason?: string;
  miss_xy_m?: number[];
  miss_m?: number;
  v_rel_mps?: number;
  cov_xy_m2?: number[][];
  sigma_major_m?: number;
  sigma_minor_m?: number;
  orientation_deg?: number;
  sigma_rtn_combined_m?: number[];
  hard_body_radius_m?: number;
  hard_body_radius_label?: string;
  dilution?: boolean;
  mahalanobis?: number | null;
  covariance_source?: string;
}

export interface Cluster {
  cluster_id: string;
  members: number[];
  n_objects: number;
  n_edges: number;
  total_weight: number;
  keystone_id: number | null;
  keystone_selected_by: string;
  keystone_score: number;
  max_pc_object_id: number | null;
  max_pc_edge: number[] | null;
  max_pc: number | null;
  keystone_differs_from_max_pc: boolean;
  critical_conjunctions: number;
  member_names: Record<string, string | null>;
}

export interface Strategy {
  strategy_id: string;
  kind: string;
  proposed_by: string;
  params: Record<string, unknown>;
  label: string;
  pc_after: Traced | null;
  future_conjunctions: Traced | null;
  dv_mps: Traced | null;
  mission_impact: Traced | null;
  systemic_cost: Traced | null;
  expected_cost: Traced | null;
  p95_cost: Traced | null;
  max_regret: Traced | null;
  mc_safe_fraction: Traced | null;
  validator_verdict: string | null;
  validator_reason: string | null;
  new_conj_ids?: string[];
  removed_conj_ids?: string[];
}

export interface StrategiesResponse {
  cluster_id: string;
  cluster: Cluster;
  strategies: Strategy[];
  rejected: Strategy[];
  recommendation: {
    expected_value_optimum: string | null;
    minimax_regret_optimum: string | null;
    optima_agree: boolean;
    note: string;
  };
  weights_used: Record<string, number>;
  mc_samples: number;
}

export interface ObjectSummary {
  norad_id: number;
  object_name: string;
  object_type: string;
  operator: string;
  country: string | null;
  launch_date: string | null;
  is_active: boolean;
  is_maneuverable: boolean;
  rcs_size: string | null;
  source: string;
  stale: boolean;
  covariance_source: string;
  mean_alt_km: number;
  perigee_alt_km: number;
  apogee_alt_km: number;
  inclination_deg: number;
  period_min: number;
  mass_kg_est: Traced;
  sigma_rtn_m: number[] | null;
  epoch: string;
}

export interface ShellRow {
  shell_id: string;
  alt_low_km: number;
  alt_high_km: number;
  alt_mid_km: number;
  n_objects: number;
  n_active: number;
  n_dead: number;
  [k: string]: unknown;
}

export interface AgentTrace {
  trace_id: string;
  driver: string;
  cluster_id: string;
  recommendation: string | null;
  explanation: string;
  guard_passed: boolean;
  guard_violations: string[];
  fell_back_to_template: boolean;
  n_llm_calls: number;
  elapsed_s: number;
  error: string | null;
  n_tool_calls: number;
  tool_calls: { tool: string; args: Record<string, unknown>; ok: boolean; summary: string; elapsed_s: number }[];
  rejections: Record<string, unknown>[];
}

export interface ChaosResult {
  injection: { kind: string; params: Record<string, unknown>; seed: number };
  applied: Record<string, unknown>;
  invalidated: string[];
  invalidation_reason: string;
  still_valid: boolean;
  new_recommendation: Strategy | null;
  diff: Record<string, unknown>;
  elapsed_s: number;
  new_run_id: string;
}
