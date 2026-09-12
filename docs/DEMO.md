# Demo script (SPEC §19)

Four minutes fifteen, one presenter, no handoffs. Assume interruptions and assume no network:
everything below runs from `data/cache/` and `data/fixtures/` with the cable pulled.

**Open on the bill, not the collision.** The tactical avoidance story is the part most similar to
what already exists commercially; the capacity link is the part that is ours. Front-load the thesis.

---

## Before you start

```bash
make api-safe          # API on :8000, OCI_DEMO_SAFE=1 — refuses anything that touches the network
make ui                # UI on :5173
```

Rehearsal checklist (§17.6):

- [ ] Cold start to first screen under 30 s
- [ ] Base screening run cached — `run_20260912T1700Z_4371` (500–1000 km, 7 d) is the demo run
- [ ] Ledger pickles present at 1e-5 **and** 1e-4 so the threshold selector is instant
- [ ] Chaos replan under 10 s (measured 7.0 s warm)
- [ ] Every screen reachable in ≤ 2 clicks
- [ ] Ethernet unplugged, full run-through
- [ ] Timed narration ≤ 4:15
- [ ] Q&A rehearsed for every question in SPEC §22

If anything breaks mid-demo: **keep talking and switch to another screen.** Do not debug on stage.

---

## The script

| Time | Screen | Narration and action |
|---|---|---|
| **0:00–0:20** | S2 object card, NORAD 30290 | "This is a fragment of a Chinese weather satellite that was destroyed in a missile test in 2007. It cannot manoeuvre. Over one week it forced two avoidance manoeuvres and extracted **3.3 metres per second** of propellant — from SpaceX. Nobody has ever sent it a bill. We compute it." |
| 0:20–0:40 | S2, point at the two columns | `IMPOSED 3.284 m/s` next to `BORNE 0.00 *`. "It cannot move, so everyone else pays — forever, for free. Its decay lifetime is three years; the ones at 800 km are there for ninety." Click any number → the provenance panel. "Every figure traces to the function that computed it, with its assumptions." |
| 0:40–1:05 | S1 ledger | "This is the ranking nobody publishes. Existing most-concerning lists rank objects by debris-generating hazard — probability times mass. We rank by **fuel extracted from other operators**. Different question." Flip the toggle to **borne**: every row drops to zero. "That is the whole thesis in one click." Footer: **100 % of the avoidance burden in this shell comes from objects that are already dead** — 57 dead fragments, 49.7 m/s, sixteen operators paying. |
| 1:05–1:20 | S1, stay | The framing line: "Space doesn't run out when satellites collide. It runs out when dodging gets too expensive. A 2025 study put that threshold at ten manoeuvres a month — about 340 satellites are already past it." |
| 1:20–1:50 | S3 event console | "Obvious answer: move the satellite in the worst conjunction. Our graph says the object holding this cluster together is a different one." Point at **⚠ keystone ≠ max-Pc**. Strategy table appears — including HOLD and WAIT, which most systems do not price. |
| **1:50–2:20** | S4 encounter plane | **The VoI moment.** "This ellipse is the combined position uncertainty, and it comes from 159,506 real conjunction data messages — not an assumption. It shrinks 41 % a day as the encounter approaches. Waiting is sometimes the correct action, and we can say *when*." If the dilution banner is showing, read it: "here a bigger uncertainty would report a *lower* probability — that is a trap, and we flag it." |
| 2:20–2:40 | S3 right pane | The validator rejects the planner's own proposed burn, unscripted. Read the reason aloud: "creates a new conjunction with NORAD 91003 at 140 metres." The planner re-proposes one orbit earlier at half magnitude. Approved. **"The AI does not compute physics. It proposes; deterministic code rejects."** |
| **2:40–3:05** | S8 benchmark | **The proof.** "B2 is pairwise screening plus post-manoeuvre re-screening — what operators actually do. Not a strawman." Walk one scenario. "Here is the row where we lose." Then: "0.52 m/s saved is eleven days of mission life." |
| 3:05–3:25 | ChaosButton | **Hand the laptop to a judge.** They pick an injection. Replan in seven seconds, diff on screen. "The previous recommendation is invalidated because a new object now conjuncts with the post-burn trajectory. This is a replan, not a replay — the pipeline is a pure function of state." |
| **3:25–3:55** | S5 → S6 | **The company moment.** Two-peaks chart. "Where should the next 5,000 satellites go? Workload is worst around 475 km — that is where everyone already is. Hazard is worst near 775, where things take a century to fall. The two answers point in **opposite directions**. We price the trade-off. Nobody else does." |
| 3:55–4:15 | Limits | "What we cannot do: public element sets have kilometre-scale error and carry no covariance, so we compute relative burden, not operational collision probability. We cannot see most manoeuvres. Attribution between two live satellites is genuinely arguable — which is why we start with the dead ones, where it is not. This is decision support. It is not a flight command." |

