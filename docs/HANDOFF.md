# OCI — HANDOFF (read this first if you are continuing the build)

Last updated: 2026-09-13 (commit `301085c`). Blocks 0–8, 10 and 11 are done — backend, REST API, demo script, and
a working frontend wired to the API. **Verified end-to-end in the browser on 2026-09-13** (`make api-safe` + `make ui`,
offline): S1 ledger (filters, borne/imposed toggle), S2 object card (NORAD 30290 with bearers, conjunctions, S4 encounter
plane), S3 event console on the real run AND on `scenario:keystone_cluster` (strategies table, rejected list, run planner
→ S7 trace with guard PASSED, ⚡ CHAOS → invalidation + diff in 6–8 s), S5 shell map (two peaks), S6 deployment
(optima disagree), S8 benchmark, S9 provenance. 155 tests pass offline.

**STRAIGHT ANSWER TO "IS IT ALL BUILT?": Yes, functionally — every screen works against real computed data. NOT done:
the visual pass on the frontend (the user wants it to look like `docs/reference-ui/preview/`, the earlier WebGL globe
mock) and the globe view (S10, cut-first per spec). Two known small gaps: (a) the decision engine's Pc* is the config's
declared 1e-4 everywhere; the UI threshold selector re-labels the ledger and re-clusters the graph but does not re-run
strategies at 1e-5 (changing that means threading `pc_threshold` through `generate_strategies/evaluate/validate`);
(b) a conjunction whose Pc underflows to exactly 0.0 prints "0" on the object card — should print "< 1e-300".**

Repo: `/Users/nikhilsridhara/bit n build` → `https://github.com/ai4333/BIT-N-BUILD-BLANK-.git`, branch `main`.
Python venv: `.venv` (Python 3.13). Run everything with `.venv/bin/python`.

If you have no other context: this file + `SPEC.md` (the 4,188-line authoritative spec, "OCI_MASTER_SPEC v2.0")
+ `README.md` are enough to continue. Read `SPEC.md` §16 (build order) and the section for whatever block you
are building before touching code. The spec wins over this file wherever they disagree, except for the
"measured deviations" listed below.

---

## 0. The non-negotiable rules (from the user, Nikhil)

1. **Hackathon rules:** everything in this repo must be original code written during the hackathon. The
   folder `inspiration/` (gitignored) contains reference repos — **read-only, never copy, never push**.
   Commit every 3–6 hours. The first commit must look deliberate.
2. **Commit trailer.** Commits through block 6 carry `Co-Authored-By: Team Blank`. From block 7 on, the
   session's attribution policy requires the AI co-author trailer, so blocks 7+ carry
   `Co-Authored-By: Claude Opus 5`. Raised with the user rather than changed silently; if the
   hackathon's originality rules need something different, that is the user's call to make, not a
   thing to paper over in a trailer.
3. **No money on LLM APIs.** The planner (M11) must work with **no API key**. The deterministic driver
   (`oci/agent/planner.py::DeterministicPlanner`) is THE path; the LLM driver exists but is only used if
   `LLM_API_KEY`/`ANTHROPIC_API_KEY` is set. **Never ask for a key.** If a feature "needs an LLM", solve it
   deterministically (templates, rules, search).
4. **Build the whole spec, don't cut corners** — the target is to win a state → national hackathon
   (Track: Space Tech & Orbital Sustainability; judging: problem impact, innovation, agentic AI, technical,
   usability, demo video). Block 12 (globe) is cut-first per §16.5. Everything else is required.
5. **Don't ask questions; keep building.** Make routine decisions yourself; note them in the README /
   `docs/ASSUMPTIONS.md`.
6. Keep `docs/reference-ui/` (an early WebGL globe mockup) as reference only — it is not the MVP UI.
7. Every number on screen carries a `Traced` label (`OBSERVED | COMPUTED | MODELLED | INDICATIVE`) or is an
   explicit `N/A` with a reason. **Never a silent zero.** (`oci/labels.py`.)

---

## 1. What the project is (one paragraph)

