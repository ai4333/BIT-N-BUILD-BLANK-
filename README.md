# Orbital Capacity Intelligence

Satellites burn propellant dodging each other and dodging dead junk. A large share of that
dodging is forced by objects that are already dead — spent rocket bodies, failed satellites —
which cannot move and impose the entire cost of avoidance on everyone else, for free, forever.

Nobody has measured that cost per object. This does.

From free public orbital data, OCI computes for every object in orbit: how many manoeuvres and
how much Δv it forces other operators to spend, who pays, and what it will cost over its
remaining life. It then uses that ledger to choose both today's avoidance manoeuvre and
tomorrow's deployment altitude.

Research prototype. Decision support, not a flight command. Not flight-certified.
Assumptions: [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md). Prior art: [docs/PRIOR_ART.md](docs/PRIOR_ART.md).
Full specification: [SPEC.md](SPEC.md).

## Status

Build order (SPEC §16.3): **blocks 0–7, 10 and 11 done and tested** — the complete backend and the
REST API; — the vertical slice, real data
+ screening validated against CelesTrak SOCRATES, graph + ledger on a real shell, the
benchmark harness (`docs/BENCHMARK.md`), the ESA Kelvins covariance fit (`docs/KELVINS.md`),
the planning agent (M11) with its number-fabrication guard, the capacity engine (M10, `docs/CAPACITY.md`),
chaos mode (M14), and the REST API (M12) with its universal envelope and RFC 7807 errors.

```
make setup
make demo                         # block 0: keystone_cluster in the terminal, ~22 s
make demo-ledger                  # block 0: dead_rocket_body — one dead object billing three operators
python -m oci ingest --debris     # block 1: live catalogue (16.5k active + 2.7k debris), ingest report
python -m oci screen --alt-low 700 --alt-high 900 --hours 72   # real shell, 2,583 objects, 74 s
python -m oci ledger --threshold 1e-5                          # the real externality ledger
python -m oci validate-socrates   # screener vs SOCRATES, same element sets and current ones
python -m oci bench               # baselines B1–B4 vs OCI on S1/S2/S3/S5 → docs/BENCHMARK.md
python -m oci kelvins             # covariance + shrinkage fit on 159k real CDMs; replay → docs/KELVINS.md
python -m oci demo --agent        # block 6: the planner's full tool trace, rejections, guarded explanation
python -m oci capacity --offline  # block 10: shell map (OCS, hazard, κ) + the 5,000-satellite deployment table → docs/CAPACITY.md
python -m oci chaos --inject NEW_OBJECT COVARIANCE_SPIKE   # block 11: perturb, invalidate, replan in ~6 s, print the diff
make api-safe                     # block 7: the REST API on :8000 from cached runs only, no network
make test                         # 150 acceptance tests; passes offline from committed fixtures
```

Measured, on 2026-09-12 data:

- **Screening vs SOCRATES, same element sets: 98/99 = 99 % recall** on genuine encounters,
  TCA agreement to the millisecond, miss distance within 0.5 m. The one miss is a
  stale element set excluded by policy. Formation-flying pairs (relative speed < 50 m/s,
  ~15 % of SOCRATES' closest 1,000 rows) are dropped by policy — there is no encounter to
  decide on.
- Screening vs SOCRATES with *today's* elements: 69 % on day 0 decaying to ~23 % by day 6.
  That decay is data, not the engine — the closest SOCRATES pairs are Starlink pairs, and a
  30 m predicted miss is exactly what makes an operator manoeuvre before the next element set.
- **The demo run: 500–1000 km, 7 days, 5,745 objects** (3,295 active of which 2,013 steerable,
  2,450 dead). 16.4 M pairs → 24,492 conjunctions within 5 km in 677 s: 58 % active-on-active,
  22 % active-vs-dead, 20 % debris-on-debris; 47 conjunctions exceed 1e-4 and 322 exceed 1e-5.
  At Pc\* = 1e-5 the ledger bills **57 dead objects of 5,643** — Fengyun-1C, Cosmos-2251 and
  Iridium-33 fragments — a total of 49.7 m/s, 3.28 m/s for the worst single fragment. The bill
  lands on sixteen operators: SpaceX, Amazon, Iridium, ESA, NASA-NOAA, ISRO, JAXA, DLR, CNES,
  CSA, Planet, Spire, ChangGuang and others. Every imposer bears zero, because none of them can
  manoeuvre.
- **The ledger is threshold-sensitive, and we say so rather than pick the flattering number.**
  At the declared 1e-4 exactly one object in this shell is billable over a week — high-Pc events
  are genuinely rare. At 1e-5 there are 60. Both are one click apart in the UI and the threshold
  is printed on every figure. An earlier 700–900 km / 72 h run produced only six billable objects,
  which is why the demo run is the wider shell over a full week: attribution needs a conjunction
  above threshold between a dead object and an *active, steerable* one, and that shell held only
  194 steerable satellites against 2,013 here. The ledger screen leads on 1e-5 for that reason,
  never silently.
- **Covariance is fitted, not invented.** `log10 σ = a + b·log(1+τ) + type + altitude`, fitted
  on 159,506 real CDMs (12,787 events) from the ESA Kelvins challenge: along-track R² 0.54,
  σ_t grows ≈ τ², debris is 10× worse than payloads. The fit is evaluated at each conjunction's
  own time-to-TCA and labelled `kelvins_fitted` everywhere; the residual spread (0.5 dex) sits
  in the assumptions panel. Our Pc correlates 0.68 with ESA's own risk field.
- **WAIT is measured, not asserted.** The chaser's uncertainty shrinks 41 %/day as TCA
  approaches (λ = 0.53/day, fitted on 10,081 event time series). Replaying 10,638 real events at
  Pc* = 1e-5: WAIT recommended 51 times — 39 correct, 12 dangerous — saving 0.65 m/s per
  correct wait. The dangerous count is printed next to the saving.
- With the fitted covariance the ledger is reported at 1e-5, with the threshold on every figure
  and a selector on the ledger screen.
- **Benchmark vs standard practice (B2 = pairwise + post-manoeuvre screening):** S1 tie
  (as the spec says it should), S2 keystone cluster — OCI matches B2's plan exactly and wins on
  regret, S3 high-uncertainty event — OCI better, S5 dead rocket body — tie. Where OCI loses a
  row (Δv, residual Pc) the table prints it. OCI's candidate set contains B2's iterated plan by
  construction, so it can only improve on standard practice, never do worse than noise.
- Three modelling flaws the harness caught before any UI existed: the safety term rewarded
  burning fuel to push Pc far below threshold (S1); Monte Carlo re-evaluated sampled misses
  with the *same* covariance, double-counting uncertainty (S2); WAIT alone was scored as a
  plan (S3). All three are fixed and documented in `oci/decide/optimize.py`.
- Rocket bodies: the public CelesTrak groups carry only two. Space-Track (registration
  pending) supplies the rest; `oci/data/spacetrack.py` is the next ingest source.

- **The planner reasons only through tools.** `oci/agent/` implements the eight tools of §14.2
  and the §14.4 procedure. Without LLM credentials it runs a deterministic driver that follows
  the same procedure through the same registry — get_cluster → get_conjunction → compute_voi →
  simulate (HOLD, WAIT-then-clear, clearing burns on keystone and max-Pc object, an "instinct"
  1 m/s burn, a late 0.3 m/s burn) → uncertainty → rank → validate *every* burn → templated
  explanation. On `keystone_cluster` the validator rejects two of its own proposals (the
  WAIT-then-clear plan on C7 — it creates a new 1.6e-4 conjunction with 91003 — and the late
  burn on C4), the planner re-proposes one orbit earlier at half magnitude, and that burn is
  the recommendation. Every number in the explanation is checked against the tool results
  (§14.6, `oci/agent/guard.py`); a forged figure is caught by the test suite.

- **The two peaks come out of the public catalogue.** The kinetic-gas flux model (§11.13) over
  50-km shells, with the existing coordinated constellations' internal traffic discounted by
  c_intra, puts the workload peak at 450–500 km (9,061 Starlink satellites in one shell) and
  the hazard peak at 750–800 km (Cosmos-2251/Iridium-33 fragments and derelicts with 77–100 yr
  lifetimes). The flux model and the pairwise screener agree within a factor 0.6–1.1 in the
  eight shells both cover — reported per shell, never tuned. For 5,000 satellites at 53°:
  workload-optimal 650 km, hazard-optimal 500 km, `optima_disagree: true`; uncoordinated
  (c_intra = 1) the same constellation would need 70 manoeuvres per satellite-year instead of 17.
  κ by simulation on the real 750–800 km shell: 0.33 (substitutes); on the synthetic corridor
  scenario the clearing burn lands the satellite in three new conjunctions (κ = 3, complements).

- **Chaos mode is a replan, not a replay.** Because `simulate` is a pure function of state, an
  injection is a new state (`oci/sim/chaos.py`): a fresh debris object placed on the
  *post-burn* path of the recommended manoeuvre, a 5× covariance spike, an unannounced
  third-party burn, a tracking gap (time passes, σ does not shrink), a refused coordination, a
  180-min uplink delay, or a 12-satellite constellation insert. The previous recommendation is
  re-simulated and re-validated on the new state — the new object makes the validator reject
  the old COORDINATE plan on C4/C7/C10, the covariance spike turns a 1.5 km pass into
  Pc 2.3e-4 — and the cluster is replanned in 6–7 s with a `{was, now, why}` diff.
- The recommendation follows the operator's rule: the expected-cost optimum among approved
  strategies that bring the post-action max Pc below Pc*. With 25 Monte Carlo samples the
  pure expected-value optimum could leave a 1.3e-3 conjunction untouched; the gate says so.

- **The API is the §12 contract, not a convenience layer.** 33 endpoints under `/api/v1`. Every
  200 carries `{data, assumptions, run_id, computed_at}` so an exported response is
  self-describing; every display number is a `Traced` on the wire with a `trace_id` the
  provenance panel keys on; errors are RFC 7807 problem+json; long operations return 202 + a job
  id. `OCI_DEMO_SAFE=1` refuses anything that would touch the network. The test suite walks every
  response tree and fails on a bare float in a display field — that test found two real ones.

In progress: frontend (M13) — the screens are built and wired to the API; the globe view and the
final visual pass are the remaining work.

## Two measured deviations from the spec, and why

1. **Screening step is 15 s, not 15 min** (`oci/physics/screen.py`). At 14 km/s relative
   speed a 15-minute sample is 6,000 km; in tests every crossing conjunction whose TCA fell
   between 15-minute samples was missed. The interpolated-dip error is ½·a·Δt² (measured
   7 km @ 30 s, 29 km @ 60 s, 117 km @ 120 s), so the step is seconds and the gate is tight.
2. **The orbit-path filter is a per-sample spatial index**, not a Keplerian path from mean
   elements: the mean-element path was measured 30+ km from the SGP4 path over a multi-day
   window and rejected a real 200 m conjunction. The index is exact and O(N log N) per sample.

3. **Weighted betweenness is estimated from 160 pivots above 400 nodes** (`oci/graph/build.py`).
   Exact is a Dijkstra from every node — measured 303 s on the 5,700-node demo run, which is a
   dead demo. Betweenness only reaches the screen; the keystone is chosen by risk-weighted degree
   and is unaffected. `GET /graph` reports `betweenness_exact: false` and says so in words.
4. **`trace_id` is derived, not stored** (`oci/api/serialize.py`). §13.8 wants an id riding on
   every `Traced`; `Traced` is a value object shared across responses, so the id is
   `sha1(function|unit|value)`, minted as responses are serialised and served by
   `GET /provenance/{trace_id}`. Same panel on screen, no id threaded through every computation.

All are documented in the module and in `docs/ASSUMPTIONS.md` (A15).

## Repository layout

```
oci/
  config.py            every tunable, with its citation or MODELLED label
  labels.py            Traced — every displayed number carries label, function, assumptions, na_reason
  data/                objects model, CelesTrak/SATCAT/SOCRATES clients (D1/D3/D5), ingest (M1), operator map, synthetic scenarios (D8)
  physics/             propagate (M2), screen (M3), geometry, pc, maneuver, decay
  graph/               conjunction graph, clusters, keystone (M4)
  ledger/              attribution rules, the externality ledger (M5)
  sim/                 pure-function simulator (M6)
  decide/              optimiser + three rankings (M7), iterated plans, value of information (M8), validator (M9)
  bench/               baselines B1–B4 and the harness (M15)
  pipeline.py          the end-to-end pure function and the terminal report
tests/                 acceptance tests per module (SPEC §10, §17)
docs/                  ASSUMPTIONS.md (generated), PRIOR_ART.md, BENCHMARK.md, KELVINS.md, reference-ui/ (earlier UI research)
models/                covariance_fit.json — the Kelvins-fitted covariance and shrinkage model (committed, 3 KB)
data/                  cache/ and kelvins/ are gitignored; fixtures/ (real element sets, SOCRATES sample) is committed
```

## Data sources

All inputs are public and free; no proprietary or restricted data is used.

- CelesTrak GP element sets (D1) — no account needed
- ESA Kelvins Collision Avoidance Challenge dataset (D2) — 162,634 real CDMs; cite ESA and arXiv:2008.03069
- CelesTrak SOCRATES (D3) — cross-validation of the screener
- Space-Track SATCAT (D4/D5) — object type, RCS, launch date, country