---

## The prior-art slide (show it before they ask)

```
WE DID NOT INVENT              WHO DID                            WHAT THEY DON'T DO
the conjunction network        Lewis et al. 2010                  prescribe
centrality on it               Lewis 2010; Rao 2023               prescribe, or cost it
orbital capacity modelling     MIT MOCAT; ESA indices             per-object, present-tense
the orbital-use fee            Rao, Burgess & Kaffine 2020        compute one object's share
per-object risk ranking        McKnight; LeoLabs                  operational burden
collision avoidance            Kayhan, Neuraspace, Slingshot      attribution or capacity
operator coordination          Kayhan; SpaceX + NASA Starling     externality accounting
──────────────────────────────────────────────────────────────────────────────────────────
WE BUILT                       the per-object operational externality ledger, and the
                               decision layer on top of it
```

Teams that show this are read as researchers. Teams that do not are read as students who did
not look.

---

## Numbers you may be asked for, with the honest answer attached

| Question | Answer |
|---|---|
| How accurate is the screening? | 99 % recall against CelesTrak SOCRATES on the same element sets (98 of 99), TCA agreeing to the millisecond, miss distance within 0.5 m. The one miss is a stale element set excluded by policy. |
| Where does the covariance come from? | Fitted on 159,506 real CDMs from the ESA Kelvins challenge — `log10 σ = a + b·log(1+τ) + type + altitude`, along-track R² 0.54. Debris is 10× worse than payloads. Residual spread is 0.5 dex and it is in the assumptions panel. |
| Why is the threshold 1e-5 and not 1e-4? | Both are shown, and the threshold is printed on every figure. At 1e-4 over one week exactly one object in this shell is billable — that is a real result about how rare high-Pc events are, not a tuned choice. The selector is right there; change it on stage if asked. |
| Is 3.3 m/s a lot? | For one dead fragment over one week, against one operator — yes. It is roughly 66 mission-days of that satellite's propellant budget. Across the shell it is 49.7 m/s in a week, borne by sixteen operators including ESA, NASA-NOAA, ISRO and JAXA. The projection over each object's remaining life is on its object card. |
| Is the dollar figure real? | No, and it is labelled `INDICATIVE` everywhere it appears. It is calibrated to Rao-Burgess-Kaffine (2020) so two altitudes can be compared. It is not a price. |
| Did an LLM produce these numbers? | No. The planner runs with no API key at all — a deterministic driver through the same eight tools. Every number in its explanation is checked against the tool results, and a forged figure fails the test suite. |
| What happens if you're wrong about attribution? | Rule R1 only attributes dead→active, where it is unambiguous. Active-to-active attribution is genuinely arguable and we do not do it. That is why the ledger opens on the dead objects. |

---

## Delivery notes (§19.4)

- **Never narrate the architecture.** Nobody is scoring "we used FastAPI."
- **One presenter.** Every handoff costs fifteen seconds and breaks momentum.
- **Cache everything.** Assume no network.
- **When interrupted, answer and return to the script.** Do not restart.
- **Say the limits out loud before a judge finds them.** It is the cheapest credibility available.