Satellites burn propellant dodging each other and dead junk. A large share of that dodging is forced by
objects that are already dead (rocket bodies, failed satellites) which impose the full cost of avoidance on
everyone else, for free. Nobody measures that cost per object. **OCI does:** from free public orbital data
(CelesTrak GP JSON + SATCAT + SOCRATES + ESA Kelvins CDMs) it screens conjunctions in an altitude shell,
builds an interaction graph, and computes an **externality ledger** — per object: manoeuvres and Δv it forces
on other operators, who pays, and the cost over its remaining life (dead → active attribution rule R1). It
then uses that ledger to pick **today's avoidance action** (HOLD / MANEUVER / WAIT-for-information /
OBSERVE / COORDINATE, ranked by expected systemic cost, p95 and minimax regret under Monte Carlo) through a
**planning agent that can only act via 8 tools**, a **deterministic validator (C1–C10)** that rejects
infeasible burns, a **number-fabrication guard**, a **capacity engine** that says what altitude a new
constellation should deploy to (done: two-peaks finding reproduced from the public catalogue), and — still to
build — a **REST API**, a **React frontend**, and **chaos mode** (inject a breakup / fail a satellite, watch
every recommendation recompute).

Stack: Python 3.13, sgp4, skyfield, numpy, scipy, networkx, pandas, fastapi, pydantic, sqlalchemy, pytest.
Frontend spec (§13): React 18 + Vite + Tailwind + Recharts + TanStack Query, **no Three.js in MVP**.

---

## 2. What is DONE (blocks 0–6, 10, 11 of §16.3) — 108 tests pass offline

Run: `make setup && make test` (≈4 min), `make demo`, `python -m oci demo --agent`.

### Files and what each does

