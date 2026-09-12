# Frontend research — what we take from where, and how

Status: research only. Nothing built. Written 2026-09-12.

Rule: every repo under `inspiration/` is **read-only reference**. It is gitignored and
never pushed. We may read a file, understand the technique, and write our own version in
our own file. We never copy a file, and we never copy keeptrack.space code at all (AGPL).

## 0. Verified facts (tested today, not assumed)

| Fact | Evidence |
|---|---|
| Celestrak GP endpoint is live, no key, no account | `gp.php?GROUP=active&FORMAT=json` → 16,564 objects in 14.5 s; `starlink` 11,130; `fengyun-1c-debris` 1,970; `cosmos-2251-debris` 585; `iridium-33-debris` 110; `cosmos-1408-debris` 3 |
| Celestrak sends **no CORS header** | browser cannot fetch it directly → backend proxies + caches (Celestrak asks ≤ 1 fetch per group per 2 h) |
| `sgp4` PyPI has macOS arm64 wheel; `skyfield` is pure Python | safe on Nikhil's Mac |
| OSTk-astrodynamics and esa/cascade ship **Linux-only** wheels | do not use — would force Docker for every dev run |
| satellite.js SGP4 for ~19k objects ≈ 200 ms per full update | must run in a Web Worker; renderer extrapolates along velocity between updates (kessler does exactly this) |
| kessler runs offline clone-and-run; its look is real, not a mockup | booted locally, reproduced the poster frame |
| Detour's live demo is down; its frontend is basic | booted locally: one satellite on a small textured globe |
| keeptrack's atmosphere shader is in the closed "pro" plugin | `earth.ts:476` checks for an empty `atmosphereFrag` — we write our own Fresnel anyway |

## 1. Stack (decided unless Nikhil overrides)

| Layer | Pick | Not |
|---|---|---|
| Build | Vite + React 19 + TypeScript | Next.js (fights R3F, no SSR needed) |
| Globe | Three.js via React Three Fiber + drei, custom GLSL | CesiumJS (5 MB, GIS look, hard to style) |
| Browser propagation | satellite.js in a **Web Worker**, transferable Float32Arrays | main-thread SGP4 |
| State | Zustand (one store) | Redux / context soup |
| Styling | Tailwind v4 + our own tokens in one CSS file | shadcn (template look) |
| Type | JetBrains Mono (data) + Inter (labels) | — |
| Charts | hand-drawn SVG with d3-scale / d3-shape | Recharts (generic, no bullseye) |
| Motion | Framer Motion, one easing, one duration scale | — |
| Live stream | SSE (`EventSource`) from FastAPI | WebSockets (two-way not needed) |
| Backend (later) | FastAPI · sgp4 · numpy/scipy cKDTree · LangGraph · LLM API | — |

## 2. Visual reference map — element → source → our version

### 2.1 Globe (from kessler `web/src/globe.ts`, 426 lines — the whole technique)

What kessler does and *why* (their comments are the best design notes in the folder):

- **No photo texture by default.** "A satellite catalogue is a plotting problem and the
  domain's own convention is a wireframe chart." Points are the only bright thing.
- Scene units = thousands of km, Earth radius ≈ 6.378. Camera at ~(14, 9, 16).
- Layers: opaque **shell** sphere at 0.995 R (occludes points behind Earth — without it
  the population looks doubled) → **graticule** as `LineSegments` every 30° (4° segments)
  → **coastline** from `world-atlas/land-110m.json` via topojson at 1.001 R.
- Points: one `THREE.Points` with `position` (DynamicDrawUsage), `colour`, `size`
  attributes and a `ShaderMaterial`. Vertex: `gl_PointSize = clamp(size * dpr * (28 / -view.z), dpr, 20*dpr)`
  — the 28 was tuned so an ordinary object is ~2.5 CSS px at default zoom; their first
  try (300) turned 2,637 debris into an opaque shell. Fragment: discard outside radius,
  `smoothstep` edge → soft round dot.
- **Selection is a ring, not a bigger dot.** Among 19k pale dots a slightly whiter dot is
  invisible; an annulus is the only annulus on screen. Separate 2-point `Points` with a
  ring fragment shader (`d > 0.5 || d < 0.34 → discard`).
