# ORBITAL CAPACITY INTELLIGENCE (OCI)
## Master Build Specification — v2.0

**Status:** Pre-development specification. Authoritative.
**Supersedes:** v1.0 "Master End-to-End Build & Product Prompt"
**Document owner:** Adithya Mahadev (Adi), RVCE
**Target:** National-level hackathon, space sustainability track
**Date:** September 2026

---

## 0. HOW TO USE THIS DOCUMENT

### 0.1 If you are a human on the team

Read sections 1–5 before you touch a keyboard. They contain the *thesis*. If you build the code
without the thesis, you will build a satellite tracker and lose.

Read section 6 (data) and section 7 (reference repos) before writing any ingest code. Both will
save you a full day each.

Read section 16 (build order) and follow it exactly. It is ordered so that you always have a
demoable artifact.

Read section 18 (honesty register) before you write a single slide. Every line in it is a sentence
you must be willing to say out loud to a judge.

### 0.2 If you are a coding agent

This document is your complete brief. Rules of engagement:

1. **Do not invent physics.** Every formula you need is in section 11. If a formula is not there,
   stop and ask, do not approximate.
2. **Do not let the LLM compute numbers.** Section 14 defines the agent's tool surface. The agent
   reasons and calls tools; deterministic Python computes. This is a hard architectural rule, not
   a style preference.
3. **Build in the order given in section 16.** Do not jump ahead to visualization.
4. **Every module has acceptance tests in its own subsection.** A module is not done until its
   tests pass.
5. **Never fabricate a number in any output surface.** If a value cannot be computed, render
   `N/A` with a reason string. Section 18.4 explains why this is a hard rule.
6. **Assumptions must be visible.** Every number the system displays must be traceable to the
   function that produced it and the assumptions that fed it. Section 10.14 specifies the audit
   trail.

### 0.3 Document map

| Section | Contents |
|---|---|
| 1–2 | What we are building and why it matters now |
| 3 | Scope: what this is and explicitly is not |
| 4 | Glossary — every invented term defined precisely |
| 5 | Novelty claim and prior art map (read before pitching) |
| 6 | Data sources: exact URLs, formats, fields, fallbacks |
| 7 | Reference repositories and what to take from each |
| 8 | System architecture |
| 9 | Data model and schemas |
| 10 | Module-by-module specification (M1–M15) |
| 11 | Mathematics appendix |
| 12 | REST API contract |
| 13 | Frontend specification |
| 14 | Agent / LLM specification |
| 15 | Benchmark harness |
| 16 | Build order, time budget, MVP cut lines |
| 17 | Testing and validation plan |
| 18 | Honesty and limitations register |
| 19 | Demo script |
| 20 | Repository layout and setup |
| 21 | Risk register |
| 22 | Expected judge questions and answers |
| 23 | References |

---

## 1. EXECUTIVE SUMMARY

### 1.1 One paragraph

Orbital Capacity Intelligence reads public satellite tracking data and computes, for every object
in low Earth orbit, **how much fuel and how many avoidance maneuvers that object forces other
operators to spend.** Dead objects — spent rocket bodies, failed satellites — cannot move, so
everybody else moves around them, indefinitely, at no cost to whoever left them there. OCI
measures that cost per object, per operator, in operational units. It then uses the same
computation to answer two decisions: *which maneuver should I perform today, given its effect on
everyone* and *at which altitude should I deploy tomorrow, given the maneuver bill that altitude
will generate over ten years.*

### 1.2 The one-sentence thesis

> Space does not run out when satellites collide. It runs out when avoiding each other becomes
> more expensive than the mission is worth — and that threshold is being crossed today.

### 1.3 The one-sentence novelty

> We convert the conjunction network from a descriptive object, which the literature already has,
> into a prescriptive and attributable one: a per-object ledger of operational cost imposed on
> others, computed from public data, that drives both tactical maneuver selection and strategic
> deployment choice.

### 1.4 The headline output

```
════════════════════════════════════════════════════════════════
 ORBITAL EXTERNALITY LEDGER
 NORAD 27386 · SL-16 R/B · rocket body · inactive
 Screening window: 2026-08-13 → 2026-09-12 (30 d)
 Screened against: 8,412 objects, 500–900 km shell
════════════════════════════════════════════════════════════════

 IMPOSES ON OTHERS
   Close approaches generated ................  214
   Maneuvers forced (modelled, Pc > 1e-4) ...   31
   Δv extracted from other operators ........   18.7 m/s
   Mission-days consumed by others ..........   47
   Distinct operators affected ..............    9
   Top burden bearer ........................  OPERATOR-A (11 mnvrs)

 BEARS ITSELF
   Maneuvers performed ......................    0   (inactive — cannot maneuver)
   Δv spent .................................    0   m/s

 NET POSITION
   NET EXTERNALITY ..........................  +18.7 m/s / 30 d imposed
   Burden concentration (Gini over bearers) .   0.61
   Projected remaining-lifetime burden ......  ~1,140 m/s
     └ based on modelled decay lifetime of 61 yr (assumption: A/m = 0.012)
   Implied orbital-use fee equivalent .......  $XXX / yr
     └ calibration: Rao, Burgess & Kaffine (2020), see §11.9 — INDICATIVE ONLY

 REGIME DIAGNOSTIC (this shell)
   STRATEGIC COMPLEMENTS — amplification factor 1.4
   → one maneuver here induces ~1.4 further maneuvers on average
   → avoidance does not relieve pressure; removal does

 [show the math]  [export CSV]  [assumptions panel]
════════════════════════════════════════════════════════════════
```

Every number above is computed. None is typed in. Section 10.5 specifies exactly how each is
derived, and section 18.4 specifies what must be labelled *modelled* rather than *observed*.

---

## 2. THE PROBLEM, WITH NUMBERS

Do not present the problem as "space is crowded." Present it as an operating cost that is
compounding. All figures below are from public sources; cite them on the slide.

### 2.1 The maneuver burden is exploding

Starlink's publicly filed collision-avoidance maneuver counts, by six-month reporting period:

| Period | Maneuvers |
|---|---|
| Dec 2021 – May 2022 | 6,873 |
| Jun 2022 – Nov 2022 | 13,612 |
| Dec 2022 – May 2023 | 25,299 |
| Jun 2023 – Nov 2023 | 24,410 |
| Dec 2023 – May 2024 | 49,384 |
| Jun 2024 – Nov 2024 | 50,666 |
| Dec 2024 – May 2025 | 144,404 |
| Jun 2025 – May 2026 | ~355,000 (12-month) |

Source: public FCC semiannual filings, compiled in arXiv:2603.23552 and FCC reporting summarised
in the ESA Space Environment Report 2026 coverage.

That is roughly 40 maneuvers per satellite per year across ~10,000 operational units. Independent
projections put the industry total near **one million maneuvers per year by 2027**.

Viasat's constellation-risk analysis projected that six large constellations would each receive
between **1 million and over 10 million conjunction warnings per year**, requiring between
**100,000 and 1.2 million maneuvers per year** — and argued that absent rules, operators will not
internalise the negative externalities they create. That last clause is the entire basis of this
project.

### 2.2 There is already a measured viability threshold

A 2025 study selected **10 collision-avoidance maneuvers per month** as the level at which
operating a satellite becomes too operationally complicated to be worthwhile. The share of
satellites above that threshold rose sevenfold between 2019 and early 2025 — from 0.2% to 1.4%,
roughly **340 satellites already past the line.**

This is the single most important number in the pitch. It means orbital capacity, measured in
operational rather than collisional terms, is **already being exceeded in specific regions today**,
not in 2100.

### 2.3 The safety margin has collapsed

The "CRASH Clock" metric (Collision Realization and Significant Harm) estimates how long until a
catastrophic collision if operators suddenly lost the ability to maneuver:

| Year | Margin |
|---|---|
| 2018 | 121 days |
| mid-2025 | 2.8 – 5.5 days |

A 20–40× compression in seven years. The environment is now held together by continuous
maneuvering, not by empty space.

### 2.4 The environment itself

From ESA's Space Environment Report 2026 and MASTER-8 modelling:

- Collision risk in LEO up **20% since 2024**
- ~54,000 objects larger than 10 cm modelled; roughly 40,000–45,000 actually tracked — meaning
  about a quarter of catastrophically dangerous objects are invisible to sensors
- ~1.2 million fragments in the 1–10 cm band (the "invisible middle tier")
- ~140 million below 1 cm
- At the 550 km band, debris density now approaches the same order of magnitude as active
  satellite density

### 2.5 The cost, in money and in life

Collision-avoidance fuel costs run about **$560 million** industry-wide and act as a direct drag
on operational lifespans. Every metre per second spent dodging is a metre per second not spent
station-keeping, which is days of mission life destroyed.

### 2.6 The crucial geographic insight — the two peaks

This is the non-obvious result that makes the project interesting rather than merely worthy.

Published analysis of the present LEO environment shows a **separation between two different
peaks**:

```
   WORKLOAD PEAK                          HAZARD PEAK
   ~500–600 km                            ~850 km
   driven by traffic density              driven by persistence
   → this is where you pay in             → this is where you pay in
     maneuvers and propellant               long-term debris risk
                                          → 96% of the LEO environmental
                                            index sits with INACTIVE objects
```

**The altitude that costs the most operationally is not the altitude that harms the environment
most.** MOCAT-family capacity work finds the number of sustainable active satellites decreases
with altitude while debris increases, and that even a small number of satellites at high altitudes
sharply reduces equilibrium capacity.

Consequence: the question "where should the next 5,000 satellites go?" has **two different correct
answers depending on which currency you pay in.** Existing tools answer one or the other. OCI
prices the trade-off. This is the system's signature result.

### 2.7 Who causes the burden

Two facts that shape the whole design:

1. **Most conjunctions involve objects that cannot move.** Roughly two-thirds of LEO conjunction
   events are debris-on-debris; even the maneuvers large operators execute are largely driven by
   debris or by satellites that cannot be moved. The cost is imposed by the immovable on the
   movable.
2. **Intra-constellation conjunctions are not real risk.** Around 45% of identified conjunctions
   in one analysis were Starlink-internal, and these are actively managed through coordinated
   station-keeping. Any model that counts them as risk will produce garbage.

Design implication (critical, see §10.3.6): **the screening engine must classify and separately
account for intra-constellation pairs, and the ledger must attribute burden primarily against
non-maneuverable objects, where causation is unambiguous.**

---

## 3. SCOPE

### 3.1 What OCI is

1. A **screening and graph engine** over public orbital data
2. An **externality ledger**: per-object, per-operator attribution of imposed operational cost
3. A **tactical decision engine**: which action (including *wait* and *observe*) minimises total
   systemic cost for a live conjunction cluster
4. A **strategic capacity engine**: what a deployment does to an orbital shell's maneuver burden
   and long-horizon hazard, in both currencies
5. A **benchmark**: proof that (3) beats pairwise local decision-making on measured metrics
6. A **decision-support tool**, advisory only, with every assumption exposed

### 3.2 What OCI is explicitly not

- Not a satellite tracker
- Not a 3D globe demo
- Not a TLE viewer
- Not a collision-probability calculator with a nice UI
- Not an LLM chatbot over space data
- Not flight-certified, not an autonomous flight command system
- Not a replacement for operational conjunction assessment services
- Not a claim to have invented the conjunction network, capacity modelling, collision avoidance,
  or AI for space traffic management. All four have prior art. See §5.

### 3.3 The golden test

Before adding any feature, ask:

> **Does this help compute, attribute, or act on the operational cost that orbital decisions
> impose on other operators?**

If no, do not build it.

### 3.4 The harder test

> **Would an existing conjunction-assessment product already produce this output?**

If yes, it is infrastructure, not differentiator. Build it if needed, but never present it as the
innovation.

---

## 4. GLOSSARY

Precise definitions. Use these exact terms in code, in the UI, and on stage. Inconsistent naming
is how a project starts sounding vague.

| Term | Symbol | Definition |
|---|---|---|
| **Conjunction** | — | A predicted close approach between two catalogued objects within a screening volume |
| **TCA** | `t_ca` | Time of closest approach |
| **Miss distance** | `d_miss` | Relative position magnitude between the two objects at TCA, metres |
| **Relative speed** | `v_rel` | Relative velocity magnitude at TCA, m/s |
| **Pc** | `Pc` | Probability of collision for a single conjunction, computed by a named method over a stated covariance |
| **Screening volume** | — | The geometric box/sphere within which a pair is flagged. Ours: 5 km spherical, configurable |
| **Maneuver trigger threshold** | `Pc*` | The Pc above which an operator is modelled to maneuver. Defaults in §6.6 |
| **Conjunction graph** | `G(V,E)` | Undirected weighted graph; nodes = objects, edges = conjunction relationships over a window |
| **Risk cluster** | — | A connected subgraph of `G` above a risk threshold |
| **Keystone object** | — | The object whose removal or maneuver most reduces total cluster risk. Not necessarily the object in the highest-Pc conjunction |
| **CAB** | `CAB_i` | *Conjunction-Attributed Burden.* The operational cost object `i` imposes on other operators over a window. Our core metric. §11.7 |
| **Externality Ledger** | — | The per-object record of CAB and its components. The headline output |
| **Burden bearer** | — | An operator that spends Δv or mission-days because of another object |
| **Regime indicator** | `κ` | Amplification factor for a shell: expected number of further maneuvers induced per maneuver. `κ<1` = strategic substitutes (self-relieving), `κ>1` = strategic complements (self-amplifying). §11.8 |
| **OCS** | `OCS_s` | *Orbital Capacity Score* for shell `s`. Prototype research metric, 0–100, based on maneuver burden per satellite-year against the viability threshold. §11.10 |
| **VoI** | `VoI` | *Value of Information.* Expected reduction in cost achievable by delaying action to acquire better tracking data. §11.11 |
| **Strategy** | — | A candidate action set: `{HOLD, MANEUVER(obj, Δv, t_burn), WAIT(Δt), OBSERVE(obj), COORDINATE(op_a, op_b)}` |
| **Systemic cost** | `J` | Weighted total cost of a strategy across safety, fuel, mission, and network impact. §11.12 |
| **Baseline** | — | The pairwise local decision policy against which OCI is benchmarked. §15 |
| **Modelled** | — | Label for any value derived from an assumption rather than observed. Mandatory in UI |

---

## 5. NOVELTY CLAIM AND PRIOR ART MAP

### 5.1 Why this section exists

Four of the pillars in the v1.0 plan were prior art. Presenting them as innovation would have been
fatal in Q&A. This section exists so that the team states the prior art *first*, credits it, and
then claims only what is genuinely unclaimed. Doing this reads as research maturity. Skipping it
reads as not having checked.

**Put this table on a slide.**

### 5.2 The prior art map

| Work | What it established | What it does not do |
|---|---|---|
| Lewis, Newland, Swinerd & Saunders (2010), *Acta Astronautica* — "A new analysis of debris mitigation and removal using networks" | The conjunction network representation; centrality predicts collision cascades; centrality-ranked removal beats random removal | Descriptive and removal-focused; no operational cost, no per-operator attribution, no live decision |
| Rao (2023/24), "Close Encounters of the LEO Kind" (arXiv:2410.04599) | Conjunction network built from real SOCRATES data (~40M alerts, 6,607 payloads); betweenness and eigenvector centrality; econometric spillover estimation around the COSMOS-1408 ASAT test; introduces the strategic substitutes vs complements question | **Purely diagnostic.** Explicitly leaves "optimal intervention strategies under varying network structures" as future work. Attributes maneuvers only for Planet and SpaceX from public thresholds |
| MIT ARCLab MOCAT family (MOCAT-SSEM, MOCAT-MC, pySSEM); D'Ambrosio & Linares, *JSR* | Orbital carrying capacity via source-sink equilibrium; capacity decreases with altitude while debris increases; validated SSEM against Monte Carlo | Population-level, decadal horizon, species not objects. Cannot speak to any specific object or this week's decision |
| Rao, Burgess & Kaffine (2020), *PNAS* — "Orbital-use fees could more than quadruple the value of the space industry" | The externality is the core problem, not technology; an internationally harmonised orbital-use fee corrects incentives; optimal fee ~$235k/satellite-year by 2040; industry value $600B → $3T | Stylised aggregate physico-economic model. **The externality has never been computed for a specific object from the real catalogue** |
| McKnight et al. / LeoLabs top-50 most-concerning objects | Per-object risk attribution: sum of Pc × mass over all conjunctions involving an object, over a 19-month window | Ranks by **debris-generating hazard**, a environmental proxy. Does not rank by operational cost imposed on other operators |
| arXiv:2603.23552 (2026) | Normalised collision-avoidance rate per active satellite-year at a declared Pc threshold; documents the two-peak structure (workload ~500–600 km, hazard ~850 km; 96% of environmental index from inactive objects) | A metric and a diagnosis, not a decision system or an attribution ledger |
| Kayhan Space (Satcat) | First operational space traffic coordination framework: maneuver intent signalling, responsibility assignment, conflict prevention | Workflow automation between operators. No systemic optimisation, no attribution, no capacity link |
| NASA Starling × SpaceX Starlink (2026) | Demonstrated in flight: Starling accepted maneuver responsibility via SpaceX's screening service and autonomously executed | Proves coordination is being solved operationally. Do not claim coordination as novelty |
| arXiv:2607.26570 (2026) | Semi-decentralised multi-spacecraft collision avoidance; coupled multi-agent planning; notes game-theoretic prior work | Confirms the coordination problem is actively researched. Again: not our novelty |
| Slingshot, LeoLabs, Neuraspace, COMSPOC | Live SSA, tracking, ML-driven CA, high-fidelity conjunction software | Per-event operational products. No attribution, no capacity bridge, no forward economics |

### 5.3 What OCI claims, precisely

Three claims. Each is narrow, defensible, and computable.

**Claim 1 — Attribution in operational currency.**
Existing per-object attribution ranks by debris-generating hazard (Pc × mass). OCI ranks by
**maneuvers forced, Δv extracted, and mission-days consumed from other operators.** Different
question, different ordering, not published.

**Claim 2 — The measurement layer for an existing policy instrument.**
The orbital-use fee is a designed, published policy with a calibrated magnitude. It has never been
applied because there was no way to compute a single object's share. OCI computes a per-object,
catalogue-derived, auditable burden figure that such an instrument could attach to.

**Claim 3 — Prescription on the conjunction network, and the regime diagnostic.**
Rao raises the substitutes-vs-complements question and leaves it open. OCI computes `κ` per shell
from the live graph and uses it to select between qualitatively different interventions:
avoidance when `κ<1`, removal or deployment change when `κ>1`. This is the prescriptive layer the
network literature explicitly does not have.

### 5.4 What OCI must never claim

- That it invented the conjunction graph or centrality analysis
- That it invented orbital capacity modelling
- That its Pc values are operationally trustworthy (they are not — §18.1)
- That its maneuver counts are observed (they are modelled — §18.2)
- That it is flight-ready (§18.6)
- That it is the first to use AI in space traffic management

### 5.5 The novelty sentence, for the slide

> Four literatures have each walked up to this gap and stopped. Capacity models describe decades
> and cannot name an object. Network science names objects but only describes. Economics prices
> the externality but only in aggregate. Operational tools act on events but attribute nothing.
> OCI is the object that connects them: a per-object, per-operator, catalogue-derived ledger of
> imposed operational cost, that drives both today's maneuver and tomorrow's deployment altitude.

---

## 6. DATA SOURCES — EXACT SPECIFICATION

This section is the one that saves you a day. Read it fully before writing ingest code.

### 6.1 Summary table

| ID | Source | What it gives | Access | Required |
|---|---|---|---|---|
| D1 | CelesTrak TLE/OMM catalogue | Orbital elements for ~30k objects | Free HTTP, no auth | **Yes** |
| D2 | ESA Kelvins Collision Avoidance Challenge dataset | 162,634 real CDMs, 13,154 events, 103 features **including covariance** | Free download | **Yes — critical** |
| D3 | CelesTrak SOCRATES | Precomputed conjunction reports, 3×/day, 5 km threshold | Free HTTP | Recommended |
| D4 | Space-Track.org | Authoritative catalogue, SATCAT metadata, historical TLEs | Free, registration required | Recommended |
| D5 | Public SATCAT metadata | Object type, launch year, country, RCS size, mass estimates | Free | **Yes** |
| D6 | Operator maneuver thresholds | Published Pc triggers per operator | Public filings/statements | **Yes** |
| D7 | ESA MASTER density model | Background spatial density by altitude | Web tool, registration | Optional |
| D8 | Synthetic scenario generator | Controlled test cases | Build it yourself | **Yes** |

### 6.2 D1 — CelesTrak TLE/OMM catalogue

**Base:** `https://celestrak.org/NORAD/elements/`

Useful groups (GP query API, JSON or TLE format):
```
https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json
https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json
https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-1408-debris&FORMAT=json
https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=json
```

**Fields you need from each record:**
```
OBJECT_NAME, NORAD_CAT_ID, OBJECT_ID (international designator),
EPOCH, MEAN_MOTION, ECCENTRICITY, INCLINATION, RA_OF_ASC_NODE,
ARG_OF_PERICENTER, MEAN_ANOMALY, BSTAR, MEAN_MOTION_DOT,
REV_AT_EPOCH, CLASSIFICATION_TYPE, ELEMENT_SET_NO
```

**Derived fields you must compute on ingest:**
```
semi_major_axis_km   = (mu / (n_rad_per_s)^2)^(1/3)      # see §11.1
perigee_alt_km       = a*(1-e) - R_earth
apogee_alt_km        = a*(1+e) - R_earth
mean_alt_km          = (perigee_alt_km + apogee_alt_km)/2
period_min           = 1440 / MEAN_MOTION
```

**Etiquette (important — do not get rate-limited mid-demo):**
- Cache every download to disk with a timestamp. Never re-fetch inside a loop.
- Fetch a group once per session, not once per object.
- Include a descriptive User-Agent.
- Build a `--offline` flag that reads only from cache. **Use this for the actual demo.**

**Hard limitation you must internalise:** a TLE contains **no covariance**. Along-track error is
of order a kilometre at epoch and grows over days. Therefore **you cannot compute a trustworthy Pc
from D1 alone.** This is exactly why D2 exists.

### 6.3 D2 — ESA Kelvins CDM dataset (THE MOST IMPORTANT DATA DECISION)

**URL:** `https://kelvins.esa.int/collision-avoidance-challenge/data/`
**Kaggle mirror:** `https://www.kaggle.com/datasets/shadmanrohan/collisionavoidancechallenge`
**Paper describing it:** arXiv:2008.03069, "Spacecraft Collision Avoidance Challenge: design and
results of a machine learning competition"

**What it is:** real conjunction data messages collected by ESA's Space Debris Office between 2015
and 2019, anonymised and released publicly.

**Shape:**
- Training set: **162,634 rows**, **13,154 unique events**, ≈12 CDMs per event
- **103 columns** per CDM
- Each event is a *time series* of CDMs for the same close approach

**Columns that matter most to us:**
```
event_id                    grouping key for the CDM time series
time_to_tca                 days between CDM issue and TCA
mission_id                  anonymised affected mission
risk                        log10 self-computed collision probability at that CDM epoch
max_risk_estimate           max Pc from scaling combined covariance
max_risk_scaling            the scaling factor used
miss_distance               relative position at TCA, metres
relative_speed              relative speed at TCA, m/s
mahalanobis_distance        miss distance normalised by combined covariance
c_sigma_r, c_sigma_t, c_sigma_n        chaser position sigmas (radial/transverse/normal)
c_sigma_rdot, c_sigma_tdot, c_sigma_ndot   chaser velocity sigmas
t_sigma_*                   same for the target
c_position_covariance_det   determinant of covariance (~volume)
c_crdot_t etc.              covariance cross-correlation terms
c_object_type               object type of the secondary
t_/c_ orbital elements      semi-major axis, eccentricity, inclination for both
```

**Why this dataset is the hinge of the whole project:**

> In the days following the first CDM, updates arrive and **the position uncertainties shrink as
> knowledge of the encounter is refined.**

That single property — observed, real, in free public data — is what makes the Value-of-Information
module *computable rather than hand-waved.* Without D2, "wait for better tracking data" is a story.
With D2, it is a measured expectation over 13,154 real events.

**How to use it (three distinct uses):**

1. **Covariance realism (§10.8).** Fit the empirical distribution of `c_sigma_*` and `t_sigma_*` as
   a function of `time_to_tca`, object type, and altitude. Use the fitted model to attach a
   *justified* covariance to TLE-derived conjunctions from D1. Label it `covariance_source:
   "Kelvins-fitted"` everywhere.
2. **Uncertainty-shrinkage model for VoI (§10.8).** For each event, measure how `mahalanobis_distance`
   and the sigmas evolve as `time_to_tca → 0`. Fit `σ(τ)`. This gives the expected information gain
   from waiting `Δt`.
3. **Validation set for the decision engine.** Replay real events through the pipeline: at each CDM
   epoch, does the engine's HOLD/WAIT/MANEUVER recommendation match what the final risk turned out
   to be? This is a genuine quantitative result you can report.

**Download and cache it before the hackathon starts.** It is ~112 MB. Do not download it on
competition wifi.