```
SPEC.md                         the spec. README.md  status + measured results. Makefile  targets below.
pyproject.toml, .env.example, .gitignore (inspiration/, docs/references/, .claude/, data/cache/, data/kelvins/, .venv)
docs/ASSUMPTIONS.md   generated by `python -m oci assumptions` from oci/config.py (oci/assumptions_doc.py)
docs/PRIOR_ART.md     literature/prior systems (§2.7)     docs/BENCHMARK.md  generated by `python -m oci bench`
docs/KELVINS.md       generated by `python -m oci kelvins`  models/covariance_fit.json  the fitted covariance (committed)
docs/reference-ui/    early UI research + a globe preview (reference only)
data/fixtures/        gp_sample.json, satcat_sample.csv, socrates_MINRANGE_1000.html, socrates_gp/*.csv, bench/*.json
                      → tests and --offline modes run from these with the cable pulled

oci/config.py         ALL tunables as frozen dataclasses; CONFIG.assumptions_block() feeds the API/UI assumption strip.
                      ScreeningConfig(screening_volume_m=5000, coarse_step_min=0.25 (=15 s), block_hours=1, gate_k=4,
                      stage1_margin_km=30, formation_v_rel_floor_mps=50, stale_after_days=7)
                      PcConfig(hard_body_radius_m=5)  ThresholdConfig(declared_pc_threshold=1e-4, per-operator table)
                      ManeuverConfig(lead 1 orbit, margin 2, dv_max 5)  MissionModelConfig  MassModelConfig  AtmosphereConfig
                      IngestConfig(maneuvering_operators, assumed_sigma_rtn_m by class)  AttributionConfig(R1, coordinated constellations)
                      FeeConfig($235k reference)  GraphConfig  DecisionConfig(weights safety .40/future .20/fuel .15/mission .15/network .10,
                      dv_grid (0.05,0.2,1.0), leads (1,2) orbits, waits (30,120,360) min, observe_cost_days 0.5, horizon_h 72, mc_samples 100)
                      VoIConfig  ValidatorConfig(dv_max 2 m/s, uplink 30 min, min lead 45 min, min_alt 300 km, miss floor 500 m)
                      CapacityConfig(M_viability 120, c_intra 0.05)  AgentConfig(model, seed 42, max_tool_calls 25)
oci/labels.py         Traced{value, unit, label, function, assumptions, na_reason}; traced(); na(); walk_for_bare_floats()

oci/data/objects.py   Elements, SpaceObject, derive_orbit(), mass_model()
oci/data/synthetic.py scenarios: two_body_head_on, keystone_cluster (6 objects; keystone 91002 ≠ max-Pc object 91001),
                      dead_rocket_body (92000 dead, imposes on 5 victims), voi_event (Pc 7e-5 < Pc*, correct answer HOLD);
                      helpers crossing_state(), object_from_state(), chaos_new_object()  ← use for chaos mode
oci/data/celestrak.py fetch_gp_group (GP JSON, cache data/cache/, ≤1 fetch/2 h, --offline), load_satcat, fetch_socrates (HTML parser
                      for table-socrates.php and data.php?CATNR=a,b), OfflineCacheMiss
oci/data/ingest.py    M1: normalise() → SpaceObject with provenance; BadElementSet rejected not coerced; infer_active/maneuverable
                      (conservative); object_sigma() uses the Kelvins fit if models/covariance_fit.json exists else class σ; shell_filter()
oci/data/operators.py + operator_map.yaml   name/owner → operator; AGENCY_OWNERS; coordinated_constellations()
oci/data/socrates.py  cross_validate_same_elements() / cross_validate_current_elements() vs SOCRATES
oci/data/kelvins.py   M8-A: load (kaggle, ~/.kaggle creds exist), fit_covariance (log10 σ_k = a + b·log10(1+τ) + type + alt band),
                      fit_shrinkage (λ=0.53/day), replay(), save_models/load_models, write_doc
oci/physics/propagate.py  M2: SGP4/TEME propagation, State(r_km, v_kms)
oci/physics/geometry.py   rtn_basis, covariance_inertial, encounter_plane   oci/physics/pc.py  foster_2d, pc_maximum, dilution_flag, compute_pc
oci/physics/screen.py     M3: screen(objects, t0, t1) → ScreeningResult(run, conjunctions). Filter chain: stage-1 apsis overlap (30 km margin)
                      → per-sample cKDTree spatial index at 15 s → parabolic dip gate → bounded TCA refinement on minutes-offset →
                      formation-flyer filter (v_rel < 50 m/s) → Pc with covariance evaluated at each conjunction's time-to-TCA.
                      Also refine_tca, annotate_risk(tca=...), brute_force_screen, screen_pair. SMALL_SET fast path ≤ 64 objects.
oci/physics/maneuver.py   rv2coe, fit_mean_elements (least-squares in EQUINOCTIAL params, x_scale="jac"), Burn, apply_maneuver, dv_to_clear
oci/physics/decay.py      lifetime estimate (INDICATIVE)
oci/graph/build.py        M4: build_graph → GraphResult(clusters, keystone by risk-weighted degree (maneuverable), disagreement flag)
oci/ledger/attribution.py R1 dead→active; intra-constellation excluded    oci/ledger/compute.py  M5: compute_ledger → LedgerResult(entries,
                      BurdenFlow); CAB in m/s; threshold on every figure; fee reference = mean borne Δv per active sat-yr
oci/sim/simulate.py       M6: Action(kind, burn, wait_min, then=Action) with burns(), expected_dv_mps, delay_risk; OrbitalState(objects, epoch,
                      conj_ids, horizon_h); simulate(state, action, …) is PURE (no hidden state — required for chaos mode); shrinkage_params()
oci/decide/optimize.py    M7: generate_strategies (HOLD, MANEUVER grid, WAIT-then-clear priced by VoI, OBSERVE, COORDINATE keystone+max-Pc,
                      iterated plans), cost_vector (log_norm safety flat below Pc*/margin; future linear vs 10·Pc*; deferred clearance Δv),
                      evaluate() with MC (samples evaluated with refined covariance σ×floor) → three rankings by_expected/by_robust/by_regret
oci/decide/iterate.py     max_pc_first, keystone_first, chain    oci/decide/voi.py  compute_voi (wait options, σ reduction, E[Pc], E[Δv], risk_of_delay)
oci/decide/validate.py    M9: validate(action, state, conjs, sim=None) → Verdict(status, reason, violated, checks C1–C10);
                      C7 = post-burn re-screen for NEW conjunctions; 500 m miss floor
oci/bench/baselines.py    B1 (max-Pc only), B2 (pairwise + post-manoeuvre re-screen = standard practice), B3, B4
oci/bench/harness.py      M15: run_scenario, render, SCENARIO_SET S1/S2/S3/S5; verdict on expected cost with 5 % tie band → docs/BENCHMARK.md
oci/agent/tools.py        M11: ToolContext(state, conjunctions, graph, ledger, strategies, calls); 8 tools + evaluate_deployment stub;
                      TOOLS registry (fn, JSON schema), DESCRIPTIONS, anthropic_tool_defs(), call_tool() logs args/result/summary/elapsed
oci/agent/prompts.py      SYSTEM_PROMPT verbatim §14.4, USER_TEMPLATE
oci/agent/guard.py        §14.6 check_no_fabricated_numbers(text, tool_results) → offending literals; tolerance = display precision or 2 %
oci/agent/planner.py      AgentTrace; DeterministicPlanner.run (procedure below); LLMPlanner (tool-use loop, optional); plan()
oci/capacity/shells.py    M10: partition(objects) → Shell(alt band, counts, inclinations, constellation_counts); mean_relative_speed_kms()
oci/capacity/flux.py      kinetic-gas flux: calibrate() vs M3, shell_flux() (c_intra on coordinated share), deployment_flux()
oci/capacity/ocs.py       ocs_from_burden (anchored 120/sat-yr), hazard index, estimate_kappa() by simulation, compute_capacity() → CapacityResult
oci/capacity/deployment.py DeploymentRequest → evaluate_deployment() → DeploymentResult (baseline, alternatives, two_peaks_finding, recommendation)
oci/capacity/report.py    render_shells/render_deployment/write_doc → docs/CAPACITY.md    CLI: python -m oci capacity [--kappa]
oci/sim/chaos.py          M14: Injection(kind, params, seed); chaos(state, prev, inj) → (new_state, applied) PURE; replan(prev, inj, n_mc=25)
                      → ChaosResult(invalidated, invalidation_reason, still_valid, diff{was, now, why, pc…}, new PipelineResult); render()
                      Policy overrides travel on OrbitalState.policy (uplink_lead_min, excluded_kinds) so injections stay pure.
                      CLI: python -m oci chaos --scenario keystone_cluster --inject NEW_OBJECT COVARIANCE_SPIKE --param factor=4
oci/pipeline.py           run_pipeline(scenario, n_mc, seed, validate_all, agent) / run_on_state(state, …) → PipelineResult; render_report()
oci/__main__.py           commands: demo [--agent], ingest, screen, ledger, validate-socrates, bench, kelvins, assumptions
tests/                    conftest, test_physics, test_screen_graph_ledger, test_decide, test_ingest, test_kelvins, test_bench, test_agent (90 tests)
```

