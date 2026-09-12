# Visual bible — the look we are building, and the recipe for every piece of it

Written 2026-09-12 after reading the rendering code of 16 repos. Companion to
`frontend-research.md` (stack + layout). This file is about **pixels**: what the globe,
the light, the lines, the panels and the motion look like, and exactly how each effect
is made. Every technique below was read from source in `inspiration/` and will be
**re-implemented in our own files**. Nothing is copied. AGPL repos (keeptrack, satvisor,
TLEscope) are technique-only, never code.

Reference screenshots: `docs/references/` (pulled from each repo's README — kept local, not committed: they are third-party images).

## 1. The three looks that exist, and the one we make

| Family | Best example | What it does well | What it does badly |
|---|---|---|---|
| **Plotted** (wireframe Earth, point cloud) | kessler | data-honest, points are the hero, unique, cheap to render | can feel cold / "just a chart" in a 60-second video |
| **Cinematic** (photoreal Earth, bloom, sunset limb) | satvisor, threejs-earth | jaw-drop factor, judges *feel* space | textures fight the data; 26 MB downloads; everyone's seen a blue marble |
| **Ops console** (windowed mono panels, live numbers) | satvisor UI, TLEscope, OpenMCT | reads as real tooling, "someone would use this" | busy; too many windows = template feel |

**Ours = plotted globe by default, cinematic *lighting* on top, ops-console panels around it,
and one cinematic hero moment when a conjunction is selected.** Concretely:

- Earth is a dark sphere with **Fibonacci-lattice land dots** (cobe's idea) — not a photo.
- It still has a **real sun**: terminator, sunset band, Fresnel atmosphere, night-side
  city-light dots, half-res bloom. So the plotted globe *feels* lit like the cinematic one.
- 19k catalog objects as soft round points, colour = class only (kessler's rule).
- When an encounter is selected: camera flies in, everything else fades to 15 %, the two
  objects get rings + orbit arcs + bloom, the post-burn arc draws on in teal.
- Panels are translucent plates anchored to viewport edges, JetBrains Mono numbers.

## 2. Globe recipes (each one is a small file in our repo)

### 2.1 Dotted land (from `inspiration/cobe/src/globe.frag.glslx`, MIT)
cobe generates a **Fibonacci lattice** on the sphere in the fragment shader and lights a
dot only where a land-mask texture is white. We do the same on the CPU once at startup:

```
N ≈ 40 000 points;  i = 0..N-1
y  = 1 - 2(i + 0.5)/N          // -1..1
r  = sqrt(1 - y²)
θ  = i · golden angle (2.399963)
p  = (r cos θ, y, r sin θ)
keep p if landMask(lon(p), lat(p)) > 0.5      // 2048×1024 black/white PNG
```
→ one `THREE.Points` of ~12k land dots, size ~1.6 px, colour `#8a93a0` at 0.9 alpha,
lit by `pow(max(dot(n, sunDir), 0), 0.6)` so the night side dims to ~20 %.
Ocean = the dark shell sphere (`#0b1a26`). Optional thin graticule every 30° at 0.35 alpha.

### 2.2 Atmosphere (from `inspiration/satvisor/src/scene/atmosphere.ts`, AGPL → technique only)
Second sphere at **R + 80 km**, `side: BackSide`, `transparent`, `depthWrite: false`.
```
NdotV   = clamp(dot(-N, V), 0, 1)           // normal flipped for BackSide
NdotL   = dot(N, sunDir)
fresnel = pow(1 - NdotV, 3.5)
sunBlend = smoothstep(-0.3, 0.3, NdotL);  brightness = mix(0.15, 1.0, sunBlend)
day     = (0.15, 0.45, 1.0);  sunset = (1.0, 0.5, 0.2)
colour  = mix(day, sunset, smoothstep(0.35, -0.15, NdotL))          // sunset near terminator
colour  = mix(colour, (0.7, 0.85, 1.0), pow(fresnel, 1.5) * 0.7)     // limb whitening
colour += (1, 0.6, 0.3) * pow(max(dot(V, sunDir), 0), 8) * 0.15 * sunBlend  // forward scatter
alpha   = fresnel * smoothstep(0, 0.25, NdotV) * brightness * 2
```
With bloom on, push `strength` to ~5 and drop limb whitening — bloom does the whitening.

### 2.3 Sun / terminator on the plotted globe (from satvisor `earth-daynight.frag.glsl` + keeptrack `earth.ts:1132`)
We have no day texture, so the terminator is applied to the **dots and the shell**:
```
intensity = dot(N, sunDir)
blend     = smoothstep(-0.15, 0.15, intensity)             // day/night mix
scatter   = smoothstep(-0.15, 0.25, i) * smoothstep(0.25, -0.15, i)   // band around terminator
sunset    = mix((0.85, 0.2, 0.08), (1.0, 0.55, 0.2), smoothstep(-0.12, 0.12, i))
shellColour = mix(nightShell, dayShell, blend) + sunset * scatter * 0.12
rim       = pow(1 - dot(N, V), 3.5) * smoothstep(-0.1, 0.3, i);  shellColour += (0.15, 0.45, 1.0) * rim * 0.6
```
Night-side city lights: a second, sparser dot set (~3k) from a night-lights mask, shown
only where `blend < 0.5`, colour `#e8c27a`, HDR value 1.6 so bloom catches them.

Sun direction: from sim time. Backend gives it (Skyfield) or the worker computes it with
the standard low-precision solar position (good to 0.01°, 15 lines).

### 2.4 Catalog points (from `inspiration/kessler/web/src/globe.ts`, MIT)
One `THREE.Points`, attributes `position | colour | size | alpha`, `DynamicDrawUsage`.
- Vertex: `gl_PointSize = clamp(size * dpr * (28 / -view.z), dpr, 20 * dpr)`
- Fragment: `d = dot(pc - 0.5, pc - 0.5); if (d > 0.25) discard; a = smoothstep(0.25, 0.06, d)`
- Per-frame: `pos += vel * dt` between worker frames (worker runs SGP4 every ~500 ms).
- Selection = **ring**, separate 2-point `Points` (annulus fragment: keep `0.34 < d < 0.5`).
- Dead objects parked at `y = -1e6`, never removed — index is identity.
- New: an `alpha` attribute so we can fade the whole population to 0.15 when an encounter
  is focused (satvisor does this: "unselectedFade").

### 2.5 Orbit arcs (satvisor `orbit-renderer.ts` → uses `Line2`/`LineMaterial`)
`Line2` + `LineMaterial` (screen-space width, `linewidth: 2`, `vertexColors`) so lines have
real thickness and per-vertex alpha. One full period, 256 samples, alpha fades from 1 at
the object to 0.15 at the far side of the orbit. Post-burn arc: `dashed: true,
dashSize 0.06, gapSize 0.025`, teal. Draw-on animation = animate `maxInstancedCount`
(or a `uProgress` uniform) over 600 ms.

### 2.6 Bloom (satvisor `post-processing.ts`)
`EffectComposer → RenderPass → UnrealBloomPass(half-res, strength 0.6, radius 0.2,
threshold 0.95) → OutputPass`. In R3F: `@react-three/postprocessing` `<Bloom
luminanceThreshold={0.95} intensity={0.6} mipmapBlur />`. Only HDR values (> 1.0) bloom:
atmosphere, city lights, the two selected objects, the proposed-burn arc. Everything else
stays crisp. Half resolution keeps 60 fps on integrated GPUs.

### 2.7 Stars
Not a texture. 2 000 `Points` on a sphere of radius 200, sizes 0.5–1.5 px, brightness
weighted `pow(random, 3)` so most are faint. Static (no twinkle — twinkle reads as cheap).

### 2.8 Camera
`OrbitControls`, damping 0.08, `minDistance 7.2 / maxDistance 60` (scene unit = 1000 km).
Fly-to on selection: tween camera position toward `normalize(target) * currentDistance * 0.55`
over 900 ms with an ease-out-quart; keep `controls.target` at origin. Slow auto-rotate
(0.15 °/s) only while nothing is selected and no input for 8 s.

## 3. Panels (ops console) — from satvisor `themes/builtins.ts` + kessler `style.css`

- Font: **JetBrains Mono** for every number and label in panels; Inter only for prose.
  (satvisor uses Overpass Mono; TLEscope the same idea in C.)
- Ground `#0d1014`; plate `rgba(13,16,20,0.82)` with `backdrop-filter: blur(8px)`;
  edge `rgba(220,225,232,0.13)` 1 px; text `#dce1e8`; dim `#8a93a0`.
- Panel = title row in 10 px uppercase tracking 0.08em + body. No rounded corners > 4 px.
  No drop shadows. No gradients except the timeline playhead glow.
- Rows: `border-bottom: 1px rgba(255,255,255,0.03)`; hover `0.03`; active `0.05` — satvisor's
  values, they read right.
- Status colours: live `#44ff44`, warning `#ff9944`, danger `#ff6666`, accent `#66aaff`.
  Use them for state only, never decoration.
- Stat tile: label 10 px dim → value 22 px mono → unit 11 px dim, all left-aligned.
- The **honesty block** (bottom-left): snapshot/live, objects screened, propagator, "no
  covariance → no Pc unless you supply σ". Kessler's idea; it wins Q&A.

## 4. Signature moments for the demo video (what the judges remember)

1. **Cold open**: black → stars fade in → atmosphere rim ignites from the sun side →
   19k points fade in over 1.5 s while the counter in the corner runs up to 19,213.
2. **Scrub the day**: drag the spine, the whole cloud moves, terminator sweeps.
3. **Pick an object**: ring snaps on, camera flies in, population dims to 15 %, orbit arc
   draws on, passages list fills, spine grows ticks whose height = miss distance.
4. **Open an encounter**: partner ring in amber, second arc, miss-distance curve drops into
   view under the spine with the TCA at x = 0.
5. **Agents negotiate**: drawer slides up, three avatars, offer cards appear one by one;
   every counter-offer redraws the teal post-burn arc and moves the "after" curve live.
6. **Agreement**: CDM-shaped record renders, fuel ledger ticks down, "approve" pulses once.
7. **Bullseye**: switch to the polar plot — every conjunction in the next 24 h as a dot
   spiralling toward the centre.

## 5. Reference index (what to open when building each piece)

| Piece | Read this | License |
|---|---|---|
| point cloud, ring selection, worker pump, colour discipline | `inspiration/kessler/web/src/{globe,palette,propagate.worker,spine}.ts` | MIT |
| dotted land via Fibonacci lattice | `inspiration/cobe/src/globe.frag.glslx` | MIT |
| atmosphere shader, sunset band, ocean glint, cloud shadows, bloom setup, unselected fade | `inspiration/satvisor/src/scene/{atmosphere,post-processing,orbit-renderer,satellite-manager}.ts`, `src/shaders/earth-daynight.frag.glsl` | **AGPL — technique only** |
| day/night blend + horizon alpha | `inspiration/keeptrack.space/src/engine/rendering/draw-manager/earth.ts:1132-1230` | **AGPL — technique only** |
| hex-polygon land, arcs with dash animation, rings | `inspiration/three-globe/src/` (also usable as an npm dependency if we ever want its arcs) | MIT |
| theme token names and values | `inspiration/satvisor/src/themes/builtins.ts` | AGPL — values are not code, but we pick our own anyway |
| windowed panel UI in C (for layout ideas only) | `inspiration/TLEscope/src/ui.c` | AGPL |
| SSE event feed → terminal lines | `inspiration/detour/frontend/components/terminal-drawer.tsx` | MIT |
| offer / counter / contract protocol | `inspiration/AgenticPay/agenticpay/agents/buyer_agent.py` | MIT |
| classic photoreal earth (day, night, clouds, atmosphere) | `inspiration/threejs-earth/` | MIT |
| orbit lines + starlink highlight look | `inspiration/satellite-tracker/` (screens in `docs/references/satellite-tracker/`) | MIT |

Screenshots: `docs/references/{satvisor,three-globe,cobe,github-globe,satellite-tracker,OrbitsGL,openmct,threejs-earth}/`.

## 6. What we deliberately do NOT do

- No photo Earth texture by default (fights the data; 4–26 MB; every demo has one).
- No CesiumJS. No shadcn. No Recharts. No light theme.
- No twinkling stars, no lens flares, no rotating "hologram" rings, no neon grid floors.
- No more than three signal colours on the globe at once (selected / partner / proposed).
- No panel with more than one job.