### 6.4 D3 — CelesTrak SOCRATES

**URL:** `https://celestrak.org/SOCRATES/`

Runs three times daily, propagates the public catalogue forward one week with SGP4, and reports all
predicted approaches within 5 km at TCA. Fields per record include both objects' NORAD IDs and
names, max probability, dilution threshold, min range, relative velocity, and TCA.

**Two uses:**
1. **Cross-validation of your own screening engine.** If your screener finds a substantially
   different set of pairs than SOCRATES over the same window, your screener has a bug. This is your
   single best correctness check. Build it as a test (§17.3).
2. **Bootstrap for the ledger.** If your own screening is too slow on day one, you can compute a
   first-pass ledger directly from SOCRATES pairs.

Note: Rao's paper used SOCRATES for exactly this purpose, so using it is methodologically
defensible and citable.

### 6.5 D4/D5 — Space-Track and SATCAT metadata

**URL:** `https://www.space-track.org` (free account required; register at least a week early —
approval is not instant)

Gives the authoritative catalogue, historical TLEs, and the SATCAT, which supplies:
```
OBJECT_TYPE      PAYLOAD | ROCKET BODY | DEBRIS | UNKNOWN
RCS_SIZE         SMALL | MEDIUM | LARGE
LAUNCH_DATE      → object age
COUNTRY          → owner attribution
DECAY_DATE       null if still in orbit
```

**Mass estimation (needed for hazard terms, §11.9):** you will not get true masses. Use a
documented lookup by object class and RCS size, and label it `modelled`:
```
ROCKET BODY  + LARGE   → 1,500–9,000 kg   (SL-16 class ~8,900 kg)
PAYLOAD      + LARGE   → 500–3,000 kg
PAYLOAD      + MEDIUM  → 100–500 kg
PAYLOAD      + SMALL   → 1–100 kg
DEBRIS       + any     → 0.01–10 kg
```
Store the assumed value AND the range. Show the range in the assumptions panel.

**Operator attribution:** derive operator from `OBJECT_NAME` prefix patterns (`STARLINK-*`,
`ONEWEB-*`, `IRIDIUM *`, `FLOCK *`) plus `COUNTRY`. Maintain an explicit
`config/operator_map.yaml`. Anything unmatched becomes `UNKNOWN-OPERATOR`, never silently dropped.

### 6.6 D6 — Operator maneuver thresholds

These drive the `maneuvers_forced` computation. Store in `config/thresholds.yaml` with citations:

| Actor | Pc trigger | Note |
|---|---|---|
| IADC guideline | 1e-4 | Recommended maneuver threshold |
| NASA | 1e-4 red / 1e-5 yellow | Red triggers action |
| Planet | 1e-4 | Publicly stated automated threshold |
| SpaceX (earlier) | 1e-5 | Publicly stated |
| SpaceX (current) | ~3e-7 | Reported as 1 in 3.3 million — 300× more conservative than industry standard |
| Default for unknown operators | 1e-4 | Conservative, IADC-aligned |

**Critical design consequence:** maneuver counts are **not comparable across operators** unless
normalised by threshold. SpaceX maneuvering 40×/sat/year at 3e-7 is a *policy choice*, not purely
environmental pressure. Therefore the ledger MUST:

- report `maneuvers_forced` **at a single declared threshold** for cross-object comparison, and
- separately report it at each affected operator's own stated threshold.

Label the field `maneuvers_forced_at_Pc_1e-4` etc. Never an unqualified "maneuvers." This one
detail is what separates a defensible metric from a misleading one, and the 2026 CAR literature
makes exactly this point.

### 6.7 D8 — Synthetic scenario generator (build this on day one)

You need deterministic, controllable scenarios for development, tests, and the demo fallback.

`scenarios/synthetic.py` must be able to generate:

| Scenario | Purpose |
|---|---|
| `two_body_head_on` | Simplest conjunction; verify Pc and B-plane code |
| `keystone_cluster` | 5–7 objects where the highest-Pc edge and the highest-centrality node **differ**. This is the demo's core moment — you must be able to guarantee it exists |
| `dead_rocket_body` | One immovable massive object forcing many maneuvers; the ledger showcase |
| `substitutes_shell` | Sparse shell, `κ < 1` |
| `complements_shell` | Dense shell, `κ > 1` |
| `voi_event` | High initial uncertainty that shrinks; WAIT beats MANEUVER |
| `chaos_injection` | Sudden new object / uncertainty spike mid-run |
| `deployment_5000` | Shell with a large constellation insertion |

Every scenario must be seeded and reproducible. Every acceptance test in §10 uses one of these.

### 6.8 Data licensing and honesty

- CelesTrak and Space-Track data are public but subject to terms of use. Do not redistribute bulk
  catalogues in your repo; ship the fetch script and the cache directory in `.gitignore`.
- The Kelvins dataset was released publicly for the competition with US Space Surveillance Network
  agreement. Cite ESA and the challenge paper when you use it.
- On the slide, state: **all inputs are public and free; no proprietary or restricted data is
  used.** This is a genuine strength — it means your result is reproducible and checkable.

---

## 7. REFERENCE REPOSITORIES — WHAT TO LEARN FROM EACH

Verified, real repositories. For each: what it is, what to take, what *not* to take.

### 7.1 Core dependencies you will actually install

| Package | Install | Role |
|---|---|---|
| `sgp4` | `pip install sgp4` | The reference SGP4/SDP4 implementation (Vallado port). Your propagation workhorse |
| `skyfield` | `pip install skyfield` — repo: `github.com/skyfielders/python-skyfield` | Higher-level astronomy/orbit API over sgp4; convenient time handling, topocentric positions, TLE loading |
| `numpy`, `scipy` | standard | Linear algebra, optimisation, integration, statistics |
| `networkx` | `pip install networkx` | Conjunction graph, connected components, betweenness and eigenvector centrality |
| `pandas` | standard | CDM dataset wrangling |
| `fastapi`, `uvicorn`, `pydantic` | standard | API layer and schema validation |
| `sqlalchemy` + `sqlite`/`postgres` | standard | Persistence |
| `pytest` | standard | Tests |

### 7.2 `github.com/esa/dSGP4` — differentiable SGP4 (ESA Advanced Concepts Team)

PyTorch implementation of SGP4. Directly relevant because it supports **state transition matrix
computation, covariance transformation and covariance propagation**, plus batched parallel TLE
propagation on CPU/GPU.

**Take:** the covariance-propagation approach, and the batched propagation pattern if your screening
is too slow. Read their tutorials on covariance transformation — this is precisely the operation
your Pc pipeline needs and getting it right from a reference implementation saves hours.

**Do not take:** the ML-hybrid propagation. Out of scope, big time sink, and it would invite the
question "why is a neural network in your propagator?"

Cite as: Acciarini, Baydin & Izzo, "Closing the Gap Between SGP4 and High-Precision Propagation via
Differentiable Programming," arXiv:2402.04830.

### 7.3 `github.com/ARCLab-MIT/pyssem` — MOCAT source-sink model, Python

Python port of MOCAT-SSEM. Investigates evolution of the LEO object population using a probabilistic
source-sink model across altitude shells and object species (active satellites, derelicts, debris,
subgroups), with the objective of estimating LEO orbital capacity.

**Take:** the **shell discretisation scheme and species accounting**. Your capacity engine (§10.10)
should follow their shell structure so your numbers are comparable to published capacity work. Read
their parameter files for realistic values of PMD success rate, decay rates by shell, and collision
cross-sections.

**Do not take:** the full 200-year integration. Your horizon is 1–10 years for the deployment
question. Running their model in full is a research project, not a hackathon module.

**Strategic value:** citing and structurally aligning with pySSEM is how you tell a judge "our
capacity layer is consistent with MIT's open-source capacity tool, and here is where we differ."
That sentence is worth real points.

Related, MATLAB, read-only for reference:
- `github.com/ARCLab-MIT/MOCAT-SSEM` — the original SSEM (MATLAB)
- `github.com/ARCLab-MIT/MOCAT-MC` — the Monte Carlo variant (MATLAB), MIT licensed

### 7.4 The Kelvins challenge solutions and post-competition papers

Not a single repo but a body of published approaches to exactly your uncertainty problem. The
challenge paper (arXiv:2008.03069) reports feature relevance rankings — top features were
self-computed risk, `max_risk_scaling`, `mahalanobis_distance`, and `c_sigma_t` (along-track
position sigma).

**Take:** that feature ranking tells you which columns actually carry the signal. Use it to build
your covariance model (§10.8) and do not waste time on the other 90 columns.

**Do not take:** the ML risk-prediction framing. Your project is not "predict final Pc better."
That competition happened in 2019 and you will not win it in a weekend.

### 7.5 What to study but not depend on

| What | Why | Caution |
|---|---|---|
| `orekit` / Orekit Python wrapper | Industrial-grade astrodynamics, proper conjunction assessment, high-fidelity propagation | Heavy JVM dependency. Installation can eat half a day. Consider it only if you have slack |
| Cesium / CesiumJS / satellite.js | 3D globe and orbital visualisation | Time sink. §13.4 explains why you build a 2D encounter view instead |
| ESA MASTER (`sdup.esoc.esa.int/master/`) | Authoritative background spatial density by altitude | Web tool, not an API. Use published density figures as constants instead |
| `pykep` (ESA) | Trajectory optimisation primitives | Powerful, but your maneuvers are small impulsive burns — SciPy suffices |

### 7.6 Repository hygiene rule

For every external repo or dataset you draw on, add a line to `REFERENCES.md` with: name, URL,
what you used it for, and citation. Do this **as you go**, not at the end. When a judge asks "what
is yours and what is borrowed," you open that file. Teams that can answer that question instantly
are read as researchers.

---

## 8. SYSTEM ARCHITECTURE

### 8.1 Principles

1. **The LLM never computes physics.** It selects tools, sequences reasoning, and explains. All
   numbers come from deterministic Python. Non-negotiable.
2. **The core pipeline is a pure function of state.** `recommend(state) → decision`. No hidden
   mutation. This is what makes Chaos Mode (§10.13) nearly free rather than a two-day retrofit.
3. **One agent, not four.** Agent count is not a capability. §14.1 explains.
4. **Every number carries provenance.** Value, producing function, inputs, assumptions. §10.14.
5. **Modules are independently testable.** Each has acceptance tests. No module depends on the
   frontend.

### 8.2 Layer diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  PRESENTATION                                                        │
│  React + Tailwind + Recharts                                         │
│  ├─ Ledger view (headline)          ├─ Encounter geometry (2D/B-plane)│
│  ├─ Worst-offenders ranking         ├─ Strategy comparison table      │
│  ├─ Capacity / two-peaks explorer   ├─ Agent reasoning trace          │
│  └─ Assumptions panel (always visible)                                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ REST / JSON  (§12)
┌───────────────────────────────▼─────────────────────────────────────┐
│  API LAYER — FastAPI                                                 │
│  Request validation (pydantic), job orchestration, provenance stamp   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│  AGENT LAYER  (M11)                                                  │
│  One LLM planner with tool calling. Reasons, proposes, explains,      │
│  replans. NEVER computes a physical quantity.                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ tool calls only
┌───────────────────────────────▼─────────────────────────────────────┐
│  DECISION CORE  (deterministic)                                      │
│                                                                      │
│   M7 OPTIMIZER ──────► M9 VALIDATOR ──────► decision                 │
│        ▲                    │                                        │
│        │                    └── rejection + reason ──► back to M11   │
│   M6 SIMULATOR                                                       │
│        ▲                                                             │
│   M8 VoI ENGINE                                                      │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│  ANALYSIS CORE                                                       │
│   M5 EXTERNALITY LEDGER  ◄──  M4 GRAPH ENGINE  ◄── M3 SCREENING      │
│   M10 CAPACITY ENGINE                            ▲                   │
│                                                  │                   │
│                                             M2 PROPAGATOR            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│  DATA LAYER                                                          │
│   M1 INGEST  →  cache (parquet/sqlite)  →  normalised object store    │
│   D1 CelesTrak │ D2 Kelvins CDMs │ D3 SOCRATES │ D4/5 SATCAT │ D8 synth│
└─────────────────────────────────────────────────────────────────────┘

     M15 BENCHMARK HARNESS runs the whole core twice — once with the
     pairwise BASELINE policy, once with OCI — over identical scenarios.
     It is infrastructure, not a deliverable. Built at step 3, not last.
```

### 8.3 Module inventory

| ID | Module | Owner file | Depends on |
|---|---|---|---|
| M1 | Ingest & normalise | `oci/data/ingest.py` | — |
| M2 | Propagator | `oci/physics/propagate.py` | M1 |
| M3 | Conjunction screening | `oci/physics/screen.py` | M2 |
| M4 | Graph engine | `oci/graph/build.py` | M3 |
| M5 | Externality ledger | `oci/ledger/compute.py` | M3, M4 |
| M6 | Future simulator | `oci/sim/simulate.py` | M2, M3 |
| M7 | Multi-objective optimiser | `oci/decide/optimize.py` | M6 |
| M8 | VoI engine | `oci/decide/voi.py` | M2, D2 |
| M9 | Physics validator | `oci/decide/validate.py` | M2, M3 |
| M10 | Capacity engine | `oci/capacity/shells.py` | M3, M5 |
| M11 | Agent planner | `oci/agent/planner.py` | M1–M10 |
| M12 | API | `oci/api/main.py` | all |
| M13 | Frontend | `web/` | M12 |
| M14 | Chaos mode | `oci/sim/chaos.py` | M6 |
| M15 | Benchmark harness | `oci/bench/harness.py` | M3–M9 |

### 8.4 Technology stack — final

**Backend**
```
Python 3.11+
FastAPI + uvicorn          API
pydantic v2                schemas, validation
numpy, scipy               math, optimisation
sgp4, skyfield             propagation
networkx                   graph
pandas, pyarrow            CDM data, caching
sqlalchemy + SQLite        persistence (Postgres only if trivially available)
pytest                     tests
```

**Frontend**
```
React 18 + Vite
Tailwind CSS               styling
Recharts                   charts
No 3D library in MVP       (see §13.4)
```

**Agent**
```
Any LLM with reliable function calling.
Tool surface defined in §14.2. Temperature 0 for the planner.
```

**Explicitly NOT in the stack**
```
Kubernetes, microservices, message queues, Cesium/Three.js in MVP,
graph databases, vector databases, multi-agent frameworks,
Redis, Celery, Docker Compose with 6 services.
```
Rationale: §16.6. Every one of these has killed a hackathon demo.

---

## 9. DATA MODEL

### 9.1 Core tables

```sql
-- Normalised catalogue object
CREATE TABLE objects (
    norad_id            INTEGER PRIMARY KEY,
    object_name         TEXT NOT NULL,
    international_id    TEXT,
    object_type         TEXT NOT NULL,   -- PAYLOAD|ROCKET_BODY|DEBRIS|UNKNOWN
    is_active           BOOLEAN NOT NULL,
    is_maneuverable     BOOLEAN NOT NULL,
    operator            TEXT NOT NULL,   -- from operator_map.yaml, else UNKNOWN-OPERATOR
    country             TEXT,
    launch_date         DATE,
    rcs_size            TEXT,            -- SMALL|MEDIUM|LARGE|NULL
    mass_kg_est         REAL,            -- MODELLED
    mass_kg_low         REAL,            -- MODELLED range low
    mass_kg_high        REAL,            -- MODELLED range high
    hard_body_radius_m  REAL,            -- MODELLED, default 5.0
    area_to_mass        REAL,            -- MODELLED, for decay estimate
    -- current elements
    epoch               TIMESTAMP NOT NULL,
    mean_motion         REAL, eccentricity REAL, inclination_deg REAL,
    raan_deg            REAL, argp_deg REAL, mean_anomaly_deg REAL,
    bstar               REAL,
    -- derived
    sma_km              REAL, perigee_alt_km REAL, apogee_alt_km REAL,
    mean_alt_km         REAL, period_min REAL,
    shell_id            INTEGER,          -- FK shells
    -- provenance
    source              TEXT NOT NULL,    -- celestrak|spacetrack|synthetic
    ingested_at         TIMESTAMP NOT NULL
);

-- One screened conjunction
CREATE TABLE conjunctions (
    conj_id             TEXT PRIMARY KEY,
    primary_id          INTEGER NOT NULL REFERENCES objects(norad_id),
    secondary_id        INTEGER NOT NULL REFERENCES objects(norad_id),
    tca                 TIMESTAMP NOT NULL,
    miss_distance_m     REAL NOT NULL,
    rel_speed_mps       REAL NOT NULL,
    -- risk
    pc                  REAL,             -- may be NULL if covariance unavailable
    pc_method           TEXT,             -- foster|chan|alfano|maximum
    covariance_source   TEXT NOT NULL,    -- kelvins_fitted|assumed|cdm_observed|none
    sigma_r_m           REAL, sigma_t_m REAL, sigma_n_m REAL,
    mahalanobis         REAL,
    -- classification
    pair_class          TEXT NOT NULL,    -- ACTIVE_ACTIVE|ACTIVE_DEAD|DEAD_DEAD
    intra_constellation BOOLEAN NOT NULL,
    -- provenance
    screening_run_id    TEXT NOT NULL REFERENCES screening_runs(run_id),
    computed_by         TEXT NOT NULL     -- function name + version
);

-- A screening run = one (window, catalogue snapshot, config) triple
CREATE TABLE screening_runs (
    run_id              TEXT PRIMARY KEY,
    window_start        TIMESTAMP NOT NULL,
    window_end          TIMESTAMP NOT NULL,
    n_objects           INTEGER NOT NULL,
    n_pairs_screened    INTEGER NOT NULL,
    n_conjunctions      INTEGER NOT NULL,
    screening_volume_m  REAL NOT NULL,
    propagator          TEXT NOT NULL,    -- sgp4
    config_hash         TEXT NOT NULL,
    runtime_s           REAL,
    created_at          TIMESTAMP NOT NULL
);

-- The headline artifact
CREATE TABLE ledger_entries (
    entry_id                TEXT PRIMARY KEY,
    norad_id                INTEGER NOT NULL REFERENCES objects(norad_id),
    run_id                  TEXT NOT NULL REFERENCES screening_runs(run_id),
    window_days             REAL NOT NULL,
    pc_threshold            REAL NOT NULL,   -- the DECLARED threshold, always stored
    -- imposed on others
    conjunctions_generated  INTEGER NOT NULL,
    maneuvers_forced        REAL NOT NULL,   -- MODELLED
    dv_imposed_mps          REAL NOT NULL,   -- MODELLED
    mission_days_imposed    REAL NOT NULL,   -- MODELLED
    operators_affected      INTEGER NOT NULL,
    top_bearer              TEXT,
    bearer_gini             REAL,
    -- borne by self
    maneuvers_performed     REAL NOT NULL,
    dv_spent_mps            REAL NOT NULL,
    -- net & projection
    cab                     REAL NOT NULL,   -- Conjunction-Attributed Burden §11.7
    cab_normalised          REAL NOT NULL,   -- per satellite-year, §11.7.4
    projected_lifetime_dv   REAL,            -- MODELLED
    decay_lifetime_yr_est   REAL,            -- MODELLED
    implied_fee_usd_yr      REAL,            -- INDICATIVE, §11.9
    -- provenance
    assumptions_json        TEXT NOT NULL,
    computed_at             TIMESTAMP NOT NULL
);

-- Per-bearer detail: who paid for whom
CREATE TABLE burden_flows (
    flow_id         TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    imposer_id      INTEGER NOT NULL REFERENCES objects(norad_id),
    bearer_id       INTEGER NOT NULL REFERENCES objects(norad_id),
    bearer_operator TEXT NOT NULL,
    n_conjunctions  INTEGER NOT NULL,
    n_maneuvers     REAL NOT NULL,
    dv_mps          REAL NOT NULL,
    mission_days    REAL NOT NULL,
    attribution_rule TEXT NOT NULL   -- §11.7.2: which rule assigned this flow
);

-- Altitude shells (align with pySSEM discretisation)
CREATE TABLE shells (
    shell_id            INTEGER PRIMARY KEY,
    alt_low_km          REAL NOT NULL,
    alt_high_km         REAL NOT NULL,
    n_objects           INTEGER,
    n_active            INTEGER,
    n_dead              INTEGER,
    spatial_density     REAL,        -- objects / km^3
    maneuver_burden_per_sat_yr REAL, -- MODELLED
    kappa               REAL,        -- regime indicator §11.8
    ocs                 REAL,        -- Orbital Capacity Score §11.10
    hazard_index        REAL,        -- persistence-weighted, §11.10.3
    decay_lifetime_yr   REAL         -- MODELLED, representative
);

-- Strategies evaluated for an event
CREATE TABLE strategies (
    strategy_id     TEXT PRIMARY KEY,
    cluster_id      TEXT NOT NULL,
    kind            TEXT NOT NULL,   -- HOLD|MANEUVER|WAIT|OBSERVE|COORDINATE
    params_json     TEXT NOT NULL,
    -- evaluated outcomes
    pc_after        REAL, future_conjunctions INTEGER,
    dv_mps          REAL, mission_impact REAL,
    systemic_cost   REAL, expected_cost REAL,
    p95_cost        REAL, max_regret REAL,
    mc_runs         INTEGER, mc_safe_fraction REAL,
    -- validation
    validator_verdict TEXT,          -- APPROVED|REJECTED
    validator_reason  TEXT,
    proposed_by     TEXT NOT NULL    -- agent|generator|baseline
);

-- Full provenance for every displayed number
CREATE TABLE provenance (
    trace_id        TEXT PRIMARY KEY,
    value_path      TEXT NOT NULL,   -- e.g. "ledger.27386.dv_imposed_mps"
    value           REAL,
    function_name   TEXT NOT NULL,
    function_version TEXT NOT NULL,
    inputs_json     TEXT NOT NULL,
    assumptions_json TEXT NOT NULL,
    label           TEXT NOT NULL,   -- OBSERVED|COMPUTED|MODELLED|INDICATIVE
    created_at      TIMESTAMP NOT NULL
);
```

### 9.2 Key pydantic models

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

Label = Literal["OBSERVED", "COMPUTED", "MODELLED", "INDICATIVE"]

class Traced(BaseModel):
    """Every number that reaches the UI is wrapped in this. No exceptions."""
    value: Optional[float]
    unit: str
    label: Label
    function: str
    assumptions: dict = Field(default_factory=dict)
    na_reason: Optional[str] = None   # set when value is None

class Conjunction(BaseModel):
    conj_id: str
    primary_id: int
    secondary_id: int
    tca: datetime
    miss_distance_m: Traced
    rel_speed_mps: Traced
    pc: Traced
    pc_method: Optional[str]
    covariance_source: Literal["kelvins_fitted","assumed","cdm_observed","none"]
    pair_class: Literal["ACTIVE_ACTIVE","ACTIVE_DEAD","DEAD_DEAD"]
    intra_constellation: bool

class LedgerEntry(BaseModel):
    norad_id: int
    object_name: str
    object_type: str
    operator: str
    window_days: float
    pc_threshold: float
    conjunctions_generated: Traced
    maneuvers_forced: Traced
    dv_imposed_mps: Traced
    mission_days_imposed: Traced
    operators_affected: Traced
    maneuvers_performed: Traced
    cab: Traced
    cab_normalised: Traced
    projected_lifetime_dv: Traced
    implied_fee_usd_yr: Traced
    regime: Literal["SUBSTITUTES","COMPLEMENTS","INDETERMINATE"]
    kappa: Traced
    bearers: list["BurdenFlow"]

class Strategy(BaseModel):
    strategy_id: str
    kind: Literal["HOLD","MANEUVER","WAIT","OBSERVE","COORDINATE"]
    params: dict
    pc_after: Traced
    future_conjunctions: Traced
    dv_mps: Traced
    mission_impact: Traced
    systemic_cost: Traced
    expected_cost: Traced
    p95_cost: Traced
    max_regret: Traced
    mc_safe_fraction: Traced
    validator_verdict: Optional[str]
    validator_reason: Optional[str]
    proposed_by: str
```

### 9.3 The `Traced` wrapper is mandatory

Any function that returns a number destined for the UI returns `Traced`, not `float`. This costs
maybe forty minutes of extra typing and it buys three things:

1. The audit trail (§10.14) is free.
2. `label` forces you to be explicit about `MODELLED` vs `COMPUTED` at the point of creation, where
   you actually know.
3. `na_reason` makes "we could not compute this and here is why" a first-class output instead of a
   silent zero. Silent zeros are how hackathon projects lie by accident.

---

## 10. MODULE SPECIFICATIONS

Format for every module: **Purpose → Inputs → Outputs → Algorithm → Pseudocode → Acceptance tests
→ Failure modes.**

---

### 10.1 M1 — INGEST & NORMALISE

**Purpose.** Turn heterogeneous public data into one normalised object store with explicit
provenance and explicit modelled fields.

**Inputs.** D1 (CelesTrak GP JSON), D4/D5 (SATCAT CSV), D2 (Kelvins CSV), `config/operator_map.yaml`,
`config/mass_model.yaml`, `config/thresholds.yaml`, or D8 synthetic.

