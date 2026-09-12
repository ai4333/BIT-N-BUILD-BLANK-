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

**Block 0 of the build order (SPEC §16.3) — the vertical slice — is done and tested.** On a
synthetic six-object scenario with declared covariance, the whole pipeline runs end to end
in the terminal: screen → graph → ledger → strategies → simulate → compare → validate → explain.

```
make setup
make demo            # keystone_cluster: keystone ≠ max-Pc object, three rankings, unscripted rejections
make demo-ledger     # dead_rocket_body: one dead object billing three operators, bearing nothing
make test            # 61 acceptance tests, ~2 min
```

What the demo shows, all computed, nothing typed in:

- **Screening** finds every designed conjunction (TCA within 1 s, miss within centimetres)
  and, on a 2,000-object random catalogue, screens 24 h in 16 s.
- **Graph** flags the cluster where the object that should move (keystone, highest
  risk-weighted degree) is not the object in the worst single conjunction — `⚠ differ`.
- **Ledger** attributes every forced manoeuvre to the dead object (rule R1), prices it in
  Δv and mission-days at a declared Pc threshold, and shows the dead object bearing zero.
- **Strategies** — HOLD, MANEUVER, WAIT (priced by value of information), OBSERVE,
  COORDINATE — are simulated over 72 h with Monte Carlo and ranked three ways (expected,
  p95, minimax regret). The rankings disagree; that is reported, not hidden.
- **Validator** rejects burns on physical grounds, unscripted — e.g. *"creates a new
  conjunction with NORAD 91002 at 441 m (< 500 m floor)"* — and the survivor is recommended
  with every number traced to the function that produced it.

Not started: real data ingest (M1), Kelvins covariance fit (M8 part A), agent planner (M11),
API (M12), frontend (M13), capacity engine (M10), chaos mode (M14), benchmark harness (M15).
The build order is fixed by SPEC §16.3 and is followed in that order.

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
  data/                objects model, synthetic scenario generator (D8)
  physics/             propagate (M2), screen (M3), geometry, pc, maneuver, decay
  graph/               conjunction graph, clusters, keystone (M4)
  ledger/              attribution rules, the externality ledger (M5)
  sim/                 pure-function simulator (M6)
  decide/              optimiser + three rankings (M7), value of information (M8), validator (M9)
  pipeline.py          the end-to-end pure function and the terminal report
tests/                 acceptance tests per module (SPEC §10, §17)
docs/                  ASSUMPTIONS.md (generated), PRIOR_ART.md, reference-ui/ (earlier UI research, not the MVP)
data/                  cache/ and kelvins/ are gitignored; fixtures/ is committed
```

## Data sources

All inputs are public and free; no proprietary or restricted data is used.

- CelesTrak GP element sets (D1) — no account needed
- ESA Kelvins Collision Avoidance Challenge dataset (D2) — 162,634 real CDMs; cite ESA and arXiv:2008.03069
- CelesTrak SOCRATES (D3) — cross-validation of the screener
- Space-Track SATCAT (D4/D5) — object type, RCS, launch date, country
