# Orbital Capacity Intelligence — 2:45 video script

One presenter, one laptop, screen recording + voice. Read the **SAY** column; do the **DO** column.
Before recording: `make api-safe` in one terminal, `make ui` in another, open http://localhost:5173,
full-screen the browser, Wi-Fi can be off.

Numbers below are from the real 12 Sep 2026 run (500–1000 km, 7 days) — say them as they are.

---

| Time | DO (on screen) | SAY (out loud) |
|---|---|---|
| **0:00–0:15** | Globe page open. Earth turning, satellites moving. Don't click yet. | "Every dot and every satellite you see here is real. These are today's public orbital element sets from CelesTrak, propagated with SGP4 in the browser. Nothing is animated by hand — this is where these objects actually are." |
| 0:15–0:35 | Hover a satellite. Card appears. Then click it — orbit, ground track, coverage cone, 3D model. | "Hover any object: name, operator, live altitude, speed, where it is over the ground. Click it: its orbit, its ground track, the area it can see. Press LIVE at the bottom and you get all nineteen thousand tracked objects at the current time, including the ISS." |
| **0:35–1:00** | Point at an **amber** satellite. Hover it: "bills others 2.1 m/s". | "Here is the problem we solve. Satellites burn fuel dodging each other — and dodging dead junk. A lot of that dodging is forced by objects that are already dead: rocket bodies, old fragments. They can't move, so everyone else pays. Nobody has ever measured that cost per object. Amber means: this object is billing everyone else. This fragment of a Chinese weather satellite destroyed in 2007 forced two manoeuvres and 3.3 metres per second of propellant — from SpaceX — in one week." |
| 1:00–1:20 | Click **WHO PAYS · ledger**. Scroll the ranked table. Click the **borne** toggle — every row drops to zero. | "This is the ledger. Every object in the shell, ranked by the fuel it extracts from other operators over the screening window. Flip to *borne* — what they pay themselves — and every dead object drops to zero. One hundred percent of the avoidance burden in this shell comes from things that are already dead. That's the whole thesis in one click." |
| **1:20–1:50** | Click **DECIDE · event console**. Point at "⚠ keystone ≠ max-Pc". Scroll to the strategies table and the **REJECTED** list. | "Now the tactical part. Most systems say: move the satellite in the worst close approach. Our interaction graph says the object holding this whole cluster together is a *different* one — the keystone. We simulate forty candidate actions — hold, wait for better tracking, observe, burn, coordinate — each re-screened against its neighbours with uncertainty sampling, and a deterministic validator rejects the infeasible ones. Read one rejection: *creates a new conjunction at 934 metres*. The AI plans; physics code says no." |
| 1:50–2:05 | Click **run planner**. Trace appears: 25 tool calls, GUARD PASSED. | "The planning agent can only act through eight tools. It cannot compute physics, only propose. Every number in its explanation is checked against the tool results — if it invents a figure, the guard blocks it." |
| 2:05–2:20 | Click **⚡ CHAOS**, pick NEW_OBJECT, inject. Diff appears in ~7 seconds. | "Judges can break it live. Inject a new fragment onto the recommended trajectory: the old recommendation is invalidated with the reason, and the whole thing replans in seven seconds. This is a replan, not a replay — the pipeline is a pure function of state." |
| **2:20–2:40** | Click **WHERE TO FLY · shell map** (two peaks). Then **NEW CONSTELLATION · deployment**, press evaluate. | "The strategic part. Where should the next five thousand satellites go? Workload is worst around 475 km — that's where everyone already is. Hazard is worst near 775 km, where dead things stay up for a century. The two answers point in opposite directions. We price the trade-off instead of hiding it in one score." |
| 2:40–2:55 | Click **PROOF · benchmark**. | "And we checked ourselves: the same scenarios through what operators do today — pairwise screening with re-screening — and through us. Where we lose a row, the table says so. Every number on every screen carries its label: observed, computed, or modelled. Decision support, not a flight command. That's Orbital Capacity Intelligence." |

---

## If something breaks on camera
Keep talking and switch to the next screen. Nothing on stage needs the network.

## The one-paragraph version (for the friend)
Satellites burn fuel dodging each other and dodging dead junk. Dead objects can't move, so everyone
else pays for them, and nobody has ever sent them a bill. We take the real public catalogue, screen
every close approach in a shell for a week, build the interaction graph, and compute a ledger: per
object, how much fuel it forces other operators to burn, who pays, and what it will cost over its
remaining life. From that we pick today's avoidance action (including *wait*, which nobody prices)
with a planning agent that can only act through tools and a validator that rejects bad burns, we let
judges perturb the system live, and we answer where the next constellation should fly — showing that
the operations-optimal and environment-optimal altitudes are different. All real data, all labelled,
all offline-safe.