**Outputs.** Populated `objects` table. Cached parquet snapshots under `data/cache/`. An ingest
report: counts by type, unmatched operators, missing fields.

**Algorithm.**
1. Fetch group (or read cache if `--offline`).
2. Parse GP records. Validate every required element is present and finite; reject and log
   otherwise. Do not silently coerce.
3. Compute derived orbital quantities (§11.1).
4. Join SATCAT on `norad_id` for type, RCS, launch date, country, decay date.
5. Assign `operator` via `operator_map.yaml` regex rules; default `UNKNOWN-OPERATOR`.
6. Assign `is_active`: payload AND not decayed AND launch recent enough / present in active group.
7. Assign `is_maneuverable`: `is_active` AND operator known to maneuver AND object type PAYLOAD.
   Default for unknown active payload: `False` (conservative — assume it cannot move).
8. Assign `mass_kg_est/low/high` from `mass_model.yaml` by (type, rcs_size). Label MODELLED.
9. Assign `hard_body_radius_m` — default 5.0 m combined, from `config`. Label MODELLED.
10. Assign `area_to_mass` by class for decay estimation. Label MODELLED.
11. Assign `shell_id` by `mean_alt_km`.
12. Write with `source` and `ingested_at`.

**Pseudocode.**
```python
def ingest(group="active", offline=False) -> IngestReport:
    raw = cache_get(group) if offline else fetch_celestrak(group)
    satcat = load_satcat()
    rows, rejects = [], []
    for rec in raw:
        try:
            el = parse_elements(rec)            # raises on bad data
        except BadElementSet as e:
            rejects.append((rec.get("NORAD_CAT_ID"), str(e))); continue
        d   = derive_orbit(el)                  # §11.1
        md  = satcat.get(el.norad_id, {})
        obj = Object(
            **el.dict(), **d.dict(),
            object_type   = md.get("OBJECT_TYPE", "UNKNOWN"),
            rcs_size      = md.get("RCS_SIZE"),
            operator      = match_operator(el.object_name, md.get("COUNTRY")),
            is_active     = infer_active(el, md, group),
            is_maneuverable = infer_maneuverable(el, md),
            **mass_model(md.get("OBJECT_TYPE"), md.get("RCS_SIZE")),   # MODELLED
            hard_body_radius_m = CONFIG.hard_body_radius_m,
            area_to_mass  = am_model(md.get("OBJECT_TYPE"), md.get("RCS_SIZE")),
            shell_id      = shell_of(d.mean_alt_km),
            source        = "celestrak", ingested_at = now(),
        )
        rows.append(obj)
    upsert(rows)
    return IngestReport(n=len(rows), rejects=rejects,
                        unmatched_operators=count_unknown(rows),
                        by_type=histogram(rows, "object_type"))
```

**Acceptance tests.**
- `test_ingest_active_group_nonempty` — ≥ 5,000 objects ingested from `GROUP=active`.
- `test_derived_orbit_matches_known` — for ISS (NORAD 25544), computed mean altitude within ±15 km
  of the published value.
- `test_no_silent_nulls` — no row has `NULL` in any NOT NULL column.
- `test_offline_mode_works_with_network_disabled` — run with network blocked; must succeed from
  cache. **This test protects your demo.**
- `test_modelled_fields_labelled` — every mass and radius field has a corresponding assumption
  entry.
- `test_unmatched_operator_not_dropped` — inject an object with a novel name; assert it appears
  with `UNKNOWN-OPERATOR`.

**Failure modes and handling.**

| Failure | Handling |
|---|---|
| CelesTrak unreachable / rate-limited | Fall back to cache, warn loudly, continue. Never crash |
| Malformed element set | Reject, log to `rejects`, continue |
| SATCAT join miss | `object_type = UNKNOWN`, mass range widened, flagged in report |
| Epoch far in the past (stale TLE) | Flag `stale=True` if epoch older than 7 days; exclude from live screening but keep in catalogue with reason |

---

### 10.2 M2 — PROPAGATOR

**Purpose.** Given an object and a time, return position and velocity in a consistent frame. Also
propagate a covariance when one is supplied.

**Inputs.** `Object` (elements), target time(s) UTC, optional initial covariance.

**Outputs.** `State(r_km[3], v_kmps[3], frame="TEME", epoch)`; optional `Cov6x6`.

**Algorithm.**
1. Build an `sgp4.Satrec` from the element set.
2. Call `sgp4_tsince()` for the target time. Check the error code — SGP4 returns nonzero codes for
   decay and convergence failures. **Never ignore the error code.**
3. Output is in TEME. Convert to a common inertial frame consistently. For screening, staying in
   TEME throughout is acceptable and simpler; document that choice.
4. For covariance: transform the RTN-frame sigma set (from §10.8) into the working frame using the
   rotation built from `r` and `v` (§11.3). If precise covariance propagation is needed, use the
   dSGP4 state-transition-matrix approach (§7.2).

**Pseudocode.**
```python
def propagate(obj: Object, t: datetime) -> State:
    sat = satrec_from_elements(obj)
    jd, fr = jday(t)
    e, r, v = sat.sgp4(jd, fr)
    if e != 0:
        raise PropagationError(obj.norad_id, sgp4_error_message(e))
    return State(r_km=r, v_kmps=v, frame="TEME", epoch=t)

def propagate_batch(objs, times) -> np.ndarray:
    # shape (n_obj, n_times, 6). Vectorise via sgp4.SatrecArray.
    ...
```

**Performance requirement.** Screening (M3) will call this in bulk. Target: **propagate 10,000
objects across 288 time steps (72 h at 15-min spacing) in under 30 seconds.** Use
`sgp4.SatrecArray` for vectorised propagation, not a Python loop. If you cannot hit this, reduce the
catalogue size — do not reduce the time resolution below 15 minutes at the coarse stage.

**Acceptance tests.**
- `test_iss_position_sanity` — ISS at a known epoch: `|r|` between 6,700 and 6,850 km.
- `test_error_code_raises` — feed a decayed object; assert `PropagationError` raised, not silence.
- `test_energy_consistency` — over a 24 h propagation, specific orbital energy drifts by less than
  a documented tolerance (SGP4 is not energy-conserving; this is a smoke test for gross bugs).
- `test_batch_matches_single` — batch propagation equals looped single propagation to 1e-9.
- `test_batch_performance` — the 10,000 × 288 target above.

**Failure modes.**

| Failure | Handling |
|---|---|
| SGP4 error code ≠ 0 | Raise, catch at screening level, exclude object from that run with logged reason |
| Deep-space object (period > 225 min) | SGP4 switches to SDP4 automatically; fine, but flag it — our LEO scope means these should be filtered out at ingest |
| Very stale TLE | Already flagged at M1; screening excludes |

---

### 10.3 M3 — CONJUNCTION SCREENING

**Purpose.** Find all pairs that pass within the screening volume during the window, efficiently
and correctly.

**This is the module that will kill your demo if you brute-force it.** 10,000 objects is
~50 million pairs. Per time step. Do not do that.

**Inputs.** Object set, window `[t0, t1]`, screening volume `d_screen` (default 5,000 m), coarse
step (default 15 min), config.

**Outputs.** `conjunctions` rows, one `screening_runs` row, timing report.

**Algorithm — the filter chain.** Apply in this order. Each stage removes the overwhelming majority
of pairs at negligible cost.

**Stage 1 — Apogee/perigee filter (pure algebra, no propagation).**
A pair can never approach within `d` if their radial ranges do not overlap:
```
if perigee_i - apogee_j > d  or  perigee_j - apogee_i > d:  reject
```
On a real LEO catalogue this typically removes 90%+ of pairs instantly.

**Stage 2 — Orbit-path geometric filter.**
Two orbits are surfaces; compute the minimum distance between the two orbit *paths* ignoring
timing (the relative geometry of the two orbital planes and the radial ranges). If that minimum
exceeds `d`, no timing can produce a conjunction. Reject.

**Stage 3 — Time filter (coarse propagation).**
For survivors, propagate both objects on the coarse grid. Keep pairs whose separation dips below a
generous gate (`k × d`, `k ≈ 4`) at any coarse step. The gate must be generous because a 15-minute
step at 7.5 km/s relative speed can step over a close approach entirely — the gate accounts for
that. Compute the required `k` from `v_rel_max × step / 2` and document it.

**Stage 4 — Fine refinement.**
For each surviving pair and each coarse dip, refine TCA by minimising separation over a short
bracket around the dip using golden-section or Brent's method, stepping at ~1 s effective
resolution. Record `tca`, `d_miss`, `v_rel`, and the relative state vector.

**Stage 5 — Risk annotation.**
Attach covariance from M8's model. Compute `Pc` by the chosen method (§11.4). Set
`covariance_source`. If no defensible covariance is available, set `pc = None` with
`na_reason = "no covariance available"` — do not invent one.

**Stage 6 — Classification (do not skip; §2.7).**
```python
pair_class = ("ACTIVE_ACTIVE" if a.is_active and b.is_active else
              "DEAD_DEAD"     if not a.is_active and not b.is_active else
              "ACTIVE_DEAD")
intra_constellation = (a.operator == b.operator
                       and a.operator in CONFIG.coordinated_constellations)
```
Intra-constellation pairs are **recorded but excluded from burden attribution by default**, because
they are actively coordinated by the operator and counting them as imposed risk produces garbage.
Make this a config flag, expose it in the assumptions panel, and mention it on stage — knowing this
is a sign you understand the domain.

**Pseudocode.**
```python
def screen(objects, t0, t1, d_screen=5000.0, coarse_min=15.0) -> ScreeningResult:
    objs = [o for o in objects if not o.stale and o.mean_alt_km < 2000]
    # Stage 1
    pairs = [(i, j) for i, j in combinations(objs, 2)
             if radial_ranges_overlap(i, j, d_screen)]
    # Stage 2
    pairs = [(i, j) for i, j in pairs
             if min_orbit_path_distance(i, j) <= d_screen]
    # Stage 3
    times = arange(t0, t1, minutes(coarse_min))
    eph   = propagate_batch(objs, times)        # vectorised
    gate  = gate_radius(d_screen, coarse_min)   # k*d, documented
    cands = []
    for (i, j) in pairs:
        sep = norm(eph[i] - eph[j], axis=1)
        for k in local_minima_below(sep, gate):
            cands.append((i, j, times[k]))
    # Stage 4
    conjs = []
    for (i, j, t_guess) in cands:
        tca, d_miss, v_rel, rel_state = refine_tca(objs[i], objs[j], t_guess)
        if d_miss <= d_screen:
            conjs.append(make_conjunction(objs[i], objs[j], tca, d_miss, v_rel, rel_state))
    # Stages 5-6
    for c in conjs:
        attach_covariance(c)      # M8 model
        c.pc = compute_pc(c)      # §11.4, may be None
        classify(c)
    return ScreeningResult(conjunctions=conjs, run=make_run_record(...))
```

**Performance requirements.**

| Catalogue | Window | Target wall time |
|---|---|---|
| 2,000 objects | 72 h | < 20 s |
| 8,000 objects | 72 h | < 3 min |
| 8,000 objects | 30 d | < 20 min (run once, cache) |

If you miss these, cut the catalogue (single shell, e.g. 500–900 km) rather than weakening the
filter chain.

**Acceptance tests.**
- `test_synthetic_head_on_found` — `two_body_head_on` scenario: the known conjunction is found, TCA
  within 2 s of truth, `d_miss` within 10 m.
- `test_filter_chain_no_false_negatives` — on a 300-object subset, run the full filter chain AND a
  brute-force all-pairs screen at 1-min resolution. **The filter chain must find every conjunction
  brute force finds.** This is the single most important test in the project.
- `test_socrates_cross_validation` — screen the public catalogue over a window for which you have
  cached SOCRATES output; assert overlap of the reported pairs above a stated recall threshold
  (target ≥ 85%; investigate and document any systematic gap).
- `test_coarse_gate_sufficient` — verify empirically that reducing the coarse step to 5 min finds no
  additional conjunctions beyond those found at 15 min with the computed gate.
- `test_intra_constellation_flagged` — Starlink-Starlink pairs are flagged and excluded from
  attribution by default.
- `test_pc_none_when_no_covariance` — with covariance disabled, `pc is None` and `na_reason` is set.

**Failure modes.**

| Failure | Handling |
|---|---|
| Combinatorial blowup | Filter chain; if still slow, restrict altitude band. Log pair counts at each stage so you can see where it blows up |
| Missed conjunction due to coarse step | Generous gate `k×d` computed from max relative speed; verified by `test_coarse_gate_sufficient` |
| Refinement finds a local, not global, minimum | Bracket each coarse local minimum separately rather than minimising over the whole window |
| Duplicate conjunctions for the same pair | Deduplicate on `(primary, secondary, round(tca, 60s))` |

---

### 10.4 M4 — GRAPH ENGINE

**Purpose.** Build the conjunction graph, find risk clusters, and compute the centrality measures
that drive keystone selection.

**Credit the prior art here explicitly in code comments and on the slide:** Lewis et al. (2010)
established the conjunction network and centrality-based removal prioritisation; Rao (2023/24)
computed it on real SOCRATES data at scale. We reimplement and then go beyond it.

**Inputs.** `conjunctions` for a run, weighting config.

**Outputs.** `networkx.Graph`; per-node centrality; cluster assignments; keystone ranking.

**Algorithm.**
1. Nodes = objects appearing in any conjunction. Node attributes: type, active, operator, mass, shell.
2. Edges = object pairs with ≥1 conjunction in the window. Edge attributes: `n_conj`,
   `min_miss_distance`, `max_pc`, `sum_pc`, `mean_v_rel`, `pair_class`.
3. Edge weight — configurable, default:
   ```
   w_ij = sum over conjunctions of Pc          if Pc available for all
   w_ij = sum over conjunctions of 1/d_miss    fallback when Pc unavailable
   ```
   Store which rule was used. Never mix rules silently within one graph.
4. Clusters: connected components of the subgraph induced by edges with `w_ij ≥ w_min`. Report
   cluster size distribution.
5. Centrality:
   - **Degree** — trivial, but the honest baseline
   - **Risk-weighted degree** = `Σ_j w_ij` — our primary keystone signal
   - **Betweenness** — Lewis's cascade indicator
   - **Eigenvector** — Rao's targeted-intervention indicator
6. **Keystone selection.** Rank nodes within a cluster by *removable* risk reduction:
   ```
   keystone_score_i = Σ_{j ∈ N(i)} w_ij   restricted to edges where
                      intervention on i is feasible
   ```
   Feasibility: for a maneuver keystone, `i` must be maneuverable. For a removal keystone (debris
   remediation framing), `i` must be inactive.
7. **The demo-critical check.** Compute whether `argmax(keystone_score)` differs from
   `argmax(max_pc over incident edges)`. When they differ, you have the demo moment: *the object
   that should move is not the object in the worst conjunction.* Flag such clusters as
   `disagreement=True` and surface them first in the UI.

**Pseudocode.**
```python
def build_graph(conjs, w_min=0.0, weight_rule="pc") -> GraphResult:
    G = nx.Graph()
    for c in conjs:
        if c.intra_constellation and CONFIG.exclude_intra:
            continue
        add_node_with_attrs(G, c.primary);  add_node_with_attrs(G, c.secondary)
        e = G.edges.get((c.primary_id, c.secondary_id), default_edge())
        e["n_conj"]   += 1
        e["sum_pc"]    = safe_add(e["sum_pc"], c.pc)
        e["max_pc"]    = safe_max(e["max_pc"], c.pc)
        e["min_miss"]  = min(e["min_miss"], c.miss_distance_m)
        G.add_edge(c.primary_id, c.secondary_id, **e)

    apply_weights(G, rule=weight_rule)            # sets w
    clusters = list(nx.connected_components(
        G.edge_subgraph([e for e in G.edges if G.edges[e]["w"] >= w_min])))

    cent = {
      "degree":      dict(G.degree()),
      "wdegree":     {n: sum(G.edges[n,m]["w"] for m in G[n]) for n in G},
      "betweenness": nx.betweenness_centrality(G, weight="w"),
      "eigenvector": nx.eigenvector_centrality_numpy(G, weight="w"),
    }
    keystones = rank_keystones(G, clusters, cent)
    return GraphResult(G=G, clusters=clusters, centrality=cent,
                       keystones=keystones,
                       disagreement_clusters=find_disagreements(G, clusters, cent))
```

**Acceptance tests.**
- `test_keystone_cluster_scenario` — on the synthetic `keystone_cluster`, the computed keystone is
  the known-correct node, and `disagreement=True`.
- `test_centrality_matches_networkx_reference` — hand-built 5-node graph, values checked against
  hand computation.
- `test_intra_constellation_excluded_from_graph` — excluded pairs produce no edges.
- `test_weight_rule_recorded` — the graph records which weight rule produced it.
- `test_eigenvector_converges` — on a disconnected graph, eigenvector centrality does not throw;
  handled per-component.

**Failure modes.**

| Failure | Handling |
|---|---|
| Eigenvector centrality fails to converge | Compute per connected component; fall back to weighted degree with a logged warning |
| One giant component containing everything | Raise `w_min` until the cluster size distribution is informative. Report the threshold used |
| `Pc` unavailable for some edges | Use the `1/d_miss` rule for the whole graph rather than mixing; record it |

---

### 10.5 M5 — EXTERNALITY LEDGER (THE CORE MODULE)

**Purpose.** For every object, compute what it imposes on other operators, in operational units.
This is the project's novel artifact. Build it carefully.

**Inputs.** `conjunctions` for a run, `objects`, declared `Pc*`, per-operator thresholds, mission
value model, decay model.

**Outputs.** `ledger_entries` rows, `burden_flows` rows, the ranking.

**Algorithm.**

**Step 1 — Attribution rule.** For each conjunction, decide who imposes and who bears. This is the
most contestable part of the method, so the rules are explicit, ranked, and stated in the UI:

| Rule | Condition | Imposer | Bearer | Confidence |
|---|---|---|---|---|
| R1 | `ACTIVE_DEAD` | the dead object | the active object | **High** — the dead object cannot move; causation is unambiguous |
| R2 | `DEAD_DEAD` | both, split 50/50 | none (no maneuver) | High for hazard accounting, zero maneuver burden |
| R3 | `ACTIVE_ACTIVE`, different operators | split by inverse maneuverability capability; if equal, 50/50 | both | **Medium** — genuinely contested |
| R4 | `ACTIVE_ACTIVE`, same operator, coordinated | excluded by default | — | N/A |

**Start with R1 only.** Report R1 results as the headline. R1 is where the number is largest, the
causation is cleanest, and no expert will argue with it. R3 is a configurable extension; when
enabled, label the output `contested attribution` in the UI. Handling attribution this carefully is
itself a credibility signal.

**Step 2 — Maneuvers forced.** For each `ACTIVE_DEAD` conjunction where the active object is
maneuverable:
```
maneuver_forced = 1 if Pc >= Pc*  else  0
```
When `Pc` is unavailable, use the geometric surrogate and label it:
```
maneuver_forced = 1 if (d_miss <= d_trigger and v_rel >= v_min) else 0
```
Sum over the window. **Always tag with the threshold used** (`maneuvers_forced_at_Pc_1e-4`).

Optionally compute a soft count for robustness:
```
maneuvers_forced_soft = Σ  sigmoid((log10(Pc) - log10(Pc*)) / s)
```
which avoids a knife-edge at the threshold. Report both.

**Step 3 — Δv imposed.** For each forced maneuver, compute the Δv needed to reduce `Pc` below the
threshold, using the along-track burn approximation (§11.5):
```
Δv_required = minimal along-track impulse at t_burn = tca - lead_time
              such that post-maneuver Pc < Pc* / margin
```
Solve by bisection on Δv magnitude, re-propagating and re-screening the primary against the
secondary. `lead_time` default 1 orbit; configurable. Sum across forced maneuvers.

**Step 4 — Mission-days consumed.** Convert Δv to mission life using the operator's station-keeping
budget (§11.6):
```
mission_days = Δv_imposed / sk_budget_mps_per_day
```
`sk_budget_mps_per_day` from `config/mission_model.yaml` by altitude band. MODELLED. This is the
number that makes the output legible to non-specialists — do not skip it.

**Step 5 — Aggregate per imposer.**
```
for each object i:
    flows      = all burden_flows where imposer = i
    conj_gen   = count of conjunctions involving i (excluding intra-constellation)
    mnvr       = Σ flows.n_maneuvers
    dv         = Σ flows.dv_mps
    days       = Σ flows.mission_days
    operators  = |distinct flows.bearer_operator|
    top_bearer = argmax over operators of dv
    gini       = gini_coefficient(dv per bearer)      # concentration of harm
```

**Step 6 — CAB and normalisation.** §11.7. Report both raw and normalised-per-satellite-year forms;
the 2026 CAR literature is explicit that unnormalised cross-actor comparison is misleading.

**Step 7 — Lifetime projection.** Estimate remaining orbital lifetime from altitude and area-to-mass
(§11.9.1), then:
```
projected_lifetime_dv = dv_imposed_per_year × min(decay_lifetime_yr, horizon_cap_yr)
```
`horizon_cap_yr` default 25. MODELLED, with the decay assumption shown.

**Step 8 — Implied fee.** §11.9.2. INDICATIVE only. One line of disclaimer attached to the field,
always rendered.

**Step 9 — Ranking.** Sort all objects by CAB descending. This is the worst-offenders table.

**Pseudocode.**
```python
def compute_ledger(run_id, pc_threshold=1e-4, rules=("R1",)) -> LedgerResult:
    conjs = load_conjunctions(run_id)
    flows = []
    for c in conjs:
        if c.intra_constellation and CONFIG.exclude_intra: continue
        for (imposer, bearer, share, rule) in attribute(c, rules):
            if not bearer.is_maneuverable:
                n_mnvr, dv = 0.0, 0.0
            else:
                n_mnvr = forced(c, pc_threshold)                  # Step 2
                dv     = dv_to_clear(c, pc_threshold) if n_mnvr else 0.0   # Step 3
            flows.append(BurdenFlow(
                imposer_id=imposer.norad_id, bearer_id=bearer.norad_id,
                bearer_operator=bearer.operator,
                n_conjunctions=1, n_maneuvers=n_mnvr*share,
                dv_mps=dv*share,
                mission_days=dv*share / sk_budget(bearer),        # Step 4
                attribution_rule=rule))
    entries = []
    for obj_id, grp in groupby(flows, key="imposer_id"):
        e = aggregate(grp, obj_id, pc_threshold)                   # Steps 5-8
        entries.append(e)
    entries.sort(key=lambda e: -e.cab.value)                       # Step 9
    persist(entries, flows)
    return LedgerResult(entries=entries, flows=flows)
```

**Acceptance tests.**
- `test_dead_rocket_body_scenario` — synthetic immovable massive object; ledger attributes all
  forced maneuvers to it and zero to itself.
- `test_dead_object_bears_nothing` — for any inactive object, `maneuvers_performed == 0`.
- `test_threshold_sensitivity` — recompute at `Pc* ∈ {1e-4, 1e-5, 3e-7}`; ranking must be reported
  per threshold and the field names must carry the threshold.
- `test_dv_reduces_pc` — for each computed `dv_to_clear`, re-screen post-maneuver and assert
  `Pc < Pc*`. **This closes the loop; without it your Δv numbers are decorative.**
- `test_mission_days_consistency` — `mission_days × sk_budget == dv` to floating tolerance.
- `test_attribution_rule_recorded` — every flow carries its rule; R3 flows are labelled contested.
- `test_ranking_differs_from_pc_mass_ranking` — compute both the CAB ranking and a Pc×mass hazard
  ranking; assert they are **not identical**. If they are identical, you have not produced a new
  result and must say so honestly (§18.5). This test is the project's scientific self-check.

**Failure modes.**

| Failure | Handling |
|---|---|
| `dv_to_clear` bisection fails to converge | Cap iterations, return `None` with `na_reason`, exclude from the Δv sum, count in a `n_dv_unresolved` field shown in the report |
| No `ACTIVE_DEAD` conjunctions in the window | Widen window or shell; report honestly rather than enabling R3 to manufacture numbers |
| One object dominates everything | That is a *result*, not a bug. Verify it is not an artifact of a stale TLE or a duplicate catalogue entry, then report it |

---

### 10.6 M6 — FUTURE SIMULATOR

**Purpose.** Given a state and a hypothetical action, produce the resulting future: new
conjunctions, new risk, over a horizon.

**Inputs.** Object set, action (`Strategy`), horizon (24/48/72 h), Monte Carlo sample count.

**Outputs.** `SimResult`: post-action conjunction list, aggregate risk metrics, per-sample outcomes.

**Algorithm.**
1. Clone the state. **Pure function — never mutate the input.** This property is what makes Chaos
   Mode free.
2. Apply the action:
   - `HOLD` — no change
   - `MANEUVER(obj, dv_vec, t_burn)` — propagate to `t_burn`, apply impulsive Δv, rebuild the
     element set from the perturbed state (§11.2), continue
   - `WAIT(Δt)` — advance the decision epoch by Δt, shrink covariance per the M8 model, re-evaluate
   - `OBSERVE(obj)` — shrink that object's covariance per the M8 model, no state change
   - `COORDINATE(a, b)` — a joint maneuver pair; evaluated as a compound action