- Between worker updates: `live[i] += velocity[i] * dt` every frame → continuous motion.
- Picking: `Raycaster` with `params.Points.threshold = 0.14`, skip dead indices.
- Dead/unparseable objects are parked at y = −1e6, never removed — **index is identity**
  (names, colours, picker all key on index; compacting would relabel the catalogue).

Our version adds what kessler deliberately left out:
- **Atmosphere rim**: second sphere at ~1.03 R, `BackSide`, Fresnel `pow(1 - dot(N, V), k)`
  × sun-facing factor, additive blend. (keeptrack has this only in the paid plugin.)
- **Day/night terminator** (from keeptrack `earth.ts:1132-1230`, technique only): a
  `diffuse = max(dot(N, sunDir), 0)`; day = texture × diffuse; night = nightLights ×
  `pow(1 - diffuse, 2)`; horizon alpha = `smoothstep(0, 0.06, dot(N, V))` for a soft limb.
  We apply this to a **toggle** "photo" mode; default stays the wireframe plot.
- **Orbit arcs**: primary (white), partner (amber), proposed post-burn (teal, dashed).
  Three colours max. Built as `Line2`/`LineSegments` from a 1-period propagation.
- Sun direction from sim time (Skyfield on the backend or a 10-line solar-position
  approximation in the worker).

### 2.2 Colour system (from kessler `web/src/palette.ts`)

Colour encodes **object class only** — never mood, never decoration. Getting it wrong is
a correctness bug. Their tests assert minimum perceptual distance between class colours.

| Role | kessler value | ours (start here, tune later) |
|---|---|---|
| ground | `#0d1014` | same family — near-black blue-grey, not pure black |
| panel veil | `rgba(13,16,20,0.82)` | same idea: panels are translucent plates over the globe |
| text / dim | `#dce1e8` / `#8a93a0` | |
| payload | `#93b7e3` (cool) | cool |
| debris | `#b08050` (dull warm) | dull warm |
| rocket body | `#8b8b96` (neutral) | neutral |
| selected | `#ffffff` | white |
| partner | `#f2b441` (amber) | amber |
| after-burn / proposed | `#4fd1c5` (teal) | teal |
| **new: Operator A / Operator B / Coordinator** | — | two agent hues + one neutral; must sit ≥ 0.3 from payload/debris so a transcript never reads as a category |

Dark only. No light theme (saves a day; kessler's light mode exists only to settle an
internal design argument).

### 2.3 Layout (from kessler `web/src/style.css` header comment)

"The globe is the page." Everything is an **overlay anchored to viewport edges** on a
full-bleed canvas — no header bar, no fixed column, nothing positioned with
`calc(100vh - Npx)`. Identity + search top-left; source note + legend bottom-left; clock
along the bottom; the object record appears top-right only when something is selected.

Ours:
```
┌──────────────────────────────────────────────────────────┐
│ mark + search                          encounter inspector│
│ (top-left)                                    (top-right) │
│                                                           │
│                   full-bleed globe                        │
│                                                           │
│ stats + legend                    ┌──────────────────────┐│
│ (bottom-left)                     │ agent room (drawer)  ││
│                                   │ slides up, bottom-rt ││
│ ── timeline spine (bottom edge, full width) ──────────── │
└──────────────────────────────────────────────────────────┘
```
Miss-distance curve hangs under the spine when an encounter is active (kessler's
`spine.ts` treats spine + curve as "one axis the globe and the curve both read from").

### 2.4 Timeline spine (from kessler `web/src/spine.ts`, 341 lines)

- 2D canvas, DPR-fitted, 24 h window, hour ticks (major every 6), one tick per passage
  whose **height encodes miss distance** so the day's shape reads before selection.
- Playhead owns the clock; everything else on the page is a projection of it.
- Separation curve below: log-scale km, ±10 min around TCA, "before" and "after burn" lines.

Ours: same idea in SVG (d3-scale) so it can animate, plus **agent event markers** on the
spine (offer / counter / agreement) so the negotiation is visible on the time axis.

### 2.5 Agent room (from Detour `frontend/components/terminal-drawer.tsx`)

Detour streams an event feed and maps each event type to a coloured line. Event types
worth keeping as the basis of our SSE schema:

```
agent_start · llm_call · thinking · tool_calls · tool_result · agent_output
agent_complete · maneuver_executed · pipeline_complete · error · done
```

