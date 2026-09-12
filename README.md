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

Build order (SPEC §16.3): **blocks 0–4 done and tested** — the vertical slice, real data
+ screening validated against CelesTrak SOCRATES, graph + ledger on a real shell, the
benchmark harness (`docs/BENCHMARK.md`), and the ESA Kelvins covariance fit (`docs/KELVINS.md`).

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
make test                         # 83 acceptance tests; passes offline from committed fixtures
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
- Real 700–900 km shell (410 active, 2,173 debris from the four public debris groups), 72 h:
  2,827 conjunctions within 5 km, 66 % debris-on-debris, 29 % active-vs-dead — the
  proportions the literature reports (§2.7). The ledger attributes every forced manoeuvre to
  Fengyun-1C and Cosmos-2251 fragments, 0.1–0.5 m/s each, bearing zero themselves.
- **Covariance is fitted, not invented.** `log10 σ = a + b·log(1+τ) + type + altitude`, fitted
  on 159,506 real CDMs (12,787 events) from the ESA Kelvins challenge: along-track R² 0.54,
  σ_t grows ≈ τ², debris is 10× worse than payloads. The fit is evaluated at each conjunction's
  own time-to-TCA and labelled `kelvins_fitted` everywhere; the residual spread (0.5 dex) sits
  in the assumptions panel. Our Pc correlates 0.68 with ESA's own risk field.
- **WAIT is measured, not asserted.** The chaser's uncertainty shrinks 41 %/day as TCA
  approaches (λ = 0.53/day, fitted on 10,081 event time series). Replaying 10,638 real events at
  Pc* = 1e-5: WAIT recommended 51 times — 39 correct, 12 dangerous — saving 0.65 m/s per
  correct wait. The dangerous count is printed next to the saving.
- With the fitted covariance, 4 conjunctions in the 72-h shell exceed 1e-4 and 52 exceed 1e-5;
  the ledger is reported at 1e-5 with the threshold on every figure.
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

Not started: agent planner (M11), API (M12), frontend (M13), capacity engine (M10), chaos mode (M14).

## Two measured deviations from the spec, and why

1. **Screening step is 15 s, not 15 min** (`oci/physics/screen.py`). At 14 km/s relative
   speed a 15-minute sample is 6,000 km; in tests every crossing conjunction whose TCA fell
   between 15-minute samples was missed. The interpolated-dip error is ½·a·Δt² (measured
   7 km @ 30 s, 29 km @ 60 s, 117 km @ 120 s), so the step is seconds and the gate is tight.
2. **The orbit-path filter is a per-sample spatial index**, not a Keplerian path from mean
   elements: the mean-element path was measured 30+ km from the SGP4 path over a multi-day
   window and rejected a real 200 m conjunction. The index is exact and O(N log N) per sample.

Both are documented in the module and in `docs/ASSUMPTIONS.md` (A15).

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