3. Re-screen the affected neighbourhood over the horizon. **Do not re-screen the whole catalogue** —
   restrict to the maneuvered object plus its 2-hop graph neighbourhood plus any object whose
   radial range overlaps the perturbed orbit. This is the difference between 2 seconds and
   2 minutes per strategy.
4. Compute post-action metrics: `pc_max`, `n_conjunctions`, `Σ Pc`, new edges created, edges removed.
5. Monte Carlo: sample initial states from the covariance, repeat steps 2–4, aggregate.

**Monte Carlo specification.**
```
N = 100 for interactive use, 1000 for the reported result
sample: r_0 ~ N(r_nominal, Σ_r)  per object with covariance
report:
    safe_fraction      = fraction of samples with max Pc < Pc*
    mean_future_conj   = mean number of conjunctions in horizon
    p95_future_conj    = 95th percentile
    worst_case         = max
NEVER call safe_fraction "accuracy" or "prediction confidence".
Call it: "fraction of sampled uncertainty scenarios in which the strategy
          remains below threshold." §18.3
```

**Acceptance tests.**
- `test_simulator_is_pure` — run twice on the same input; identical output; input object unchanged
  by identity and value.
- `test_hold_changes_nothing` — `HOLD` produces exactly the pre-action conjunction set.
- `test_maneuver_reduces_target_pc` — a maneuver sized by M5's `dv_to_clear` drops the target Pc
  below threshold in the simulation.
- `test_maneuver_can_create_new_conjunction` — construct a scenario where a maneuver creates a new
  conjunction; assert the simulator detects it. **If you cannot construct this case, your
  neighbourhood re-screening is too narrow.**
- `test_mc_reproducible_with_seed` — fixed seed gives identical results.
- `test_neighbourhood_rescreen_sufficient` — compare neighbourhood re-screening against full
  catalogue re-screening on a small case; assert no missed new conjunctions.

**Failure modes.**

| Failure | Handling |
|---|---|
| Element-set rebuild after Δv is inaccurate | Use the osculating-to-mean conversion in §11.2; validate that a zero Δv round-trips to the original elements within tolerance. Add this as a test |
| Monte Carlo too slow | Reduce N for interactive, keep N=1000 for the reported benchmark only. Vectorise sampling |
| Neighbourhood too narrow, misses secondary conjunctions | Expand to 2-hop + radial-overlap; verified by the test above |

---

### 10.7 M7 — MULTI-OBJECTIVE OPTIMISER

**Purpose.** Generate candidate strategies, evaluate them, and select the one minimising systemic
cost — including the decision-theoretic alternatives to simply moving.

**Inputs.** Cluster, weights `w`, constraints, simulator handle.

**Outputs.** Ranked `Strategy` list with full cost breakdown, expected cost, p95 cost, and max
regret.

**Strategy generation — the action space.** This is where OCI differs from a maneuver planner.
```
HOLD
MANEUVER(obj, dv, t_burn)     for each maneuverable obj in cluster,
                              dv ∈ grid, t_burn ∈ {1, 2, 4 orbits before TCA}
WAIT(Δt)                      Δt ∈ {30 min, 2 h, 6 h, next tracking pass}
OBSERVE(obj)                  request refined tracking on obj
COORDINATE(a, b)              joint maneuver, cost split
```
Cap the generated set at ~40 strategies for interactive latency. Generate the grid coarsely, then
refine around the best.

**Cost function.** §11.12. Weights configurable and exposed in the UI — the point is that different
operators get different answers.
```
J = w_s · SafetyCost + w_f · FutureRisk + w_v · FuelCost
  + w_m · MissionCost + w_n · NetworkImpact
```
Normalise each term to [0,1] against scenario-specific reference values so the weights are
meaningful. Document the normalisation.

**Three rankings, not one.** This is a cheap, high-value addition:

| Ranking | Criterion | Who it suits |
|---|---|---|
| Expected cost | `E[J]` over MC samples | An operator with many satellites who can average over outcomes |
| Robust | 95th-percentile `J` | An operator who cannot afford a bad tail |
| Minimax regret | `max over scenarios of (J − J_best_in_that_scenario)` | An operator facing deep uncertainty |

Then state, on stage: *the expected-value optimum and the minimax-regret optimum are frequently
different strategies, and a single-satellite operator should not choose the same action as a
300-satellite operator.* One extra column of arithmetic over data you already have, and it reads
as decision analysis rather than a scoring heuristic.

**Pseudocode.**
```python
def optimize(cluster, weights, sim, n_mc=100) -> OptimizeResult:
    strategies = generate_strategies(cluster)          # capped
    evaluated  = []
    for s in strategies:
        res   = sim.run(cluster.state, s, horizon_h=72, n_mc=n_mc)
        costs = [cost_vector(sample, weights) for sample in res.samples]
        evaluated.append(s.with_costs(
            expected = mean(costs), p95 = percentile(costs, 95),
            systemic = cost_vector(res.nominal, weights)))
    regret = compute_minimax_regret(evaluated)         # §11.12.3
    return OptimizeResult(
        by_expected = sorted(evaluated, key=lambda s: s.expected),
        by_robust   = sorted(evaluated, key=lambda s: s.p95),
        by_regret   = sorted(evaluated, key=lambda s: regret[s.id]),
        weights_used = weights)
```

**Acceptance tests.**
- `test_weights_change_recommendation` — two weight vectors that must produce different winners.
  **If no weight vector changes the answer, the optimiser is not solving a decision problem and
  you must say so.**
- `test_wait_wins_under_high_uncertainty` — on the `voi_event` scenario, `WAIT` must beat
  `MANEUVER` on expected cost.
- `test_hold_wins_when_risk_negligible` — with all Pc far below threshold, `HOLD` wins.
- `test_coordinate_beats_unilateral_when_appropriate` — on the `keystone_cluster`, coordination wins
  on systemic cost.
- `test_rankings_can_disagree` — assert that expected / robust / regret orderings are not always
  identical.
- `test_cost_normalisation_bounded` — every normalised cost term lies in [0,1].

**Failure modes.**

| Failure | Handling |
|---|---|
| All strategies score identically | Cost terms are badly normalised or the scenario is degenerate. Log and report; do not pick arbitrarily and present it as a recommendation |
| Strategy explosion / slow | Cap at 40; coarse-then-refine grid |
| Optimiser recommends an infeasible maneuver | That is M9's job. The optimiser is allowed to propose infeasible actions — the validator catches them. This is the intended closed loop |

---

### 10.8 M8 — UNCERTAINTY AND VALUE-OF-INFORMATION ENGINE

**Purpose.** Supply defensible covariances, model how uncertainty shrinks with time-to-TCA, and
compute the value of waiting. **This is the project's best idea and its most exposed flank.**

**Inputs.** D2 (Kelvins CDMs), object metadata, `time_to_tca`.

**Outputs.** `Covariance` estimates with `covariance_source`; `σ(τ)` shrinkage model; `VoI` per
event.

**Part A — Covariance model fitted to real CDMs.**

The problem: TLEs carry no covariance, so any Pc computed from D1 alone rests on an invented error
ellipsoid. The solution: fit the ellipsoid to 13,154 real events.

1. Load the Kelvins training set (162,634 rows).
2. Group by `event_id`; each group is a CDM time series indexed by `time_to_tca`.
3. For the covariance components — `c_sigma_r/t/n`, `t_sigma_r/t/n` — fit
   ```
   log σ_k(τ, type, alt) = a_k + b_k · log(1 + τ) + c_k · I[object_type] + d_k · alt_band
   ```
   by ordinary least squares. Use the challenge paper's feature-relevance finding to prioritise:
   along-track sigma (`c_sigma_t`) and `mahalanobis_distance` carry most of the signal, so fit
   along-track most carefully.
4. Persist coefficients to `models/covariance_fit.json` with the fit diagnostics (R², residual
   spread) — those diagnostics go in the assumptions panel.
5. When annotating a D1-derived conjunction, evaluate the fit at that conjunction's `time_to_tca`,
   object types, and altitude. Set `covariance_source = "kelvins_fitted"`.

**Say this on stage, verbatim or close to it:**
> A TLE contains no covariance, so we do not invent one. We fit the covariance model to 13,154 real
> conjunction events released publicly by ESA, and we display the fit and its residual spread
> alongside every number that depends on it.

That sentence converts your weakest technical point into a strength.