Ours differs in kind, not just style: **three speakers** (Operator A, Operator B,
Coordinator), each with an avatar colour; tool calls rendered as inline chips
(`propagate`, `screen`, `simulate_burn`); and **structured offer cards** inside the
transcript instead of only text lines.

### 2.6 Offer cards (from AgenticPay `agenticpay/agents/buyer_agent.py` prompts)

AgenticPay's mechanics: each side holds a **private reservation value** (never revealed);
every turn must carry exactly one structured numeric offer tag plus a free-text
`<message>`; acceptance repeats the final contract JSON in `<contract>`. The environment
scores buyer utility, seller utility, and global welfare.

Mapped to us:
- price → **Δv (m/s) each side spends**, and *when* (lead time before TCA)
- private reservation → each operator's **fuel margin, mission constraints, blackout windows**
- contract JSON → **CDM-shaped record** (TCA, MISS_DISTANCE, RELATIVE_SPEED, Pc,
  OBJECT1/OBJECT2 blocks — field names from ccsds-ndm, read-only) + a maneuver plan
- scores → total fuel spent, residual Pc, fairness

We implement this with LLM tool-use / structured output, not regex tags.

### 2.7 Charts nobody else will have

- **Bullseye plot** (idea from ACM-Orbital's README; their code is not public): polar SVG,
  radius = time to TCA, angle = approach direction in the RTN frame, colour = risk.
- **Fuel ledger** per satellite that visibly drops after an agreed burn (memory across runs).

## 3. Real-time data pipeline (frontend view)

```
Celestrak (JSON GP, per group)  ──2h cache──▶  FastAPI /api/catalog(.tle)
                                                     │
                     browser ◀─── one fetch on load ──┘
                       │
                  Web Worker: satellite.js SGP4 for all N objects at epoch t
                       │  postMessage(positions, velocities, ok) with transferables
                  main thread: Points buffer update; per-frame velocity extrapolation
```
Groups to load: `active` + `fengyun-1c-debris` + `cosmos-2251-debris` +
`iridium-33-debris` + `cosmos-1408-debris` (~19.2k objects, ~20 s cold fetch, then cached).
Screening (KD-tree, TCA refine) and agents stay on the backend and stream over SSE.

## 4. Open questions for Nikhil (answer when you share the project)

1. Is the negotiation the hero (globe supports it) or the globe the hero?
2. Which two operators do we demo? (e.g. a Starlink vs OneWeb pair from the live catalog
   is realistic; a synthetic "our satellite" injected into the catalog is more controllable)
3. Human approval gate — one operator clicks approve, or both?
4. Does the demo need to survive without internet? (If yes, we also commit a dated snapshot
   like kessler does, and show "live / snapshot" in the stats block.)

## 5. Inspiration folder index

See `visual-bible.md` for the rendering recipes; the 8 visual-technique repos added on the second pass (cobe, three-globe, github-globe, threejs-earth, satvisor, TLEscope, OrbitsGL, satellite-tracker) are indexed there.


| path | license | what to read it for |
|---|---|---|
| `inspiration/kessler/web/src/{globe,palette,spine,propagate.worker,style}.*` | MIT | globe technique, colour discipline, overlay layout, timeline |
| `inspiration/detour/frontend/components/terminal-drawer.tsx`, `globe-view.tsx` | MIT | SSE event feed → UI; R3F globe with satellite.js |
| `inspiration/detour/agents/graph.py`, `tools.py` | MIT | LangGraph multi-agent + tool-boundary pattern (backend, later) |
| `inspiration/keeptrack.space/src/engine/rendering/draw-manager/earth.ts` | **AGPL — technique only, never code** | day/night shader math, horizon alpha |
| `inspiration/AgenticPay/agenticpay/agents/*.py` | MIT | negotiation protocol: private reservation, per-turn structured offer, contract on accept |
| `inspiration/satvis`, `inspiration/orbica` | MIT | worker + catalog pipeline variants (Cesium / Svelte) — skim only |
| `inspiration/NabhRakshak/frontend` | unspecified | React + Three + Framer Motion panel motion — skim only |
| `inspiration/LLMSat` | MIT | prior art to cite (single-agent LLM spacecraft controller, KSP) |