### The deterministic planner procedure (what `python -m oci demo --agent` shows)
get_cluster → get_conjunction (max-Pc edge) → compute_voi → simulate_action for HOLD, WAIT-then-clear (best VoI wait),
clearing burn on keystone, clearing burn on max-Pc object, "instinct" 1 m/s along-track one orbit out, late 0.3 m/s burn
at TCA−40 min → run_uncertainty_analysis on each → rank_strategies → **validate_action on EVERY burn** (rejections are the
validator's, e.g. late burn fails C4, WAIT-then-clear fails C7 by creating a new conjunction with 91003) → a C3/C4/C7
rejection is re-proposed once, one orbit earlier at half magnitude → re-rank → best-ranked APPROVED = recommendation →
templated explanation (RECOMMENDATION / WHY 1–5 with `[source: tool]` / TRADE-OFFS / CONFIDENCE BASIS / ASSUMPTIONS)
→ guard. keystone_cluster: 25 tool calls, 2 rejections, guard PASSED, ~14 s.

### Measured results (all reproduced by the CLI; quote these in the demo)
- Screening vs SOCRATES, same elements: **99 % recall** (98/99), TCA to the ms, miss < 0.5 m. Real 700–900 km shell,
  2,583 objects, 72 h → 2,827 conjunctions in 74 s; 66 % debris-on-debris, 29 % active-vs-dead.
- Real ledger at Pc* 1e-5 bills Fengyun-1C / Cosmos-2251 fragments to Yaogan / Iridium / ESA, 0.1–0.5 m/s each.
- Kelvins fit on 159,506 CDMs: along-track R² 0.54, debris 10× worse; shrinkage λ = 0.53/day (41 %/day); replay at 1e-5:
  51 WAIT / 39 correct / 12 dangerous / 0.65 m/s saved per correct wait; our Pc correlates 0.68 with ESA's risk field.
- Benchmark: S1 NEUTRAL, S2 OCI_BETTER (matches B2's plan, better regret), S3 OCI_BETTER, S5 NEUTRAL.
- Capacity (`python -m oci capacity --offline`, docs/CAPACITY.md): workload peak 450–500 km (9,061 Starlink in one shell),
  hazard peak 750–800 km; flux vs pairwise calibration factor 0.6–1.1 over eight shells; 5,000 sats @ 53°: workload-optimal
  650 km, hazard-optimal 500 km, optima_disagree=true; uncoordinated would need 70 manoeuvres/sat-yr vs 17; κ(750–800 km)=0.33
  SUBSTITUTES (real), κ=3 COMPLEMENTS on the synthetic corridor scenario.

### Measured deviations from the spec (keep; documented in README)
1. Screening coarse step is **15 s, not 15 min** (15-min samples missed every off-grid crossing TCA; error bound ½·a·Δt²).
2. Stage-1 mean-element path filter replaced by a **per-sample cKDTree spatial index** + apsis margin 30 km (the Keplerian
   filter rejected a real 200 m SOCRATES conjunction).
3. Mean-element rebuild after a burn is a least-squares fit in **equinoctial** elements (Keplerian stalled at e≈1e-4).
4. TCA refinement optimises a **minutes offset**, not the absolute JD (scalar minimiser never moved at x≈2.46e6).
5. Fee reference is **mean borne Δv per active sat-year** (spec's reference is identically zero under R1).

### Things that bit us (don't repeat)
- Formation-flying pairs (v_rel≈0) produce NaN Pc → filtered at 50 m/s; counted in `run.n_formation_pairs_dropped`.
- Safety cost must be flat below Pc*/margin or the optimiser burns fuel for nothing (caught by benchmark S1).
- MC must re-evaluate sampled misses with the *refined* covariance, not the original (double-counting; S2).
- WAIT alone is not a plan — it is priced as WAIT-then-clear using VoI expected Δv (S3).
- Rocket bodies: CelesTrak public groups carry only two. Space-Track registration is pending (`.env.example`).
- Guard tolerance: numbers permitted if within half a unit of the displayed precision or 2 % of a tool value, integer % of a
  fraction, or ×1000 unit change. `rank_strategies` rows include `safe_fraction` so the explanation can cite it.

---

## 3. What REMAINS — build in this order

Time estimates are for one focused session; each block ends with tests, README update, commit, push.

### Block 10 — Capacity engine M10 — DONE (commit "Block 10"). Kept here for what the UI needs:
`compute_capacity(objects, conjunctions, screened_ids, window_days, pc_threshold, kappa_state=None)` → `CapacityResult.shells[i].row()`
(everything S5 needs) and `evaluate_deployment(cap, DeploymentRequest(...)).as_dict()` is exactly the §12.3 JSON. Original plan:
- `shells.py`: partition an altitude range into shells (e.g. 25 km bins 300–2,000 km); per shell count active / dead /
  debris, mean inclination spread, decay lifetime (from `oci/physics/decay.py`).
- `flux.py`: per-shell collision flux / interaction rate from the screening result (conjunctions per object-day) and the
  ledger (imposed Δv per active sat-year). Label COMPUTED where from screening, MODELLED where extrapolated.
- `ocs.py`: **Orbital Capacity Score** per shell with the κ regime (spec defines κ = interaction density relative to
  viability M_viability=120; c_intra=0.05 in `CapacityConfig`); the **"two peaks"** chart data (S5): a shell is attractive
  (low flux, long life) vs. crowded; produce Traced values with the regime label.
- `deployment.py`: `evaluate_deployment(constellation_size, altitude_km, inclination_deg, …)` → marginal capacity
  consumption, expected imposed/borne Δv per sat-year, substitutes/complements shell verdict, alternatives sweep over
  nearby altitudes (cut 2nd if time collapses — keep the single-altitude evaluation).
- Wire `oci/agent/tools.py::evaluate_deployment` (currently returns an error stub) to it; add scenarios
  `substitutes_shell`, `complements_shell`, `deployment_5000` in `oci/data/synthetic.py`; CLI `python -m oci capacity`;
  tests `tests/test_capacity.py` (§10.10 acceptance criteria in the spec).

### Block 11 — Chaos mode M14 — DONE (commit "Block 11"). What the API/UI need: `replan(prev, Injection(kind, params, seed))`
returns `ChaosResult`; `KINDS` lists the seven injection kinds; `render()` is the terminal view; the diff dict is the §12.4
`POST /chaos` response body (`invalidated`, `invalidation_reason`, `new_recommendation`, `diff{was, now, why}`).

### Block 7 — REST API M12 — DONE. What exists:
`oci/api/` — `app.py` (33 endpoints under `/api/v1`), `store.py` (run registry), `jobs.py` (202 + poll),
`schemas.py`, `serialize.py`, `errors.py`. Every 200 carries `{data, assumptions, run_id, computed_at, meta}`;
every display number is a `Traced` on the wire plus a `trace_id`; errors are RFC 7807. `OCI_DEMO_SAFE=1`
refuses anything that would touch the network. `tests/test_api.py` — 42 tests including the three §17.5
honesty tests that had never been written.

Three things worth knowing before you touch it:
- **`/shells` and `/deployment` compute over the whole catalogue, not the screened shell.** On one shell the
  two peaks collapse into one. `store.catalogue()` ingests once per process and caches.
- **`trace_id` is derived, not stored.** SPEC §13.8 wants an id riding on every `Traced`; `Traced` is a value
  object shared across responses, so the id is `sha1(function|unit|value)`, minted and registered in
  `serialize.traced_wire` as responses are serialised, and served by `GET /provenance/{trace_id}`. That is a
  deviation from `oci/provenance.py` as specced, and it is deliberate — same panel on screen, no plumbing
  threaded through every computation.
- **`walk_for_bare_floats` is now wired and it fails the build.** `labels.STRUCTURAL_KEYS` grew a documented
  allow-list in three groups (orbital identity, diagnostics that ride alongside a Traced, wall-clock). If you
  add a display number, make it a `Traced` — do not widen that list to make a test pass.

### THE DEMO RUN — read this before quoting any ledger figure
`run_20260912T1700Z_4371` (500–1000 km, 7 days, 5,745 objects) is the run the demo uses. The earlier
700–900 km / 72 h run produced an **empty ledger at Pc\* 1e-4 and six rows at 1e-5** — attribution under R1
needs a conjunction above threshold between a dead object and an *active, steerable* one, and that shell had
194 steerable satellites. The wider shell over a full week has 2,013 and bills 57 objects / 49.7 m/s to
sixteen operators. Do not re-screen below 500 km expecting more: 7 days is the ceiling because element sets
are flagged stale at 7. At 1e-4 exactly **one** object is billable even on the good run — that is reported,
not hidden.

### Blocks 8–9 — Frontend M13 — BUILT, visual pass outstanding
`frontend/` — Vite + React 18 + TypeScript + TanStack Query + Recharts. `make ui-setup` once, then `make ui`.
Screens S1 ledger, S2 object card, S3 event console, S4 encounter plane (plain SVG), S5 shell map,
S6 deployment, S7 agent trace, S8 benchmark, S9 provenance. Components per §13.9: `AssumptionStrip`,
`TracedNumber`, `NaValue`, `ProvenancePanel`, `ChaosButton`, `Plate`. Design tokens in
`src/styles/tokens.css`, layout in `console.css` — the aerospace ops-console language, written from scratch.

**Outstanding, and the user is directing it:** the globe view and the final visual pass. The user wants it to
match the earlier WebGL globe preview in `docs/reference-ui/preview/` (dotted-land Fibonacci globe, Fresnel
atmosphere, sunset terminator) with the console panels around it — see `docs/reference-ui/visual-bible.md`
for the recipes. Note this contradicts SPEC §13 (which says no Three.js and cuts the globe first); the user
has overridden that deliberately. Everything under `inspiration/` and the AGPL references is technique-only.

### Demo & polish — DONE except the rehearsal
`docs/DEMO.md` is written: the §19 script timed to 4:15, the offline rehearsal checklist, and seven judge
questions answered honestly (including why the threshold is 1e-5 and why the dollar figure is INDICATIVE).
`make api`, `make api-safe`, `make ui`, `make dev`, `make demo-safe`, `make capacity`, `make chaos` exist.

**Still to do:** three timed rehearsals with the cable pulled (§17.6), the globe + visual pass, and a push
to the remote.

---

## 4. How to work in this repo

```
make setup            # venv + editable install
make test             # 90 tests, offline, ~4 min
make demo             # keystone_cluster terminal report (~25 s)
python -m oci demo --scenario dead_rocket_body --agent --mc 0
python -m oci screen --alt-low 700 --alt-high 900 --hours 72 --offline   # uses data/cache (fetch once online first)
python -m oci ledger --threshold 1e-5
python -m oci bench && python -m oci kelvins && python -m oci assumptions
git add -A && git commit -m "Block N: …

Co-Authored-By: Team Blank" && git push origin main
```

Conventions: module docstring cites the SPEC section; every tunable lives in `oci/config.py`; every output number is
`Traced`; simulation is pure; tests live in `tests/test_<module>.py` and must pass with no network; README "Status" and the
measured-results list are updated at every block; commits are titled `Block N: <what>` with the Team Blank trailer.