**Part B — Shrinkage model (the VoI engine's foundation).**

The real, observed property: as CDM updates arrive and TCA approaches, position uncertainties
shrink because knowledge of the encounter is refined. Fit it:
```
σ_t(τ) = σ_∞ + (σ_0 - σ_∞) · exp(-λ · (τ_0 - τ))
```
Estimate `λ` per altitude band and object class from the Kelvins time series. Report `λ` with a
confidence interval.

**Part C — Value of information.**
```
Option A: act now
    Δv_now = dv_to_clear(Pc(σ(τ_now)))
    cost_A = fuel(Δv_now) + risk_residual + 0

Option B: wait Δt, then act
    σ' = σ(τ_now - Δt)                      # from Part B
    E[Δv_later] = E over Pc' ~ p(Pc | σ') of dv_to_clear(Pc')
    cost_B = fuel(E[Δv_later]) + risk_residual' + risk_of_waiting(Δt)

VoI = cost_A - cost_B
Recommend WAIT if VoI > 0 AND the remaining lead time after waiting still
permits a maneuver (hard constraint — checked by M9).
```
`risk_of_waiting` must be genuinely modelled, not zeroed: it is the probability that the refined
estimate arrives too late, or that the risk turns out higher and the required Δv grows. Compute it
from the same fitted distribution. A VoI module that always says "wait" is broken.

**Validation against real events (do this — it is a publishable-grade result).**
Replay Kelvins events: at each CDM epoch, ask the engine WAIT / MANEUVER / HOLD. Then compare
against the actual final risk in the last CDM of that event. Report:
```
n_events_replayed
fraction where WAIT was recommended and final risk was indeed below threshold  (correct wait)
fraction where WAIT was recommended and final risk exceeded threshold          (dangerous wait)
mean modelled Δv saved by correct waits
```
Those four numbers, computed on 13,154 real events, are worth more than any visualisation you could
build. **Budget time for this.**

**Acceptance tests.**
- `test_covariance_fit_converges` — fit runs, R² reported, coefficients finite.
- `test_sigma_decreases_with_decreasing_tau` — the fitted `σ(τ)` is monotone decreasing toward TCA.
- `test_voi_positive_under_high_uncertainty` — `voi_event` scenario: VoI > 0.
- `test_voi_negative_when_lead_time_short` — with TCA imminent, VoI ≤ 0 and WAIT is not recommended.
- `test_voi_not_always_wait` — across the replay set, WAIT is recommended in strictly less than 100%
  of cases.
- `test_covariance_source_always_labelled` — no conjunction has a Pc without a covariance source.

**Failure modes.**

| Failure | Handling |
|---|---|
| Kelvins fit is poor (low R²) | Report the R². Fall back to a stated conservative constant covariance, labelled `assumed`, and say so. **Do not hide a bad fit** |
| Fitted model extrapolated outside the Kelvins altitude range | Clamp to the fitted range and flag `extrapolated=True` on affected conjunctions |
| VoI always recommends waiting | `risk_of_waiting` is under-modelled. Fix before demo — this is a credibility-destroying bug |

---

### 10.9 M9 — PHYSICS VALIDATOR

**Purpose.** Reject physically or operationally infeasible proposals, with a reason. This module is
what makes the closed-loop agentic story *true* rather than theatre.

**Read this carefully — it is the fix for a fatal flaw in the v1.0 plan.** If the agent only picks
from a pre-generated list of feasible strategies, the validator can never reject anything, and any
"rejection" you show would have to be scripted. So: **the agent is allowed to propose free-form
maneuvers** — arbitrary Δv vector, arbitrary burn time — and the validator does real work.

**Inputs.** Proposed `Strategy`, object state, constraint config.

**Outputs.** `Verdict(APPROVED | REJECTED, reason, violated_constraints[])`.

**Constraint checks.**

| # | Check | Rejection reason |
|---|---|---|
| C1 | `|Δv| ≤ dv_max_per_burn` | Exceeds thruster capability |
| C2 | `|Δv| ≤ remaining_propellant_dv` | Insufficient propellant budget |
| C3 | `t_burn ≥ now + command_uplink_lead` | No ground contact in time to command |
| C4 | `t_burn ≤ tca - min_maneuver_lead` | Too late to be effective |
| C5 | Post-maneuver perigee ≥ `min_alt_km` | Would lower perigee into unacceptable drag / reentry |
| C6 | Post-maneuver orbit still within mission constraints (altitude band, inclination, revisit) | Violates mission requirements |
| C7 | **Post-maneuver re-screen: no new conjunction with `Pc > Pc*` in the horizon** | Creates a secondary conjunction |
| C8 | Burn not during eclipse if power-constrained | Power constraint |
| C9 | Slew time feasible for the required attitude | Attitude/slew infeasible |
| C10 | For `COORDINATE`: both operators' constraints individually satisfied | Partner constraint violated |

C7 is the one that produces the most interesting rejections and the one your v1.0 plan wanted. It
is real because the agent can propose an arbitrary burn.

**Pseudocode.**
```python
def validate(strategy, state, constraints) -> Verdict:
    violations = []
    if strategy.kind == "MANEUVER":
        dv = norm(strategy.params["dv_vec"])
        if dv > constraints.dv_max_per_burn:
            violations.append(("C1", f"|dv|={dv:.3f} > max {constraints.dv_max_per_burn}"))
        if dv > constraints.remaining_dv:
            violations.append(("C2", "insufficient propellant"))
        if strategy.params["t_burn"] < now() + constraints.uplink_lead:
            violations.append(("C3", "no ground contact before burn"))
        if strategy.params["t_burn"] > strategy.tca - constraints.min_lead:
            violations.append(("C4", "burn too late to be effective"))
        post = apply_maneuver(state, strategy)
        if perigee_alt(post) < constraints.min_alt_km:
            violations.append(("C5", f"post-burn perigee {perigee_alt(post):.1f} km too low"))
        if not within_mission_box(post, constraints.mission):
            violations.append(("C6", "violates mission orbit constraints"))
        newc = rescreen_neighbourhood(post, horizon_h=72)
        bad  = [c for c in newc if c.pc and c.pc > constraints.pc_threshold
                                and c.conj_id not in state.known_conj_ids]
        if bad:
            violations.append(("C7",
              f"creates {len(bad)} new conjunction(s), worst Pc={max(c.pc for c in bad):.2e} "
              f"with NORAD {bad[0].secondary_id}"))
    if strategy.kind == "WAIT":
        if strategy.tca - (now() + strategy.params["delta_t"]) < constraints.min_lead:
            violations.append(("C4", "waiting would eliminate the maneuver window"))
    return Verdict(
        status = "REJECTED" if violations else "APPROVED",
        reason = "; ".join(v[1] for v in violations) or "all constraints satisfied",
        violated = [v[0] for v in violations])
```

**Acceptance tests.**
- `test_excessive_dv_rejected` — C1 fires.
- `test_late_burn_rejected` — C4 fires.
- `test_secondary_conjunction_rejected` — construct a maneuver that creates a new conjunction;
  assert C7 fires with the offending NORAD ID in the reason.
- `test_valid_maneuver_approved` — a sane maneuver passes all ten checks.
- `test_rejection_is_unscripted` — run the agent loop on a scenario with no hardcoded rejection;
  assert at least one rejection occurs across the strategy set purely from the constraint logic.
  **This test is the difference between a real closed loop and a staged one.**
- `test_wait_eliminating_window_rejected` — C4 fires for `WAIT`.

**Failure modes.**

| Failure | Handling |
|---|---|
| Validator rejects everything | Constraints are too tight or the generator is producing nonsense. Log the histogram of violated constraint IDs — that histogram is also a great UI element |
| Validator approves everything | C7 re-screening is too narrow, or thresholds are too loose. Fix before demo; an always-approving validator makes the whole loop theatre |

---

### 10.10 M10 — CAPACITY ENGINE

**Purpose.** Answer the strategic question — what does a deployment do to a shell — in **both**
currencies, workload and hazard, and expose that they disagree.

**Inputs.** Shell definition, current catalogue, proposed deployment (`N` satellites, altitude,
inclination), horizon.

**Outputs.** Per-shell `OCS`, maneuver burden per satellite-year, hazard index, `κ`, and the
deployment comparison table.

**Critical modelling decision.** You cannot answer this with pairwise screening. 5,000 new objects
against 30,000 existing is 150 million pairs per time step, and it is the *wrong model* because
large constellations are phase- and plane-separated by design, so intra-constellation mutual risk
is actively managed, not free. A naive pairwise count of 5,000 co-altitude satellites will produce
12.5 million internal "conjunctions" and crater your capacity score for a reason that is a pure
model artifact. An expert will see it instantly.

**So: two engines.**

| Question | Engine | Why |
|---|---|---|
| Tactical: this event, next 72 h | Pairwise screening (M3) | Individual objects matter; counts are small |
| Strategic: this shell, next 10 years | **Kinetic-gas / spatial-density flux** | Population-level; intra-constellation traffic treated as coordinated |

**Flux model (§11.13 for full derivation).**
```
Collision / conjunction rate per object in shell s:

    R_s = spatial_density_s · σ_cross · v_rel_mean_s

where
    spatial_density_s = N_s / V_s              objects per km³
    V_s               = (4/3)π (r_high³ - r_low³)
    σ_cross           = π (r_screen)²           screening cross-section
    v_rel_mean_s      = mean relative speed in the shell, from inclination
                        distribution (~7-14 km/s in LEO; compute, don't guess)

Conjunctions per satellite-year:
    C_s = R_s · seconds_per_year

Maneuvers per satellite-year at threshold Pc*:
    M_s = C_s · P(Pc > Pc* | conjunction in shell s)
```
The conditional probability is calibrated against the observed pairwise screening from M3 in the
same shell. **That calibration is what keeps the flux model honest** — the two engines cross-check
each other. Report the calibration factor.

**Intra-constellation handling.** When adding `N` satellites as a coordinated constellation, apply
a coordination factor `c_intra ∈ [0,1]` to the internal component of the flux, default 0.05 with a
citation to the observation that intra-constellation conjunctions are managed by robust operational
station-keeping. Expose `c_intra` as a slider. Show what happens at `c_intra = 1.0` (uncoordinated)
so the judge sees that you know the difference.

**Hazard index (the second currency).** Workload is not the only cost. §11.10.3:
```
hazard_s = Σ_{i in s} mass_i · persistence_i · P(involved in fragmentation)
persistence_i = min(decay_lifetime_i, cap)
```
Weight by whether the object is active or inactive — the environmental index is dominated by
inactive objects, so inactive mass carries far more hazard weight per kilogram than active mass.

**OCS.** §11.10.1. Anchored to the measured viability threshold of 10 maneuvers per month:
```
OCS_s = 100 · clamp(1 - M_s / M_viability, 0, 1)

with M_viability = 120 maneuvers per satellite-year (= 10/month, the
published operational-viability threshold)
```
So `OCS = 100` means negligible burden; `OCS = 0` means the shell is at or past the level where
operating there is not worth it. **This is why OCS is anchored rather than invented** — the anchor
is a published figure, not a number you chose. Say that on stage.

**The deployment comparison — the signature output.**
```
Query: 5,000 satellites, inclination 53°, candidate altitudes

Alt   | OCS  | Mnvr/sat/yr | Hazard idx | Decay yr | WORKLOAD rank | HAZARD rank
------|------|-------------|------------|----------|---------------|-------------
540km |  ..  |     ..      |     ..     |   ..     |      ..       |     ..
550km |  ..  |     ..      |     ..     |   ..     |      ..       |     ..
570km |  ..  |     ..      |     ..     |   ..     |      ..       |     ..
600km |  ..  |     ..      |     ..     |   ..     |      ..       |     ..

⚠  WORKLOAD-OPTIMAL and HAZARD-OPTIMAL altitudes DIFFER.
   Recommendation depends on which cost the operator and the regulator
   are each paying. The system presents both; it does not collapse them
   into a single score.
```

**Do not pre-decide the answer.** The v1.0 plan asserted 570 km beats 550 km on congestion. The
physically dominant long-horizon variable at these altitudes is atmospheric decay — lower orbits
self-clean faster, which is why capacity work finds sustainable active-satellite counts decreasing
with altitude while debris increases, and why higher altitudes are far more sensitive. So the
honest answer may well be *lower is better despite worse near-term congestion.* If your correctly
built model says that, **report it** — a counterintuitive defensible result beats a tidy fabricated
one every single time.

**Acceptance tests.**
- `test_flux_calibrates_against_pairwise` — in one shell, the flux-model conjunction rate matches
  the M3 pairwise rate within a stated factor; report the factor.
- `test_intra_constellation_factor_matters` — `c_intra = 0.05` vs `1.0` changes OCS materially.
- `test_decay_included` — removing the decay term changes the altitude ranking. Proves decay is
  actually in the model.
- `test_two_peaks_reproduced` — the computed workload peak and hazard peak occur at different
  altitudes, qualitatively matching the published 500–600 km vs ~850 km structure.
- `test_ocs_bounded` — `OCS ∈ [0,100]` always.
- `test_ocs_anchor_documented` — `M_viability` is read from config with its citation attached.

**Failure modes.**

| Failure | Handling |
|---|---|
| Flux model disagrees wildly with pairwise | Report the discrepancy as a finding. Do not tune one to match the other silently |
| Capacity score saturates at 0 everywhere | `M_viability` or the flux constants are wrong. Check units — this is almost always a km/m error |
| Model says the opposite of the intuitive answer | Verify the decay and density terms, then **report it as the result** |

---

### 10.11 M11 — AGENT PLANNER

Full specification in §14. Summary here for architectural completeness.

**Purpose.** Sequence the analysis, propose free-form actions, interpret validator rejections,
replan, and generate the explanation — using only computed values.

**Hard rules.**
1. One agent. Not four. §14.1.
2. The agent may not state a numerical value it did not receive from a tool. §14.4.
3. The agent's proposals are free-form so the validator does real work. §10.9.
4. Every agent turn is logged as a reasoning trace and displayed in the UI.

---

### 10.12 M12 — API

Full contract in §12.

---

### 10.13 M14 — CHAOS MODE

**Purpose.** Demonstrate that the system is adaptive rather than a static replay, by letting the
judge perturb the environment mid-run.

**This is nearly free if and only if M6 is a pure function of state.** If it is,
`chaos(state) → state'` then `recommend(state')`. If M6 mutates hidden state, this becomes a
two-day retrofit and you will skip it. Architect for purity on day one.

**Perturbations.**

| Injection | Implementation |
|---|---|
| New object appears | Insert a synthetic object into the catalogue on a conjuncting trajectory |
| Uncertainty spike | Multiply the covariance of one or more objects by a factor |
| Unexpected maneuver by a third party | Apply an unannounced Δv to a non-cluster object |
| Tracking gap | Advance `time_to_tca` without shrinking covariance |
| Operator refuses coordination | Remove `COORDINATE` from the action space |
| Command uplink delay | Increase `constraints.uplink_lead`, invalidating `t_burn` choices |
| Constellation insertion | Add `N` objects to a shell (links to M10) |

**Required behaviour after injection.**
```
1. Detect the state change (diff the conjunction set / covariances)
2. Mark the previous recommendation INVALIDATED, with the reason
3. Rebuild the graph over the affected neighbourhood
4. Regenerate and re-evaluate strategies
5. Re-validate
6. Emit a new recommendation with a diff against the old one
```
The **diff** is the impressive part: "previous recommendation MANEUVER SAT-A is now invalid because
the new object creates a conjunction with the post-burn trajectory; new recommendation is WAIT then
MANEUVER SAT-B."

**Acceptance tests.**
- `test_chaos_invalidates_previous` — after injection, prior recommendation is marked invalid with a
  reason.
- `test_chaos_produces_new_recommendation` — a new, different recommendation is emitted.
- `test_chaos_deterministic_with_seed` — reproducible for the demo.
- `test_chaos_end_to_end_under_10s` — full replan completes inside 10 seconds. **Nobody watches a
  30-second spinner on stage.**

---

### 10.14 AUDIT TRAIL / "SHOW THE MATH"

**Purpose.** Make every displayed number traceable, and make the assumption set permanently visible.

**Why it matters more than it looks.** Aerospace is a traceability culture, so this reads as
professional maturity rather than as a feature. And it structurally answers the suspicion every
judge now carries about LLM demos — *is the AI making the numbers up?* You can disprove that live,
in ten seconds, which is cheap insurance on your most exposed flank.

**Implementation.**
1. Every UI number comes from a `Traced` object (§9.2/9.3) carrying `label`, `function`,
   `assumptions`, and `na_reason`.
2. Clicking a number opens a panel showing: value, unit, label, producing function and version,
   input values, and the assumption set.
3. A **persistent assumptions panel** is always visible, showing:
   ```
   Covariance source      : Kelvins-fitted (R² = 0.xx, n = 13,154 events)
   Propagator             : SGP4 (sgp4 x.y.z)
   Screening volume       : 5,000 m
   Coarse step / gate      : 15 min / k = 4
   Pc method              : Foster (2D)
   Declared Pc threshold  : 1e-4 (IADC)
   Hard-body radius       : 5.0 m (MODELLED)
   Mass model             : class×RCS lookup (MODELLED, ranges shown)
   Horizon                : 72 h
   Monte Carlo samples    : 100
   Intra-constellation    : EXCLUDED from attribution (c_intra = 0.05)
   Attribution rules      : R1 only (unambiguous)
   Objective weights      : safety 0.40 / future 0.20 / fuel 0.15 / mission 0.15 / network 0.10
   ```
4. Every export (CSV, JSON) embeds the same assumption block.

**Acceptance tests.**
- `test_every_api_number_is_traced` — walk the API response tree; assert no bare float reaches a
  display field.
- `test_na_has_reason` — every `None` value carries a non-empty `na_reason`.
- `test_assumptions_panel_complete` — all keys listed above are present and non-null.
- `test_export_embeds_assumptions` — CSV/JSON export contains the assumption block.

---

### 10.15 M15 — BENCHMARK HARNESS

Full specification in §15. **Built at step 3 of the build order, not last.** It is your scoring
function during development, and if the result comes out neutral you need to know on day one, not
at hour forty.

---

## 11. MATHEMATICS APPENDIX

Every formula the implementation needs. Constants first.

```
mu_earth  = 398600.4418          km³/s²
R_earth   = 6378.137             km
J2        = 1.08262668e-3
omega_E   = 7.2921159e-5         rad/s
```

### 11.1 Derived orbital quantities from a TLE

```
n_rev_per_day  = MEAN_MOTION                       (TLE field)
n_rad_per_s    = n_rev_per_day · 2π / 86400
a              = (mu / n_rad_per_s²)^(1/3)         km
r_p            = a (1 - e)                         km
r_a            = a (1 + e)                         km
perigee_alt    = r_p - R_earth                     km
apogee_alt     = r_a - R_earth                     km
period_min     = 1440 / n_rev_per_day              min
```

### 11.2 Impulsive maneuver and element-set rebuild

Apply Δv at time `t_burn`:
```
r_after = r(t_burn)
v_after = v(t_burn) + Δv
```
To continue propagating with SGP4 you need an element set from `(r_after, v_after)`:
1. Convert the state to osculating Keplerian elements (standard `rv2coe`).
2. Convert osculating to mean elements (remove short-period J2 terms) — the Brouwer–Lyddane
   transformation. A first-order approximation is acceptable for small Δv; **document that it is
   first-order.**
3. Rebuild the `Satrec`.

**Mandatory validation test:** with `Δv = 0`, the round trip must return the original element set
within tolerance. If it does not, your conversion is wrong and every post-maneuver number in the
project is wrong.

For along-track burns the change in semi-major axis is, to first order:
```
Δa ≈ 2 a² v / mu · Δv_alongtrack
```
Sanity anchor: at 550 km, a 1 m/s along-track burn shifts `a` by a few hundred metres. **Internalise
this scale.** It is why single-event cascade chains (A moves → threatens C → C moves → threatens D)
are not a real 72-hour dynamic, and why the honest framing is population-level burden, not a
causal chain of four satellites (§2.7, §18.7).

### 11.3 RTN frame and covariance rotation

RTN (radial / transverse / normal) basis from state `(r, v)`:
```
R̂ = r / |r|
N̂ = (r × v) / |r × v|
T̂ = N̂ × R̂
M  = [R̂ᵀ; T̂ᵀ; N̂ᵀ]          rotation inertial → RTN
```
Given RTN sigmas from §10.8, the position covariance in RTN is
```
Σ_RTN = diag(σ_R², σ_T², σ_N²)   (+ correlation terms from the CDM when available)
```
and in the inertial frame
```
Σ_inertial = Mᵀ Σ_RTN M
```
Combined covariance for a conjunction (assuming independence):
```
Σ_combined = Σ_primary + Σ_secondary
```

### 11.4 Probability of collision

**Encounter (B-)plane construction.** For a short-term encounter, project into the plane
perpendicular to the relative velocity at TCA:
```
û_z = v_rel / |v_rel|                       out-of-plane axis
û_x = any unit vector ⊥ û_z (use the projected miss vector)
û_y = û_z × û_x
```
Project `Σ_combined` into the B-plane → 2×2 matrix `C`. Project the miss vector → `(x_m, y_m)`.

**Foster's 2D method** (use this as the default; it is the standard short-term-encounter method):
```
Pc = (1 / (2π √det C)) ∬_{disk of radius HBR}
       exp( -½ [x-x_m, y-y_m] C⁻¹ [x-x_m, y-y_m]ᵀ ) dx dy
```
with `HBR` the combined hard-body radius (sum of the two objects' radii; default 5.0 m combined,
MODELLED). Evaluate numerically by polar-coordinate quadrature; verify against a Monte Carlo
estimate in a unit test.

**Maximum probability** (when covariance is unreliable — and yours partly is):
```
Pc_max = max over covariance scaling factors k of Pc(k · C)
```
This is the quantity the Kelvins dataset exposes as `max_risk_estimate` via `max_risk_scaling`. It
is the honest metric to lead with when covariance confidence is low, because it is an upper bound
rather than a point estimate. **Report both `Pc` and `Pc_max`, and say which one you are using for
each decision.**

**Mandatory conditions on any Pc you report:**
```
pc_method         = "foster_2d" | "chan" | "maximum"
covariance_source = "kelvins_fitted" | "cdm_observed" | "assumed" | "none"
hbr_m             = value used
If covariance_source == "none":  pc = None, na_reason set.  NEVER fabricate.
```

### 11.5 Δv required to clear a threshold

No closed form. Solve numerically:
```
find minimal |Δv| along the along-track direction at t_burn = tca - lead
such that Pc(post-maneuver geometry) < Pc* / margin

method: bisection on |Δv| ∈ [0, dv_max]
        each evaluation: apply Δv (§11.2), re-propagate to TCA,
                         recompute miss vector and Pc (§11.4)
        margin default 2.0
        tolerance 1e-3 m/s, max 40 iterations
```
Along-track is the efficient direction for changing along-track separation, which is what dominates
most LEO conjunction geometry. Also evaluate radial and cross-track as a comparison and report the
best; do not hardcode along-track as optimal without checking.

### 11.6 Δv → mission life

```
mission_days_lost = Δv / sk_budget_mps_per_day

sk_budget_mps_per_day by altitude (MODELLED, config/mission_model.yaml):
    400–500 km :  ~0.15   m/s/day        (high drag)
    500–600 km :  ~0.05   m/s/day
    600–700 km :  ~0.02   m/s/day
    700–900 km :  ~0.005  m/s/day
```
These are order-of-magnitude station-keeping budgets and must be labelled MODELLED with the range
shown. Cross-check against the published GEO figures as a sanity anchor: east-west station-keeping
runs about 2–2.8 m/s per year, while north-south inclination control runs roughly 44–55 m/s per
year — which tells you immediately that a 1 m/s conjunction maneuver is a meaningful fraction of a
LEO satellite's annual budget, not a rounding error.

Then, to make the number legible:
```
fleet_satellite_years_lost = Σ over fleet of mission_days_lost / 365
```

### 11.7 CAB — Conjunction-Attributed Burden

**11.7.1 Definition.** For object `i`, over window `W`, at declared threshold `Pc*`:
```
CAB_i(W, Pc*) = α_m · M_i + α_v · V_i + α_d · D_i

M_i = Σ_{c ∈ C_i}  1[Pc_c ≥ Pc*] · 1[bearer maneuverable] · share_c
V_i = Σ_{c ∈ C_i}  Δv_required(c, Pc*) · share_c                    [m/s]
D_i = Σ_{c ∈ C_i}  Δv_required(c, Pc*) / sk_budget(bearer) · share_c [days]

C_i    = conjunctions where i is the imposer under the active attribution rules
share_c = attribution share from §10.5 Step 1
```
Default weights: report the components separately and use `α = (0, 1, 0)` — i.e. **CAB is reported
primarily in metres per second**, because Δv is the unit an operator actually feels and it is
dimensionally clean. Provide the composite as an option, never as the only figure.

**11.7.2 Attribution shares.** As in §10.5 Step 1. Always store `attribution_rule` per flow.

**11.7.3 Concentration.** Harm concentration across bearers:
```
gini_i = Gini coefficient of {V_i→j} over bearers j
```
High Gini means one operator eats the cost — relevant to fairness and to who would fund removal.

**11.7.4 Normalisation.** Following the 2026 CAR formulation — cross-actor comparison is
analytically misleading without normalising by both fleet size and trigger threshold:
```
CAB_normalised_i = CAB_i / (Δt_years)                       per year
CAR_operator(Pc*) = M_CA / (N_sat · Δt)                     maneuvers per satellite-year
```
**Every reported burden figure carries its `Pc*`.** No exceptions.

### 11.8 Regime indicator κ

Rao raises substitutes-vs-complements and leaves it open. Operationalise it:
```
For shell s, over window W:

κ_s = E[ number of NEW conjunctions above Pc* created per executed maneuver ]

Estimate by simulation:
    sample K maneuvering events in shell s
    for each: apply the Δv that clears its threshold (§11.5),
              re-screen the neighbourhood (M6),
              count new conjunctions with Pc > Pc* that did not exist before
    κ_s = mean of those counts

Interpretation:
    κ < 1  STRATEGIC SUBSTITUTES   — avoidance relieves pressure; the shell
                                     is self-relieving. Maneuvering scales.
    κ ≈ 1  INDETERMINATE           — report as such; do not force a label
    κ > 1  STRATEGIC COMPLEMENTS   — avoidance propagates pressure; the shell
                                     is self-amplifying. Removal or deployment
                                     change is required, not better dodging.
```
Report `κ` with a confidence interval from the sampling. The **action implication differs
qualitatively** across the regimes, which is exactly the prescriptive step the network literature
does not take.

### 11.9 Hazard, lifetime, and the indicative fee

**11.9.1 Decay lifetime estimate (MODELLED).**
```
Simplified exponential-atmosphere estimate:
    ρ(h) = ρ_0 exp(-(h - h_0)/H)
    da/dt = -(A/m) ρ(h) √(mu · a)          (circular orbit approximation)
    integrate numerically from current a down to a_reentry (h = 100 km)
```
Parameters from `config/atmosphere.yaml` with an explicit solar-activity assumption. Label MODELLED
and show the assumed `A/m` and solar condition. Cross-check: the published guidance environment
moved from a 25-year post-mission disposal rule toward 5-year and 1-year proposals precisely
because lifetime at these altitudes is long — so if your model gives 61 years for an 850 km object,
that is the right order of magnitude.

**11.9.2 Indicative fee.**
```
fee_indicative_i = (CAB_normalised_i / CAB_normalised_reference) · fee_reference

fee_reference = the published optimal orbital-use fee magnitude
                (~$235,000 per satellite-year in 2040, from Rao, Burgess
                 & Kaffine 2020, PNAS)
CAB_normalised_reference = the mean CAB per active satellite-year in the
                           same shell
```
**Label INDICATIVE, always, with this exact caveat attached to the field:** *this is a scaling of a
published aggregate fee estimate onto our per-object burden measure; it is not a price, not a legal
assessment, and not calibrated to any regulatory instrument.*

Why include it anyway: it converts an abstract metric into a number a non-technical judge or a
regulator can reason about, and it names the exact literature you are extending. That is a strength
if labelled and a liability if not.

### 11.10 OCS — Orbital Capacity Score

**11.10.1 Workload form (primary).**
```
OCS_workload(s) = 100 · clamp(1 - M_s / M_viability, 0, 1)

M_s           = modelled maneuvers per satellite-year in shell s
M_viability   = 120                     [maneuvers per satellite-year]
                = 10 per month, the published threshold at which satellite
                  operation is considered too operationally complicated to
                  be beneficial
```
The anchor is published, not invented. That single fact is what makes OCS defensible where an
arbitrary composite score would not be.

**11.10.2 Components, always exposed.**
```
spatial_density_s, v_rel_mean_s, conjunctions_per_sat_yr_s,
P(Pc > Pc* | conjunction)_s, c_intra, M_s, M_viability
```
Never present OCS without its components. A single opaque score is exactly what §16 of the v1.0
plan rightly warned against.

**11.10.3 Hazard form (the second currency).**
```
hazard_index(s) = Σ_{i ∈ s} m_i · w_state(i) · persistence_i / normaliser

w_state(i) = 1.0   if inactive (derelict, rocket body, debris)
           = w_a   if active, default 0.1
persistence_i = min(decay_lifetime_yr_i, 100)
```
`w_state` is asymmetric because the environmental index is dominated by inactive objects — on the
order of 96% of the LEO environmental index is associated with inactive objects under current
assumptions. Cite that when asked why active mass is discounted.

**11.10.4 Never collapse the two.**
```
Report:  OCS_workload(s)  AND  hazard_index(s)  AND  the argmin altitude of each.
Flag when they disagree.  Do NOT produce a single blended "sustainability score."
```
The disagreement *is* the result.

### 11.11 Value of information

As in §10.8 Part C. Formal statement:
```
Let τ = time to TCA, σ(τ) the fitted uncertainty (§10.8 Part B).

cost_now  = c_f · Δv(Pc(σ(τ)))  +  c_r · P_residual(σ(τ))

cost_wait(Δt) =
      c_f · E_{Pc' ~ p(·|σ(τ-Δt))} [ Δv(Pc') ]
    + c_r · E[ P_residual(σ(τ-Δt)) ]
    + c_l · P(window closes | Δt)                  ← must be nonzero
    + c_u · P(risk grows beyond recoverable | Δt)  ← must be nonzero

VoI(Δt) = cost_now - cost_wait(Δt)
recommend WAIT(Δt*) where Δt* = argmax VoI(Δt), subject to VoI > 0
                                and M9 constraint C4 satisfied
```
The last two terms in `cost_wait` are what stop the module from always saying wait. If either is
zero in your implementation, the module is broken (§10.8 failure modes).

### 11.12 Systemic cost

**11.12.1 Cost vector.**
```
SafetyCost     = max Pc over cluster after action, normalised by Pc*
FutureRisk     = Σ Pc over new conjunctions in horizon, normalised
FuelCost       = Σ Δv over all maneuvering objects / dv_reference
MissionCost    = Σ mission-days lost / days_reference
NetworkImpact  = Δ(Σ w_ij over cluster edges) / reference
                 i.e. did the action make the local graph better or worse

J = w_s·Safety + w_f·FutureRisk + w_v·Fuel + w_m·Mission + w_n·Network
```
All terms normalised to [0,1] against scenario-specific references; document each reference.

**11.12.2 Defaults.**
```
w_s = 0.40   safety
w_f = 0.20   future risk
w_v = 0.15   fuel
w_m = 0.15   mission
w_n = 0.10   network impact
```
**Configurable and exposed.** The demonstration that changing weights changes the recommendation is
what proves you are solving a decision problem rather than emitting a fixed answer.

**11.12.3 Minimax regret.**
```
For strategies S and Monte Carlo scenarios Ω:
    regret(s) = max_{ω ∈ Ω} [ J(s, ω) - min_{s'} J(s', ω) ]
    robust choice = argmin_s regret(s)
```

### 11.13 Flux / kinetic-gas capacity model

```
Shell s: r_low = R_earth + h_low,  r_high = R_earth + h_high
V_s = (4/3)π (r_high³ - r_low³)                              km³
D_s = N_s / V_s                                              objects/km³

Mean relative speed. For objects on circular orbits at the same altitude with
inclinations i₁, i₂ and random relative node geometry, the relative speed depends
on the angle between velocity vectors. Compute:
    v_orb  = √(mu / a)
    v_rel  = 2 v_orb sin(Δ/2)    where Δ is the angle between velocity vectors
    v_rel_mean_s = E[v_rel] over the empirical inclination distribution of the shell
LEO reference: reported relative speeds in conjunctions commonly fall in the
~7 km/s range for crossing geometries; use the computed value, sanity-check it
against that.

Conjunction cross-section:  σ_c = π d_screen²                 km²
Rate per object:            R = D_s · σ_c · v_rel_mean_s      per second
Conjunctions/sat/year:      C_s = R · 3.156e7
Maneuvers/sat/year:         M_s = C_s · q_s(Pc*)

q_s(Pc*) = P(Pc > Pc* | conjunction in shell s), CALIBRATED against the
           pairwise screening result from M3 in the same shell.

Deployment of N new coordinated satellites:
    D_s' = (N_existing + N) / V_s
    internal component of the new traffic scaled by c_intra (default 0.05)
    external component full weight
    recompute C_s', M_s', OCS'
```
Spatial-density sanity anchor: high spatial density in LEO is on the order of 1e-7 objects per
cubic kilometre and low density on the order of 1e-9. If your computed `D_s` is far outside that
range, you have a unit error.

---

## 12. REST API CONTRACT

### 12.1 Conventions

```
Base URL         /api/v1
Content-Type     application/json
Errors           RFC 7807 problem+json
Auth             none in MVP (localhost demo). Do not add auth; it costs hours and buys nothing.
Timestamps       ISO 8601 UTC, always with the Z suffix
Numbers          every number destined for display is a Traced object (§9.2), never a bare float
Long operations  202 + job_id, poll /jobs/{job_id}
```

**Universal envelope.** Every 200 response carries the assumption block, so an exported response is
self-describing and cannot be quoted out of context:

```json
{
  "data": { },
  "assumptions": {
    "covariance_source": "kelvins_fitted",
    "propagator": "sgp4-2.23",
    "screening_volume_m": 5000,
    "pc_method": "foster",
    "pc_threshold": 1e-4,
    "hard_body_radius_m": 5.0,
    "horizon_h": 72,
    "mc_samples": 100,
    "intra_constellation_excluded": true,
    "attribution_rules": ["R1"],
    "weights": {"safety":0.40,"future":0.20,"fuel":0.15,"mission":0.15,"network":0.10}
  },
  "run_id": "run_20260912T1030Z_a91f",
  "computed_at": "2026-09-12T10:31:04Z"
}
```

**The `Traced` shape on the wire:**

```json
{ "value": 18.7, "unit": "m/s", "label": "MODELLED",
  "function": "ledger.compute_dv_imposed@0.4.1",
  "assumptions": {"pc_threshold": 1e-4, "dv_per_cam_mps": 0.6},
  "na_reason": null }
```

### 12.2 Endpoint inventory

| Method | Path | Purpose | §ref |
|---|---|---|---|
| GET | `/health` | Liveness, versions, data freshness | — |
| POST | `/ingest` | Pull or refresh catalogue | M1 |
| GET | `/objects` | Search/filter catalogue | M1 |
| GET | `/objects/{norad_id}` | One object, full record | M1 |
| POST | `/screen` | Run conjunction screening over a window | M3 |
| GET | `/screening-runs/{run_id}` | Run metadata and counts | M3 |
| GET | `/conjunctions` | Query screened conjunctions | M3 |
| GET | `/graph` | Interaction graph for a run/shell | M4 |
| GET | `/graph/clusters` | Risk clusters with keystone objects | M4 |
| **POST** | **`/ledger/compute`** | **Compute the externality ledger** | **M5** |
| **GET** | **`/ledger`** | **Ranked ledger (the headline output)** | **M5** |
| **GET** | **`/ledger/{norad_id}`** | **One object's full ledger card** | **M5** |
| GET | `/ledger/{norad_id}/bearers` | Who paid, broken down | M5 |
| GET | `/ledger/by-operator` | Aggregated imposed vs borne per operator | M5 |
| POST | `/clusters/{cluster_id}/strategies` | Generate + evaluate strategies | M6,M7 |
| GET | `/strategies/{strategy_id}` | One strategy, full evaluation | M7 |
| POST | `/voi` | Value-of-information analysis | M8 |
| POST | `/validate` | Validate a proposed maneuver | M9 |
| GET | `/shells` | All shells with OCS, κ, hazard | M10 |
| GET | `/shells/{shell_id}` | One shell detail | M10 |
| **POST** | **`/deployment/evaluate`** | **Constellation deployment optimiser** | **M10** |
| POST | `/agent/analyse` | Run the planner on a cluster | M11 |
| GET | `/agent/trace/{trace_id}` | Full reasoning + tool-call trace | M11 |
| POST | `/chaos` | Inject a perturbation | M14 |
| POST | `/bench/run` | Baseline vs OCI benchmark | M15 |
| GET | `/provenance/{trace_id}` | Show the math for one number | §10.14 |
| GET | `/assumptions` | Current assumption set | §10.14 |

### 12.3 The three endpoints that matter

Everything else is plumbing. If you only get three right, get these right.

#### `GET /ledger` — the headline

```
GET /api/v1/ledger
  ?run_id=run_20260912T1030Z_a91f
  &sort=dv_imposed_mps        # cab | dv_imposed_mps | maneuvers_forced | operators_affected
  &order=desc
  &object_type=ROCKET_BODY    # optional filter
  &is_active=false            # optional filter
  &shell_id=12                # optional filter
  &pc_threshold=1e-4          # REQUIRED — burden is meaningless without it
  &limit=50&offset=0
```

```json
{
  "data": {
    "total": 8412,
    "window_days": 30.0,
    "pc_threshold": 1e-4,
    "entries": [
      {
        "norad_id": 27386,
        "object_name": "SL-16 R/B",
        "object_type": "ROCKET_BODY",
        "operator": "UNKNOWN-OPERATOR",
        "country": "CIS",
        "launch_date": "1987-05-19",
        "is_active": false,
        "is_maneuverable": false,
        "mean_alt_km": 846.2,
        "shell_id": 17,
        "conjunctions_generated": {"value": 214, "unit":"count","label":"COMPUTED","function":"ledger.count_conj@0.4.1"},
        "maneuvers_forced":       {"value": 31.0, "unit":"count","label":"MODELLED","function":"ledger.maneuvers_forced@0.4.1",
                                   "assumptions":{"pc_threshold":1e-4,"threshold_source":"IADC"}},
        "dv_imposed_mps":         {"value": 18.7, "unit":"m/s","label":"MODELLED","function":"ledger.dv_imposed@0.4.1"},
        "mission_days_imposed":   {"value": 47.0, "unit":"days","label":"MODELLED","function":"ledger.mission_days@0.4.1"},
        "operators_affected":     {"value": 9,   "unit":"count","label":"COMPUTED","function":"ledger.operators@0.4.1"},
        "maneuvers_performed":    {"value": 0.0, "unit":"count","label":"OBSERVED","function":"ledger.borne@0.4.1",
                                   "assumptions":{"reason":"object is non-maneuverable"}},
        "cab":                    {"value": 18.7,"unit":"m/s","label":"MODELLED","function":"ledger.cab@0.4.1"},
        "cab_normalised":         {"value": 0.0022,"unit":"m/s per sat-yr","label":"MODELLED","function":"ledger.cab_norm@0.4.1"},
        "decay_lifetime_yr_est":  {"value": 61.0,"unit":"yr","label":"MODELLED","function":"capacity.decay@0.3.0"},
        "projected_lifetime_dv":  {"value": 1140.0,"unit":"m/s","label":"MODELLED","function":"ledger.project@0.4.1",
                                   "assumptions":{"decay_model":"exponential_atmosphere","burden_decay":"linear_with_density"}},
        "implied_fee_usd_yr":     {"value": 71000.0,"unit":"USD/yr","label":"INDICATIVE","function":"ledger.fee@0.4.1",
                                   "assumptions":{"calibration":"Rao-Burgess-Kaffine-2020","note":"indicative only"}},
        "regime": "SUBSTITUTES",
        "kappa": {"value": 0.71,"unit":"ratio","label":"MODELLED","function":"graph.kappa@0.2.0"},
        "rank_by_dv_imposed": 1,
        "on_published_top50": false
      }
    ]
  },
  "assumptions": { }
}
```

The `on_published_top50` flag exists for one reason: **it is how you prove novelty acceptance
(§6.4) on stage.** If a high-burden object is not on the published most-concerning list, your
ranking has found something the hazard ranking misses.

#### `POST /clusters/{cluster_id}/strategies`

```json
{
  "horizon_h": 72,
  "include_kinds": ["HOLD","MANEUVER","WAIT","OBSERVE","COORDINATE"],
  "mc_samples": 100,
  "weights": {"safety":0.40,"future":0.20,"fuel":0.15,"mission":0.15,"network":0.10},
  "seed": 42
}
```

Response — note that the recommendation carries both the expected-value optimum and the
minimax-regret optimum, and that they may differ:

```json
{
  "data": {
    "cluster_id": "clu_27386_9f2a",
    "cluster": {"n_objects": 5, "n_edges": 12, "critical_conjunctions": 1,
                "keystone_id": 44713, "keystone_selected_by": "risk_weighted_degree",
                "max_pc_object_id": 51002,
                "keystone_differs_from_max_pc": true},
    "strategies": [
      {"strategy_id":"str_hold","kind":"HOLD","params":{},
       "pc_after":{"value":4.1e-4,...},"future_conjunctions":{"value":11,...},
       "dv_mps":{"value":0.0,...},"systemic_cost":{"value":0.94,...},
       "expected_cost":{"value":0.94,...},"p95_cost":{"value":1.00,...},
       "max_regret":{"value":0.61,...},"mc_safe_fraction":{"value":0.62,...},
       "validator_verdict":"APPROVED","proposed_by":"generator"},

      {"strategy_id":"str_wait_b","kind":"WAIT","params":{"wait_min":40,"then":"MANEUVER","target":44713},
       "pc_after":{"value":8.0e-6,...},"future_conjunctions":{"value":4,...},
       "dv_mps":{"value":0.52,...},"systemic_cost":{"value":0.21,...},
       "expected_cost":{"value":0.23,...},"p95_cost":{"value":0.44,...},
       "max_regret":{"value":0.09,...},"mc_safe_fraction":{"value":0.96,...},
       "validator_verdict":"APPROVED","proposed_by":"agent"}
    ],
    "recommendation": {
      "expected_value_optimum": "str_wait_b",
      "minimax_regret_optimum": "str_wait_b",
      "optima_agree": true,
      "note": "When optima disagree, surface both. A single-satellite operator and a 300-satellite operator should not choose the same strategy."
    },
    "rejected": [
      {"strategy_id":"str_agent_1","kind":"MANEUVER",
       "params":{"target":51002,"dv_vector_mps":[0.0,0.9,0.0],"t_burn":"2026-09-13T04:12:00Z"},
       "validator_verdict":"REJECTED",
       "validator_reason":"post-burn screening: creates conjunction with NORAD 48221 at 2026-09-14T22:41Z, miss 140 m (< 500 m floor)",
       "proposed_by":"agent"}
    ]
  }
}
```

**The `rejected` array is load-bearing.** It is the on-stage evidence that the validator does real
work and that the agent is not magically correct. If this array is always empty, the loop in §10.9
is theatre and you must widen the agent's action space until it fires on its own (§14.3).

#### `POST /deployment/evaluate`

```json
{
  "n_satellites": 5000,
  "target_alt_km": 550,
  "inclination_deg": 53.0,
  "sat_mass_kg": 300,
  "sat_area_m2": 12.0,
  "pmd_success_rate": 0.9,
  "mission_life_yr": 5,
  "alternatives_km": [500, 525, 550, 570, 600, 650],
  "horizon_yr": 15
}
```

```json
{
  "data": {
    "baseline": {
      "alt_km": 550,
      "ocs": {"value": 43,"unit":"score","label":"MODELLED"},
      "maneuver_burden_per_sat_yr": {"value": 5.2,...},
      "months_above_viability_threshold": {"value": 0.0,...},
      "burden_imposed_on_incumbents_mps_yr": {"value": 2140.0,...},
      "hazard_index": {"value": 0.31,...},
      "decay_lifetime_yr": {"value": 8.0,...},
      "persistence_after_pmd_failure_yr": {"value": 8.0,...}
    },
    "alternatives": [
      {"alt_km":500,"ocs":68,"maneuver_burden_per_sat_yr":3.1,"hazard_index":0.12,"decay_lifetime_yr":3.0},
      {"alt_km":570,"ocs":79,"maneuver_burden_per_sat_yr":2.1,"hazard_index":0.44,"decay_lifetime_yr":17.0},
      {"alt_km":650,"ocs":81,"maneuver_burden_per_sat_yr":1.7,"hazard_index":0.72,"decay_lifetime_yr":48.0}
    ],
    "two_peaks_finding": {
      "workload_optimal_alt_km": 650,
      "hazard_optimal_alt_km": 500,
      "optima_disagree": true,
      "explanation": "Workload falls monotonically with altitude across this range because traffic density peaks near 500-600 km. Hazard rises with altitude because natural decay lifetime grows from ~3 yr to ~48 yr, so any PMD failure persists far longer. The two currencies point in opposite directions; there is no single optimum without a stated weighting."
    },
    "recommendation": {
      "if_priority_is_operations": 650,
      "if_priority_is_environment": 500,
      "balanced_under_stated_weights": 570,
      "honest_note": "This is a trade-off, not an optimum. Report both."
    }
  }
}
```

**This response is the single most important JSON object in the project.** `optima_disagree: true`
is the non-obvious result from §2.5. Do not collapse it into one number to make the UI tidier.

### 12.4 Remaining endpoints, abbreviated

```
GET /health
  → {status, version, data_freshness: {catalogue_epoch_age_h, last_screening_run, n_objects}}

POST /ingest
  {source: "celestrak"|"spacetrack"|"synthetic", group: "active"|"debris"|..., force_refresh: bool}
  → 202 {job_id}    # never block on network I/O

GET /objects?q=&object_type=&operator=&shell_id=&is_active=&alt_min_km=&alt_max_km=&limit=&offset=

POST /screen
  {window_start, window_end, object_ids?: [int], shell_ids?: [int],
   screening_volume_m: 5000, coarse_step_min: 15, gate_k: 4, pc_method: "foster"}
  → 202 {job_id}    # then GET /jobs/{job_id} → {state, progress, run_id}

GET /conjunctions?run_id=&primary_id=&min_pc=&max_miss_m=&pair_class=&exclude_intra=true

GET /graph?run_id=&shell_id=&min_pc=
  → {nodes:[{norad_id,label,degree,risk_weighted_degree,betweenness,eigenvector}],
     edges:[{source,target,pc,miss_distance_m,rel_speed_mps,tca}],
     metrics:{n_nodes,n_edges,density,kappa}}

GET /graph/clusters?run_id=&min_size=2
  → {clusters:[{cluster_id,members,n_edges,keystone_id,keystone_selected_by,
                max_pc_object_id,keystone_differs_from_max_pc,total_pc}]}

POST /voi
  {conj_id, wait_options_min:[0,20,40,60], cov_shrink_model:"kelvins_fitted"}
  → {options:[{wait_min, expected_sigma_reduction, expected_pc, expected_dv_mps,
               risk_of_delay, voi_net}], recommended_wait_min}

POST /validate
  {target_id, dv_vector_mps:[r,t,n], t_burn, constraints_override?}
  → {verdict:"APPROVED"|"REJECTED", checks:[{name,passed,detail}], reason}

GET /shells → [{shell_id,alt_low_km,alt_high_km,n_objects,n_active,n_dead,spatial_density,
                maneuver_burden_per_sat_yr,kappa,regime,ocs,hazard_index,decay_lifetime_yr}]

POST /agent/analyse
  {cluster_id, max_tool_calls: 25, temperature: 0, seed: 42}
  → {trace_id, recommendation, explanation, tool_calls:[...], rejections:[...]}

POST /chaos
  {run_id, injection: "NEW_OBJECT"|"COVARIANCE_SPIKE"|"THIRD_PARTY_MANEUVER"|
                      "TRACKING_GAP"|"REFUSE_COORDINATION"|"UPLINK_DELAY"|"CONSTELLATION_INSERT",
   params: {...}, seed: 42}
  → {new_run_id, invalidated:[strategy_id], invalidation_reason,
     new_recommendation, diff:{was, now, why}}

POST /bench/run
  {scenario_id, baselines:["pairwise_max_pc"], seed:42}
  → {scenario_id, baseline:{...}, oci:{...}, deltas:{...}, verdict:"OCI_BETTER"|"NEUTRAL"|"OCI_WORSE"}

GET /provenance/{trace_id}
  → {value, unit, label, function, function_version, inputs, assumptions, created_at}
```

### 12.5 Error contract

```json
{
  "type": "/errors/insufficient-covariance",
  "title": "Cannot compute Pc",
  "status": 422,
  "detail": "No covariance available for NORAD 51002 and covariance_source is set to 'none'. Pc is undefined. Use geometry-only screening or set covariance_source='assumed'.",
  "instance": "/api/v1/conjunctions?conj_id=cj_a91f"
}
```

**Never return `pc: 0.0` when covariance is missing.** Return `null` with an `na_reason`. A silent
zero is how a project lies by accident, and a judge who spots one will discount every other number
you show.

Error types to implement: `insufficient-covariance`, `run-not-found`, `object-not-found`,
`window-too-large`, `screening-timeout`, `validator-infeasible`, `agent-tool-limit-exceeded`,
`threshold-not-declared`.

### 12.6 Performance budgets

Budgets, not aspirations. Exceed one and the demo suffers visibly.

| Endpoint | Target | Hard ceiling |
|---|---|---|
| `GET /ledger` (cached run) | < 200 ms | 1 s |
| `GET /ledger/{id}` | < 100 ms | 500 ms |
| `POST /screen` (2,000 objects, 72 h) | < 45 s | 3 min |
| `POST /screen` (8,000 objects, 72 h) | < 4 min | 10 min |
| `POST /ledger/compute` (2,000 objects) | < 60 s | 5 min |
| `POST /clusters/../strategies` (5 strategies, 100 MC) | < 8 s | 20 s |
| `POST /chaos` full replan | **< 10 s** | 15 s |
| `POST /agent/analyse` | < 30 s | 60 s |

**Chaos mode is the one with a hard behavioural requirement: nobody watches a 30-second spinner on
stage.** Pre-compute and cache the base run before the demo; chaos only re-runs the affected
neighbourhood, never the full catalogue.

---

## 13. FRONTEND SPECIFICATION

### 13.1 Design principles

1. **Professional, not gaming.** Dark neutral background, one accent colour, monospace for numbers.
   Aerospace operations software, not a sci-fi HUD.
2. **Numbers are clickable.** Every displayed figure opens its provenance panel.
3. **Assumptions always visible.** A persistent strip, never a hidden modal.
4. **No fake motion.** No orbiting dots for decoration. Motion means data changed.
5. **Labels shown.** `MODELLED` and `INDICATIVE` figures are visually marked, always.
6. **Degrade honestly.** A missing value renders as `—` with a tooltip giving `na_reason`, never as 0.

### 13.2 Screen inventory

| # | Screen | Route | Purpose | Priority |
|---|---|---|---|---|
| S1 | **Ledger** | `/ledger` | Ranked externality table — the headline | **P0** |
| S2 | **Object card** | `/object/:id` | One object's full bill, with bearers | **P0** |
| S3 | **Event console** | `/cluster/:id` | Cluster, strategies, recommendation, validator | **P0** |
| S4 | **Encounter geometry** | component | 2D B-plane view of a conjunction | **P1** |
| S5 | **Shell map** | `/shells` | OCS, κ, hazard by altitude — the two peaks | **P1** |
| S6 | **Deployment planner** | `/deploy` | Constellation what-if | **P1** |
| S7 | **Agent trace** | drawer | Reasoning + tool calls + rejections | **P1** |
| S8 | **Benchmark** | `/bench` | Baseline vs OCI | **P1** |
| S9 | **Provenance panel** | modal | Show the math | **P0** |
| S10 | **Globe** | `/globe` | 3D orbital view | **P3 — cut freely** |

P0 = demo fails without it. P3 = build only if Phase 1–9 are done with hours to spare.

### 13.3 S1 — Ledger (the screen that wins)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ORBITAL CAPACITY INTELLIGENCE                    run_20260912T1030Z  ● fresh │
├──────────────────────────────────────────────────────────────────────────────┤
│ ASSUMPTIONS  cov: kelvins_fitted │ Pc thr: 1e-4 (IADC) │ HBR: 5.0 m MODELLED │
│              window: 30 d │ shell: 800-900 km │ intra-constellation: excluded│
├──────────────────────────────────────────────────────────────────────────────┤
│ WHO IS MAKING WHOM BURN FUEL          sort ▾ Δv imposed    [CSV] [JSON]      │
│                                                                              │
│ #  OBJECT              TYPE     ALT    CONJ  MNVR   Δv IMPOSED  OPS  FEE/yr  │
│ ─────────────────────────────────────────────────────────────────────────────│
│ 1  SL-16 R/B (27386)   R/B      846km   214    31     18.7 m/s    9  $71k  ⚑ │
│ 2  COSMOS 1408 DEB     DEBRIS   478km   198    27     16.1 m/s   14  $58k    │
│ 3  DEFUNCT PAYLOAD     PAYLOAD  551km   176    24     14.3 m/s   11  $52k  ⚑ │
│ ...                                                                          │
│ ─────────────────────────────────────────────────────────────────────────────│
│ ⚑ = not on the published top-50 most-concerning list                         │
│                                                                              │
│ TOTALS  8,412 objects │ Δv imposed by DEAD objects: 71% of all burden        │
└──────────────────────────────────────────────────────────────────────────────┘
```

Requirements:

- Default sort: `dv_imposed_mps` descending. This is the ranking nobody else publishes.
- The `⚑` flag renders when `on_published_top50 === false` and rank ≤ 20. **This is your novelty
  proof, on screen, no narration needed.**
- The footer share-of-burden-from-dead-objects figure is the sentence that makes the room go quiet.
- Toggle: **imposed** ↔ **borne** ↔ **net**. Flipping to "borne" and seeing dead objects drop to
  zero makes the asymmetry obvious instantly.
- Filters: object type, active/dead, shell, operator, country.
- Every cell clickable → S9 provenance.
- CSV/JSON export embeds the assumption block.

### 13.4 S2 — Object card

The screen the demo opens on. One object, its entire bill.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← NORAD 27386 — SL-16 R/B                                    ROCKET BODY     │
│   Launched 1987-05-19 · CIS · 846 km · 71.0° · DEAD · NON-MANEUVERABLE       │
├──────────────────────────────────────────────────────────────────────────────┤
│ IMPOSED ON OTHERS (30 d, Pc > 1e-4)      │ BORNE BY ITSELF                   │
│   Close approaches ............. 214     │   Maneuvers ............... 0     │
│   Maneuvers forced ......... 31 (M)      │   Δv spent ............. 0 m/s    │
│   Δv extracted ......... 18.7 m/s (M)    │   ("cannot manoeuvre")            │
│   Mission-days consumed ..... 47 (M)     │                                   │
│   Operators affected ............ 9      │ NET EXTERNALITY  +18.7 m/s /month │
├──────────────────────────────────────────────────────────────────────────────┤
│ PROJECTION                                │ REGIME (this shell)              │
│   Est. decay lifetime ..... 61 yr (M)     │   κ = 0.71  SUBSTITUTES          │
│   Projected lifetime Δv .. 1,140 m/s (M)  │   one manoeuvre here triggers    │
│   Indicative fee ....... $71k /yr (IND)   │   0.71 further manoeuvres        │
├──────────────────────────────────────────────────────────────────────────────┤
│ WHO PAYS  (top bearers)                                                      │
│   OPERATOR-A   11 mnvr  6.6 m/s  ████████████                                │
│   OPERATOR-B    7 mnvr  4.2 m/s  ███████                                     │
│   OPERATOR-C    5 mnvr  3.0 m/s  █████                                       │
│   ... 6 more operators                                                       │
└──────────────────────────────────────────────────────────────────────────────┘
  (M) = MODELLED   (IND) = INDICATIVE   click any number to show the math
```

The `BORNE BY ITSELF = 0` column with the parenthetical "cannot manoeuvre" is the whole thesis in
one visual. Do not remove it to save space.

### 13.5 S4 — Encounter geometry (replaces the globe)

**Why this instead of a 3D Earth:** a judge's comprehension is gated on one image, and four minutes
is not enough time to build a mental model from tables. But a globe costs a full day, demos nothing
the thesis needs, and shows *where* rather than *why*. A 2D B-plane view costs a quarter of the
time, explains why a manoeuvre helps, and signals that you have read the literature.

```
        cross-track (n)
              │
         ╭────┼────╮          ┌─ combined 1σ error ellipse
        │     │     │         │  (from CDM covariance)
        │  ·  │     │         │
   ─────┼─────●─────┼───── in-track (t)
        │     │  ╲  │            ● = secondary at TCA
        │     │   ╲ │            ○ = primary at origin
         ╰────┼────╯             ╲ = miss vector
              │                   · = hard-body circle (HBR)
    miss 140 m │ rel speed 14.2 km/s │ Pc 4.1e-4 │ σ_t 820 m (Kelvins-fitted)
```

Requirements:

- Combined covariance projected into the encounter plane, drawn at 1σ/2σ/3σ.
- Hard-body circle at HBR, visibly labelled `MODELLED`.
- Overlay post-manoeuvre geometry as a ghost, so the effect of the burn is visible.
- **Dilution warning banner** when increasing σ would *lower* Pc — the trap in §7.2. Flagging it
  signals real domain knowledge.
- A time slider showing the covariance ellipse *shrinking* as TCA approaches. This is the VoI
  feature made visible, and it is only honest because the shrink comes from real CDM data (§8.3).

### 13.6 S3 — Event console

Three panes, left to right: cluster graph → strategy table → recommendation and validator.

```
┌─────────────────┬────────────────────────────────┬─────────────────────────┐
│ CLUSTER clu_9f2a│ STRATEGIES                     │ RECOMMENDATION          │
│                 │                                │                         │
│      B          │ STRAT    Pc     FUT  Δv   REGRET│ WAIT 40 min, then       │
│    ╱   ╲        │ HOLD    4.1e-4   11  0.00  0.61 │ MANEUVER SAT-B          │
│   A     C       │ MOVE A  1.2e-6    8  1.40  0.34 │                         │
│         │       │ MOVE B  9.0e-6    6  1.10  0.28 │ Δv 0.52 m/s             │
│         D       │ COORD   2.0e-6    3  0.80  0.14 │ = 11 days of mission    │
│         │       │ ▶WAIT+B 8.0e-6    4  0.52  0.09 │   life preserved        │
│         E       │                                │                         │
│                 │ EV optimum    : WAIT+B         │ VALIDATOR               │
│ keystone: B     │ Regret optimum: WAIT+B         │  ✓ thrust limit         │
│ max-Pc : A↔C    │ → agree                        │  ✓ slew feasible        │
│ ⚠ differ        │                                │  ✓ uplink window        │
│                 │ REJECTED (1)                   │  ✓ post-burn screening  │
│ κ=0.71 SUBST.   │  agent MOVE A 0.9 m/s →        │  ✓ eclipse/power        │
│                 │  creates 140 m conj w/ 48221   │  APPROVED               │
└─────────────────┴────────────────────────────────┴─────────────────────────┘
```

The `⚠ differ` badge — keystone object is not the max-Pc object — is the moment the graph earns its
place. If it never fires on your data, say so rather than manufacturing it.

### 13.7 S5 — Shell map (the two peaks)

A single chart with two y-axes over altitude 200–1,000 km:

- **Maneuver burden per satellite-year** (left axis) — peaks around 500–600 km
- **Hazard index**, persistence-weighted (right axis) — rises with altitude, peaks near 850 km
- Horizontal reference line at the **viability threshold** (10 manoeuvres/month → 120/sat-yr)
- Shaded band marking where the two curves' optima disagree

Caption, fixed text:

> The altitude that costs you most operationally is not the altitude that harms the environment
> most. There is no single optimum without a stated weighting.

This chart is the intellectual core of the deployment story. One chart, two curves, opposite
gradients.

### 13.8 S9 — Provenance panel

```
┌────────────────────────────────────────────────────┐
│ Δv imposed = 18.7 m/s                    MODELLED  │
├────────────────────────────────────────────────────┤
│ function   ledger.dv_imposed@0.4.1                 │
│ formula    Σ over forced manoeuvres of Δv_required │
│ inputs     n_conjunctions_above_threshold = 31     │
│            mean_dv_per_cam_mps = 0.603             │
│            attribution_rule = R1 (dead→active)     │
│ assumes    pc_threshold = 1e-4 (IADC guidance)     │
│            covariance_source = kelvins_fitted      │
│            hard_body_radius_m = 5.0 (MODELLED)     │
│            intra-constellation excluded            │
│ caveat     Δv per CAM is modelled from required    │
│            miss-distance clearance, not observed.  │
│            Actual operator burns may differ.       │
├────────────────────────────────────────────────────┤
│ [view the 31 contributing conjunctions]            │
└────────────────────────────────────────────────────┘
```

Implementation: `GET /provenance/{trace_id}` where `trace_id` rides on every `Traced` value.

### 13.9 Component inventory

```
web/src/components/
  AssumptionStrip.tsx      persistent, always visible
  TracedNumber.tsx         renders value + label badge + click → provenance
  LedgerTable.tsx          sortable, filterable, virtualised
  ObjectCard.tsx           S2
  BurdenFlowBars.tsx       who pays
  ClusterGraph.tsx         force-directed, risk-weighted edges
  EncounterPlane.tsx       S4, plain SVG — no 3D library
  StrategyTable.tsx        incl. regret column
  ValidatorChecks.tsx      pass/fail list with reasons
  ShellChart.tsx           S5 two-peaks, Recharts
  DeploymentForm.tsx       S6 inputs
  DeploymentResult.tsx     S6 incl. optima_disagree banner
  AgentTrace.tsx           S7 tool calls + rejections
  BenchTable.tsx           S8
  ProvenancePanel.tsx      S9
  ChaosButton.tsx          the judge's button
  NaValue.tsx              renders "—" + na_reason tooltip
```

### 13.10 State and error handling

- Server state via TanStack Query; no global store. Screens are read-mostly.
- Long jobs: `202 job_id` → poll with backoff → progress bar with the actual stage name
  (`screening pairs 41,203 / 2,001,000`), never an indeterminate spinner.
- Chaos mode diff: animate only the rows that changed. Everything else holds still.
- On 422 `insufficient-covariance`, render the affected column as `—` with the reason. **Do not
  hide the row.** Showing what you could not compute is more credible than showing only what you
  could.

### 13.11 The one rule for the frontend

> If a pixel does not carry a number that came from the backend, or a label explaining one, delete it.

---

## 14. AGENT / LLM SPECIFICATION

### 14.1 One agent, not four

v1.0 specified four agents (Environment, Simulation, Optimisation, Validation). **Collapse to one
planner plus three deterministic services.** The reasoning:

**The case for four agents:** judges outside aerospace respond to it; separation of concerns is
real; it gives the explanation layer a natural home.

**The case against, which wins:** four LLM agents in front of a deterministic pipeline buys latency,
nondeterminism and demo risk in exchange for zero computational capability. Worse, it makes the
"AI can be wrong, validator rejects it" loop *structurally impossible to fire*: if the optimisation
agent only picks from an enumerated list of pre-generated feasible strategies, the validator can
never reject anything. You would ship a rejection loop that never triggers, and then be tempted to
hardcode a rejection for the demo. A judge who notices that is fatal, not cosmetic.

**Resolution:** one planner with a *free-form* action space (§14.3), so the validator has genuine
work and rejection happens unscripted. And say it on stage: *"we deliberately used one agent,
because agent count is not a capability."* Technical judges exhale.

```
Planner (LLM)  ──tool calls──▶  M3 screening / M4 graph / M5 ledger / M6 sim
                               M7 optimiser / M8 VoI / M9 validator / M10 capacity
     ▲                                          │
     └──────────── results, rejections ─────────┘
```

### 14.2 Tool surface

Exactly these. Adding tools makes the planner worse, not better.

```python
TOOLS = [
  # OBSERVE — what is happening
  {"name": "get_cluster",
   "desc": "Return a risk cluster: members, edges, keystone, max-Pc object, kappa.",
   "params": {"cluster_id": "str"},
   "returns": "ClusterSummary"},

  {"name": "get_ledger_entry",
   "desc": "Return one object's externality ledger entry.",
   "params": {"norad_id": "int"},
   "returns": "LedgerEntry"},

  {"name": "get_conjunction",
   "desc": "Return one conjunction with geometry, covariance source and Pc.",
   "params": {"conj_id": "str"},
   "returns": "Conjunction"},

  # SIMULATE — what could happen
  {"name": "simulate_action",
   "desc": "Apply a hypothetical action to the state and propagate forward. Returns the resulting "
           "conjunction set, Pc values, and systemic cost. Does NOT validate feasibility.",
   "params": {"target_id":"int","action":"HOLD|MANEUVER|WAIT|OBSERVE|COORDINATE",
              "dv_vector_mps":"[float,float,float]|null","t_burn":"iso8601|null",
              "wait_min":"float|null","horizon_h":"float"},
   "returns": "SimulationResult"},

  {"name": "run_uncertainty_analysis",
   "desc": "Monte Carlo over the covariance for a given action. Returns expected cost, "
           "95th-percentile cost, max regret, and safe fraction.",
   "params": {"strategy_id":"str","n_samples":"int"},
   "returns": "UncertaintyResult"},

  {"name": "compute_voi",
   "desc": "Value of information: expected cost reduction from delaying to acquire better tracking, "
           "net of the risk of delay.",
   "params": {"conj_id":"str","wait_options_min":"[float]"},
   "returns": "VoIResult"},

  # DECIDE — what should we do
  {"name": "rank_strategies",
   "desc": "Score a set of simulated strategies under the configured objective weights. Returns "
           "both the expected-value optimum and the minimax-regret optimum.",
   "params": {"strategy_ids":"[str]","weights":"dict|null"},
   "returns": "RankingResult"},

  # VALIDATE — is it flyable
  {"name": "validate_action",
   "desc": "Deterministic feasibility and safety check on a concrete proposed burn. May REJECT "
           "with a specific reason. Rejection is normal; incorporate the reason and re-propose.",
   "params": {"target_id":"int","dv_vector_mps":"[float,float,float]","t_burn":"iso8601"},
   "returns": "ValidationResult"},

  # CAPACITY — the wider question
  {"name": "evaluate_deployment",
   "desc": "Evaluate a proposed constellation deployment across altitudes. Returns burden, hazard, "
           "OCS and whether the two optima disagree.",
   "params": {"n_satellites":"int","target_alt_km":"float","inclination_deg":"float",
              "alternatives_km":"[float]"},
   "returns": "DeploymentResult"}
]
```

### 14.3 The action space must be free-form

This is the design decision that makes §10.9 and the `rejected` array real.

**Wrong:** the planner selects from `["HOLD","MOVE_A","MOVE_B","COORDINATE"]`. Everything is
pre-validated; the validator is decoration.

**Right:** the planner proposes a concrete burn — target object, Δv vector in the RTN frame, burn
epoch. Now the validator does genuine work:

| Check | Why the agent will fail it unprompted |
|---|---|
| Thrust / Δv magnitude limit | The LLM has no propulsion model and will over-ask |
| Slew/attitude feasibility before `t_burn` | It will pick a burn time too soon after the last attitude state |
| Uplink window availability | It will pick a burn epoch with no ground contact ahead of it |
| Eclipse / power state | It will burn in eclipse on a solar-constrained platform |
| Station-keeping box violation | Its burn will drift the object out of its operational box |
| **Post-burn re-screening** | Its burn will create a new close approach it did not anticipate |
| Minimum miss-distance floor (500 m) | Its burn will clear Pc but leave an unacceptably small geometric miss |

Rejection then happens on its own. That unscripted thirty seconds — propose, reject with a concrete
physical reason, re-propose, approve — is more impressive than an AI that is magically right, and it
costs *less* code than orchestrating four agents.

### 14.4 System prompt for the planner

```
You are the planning component of Orbital Capacity Intelligence, a decision-support system for
space traffic operations. You reason about orbital conjunctions and recommend actions.

ABSOLUTE RULES

1. You do not compute physics. You never estimate, guess or assert a numerical value for a miss
   distance, collision probability, delta-v, covariance, orbital element, decay lifetime, or cost.
   Every number in your output must have come from a tool result in this conversation. If you need
   a number you do not have, call a tool.

2. If you state a number that did not come from a tool result, you have failed the task.

3. The validator is authoritative. If validate_action returns REJECTED, the action is not available.
   Read the reason, incorporate it, and propose a different action. Do not argue with the validator
   and do not re-propose a rejected action unchanged.

4. Rejection is expected and normal. It is evidence the system is working, not a failure.

5. Your action space includes HOLD, MANEUVER, WAIT, OBSERVE and COORDINATE. WAIT and OBSERVE are
   first-class actions, not fallbacks. When uncertainty is high and time to TCA is long, waiting to
   acquire better tracking data frequently dominates manoeuvring now. Always call compute_voi before
   recommending an immediate manoeuvre on a high-uncertainty event.

6. When you propose a MANEUVER, propose a concrete burn: target object, delta-v vector in the RTN
   frame, and burn epoch. Do not propose "a small manoeuvre".

7. Distinguish the keystone object from the highest-Pc object. The object in the worst single
   conjunction is often not the object whose manoeuvre helps most. Check get_cluster for both.

8. Report the expected-value optimum and the minimax-regret optimum separately when they differ.
   A single-satellite operator and a three-hundred-satellite operator should not necessarily choose
   the same strategy.

9. Your output is decision support for a human operator. It is never a flight command. Never imply
   that the system will execute anything.

10. Label uncertainty honestly. If a value came from a tool with label MODELLED or INDICATIVE, say
    so when you use it in your reasoning.

PROCEDURE

  1. get_cluster — understand the structure. Note keystone vs max-Pc.
  2. get_conjunction on the critical edge — check the covariance source.
  3. compute_voi — is waiting better than acting?
  4. simulate_action for each candidate, including HOLD and WAIT.
  5. run_uncertainty_analysis on the leading candidates.
  6. rank_strategies.
  7. validate_action on your preferred concrete burn. If REJECTED, return to step 4 with the reason.
  8. Explain the recommendation using only computed values.

OUTPUT FORMAT

  RECOMMENDATION: <action, concretely stated>
  WHY:
    1. <claim> [source: tool_name]
    2. ...
  TRADE-OFFS: <what this costs>
  CONFIDENCE BASIS: <which tool produced the robustness figure, and what it means —
                     it is the fraction of simulated scenarios remaining safe under the stated
                     covariance model, NOT a prediction accuracy>
  ASSUMPTIONS THAT MATTER: <the two or three that would change the answer if wrong>
```

### 14.5 Configuration

```
temperature        0.0          determinism matters more than creativity here
seed               fixed        reproducible demo
max_tool_calls     25           then hard stop with agent-tool-limit-exceeded
timeout            60 s
retry on tool err  1, then surface the error in the trace rather than hiding it
```

### 14.6 Number-fabrication guard (mandatory)

Do not trust rule 1. Enforce it.

```python
def check_no_fabricated_numbers(agent_output: str, tool_results: list[dict]) -> list[str]:
    """Extract every numeric literal from the agent's prose and assert it appears in some
    tool result (within rounding tolerance). Return violations."""
    permitted = collect_numeric_values(tool_results)      # flatten all tool results
    violations = []
    for n in extract_numbers(agent_output):
        if not any(abs(n - p) <= max(1e-9, 0.01 * abs(p)) for p in permitted):
            violations.append(n)
    return violations
```

If violations is non-empty: **do not display the output.** Regenerate once, then fall back to the
deterministic template explanation (§10.14). Log the incident.

Test: `test_agent_cannot_fabricate_numbers` — feed the planner a cluster with tool results
deliberately lacking a Δv figure and assert it either calls the tool or reports the value as
unavailable, and never invents one.

### 14.7 What the agent is genuinely for

Be honest internally about this, because it shapes how much to invest.

The agent adds real value in four places:
1. **Sequencing** — deciding to call `compute_voi` before recommending a burn.
2. **Interpreting rejections** — turning "creates 140 m conjunction with 48221" into a different
   proposal rather than a retry.
3. **Explanation** — assembling computed values into prose a human can act on.
4. **Replanning** after chaos injection.

It adds *no* value in optimisation, screening, propagation or validation. Anywhere you are tempted
to let it help with those, you are introducing nondeterminism for nothing.

---

## 15. BENCHMARK HARNESS (M15)

### 15.1 Why this is infrastructure, not a deliverable

§38 of v1.0 had this as a final flourish. That is backwards. The benchmark is:

1. **Your scoring function during development.** Without it you cannot tell whether a change helped.
2. **Your novelty proof.** It is the only thing that demonstrates the systemic approach beats the
   local one.
3. **Your early-warning system.** If the result comes out neutral, you need to know on day one so
   you can improve the algorithm, narrow the problem, or find a different differentiator — not at
   hour forty with nothing to show.

**Build it at step 3 of the build order.** Run it continuously thereafter.

### 15.2 The baselines

| ID | Baseline | Rule |
|---|---|---|
| `B1` | **Pairwise max-Pc** | Find the highest-Pc conjunction. Manoeuvre the primary. Re-screen once. Done. This is the honest representation of standard practice. |
| `B2` | Pairwise + post-manoeuvre screening | B1 but iterate until no conjunction exceeds threshold. Closer to real operational practice; a harder baseline. **Include it — beating only B1 is a weak claim.** |
| `B3` | Always-manoeuvre | Manoeuvre on every alert above threshold. Upper bound on Δv expenditure. |
| `B4` | Never-manoeuvre | Lower bound on Δv, upper bound on risk. Reference floor. |

**Be intellectually honest about B2.** Post-manoeuvre screening is already standard operational
practice — every real CA workflow screens the post-burn trajectory against the catalogue before
committing. If OCI only beats B1, you have beaten a strawman. Your claim must be: OCI beats B2.

### 15.3 Metrics

For each scenario, both systems report:

```
collision_risk_final        max Pc across the cluster after the decision
future_conjunctions_72h     count above threshold in the horizon
total_dv_mps                summed across ALL objects, not just the primary
mission_impact              modelled disruption score
systemic_cost               §11.12, the weighted scalar
p95_cost                    95th-percentile under Monte Carlo
max_regret                  §11.12
n_maneuvers                 count of burns commanded
n_operators_burdened        how many distinct operators paid
runtime_s                   wall clock
```

### 15.4 Scenario set

Minimum eight scenarios, fixed seeds, checked into the repo as JSON.

| ID | Scenario | What it tests |
|---|---|---|
| `S1` | Simple two-object conjunction | Sanity — OCI should roughly *tie* B1 here, not win. A win would be suspicious. |
| `S2` | Five-object cluster, keystone ≠ max-Pc | The core graph claim |
| `S3` | High-uncertainty event, long time to TCA | VoI — WAIT should dominate |
| `S4` | Two active satellites, both maneuverable | Coordination; who should move |
| `S5` | Dead-object-dominated cluster | Ledger attribution; avoidance cannot fix it |
| `S6` | Post-COSMOS-1408-style debris squall | Load and regime shift toward complements |
| `S7` | Chain case: naive burn creates secondary | B1 fails, B2 partially recovers, OCI should avoid it upfront |
| `S8` | Dense shell, κ > 1 | Complements regime; removal beats avoidance |

### 15.5 Output format

```
BENCHMARK  scenario S2  seed 42  Pc threshold 1e-4  cov kelvins_fitted

                              B1        B2       OCI     Δ vs B2
collision risk final       1.2e-6    9.0e-7   8.0e-6      worse
future conjunctions 72h        11         7        4       -43%
total Δv (all objects)    1.40 m/s  1.85 m/s  0.52 m/s     -72%
manoeuvres commanded            1         2        1         -1
operators burdened              1         2        1         -1
mission impact               0.31      0.38     0.11       -71%
systemic cost                0.62      0.54     0.21       -61%
p95 cost                     0.88      0.71     0.44       -38%
max regret                   0.34      0.29     0.09       -69%
runtime                      0.2 s     1.1 s    6.8 s     slower

VERDICT: OCI_BETTER on systemic cost, Δv, future conjunctions, regret.
         OCI accepts a HIGHER residual Pc (8.0e-6 vs 9.0e-7) in exchange.
         Both remain below the declared 1e-4 threshold.
```

**Report the row where you lose.** OCI accepting a higher residual Pc while staying under threshold
is a legitimate trade, and stating it plainly is far stronger than hiding it. A judge who finds a
hidden loss discounts everything.

### 15.6 The failure clause

From v1.0 §39, kept verbatim in spirit because it is the most credible thing in the document:

> If we cannot demonstrate that the systemic approach produces a measurable improvement over a
> simple local baseline, we do not pretend it is innovative. We either improve the algorithm,
> narrow the problem, or find a better differentiator. Evidence over marketing.

Put this on a slide. Teams that show a negative result and explain it are read as researchers.

---

## 16. BUILD ORDER, TIME BUDGET, MVP CUT LINES

### 16.1 Why v1.0's build order was wrong

v1.0 §30 was a dependency ordering, not a hackathon plan. It put the benchmark at position zero
(absent), visualisation at phase 12, explanation at 13, chaos at 14. If you stall at phase 8 — and
you will, because conjunction screening over a real catalogue is harder than it looks — **you have
nothing to show.** A partially built pipeline scores zero on demo.

### 16.2 The two structural fixes

**Fix 1 — vertical slice first.** Hour zero to hour ten: end-to-end on a hardcoded 6-object
synthetic scenario with declared covariance. Detect → graph → ledger → 3 strategies → simulate →
compare → validate → print explanation. Ugly, terminal output, fake data. Then widen each stage to
real data. After hour ten you always have something demoable. v1.0's plan had exactly one demoable
artifact, at the very end, if nothing went wrong.

**Fix 2 — benchmark at step 3.** Not last. See §15.1.

### 16.3 The build order

| # | Block | Content | Est. | Cumulative | Demoable after? |
|---|---|---|---|---|---|
| 0 | **Vertical slice** | Synthetic 6 objects, hardcoded covariance, terminal output, full pipeline | 8–10 h | 10 h | **Yes — terminal** |
| 1 | **Real data + propagation + screening** | M1, M2, M3 with the filter chain. Hardest unknown; do it early. | 8–10 h | 20 h | Yes |
| 2 | **Graph + ledger** | M4, M5. Risk-weighted vertex selection. One shell. | 6–8 h | 28 h | **Yes — the headline** |
| 3 | **Benchmark harness** | M15, baselines B1 + B2, scenarios S1, S2, S5 | 3–4 h | 32 h | Yes |
| 4 | **Strategies incl. WAIT/OBSERVE** | M6, M7, M8. Kelvins covariance wired in. | 8–10 h | 42 h | Yes |
| 5 | **Monte Carlo + regret** | Extend M7. Cheap, high depth return. | 3 h | 45 h | Yes |
| 6 | **Free-form planner + real validator** | M9, M11. Makes the rejection loop honest. | 5–6 h | 51 h | Yes |
| 7 | **Ledger UI + object card** | S1, S2, S9, AssumptionStrip | 8 h | 59 h | **Yes — the demo** |
| 8 | **Event console + encounter plane** | S3, S4 | 6 h | 65 h | Yes |
| 9 | **Explanation + audit trail** | §10.14, provenance panel | 3 h | 68 h | Yes |
| 10 | **Capacity + deployment** | M10, S5, S6. The company moment. | 5–6 h | 74 h | Yes |
| 11 | **Chaos mode** | M14. Nearly free if M6 is pure. | 2–3 h | 77 h | Yes |
| 12 | **Globe** | S10. Only if everything above is done. | 6 h | 83 h | — |

**Buffer: add 20%.** If your total is 77 h, plan 92 h. You will use it.

### 16.4 The purity requirement for chaos mode

Chaos mode is near-free **if and only if** the pipeline is a pure function of state:

```python
def recommend(state: OrbitalState, config: Config) -> Recommendation: ...
def chaos(state: OrbitalState, injection: Injection) -> OrbitalState: ...
# then: recommend(chaos(state, inj), config)
```

If M6 mutates hidden state, module-level caches, or a database as a side effect, chaos becomes a
two-day retrofit and you will cut it. **Architect for purity on day one**; it costs nothing then and
buys your best judge-interaction feature later.

### 16.5 MVP cut lines

If time collapses, cut in this order — later items first.

```
CUT 1st   Globe (S10)
CUT 2nd   Deployment optimiser alternatives sweep (keep the single-altitude evaluation)
CUT 3rd   Chaos mode
CUT 4th   Agent planner (fall back to deterministic strategy generation + template explanation)
CUT 5th   Coordination strategy kind
CUT 6th   Monte Carlo (fall back to point estimates, clearly labelled)
──────────────────────────────────────────────────────────────────────────
NEVER CUT Ledger (M5) + object card (S2)     — this is the project
NEVER CUT Screening filter chain (M3)        — everything depends on it
NEVER CUT Benchmark (M15)                    — without it there is no claim
NEVER CUT Assumption strip + labels          — without it there is no credibility
NEVER CUT WAIT/OBSERVE as an action          — your best untaken idea
```

### 16.6 The irreducible MVP

If everything goes wrong, this is what must work:

```
Public TLE/OMM for ONE shell (2,000 objects)
        ↓
Filtered conjunction screening, 7-day window
        ↓
Interaction graph
        ↓
EXTERNALITY LEDGER — ranked, with the dead/alive asymmetry visible
        ↓
One cluster → 4 strategies including WAIT → simulate → compare
        ↓
Validator approves or rejects, with a reason
        ↓
Explanation from computed values, every number traceable
        ↓
Benchmark table vs B2 on one scenario
```

That is a complete, honest, novel contribution. Everything above it is upside.

### 16.7 Anti-overengineering rules

```
NO Kubernetes            NO microservices        NO message queues
NO graph database        NO vector database      NO multi-agent framework
NO Redis / Celery        NO auth system          NO Docker Compose with 6 services
NO Cesium/Three in MVP   NO ORM migrations tool  NO CI pipeline
```

SQLite in a file. FastAPI in one process. React from Vite. Every item on that list has killed a
hackathon demo, and none of them makes the science better.

> A small scientifically defensible system beats a giant fake system.

---

## 17. TESTING AND VALIDATION PLAN

### 17.1 Test pyramid

```
        ┌──────────────────────┐
        │  3 demo rehearsals   │  full run, timed, on the demo machine
        ├──────────────────────┤
        │  8 benchmark scen.   │  §15.4, regression-gated
        ├──────────────────────┤
        │  ~15 integration     │  endpoint → DB → computation → response
        ├──────────────────────┤
        │  ~60 unit tests      │  physics, math, attribution, labels
        └──────────────────────┘
```

### 17.2 Physics validation — non-negotiable

You cannot claim physics-based anything without these.

| Test | Method | Tolerance |
|---|---|---|
| `test_sgp4_against_reference` | Propagate the standard SGP4 verification TLEs and compare to published expected state vectors | matches the reference implementation's published tolerance |
| `test_sgp4_vs_independent_lib` | Same TLE via `sgp4` and via `skyfield`; compare positions | < 1 m disagreement |
| `test_energy_after_impulsive_dv` | Apply Δv, recompute specific orbital energy, check against vis-viva | < 1e-9 relative |
| `test_sma_change_matches_analytic` | Small along-track Δv; compare Δa to `2a²v/μ · Δv` | < 1% |
| `test_period_from_mean_motion` | Round-trip mean motion ↔ period ↔ SMA | < 1e-6 relative |
| `test_rtn_rotation_orthonormal` | RTN basis is orthonormal and right-handed | < 1e-12 |
| `test_covariance_rotation_preserves_trace` | Rotating a covariance preserves its trace | < 1e-10 |
| `test_pc_monotonic_in_miss_distance` | Pc decreases as miss distance grows, other things fixed | strict monotonicity |
| `test_pc_dilution_region_detected` | Inflate σ until Pc decreases; assert the dilution flag fires | flag set |
| `test_pc_against_published_case` | Reproduce a published worked Pc example | within the published figure's precision |
| `test_decay_lifetime_ordering` | Decay lifetime strictly increases with altitude across 400–1000 km | monotonic |

**A 1 m/s along-track burn changes semi-major axis by a few hundred metres.** If your Δv-to-geometry
mapping disagrees with that order of magnitude, something is wrong. Write that as an explicit test —
it is also the fact that kills the naive "A moves, now threatens C, C moves, now threatens D" cascade
picture from v1.0 §3.

### 17.3 Screening correctness

| Test | Purpose |
|---|---|
| `test_filter_chain_no_false_negatives` | Brute-force a 300-object subset; assert the filter chain finds every conjunction the brute force finds |
| `test_filter_chain_speedup` | Assert ≥ 50× fewer fine propagations than brute force on 2,000 objects |
| `test_apogee_perigee_filter_correct` | Pairs that cannot geometrically approach are excluded |
| `test_screening_deterministic` | Same inputs + seed → identical conjunction set |
| `test_tca_refinement_converges` | Bisection/golden-section on the separation function converges to < 1 s |

`test_filter_chain_no_false_negatives` is the single most important test in the repo. A filter chain
that silently drops conjunctions invalidates every ledger number.

### 17.4 Ledger and attribution

| Test | Purpose |
|---|---|
| `test_dead_object_borne_burden_is_zero` | Non-maneuverable objects bear nothing, by construction |
| `test_attribution_conserves_total` | Σ imposed across objects = Σ borne across objects, within tolerance |
| `test_intra_constellation_excluded` | Starlink-Starlink conjunctions do not inflate Starlink's imposed burden |
| `test_counterfactual_removal_reduces_burden` | Removing object *i* strictly reduces others' burden |
| `test_ledger_threshold_sensitivity` | Burden at Pc > 1e-4 vs 1e-5 vs 3e-7 differs by orders of magnitude and the threshold is recorded in every entry |
| `test_ambiguous_attribution_flagged` | Active-active pairs are flagged, not silently split 50/50 |
| `test_kappa_bounds` | κ ≥ 0, and κ computed on a sparse shell < κ on a dense shell |

**The intra-constellation test matters more than it looks.** Large constellations are phased and
plane-separated by design, and intra-constellation conjunctions have been reported as a large share
of total alerts — around 45% for Starlink in one analysis. Counting those as imposed burden would
make your worst offender a mega-constellation for reasons that are an artifact of your model rather
than physics. An expert will spot it instantly.

### 17.5 Honesty tests (unusual, and the ones that save you)

| Test | Purpose |
|---|---|
| `test_no_bare_floats_in_api_response` | Walk every response tree; assert no display field is a bare float instead of `Traced` |
| `test_every_na_has_reason` | Every `None` value carries a non-empty `na_reason` |
| `test_pc_null_when_no_covariance` | With `covariance_source="none"`, Pc is `null`, never `0.0` |
| `test_modelled_values_labelled` | Every mass, HBR, decay lifetime and fee carries label `MODELLED` or `INDICATIVE` |
| `test_assumptions_block_on_every_response` | Every 200 response includes the full assumption block |
| `test_agent_cannot_fabricate_numbers` | §14.6 |
| `test_no_flight_certified_language` | Grep the codebase and UI strings for forbidden phrases (§18.4) |

### 17.6 Demo rehearsal protocol

Three full rehearsals minimum, on the machine that will be used, on the network that will be
available (assume none — cache everything).

```
Rehearsal checklist
  [ ] Cold start to first screen  < 30 s
  [ ] Base screening run pre-computed and cached
  [ ] Chaos replan               < 10 s
  [ ] Every screen reachable in  ≤ 2 clicks
  [ ] Offline mode verified (pull the ethernet cable and run it)
  [ ] Fallback: static JSON fixtures for every endpoint, behind a --demo-safe flag
  [ ] Timed narration            ≤ 4:15
  [ ] Q&A answers rehearsed for every question in §22
```

**Build the `--demo-safe` flag.** It serves recorded fixtures instead of live computation. You will
either never need it or it will save the entire project.

---

## 18. HONESTY AND LIMITATIONS REGISTER

**This section governs every other section.** If a feature requires violating it, the feature is
wrong.

### 18.1 The assumptions register

Every one of these is displayed in the UI and embedded in every export.

| # | Assumption | Label | Impact if wrong |
|---|---|---|---|
| A1 | Covariance fitted from public CDM datasets, applied to TLE-derived states | MODELLED | Pc values shift; **relative rankings are more robust than absolute values** |
| A2 | Hard-body radius default 5.0 m where dimensions unknown | MODELLED | Pc scales roughly with HBR; affects thresholds crossed |
| A3 | Mass estimated from object class and RCS size bucket | MODELLED | Affects hazard index, not burden |
| A4 | Maneuver triggered when Pc exceeds a declared threshold | MODELLED | **Burden counts scale by orders of magnitude with threshold.** Always stated. |
| A5 | Δv per CAM derived from required miss-distance clearance | MODELLED | Δv totals shift; ordering largely preserved |
| A6 | Intra-constellation conjunctions excluded from imposed burden | STATED | Including them would make mega-constellations rank first for modelling reasons |
| A7 | Attribution rule R1 only (dead→active unambiguous) in headline figures | STATED | Active-active flows flagged separately, never silently split |
| A8 | Decay lifetime from a static exponential atmosphere model | MODELLED | Solar-cycle variation is not modelled; lifetimes at 500–700 km can be off by a factor |
| A9 | PMD success rate as entered by the user | STATED | Dominates long-horizon hazard |
| A10 | Implied fee calibrated from published orbital-use-fee work | **INDICATIVE** | Not a price. An illustration of magnitude. |
| A11 | OCS is our own prototype metric | **PROTOTYPE** | Not an industry standard. Components always shown. |
| A12 | Monte Carlo robustness is the fraction of simulated scenarios remaining safe **under A1** | MODELLED | **Not prediction accuracy.** Never call it that. |
| A13 | SGP4 propagation, general-perturbations accuracy | STATED | Kilometre-scale error at 72 h; unsuitable for operational decisions |
| A14 | Lethal non-trackable debris not modelled | STATED | True risk is higher than computed; roughly a quarter of catastrophically-dangerous objects are untracked |

### 18.2 What we know we cannot do

State these before being asked.

1. **We cannot produce operationally trustworthy absolute collision probabilities.** Public TLEs
   have kilometre-scale error and carry no covariance. We compute *relative* burden and rankings
   credibly; we do not claim operational Pc.
2. **We cannot observe most maneuvers.** Only a handful of operators publish thresholds. Maneuver
   counts are modelled, not observed, and are labelled as such.
3. **We cannot resolve attribution between two active satellites cleanly.** Who "caused" a
   conjunction between two operating spacecraft is genuinely arguable. We flag these and exclude
   them from headline figures. **Dead objects are unambiguous, which is why we start there.**
4. **We cannot see untracked debris.** Roughly 1.2 million fragments in the 1–10 cm range are
   modelled population, not catalogue entries. Our burden figures are therefore lower bounds.
5. **We cannot validate against ground truth.** No public dataset records which maneuvers were
   actually executed by which operator for which conjunction.
6. **We are not flight-certified, and nothing we produce is a flight command.**

### 18.3 The counterintuitive-result clause

If the capacity engine, built correctly with decay lifetime and PMD included, recommends a *lower*
altitude despite worse near-term congestion — because objects fall out of it faster — **that is the
correct answer and you present it.** A counterintuitive but defensible result beats a clean
fabricated one. If your model instead produces the tidy answer v1.0 assumed (570 km beats 550 km on
congestion grounds alone), check whether you have omitted decay lifetime; if you have, the model is
producing sustainability advice that may be backwards, which is worse than having no capacity
feature at all.

### 18.4 Forbidden language

Grep for these in code, UI strings and slides. `test_no_flight_certified_language` enforces it.

```
FORBIDDEN                          USE INSTEAD
"prediction accuracy"           →  "fraction of simulated scenarios remaining safe"
"94% confident"                 →  "94 of 100 simulated scenarios remained safe under A1"
"flight-certified"              →  "research prototype"
"autonomous collision avoidance"→  "decision support for a human operator"
"industry-standard metric"      →  "our prototype research metric"
"the AI calculated"             →  "the physics engine calculated; the planner selected"
"real-time"                     →  "refreshed every N minutes"
"digital twin"                  →  (avoid entirely — Slingshot markets this term; §5.2)
"we invented"                   →  "we combined; the components are cited in §5"
"guaranteed"                    →  (never)
```

### 18.5 The closing slide

End the pitch on the limits slide, not the vision statement. Deliberate choice: at national level,
the teams that lose credibility are the ones that oversell. The team that says *here is exactly
where our model breaks* is the team judges believe about everything else.

---

## 19. DEMO SCRIPT

### 19.1 Why v1.0's demo order was inverted

v1.0 §32 spent 3:20 on the tactical scenario and 30 seconds on the capacity vision. The tactical
scenario is the part most similar to what already exists commercially; the capacity link is the part
that is ours. Also: at a national hackathon you will not get 4:15 of silence. Assume interruptions.
Front-load the thesis.

### 19.2 The script

| Time | Screen | Narration and action |
|---|---|---|
| **0:00–0:20** | Title | **Open on the bill, not the collision.** "This rocket body was launched in 1987. It has been dead for 38 years. Last month it forced 31 manoeuvres and extracted 18.7 metres per second of propellant from nine different operators. Nobody has ever sent it a bill. We compute it." |
| 0:20–0:40 | S2 object card | Point at `BORNE BY ITSELF = 0` next to `IMPOSED = 18.7 m/s`. "It cannot move. So everyone else pays, forever, for free." Click one number → provenance panel. "Every figure traces to the function that computed it." |
| 0:40–1:05 | S1 ledger | Rank the whole shell by Δv imposed. "This is the ranking nobody publishes. Existing lists rank objects by debris-generating hazard — probability times mass. We rank by fuel extracted from other operators. Different question." Point at a `⚑` row: "this one is not on the published top-50 most-concerning list." Footer: "71% of all burden in this shell comes from objects that are already dead." |
| 1:05–1:20 | S1 → stat | The framing line: "Space doesn't run out when satellites collide. It runs out when dodging gets too expensive. A 2025 study put that threshold at ten manoeuvres a month. About 340 satellites are already past it." |
| 1:20–1:50 | S3 event console | Live cluster. "Obvious answer: move the satellite in the worst conjunction. Our graph says the keystone object is a different one." Show `⚠ differ`. Strategies table appears including HOLD and WAIT. |
| **1:50–2:20** | S4 encounter plane | **The VoI moment — your strongest untaken idea.** Drag the time slider; the covariance ellipse shrinks. "This shrink is real — it comes from public conjunction data messages, not an assumption. Waiting 40 minutes cuts expected Δv by 55%. Sometimes the right action is to wait, and we can prove when." |
| 2:20–2:40 | S3 right pane | Validator rejects the planner's proposed burn, unscripted. Read the reason aloud: "creates a 140-metre conjunction with another object". Planner re-proposes. Approved. "The AI does not compute physics. It proposes; deterministic code rejects." |
| **2:40–3:05** | S8 benchmark | **The proof.** Table vs B2, not just B1. "Against post-manoeuvre-screening baseline — which is what operators actually do — 43% fewer future conjunctions, 72% less Δv. We accept a higher residual Pc, still three orders under threshold. Here is the row where we lose." Then: "0.52 m/s saved is 11 days of mission life." |
| 3:05–3:25 | ChaosButton | Hand it to the judge. They click. Replan in under 10 seconds, diff displayed. "Previous recommendation invalidated because a new object conjuncts with the post-burn trajectory." |
| **3:25–3:55** | S5 → S6 | **The company moment.** Two-peaks chart. "Where should the next 5,000 satellites go? Workload is worst around 550 km. Hazard is worst near 850, where things take decades to fall. The two answers point in opposite directions. We price the trade-off. Nobody else does." |
| 3:55–4:15 | Limits slide | "Here is what we cannot do: public TLEs have kilometre-scale error and no covariance, so we compute relative burden, not operational collision probability. We cannot see most manoeuvres. Attribution between two live satellites is genuinely arguable, which is why we start with the dead ones. This is decision support, not a flight command." |

### 19.3 The prior-art slide (show it before they ask)

Between 2:40 and 3:05, or on request:

```
WE DID NOT INVENT              WHO DID                            WHAT THEY DON'T DO
the conjunction network        Lewis et al. 2010                  prescribe
centrality on it               Lewis 2010; Rao 2023               prescribe, or cost it
orbital capacity modelling     MIT MOCAT; ESA indices             per-object, present-tense
the orbital-use fee            Rao, Burgess & Kaffine 2020        compute one object's share
per-object risk ranking        McKnight; LeoLabs                  operational burden
collision avoidance            Kayhan, Neuraspace, Slingshot      attribution or capacity
operator coordination          Kayhan; SpaceX + NASA Starling     externality accounting
─────────────────────────────────────────────────────────────────────────────────────────
WE BUILT                       the per-object operational externality ledger, and the
                               decision layer on top of it
```

Teams that do this are read as researchers. Teams that do not are read as students who did not look.

### 19.4 Delivery notes

- **Never narrate the architecture.** No "we used a multi-agent system with FastAPI." Judges care
  what it computes.
- **One presenter.** Handoffs eat 15 seconds each and break momentum.
- **Cache everything.** Assume no network.
- **If something breaks, switch to `--demo-safe` and keep talking.** Do not debug on stage.
- **When interrupted, answer and return to the script.** Do not restart.

---

## 20. REPOSITORY LAYOUT AND SETUP

### 20.1 Tree

```
orbital-capacity-intelligence/
├── README.md                     ← thesis in 10 lines, then quickstart
├── SPEC.md                       ← this document
├── pyproject.toml
├── .env.example                  ← SPACETRACK_USER, SPACETRACK_PASS, LLM_API_KEY
├── Makefile                      ← make setup / data / screen / ledger / bench / dev / demo
│
├── oci/
│   ├── __init__.py
│   ├── config.py                 ← ALL tunables. No magic numbers anywhere else.
│   ├── labels.py                 ← Traced, Label, na_reason helpers  §9.2
│   ├── provenance.py             ← trace recording  §10.14
│   │
│   ├── data/
│   │   ├── ingest.py             M1
│   │   ├── celestrak.py          D1
│   │   ├── spacetrack.py         D4
│   │   ├── kelvins.py            D2 — covariance fitting
│   │   ├── socrates.py           D3
│   │   ├── operator_map.yaml     NORAD → operator, hand-curated
│   │   ├── mass_model.yaml       class × RCS → mass range (MODELLED)
│   │   └── synthetic.py          D8 — build this on day one
│   │
│   ├── physics/
│   │   ├── propagate.py          M2
│   │   ├── screen.py             M3 — the filter chain
│   │   ├── geometry.py           RTN, B-plane, covariance rotation
│   │   ├── pc.py                 Foster/Chan, dilution detection
│   │   ├── maneuver.py           impulsive Δv, element rebuild
│   │   └── decay.py              lifetime estimate
│   │
│   ├── graph/
│   │   ├── build.py              M4
│   │   ├── clusters.py           risk-weighted vertex selection
│   │   └── regime.py             κ  §11.8
│   │
│   ├── ledger/
│   │   ├── compute.py            M5 — THE CORE MODULE
│   │   ├── attribution.py        R1/R2/R3 rules  §11.7.2
│   │   ├── project.py            lifetime burden
│   │   └── fee.py                indicative fee  §11.9
│   │
│   ├── sim/
│   │   ├── simulate.py           M6 — PURE FUNCTION. §16.4
│   │   ├── montecarlo.py         M6b
│   │   └── chaos.py              M14
│   │
│   ├── decide/
│   │   ├── generate.py           strategy enumeration
│   │   ├── optimize.py           M7, regret
│   │   ├── voi.py                M8
│   │   └── validate.py           M9 — deterministic, authoritative
│   │
│   ├── capacity/
│   │   ├── shells.py             M10
│   │   ├── flux.py               kinetic-gas model  §11.13
│   │   ├── ocs.py                §11.10
│   │   └── deployment.py         deployment optimiser
│   │
│   ├── agent/
│   │   ├── planner.py            M11
│   │   ├── tools.py              §14.2
│   │   ├── prompts.py            §14.4
│   │   └── guard.py              §14.6 number-fabrication guard
│   │
│   ├── api/
│   │   ├── main.py               M12
│   │   ├── routes/               one file per resource group
│   │   ├── schemas.py            §9.2
│   │   └── jobs.py               202 + polling
│   │
│   └── bench/
│       ├── harness.py            M15
│       ├── baselines.py          B1–B4
│       └── scenarios/*.json      S1–S8, fixed seeds
│
├── web/                          M13 — see §13
│   ├── src/components/           §13.9
│   ├── src/pages/                S1–S10
│   └── src/api/client.ts
│
├── data/
│   ├── cache/                    gitignored — TLE/OMM snapshots
│   ├── kelvins/                  gitignored — CDM dataset
│   └── fixtures/                 COMMITTED — demo-safe recorded responses
│
├── tests/                        §17
└── docs/
    ├── ASSUMPTIONS.md            §18.1, generated from config.py
    ├── PRIOR_ART.md              §5
    └── DEMO.md                   §19
```

### 20.2 Setup

```bash
git clone <your-repo> && cd orbital-capacity-intelligence

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env        # add Space-Track credentials + LLM key

make data                   # pull CelesTrak catalogue, fit Kelvins covariance model
make screen SHELL=17        # screen one shell, 72h window
make ledger                 # compute the externality ledger
make bench                  # run benchmark scenarios
make dev                    # API on :8000, web on :5173
make demo                   # pre-computes and caches everything for the demo
make demo-safe              # serve committed fixtures, no computation
```

### 20.3 Day-one actions

Do these before writing code; two of them have external latency.

1. **Register on Space-Track.org.** Approval is not instant. Do it now.
2. **Download the Kelvins CDM dataset.** This is the single most important data decision (§8.3).
3. **Write `oci/config.py` and `oci/labels.py` first.** Every other module imports them. If magic
   numbers leak into modules, the assumption register becomes a lie by hour thirty.
4. **Write `oci/data/synthetic.py`.** The 6-object scenario. It unblocks the entire vertical slice
   before any real data arrives.
5. **Commit `data/fixtures/`.** Your demo-safe fallback.

### 20.4 README opening (write this first — it forces clarity)

```markdown
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
Assumptions: docs/ASSUMPTIONS.md. Prior art: docs/PRIOR_ART.md.
```

---

## 21. RISK REGISTER

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Screening does not finish; demo times out | **High** | Fatal | Filter chain (§10.3), one shell only, pre-cache the base run, `test_filter_chain_speedup` |
| R2 | Kelvins CDM dataset unobtainable or unusable | Medium | High | Fallback C: declared synthetic covariance with visible slider (§8.3). VoI becomes weaker but honest |
| R3 | Space-Track registration not approved in time | Medium | Medium | CelesTrak needs no auth; start there |
| R4 | Benchmark comes out neutral — OCI does not beat B2 | **Medium** | High | Discovered at hour 32, not hour 70 (§15.1). Then: narrow to dead-object-dominated clusters where the claim is strongest, or report the negative result per §15.6 |
| R5 | Judge identifies the graph/centrality work as published | **High** | Medium if unprepared, **zero if prepared** | The prior-art slide (§19.3). Show it first |
| R6 | Validator never rejects; loop looks staged | Medium | High | Free-form action space (§14.3). Test: assert the `rejected` array is non-empty on scenario S7 |
| R7 | Agent fabricates a number on stage | Medium | **Fatal** | Guard (§14.6), temperature 0, fallback to template explanation |
| R8 | Capacity model gives backwards advice (omits decay) | Medium | High | §10.12 includes decay lifetime and PMD. `test_decay_lifetime_ordering` |
| R9 | Mega-constellation ranks #1 for modelling reasons | **High if untested** | High | `test_intra_constellation_excluded` (§17.4). This is the mistake an expert spots instantly |
| R10 | Chaos mode needs a retrofit because M6 is impure | Medium | Medium | Purity requirement on day one (§16.4) |
| R11 | Network unavailable at the venue | Medium | Fatal if unhandled | Cache everything; `--demo-safe` fixtures |
| R12 | Team builds the globe first because it looks impressive | **High** | High | It is priority P3 and cut #1 (§16.5). Pin §1.5 where everyone sees it |
| R13 | Scope creep into 20 features, none finished | **High** | Fatal | The golden test (§1.6), the cut lines (§16.5), the anti-overengineering list (§16.7) |
| R14 | Demo runs over 4:15 | High | Medium | Three timed rehearsals (§17.6), one presenter |

**The two highest-leverage mitigations, if you only do two:** the filter chain (R1) and the prior-art
slide (R5).

---

## 22. EXPECTED JUDGE QUESTIONS AND ANSWERS

Rehearse every one of these aloud. The answer is not the point; the *absence of hesitation* is.

**Q: Where does your covariance come from?**
From public conjunction data message datasets released for the collision-avoidance machine-learning
challenges, fitted as a function of time-to-TCA and object class. It is on screen in the assumption
strip. TLEs carry no covariance at all, which is exactly why we did not use TLE-derived uncertainty
— any probability from that would be fabricated. Where we have no covariance, we return null with a
reason, never zero.

**Q: Isn't post-manoeuvre screening already standard practice?**
Yes, and that is why our baseline B2 includes it. Screening your own post-burn trajectory is routine.
What is not routine is knowing *how much* of your manoeuvre budget a specific third object is
consuming, across all operators. That is the ledger, and it is a different question.

**Q: How is this different from Kayhan / LeoLabs / Neuraspace / Slingshot?**
They operate per event: alert, assess, manoeuvre, coordinate. Kayhan built the first operational
coordination framework and SpaceX and NASA have flown responsibility handoff. None of them computes
the attributable operational externality per object, and none links the 72-hour decision to the
multi-year deployment decision in common units. We do not compete with their alerting; we sit above
it.

**Q: Hasn't MIT already built orbital capacity modelling?**
Yes — MOCAT, source-sink models, and we cite them. Those operate on decadal to century population
equilibria and answer policy questions. They say nothing about any individual object or about this
week's decision. We measure capacity as present-tense affordability against a documented viability
threshold, per object. Different horizon, different granularity, different question.

**Q: Isn't your graph work just Lewis 2010 and Rao 2023?**
The representation and the centrality analysis are theirs, and we cite both. Rao's paper explicitly
leaves optimal intervention strategies as future work. That prescriptive layer — and the attribution
in operational currency — is what we built.

**Q: Your Pc values are not operationally trustworthy. So what use is this?**
Correct, and we say so on the limits slide. Absolute Pc from public data is not trustworthy. But the
ledger is a *relative ranking* under a *single consistent* covariance model and a *declared*
threshold, and relative rankings are far more robust than absolute values. The product claim is
"this object costs you more than that one", not "this object has a 1-in-8,000 chance of collision".

**Q: How do you know a manoeuvre was actually performed?**
We do not, and it is labelled MODELLED everywhere. Only a handful of operators publish thresholds.
We compute manoeuvres-forced at a declared threshold and state the threshold with every figure,
because burden counts change by orders of magnitude between a 1e-4 threshold and a 3e-7 one.

**Q: Who "caused" a conjunction between two active satellites?**
Genuinely arguable, which is why we flag those flows separately and exclude them from headline
figures. For a dead object against a live one it is not arguable at all — the dead one cannot move.
That is why we start with dead objects: cleanest case, largest share of burden, zero dispute.

**Q: Why not just remove the top objects? Isn't that already the plan?**
Removal prioritisation exists and ranks by debris-generating hazard. Our ranking is by operational
burden, and the two differ — a massive derelict at 850 km with few close approaches ranks high on
hazard and lower on burden; a modest dead payload inside the 550 km traffic lane ranks the reverse.
Both are correct. Only one tells an operator what is costing them propellant this month.

**Q: Is the AI doing anything real, or is it a wrapper?**
The planner sequences analysis, interprets validator rejections, replans after perturbation, and
writes the explanation. It computes no physics, and we enforce that with a guard that rejects any
output containing a number that did not come from a tool result. You saw the validator reject its
proposal live — that was not scripted.

**Q: Why only one shell?**
Time. The method is shell-agnostic; the cost is screening runtime. We chose to make one shell
correct and reproducible rather than four shells that time out on stage.

**Q: Could this be deployed for real?**
As an advisory and analytics product for insurers, regulators and small operators — plausibly, on a
two-to-four-year path, with better tracking data and an anchor customer. In the operational manoeuvre
loop, trusted with real spacecraft — no, and we are not claiming a path there. That needs
certification, flight heritage and radar-grade tracking. Our honest confidence is roughly 30–35% for
the advisory product and about 5% for the operational one.

**Q: What is your weakest assumption?**
A4 — the maneuver threshold. Burden counts scale by orders of magnitude with it, and operators use
wildly different thresholds. We always display the threshold, and the ledger is recomputable at any
threshold, so the ranking can be checked for sensitivity. It is the first thing we would want real
operator data for.

**Q: What surprised you?**
[Answer from your actual data — see §6.4. If nothing surprised you, say that, and say what it
implies. A team that reports "our result matched published rankings, so our contribution is the
method not the finding" is more credible than one that manufactures a surprise.]

---

## 23. REFERENCES

Verify every link and current status before presenting; this field moves quickly and several of
these are recent.

### 23.1 Foundational academic work

- Lewis, H.G., Newland, R.J., Swinerd, G.G. & Saunders, A. (2010). "A new analysis of debris
  mitigation and removal using networks." *Acta Astronautica* 66(1-2), 257–268. — the conjunction
  network and centrality-based removal prioritisation.
- Rao, A. "Close Encounters of the LEO Kind: Spillovers and Resilience in Partially-Automated
  Traffic Systems." arXiv:2410.04599. — conjunction network on ~40M real alerts; betweenness and
  eigenvector centrality; COSMOS-1408 identification; strategic substitutes vs complements.
- Rao, A., Burgess, M.G. & Kaffine, D. (2020). "Orbital-use fees could more than quadruple the value
  of the space industry." *PNAS* 117(23), 12756–12762. — the Pigouvian orbital-use fee.
- D'Ambrosio, A. & Linares, R. "Carrying Capacity of Low Earth Orbit Computed Using Source-Sink
  Models." *Journal of Spacecraft and Rockets*, doi:10.2514/1.A35729. — MOCAT-3, capacity via stable
  equilibria.
- "Stable and sustainable orbital capacity solutions in Low Earth Orbit." *Acta Astronautica* (2025).
  — MOCAT-SSEM, debris spreading, SSEM-vs-Monte-Carlo validation.
- "MOCAT-pySSEM: an open-source Python library and user interface." *SoftwareX* (2025).
- McKnight, D. et al. — statistically-most-concerning-objects lists; LeoLabs debris-generating risk
  continuum (AMOS / ESA Space Debris Conference proceedings).
- "CAMmary: A review of spacecraft collision avoidance manoeuvre design." *Acta Astronautica* (2025).
  — CAM design landscape, operator threshold heterogeneity.
- "Fuel-Optimal Collision Avoidance Maneuvers in Long-Term Encounters with Station-Keeping
  Constraints." arXiv:2307.06004.
- "Semi-Decentralized Multi-Spacecraft Collision Avoidance under [asynchronous information]."
  arXiv:2607.26570 (2026). — coupled multi-operator planning.
- "Orbital Debris in Earth Orbit: Operations, Stability, Control, and Market Formation."
  arXiv:2603.23552 (2026). — normalised collision-avoidance rate per satellite-year; the two-peaks
  separation between workload and persistence.
- "A novel conjunction filter based on the minimum distance between perturbed trajectories."
  arXiv:2410.20928. — all-vs-all screening beyond the one-vs-all paradigm.

### 23.2 Standards and institutional sources

- CCSDS Conjunction Data Message (CDM) — 508.0-B — the CDM field definitions.
- CCSDS Orbit Data Messages (ODM) / Orbit Mean-Elements Message (OMM) — 502.0-B.
- IADC Space Debris Mitigation Guidelines — threshold and PMD guidance.
- ESA Annual Space Environment Report — population, PMD compliance, density by altitude.
- NASA Orbital Debris Quarterly News — event records.
- Viasat, "Managing Mega-Constellation Risks in LEO" (white paper, 2022) — projected warning and
  manoeuvre volumes; externality argument.
- SpaceX FCC semiannual constellation reports — the public manoeuvre count record.
- Space Sustainability Rating (EPFL eSpace) — operator scoring, for positioning.

### 23.3 Software to depend on

| Repository | Use |
|---|---|
| `github.com/brandon-rhodes/python-sgp4` | SGP4 propagation. The reference Python implementation. Includes the standard verification TLEs — use them for `test_sgp4_against_reference`. |
| `github.com/skyfielders/python-skyfield` | Time handling, frames, second-opinion propagation for cross-validation |
| `github.com/esa/dSGP4` | Differentiable SGP4 (ESA ACT). Read it for how they structure propagation and for gradient-based manoeuvre search if you go there. |
| `github.com/ARCLab-MIT/pyssem` | MOCAT source-sink in Python. **Take the shell discretisation and the species bookkeeping.** Align your `shells` table to theirs so your capacity numbers are comparable to published work. |
| `github.com/ARCLab-MIT/MOCAT-MC` | Monte Carlo population evolution. Study the collision-rate treatment; do not depend on it for a hackathon. |
| `networkx/networkx` | Graph, centrality, connected components |
| `scipy` | Optimisation, root-finding for TCA refinement, statistics |
| `github.com/python-astrodynamics/spacetrack` | Space-Track REST client |
| `github.com/esa/pykep`, `github.com/esa/pygmo2` | Trajectory primitives and multi-objective optimisers, if SciPy proves insufficient |
| `github.com/nasa/CARA_Analysis_Tools` | NASA CARA conjunction assessment tools. **Read the Pc implementations and the dilution treatment** — this is the closest thing to an authoritative reference for §11.4. Largely MATLAB; port the method, not the code. |
| `github.com/kesslerlib/kessler` | ML for conjunction assessment, associated with the Kelvins challenge work. Read for CDM handling and covariance modelling. |
| `github.com/CelesTrak` / celestrak.org | TLE/OMM and SOCRATES data access patterns |

### 23.4 What to study but not depend on

- Cesium / CesiumJS and satellite.js — only if the globe survives to P3.
- OKAPI:Orbits published material on CAM optimisation with station-keeping constraints — useful for
  the validator's constraint list (§14.3).
- Kelvins challenge post-competition write-ups — the strongest public guidance on what CDM
  covariance data can and cannot support.

### 23.5 Repository hygiene rule

Every external repository you learn from gets a line in `docs/PRIOR_ART.md` naming what you took.
Two reasons: it keeps the prior-art slide honest and current, and it means nobody on the team can
accidentally present someone else's method as ours.

---

## APPENDIX A — THE ONE-PAGE BRIEF

For pinning above the desk.

```
WHAT WE BUILD
  A ledger that computes, per object, how much propellant and how many manoeuvres it
  forces other operators to spend — from free public data. Then a decision layer that
  uses it for today's manoeuvre and tomorrow's deployment altitude.

THE LINE
  "A dead rocket body from 1987 is still making other people's satellites burn fuel
   every month. Nobody has ever sent it a bill. We compute the bill."

THE REFRAME
  Space doesn't run out when satellites collide. It runs out when dodging gets too
  expensive. ~340 satellites are already past the viability threshold.

THE NOVELTY  (narrow, defensible)
  N1  attribution in operational currency (Δv extracted from others), not hazard
  N2  the measurement layer for orbital-use fees, which exist on paper only
  N3  capacity as present-tense affordability, not century-scale collision equilibrium
  N4  live substitutes-vs-complements regime diagnostic

THE NON-OBVIOUS RESULT
  Workload peaks at 500-600 km. Persistence hazard peaks near 850 km.
  The two optima disagree. There is no single best altitude.

NEVER CUT
  the ledger · the filter chain · the benchmark · WAIT as an action · the labels

NEVER SAY
  "prediction accuracy" · "flight-certified" · "digital twin" · "we invented"

THE GOLDEN TEST
  Does this help compute, price, or act on the cost one object imposes on another?

THE FAILURE CLAUSE
  If we can't beat a post-manoeuvre-screening baseline on a measured benchmark,
  we say so. Evidence over marketing.
```

---

*End of specification. v2.0.*
