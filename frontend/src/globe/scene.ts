/** S10 — the globe. Three.js, one scene, everything drawn from the same numbers the
 *  backend computed: satellites are the run's catalogue propagated with SGP4 in a worker,
 *  the Earth turns by GMST, the Sun is where the ephemeris puts it, and a manoeuvre is the
 *  post-burn element set the simulator produced — drawn as a second orbit next to the first.
 *
 *  Frames: TEME/ECI (x, y, z with z polar) → three.js y-up as (x, z, −y). 1 unit = 1000 km. */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { gstime, jday, json2satrec, propagate, sunPos, type SatRec } from "satellite.js";
import PropWorker from "./propagate.worker?worker";

export const KM = 0.001;                       // scene units per km
export const R_E = 6378.137 * KM;

export type Role = "active" | "dead" | "debris" | "rocket_body";
export interface CatObject {
  id: number; name: string; role: Role; operator: string; maneuverable: boolean;
  alt_km: number; inc_deg: number; period_min: number; dv_imposed_mps: number; dv_borne_mps: number;
  omm: Record<string, unknown>;
}
export interface Layers {
  skybox: boolean; darkSide: boolean; clouds: boolean; countries: boolean; grid: boolean;
  spotlight: boolean; orbits: boolean; labels: boolean; atmosphere: boolean;
  active: boolean; dead: boolean; debris: boolean; rocket_body: boolean; billedOnly: boolean;
}
export const DEFAULT_LAYERS: Layers = {
  skybox: true, darkSide: true, clouds: true, countries: false, grid: false, spotlight: true, orbits: true,
  labels: true, atmosphere: true, active: true, dead: true, debris: true, rocket_body: true, billedOnly: false,
};

export const ROLE_COLOR: Record<Role, string> = {
  active: "#8fc2ff", dead: "#a996d6", debris: "#c98e5a", rocket_body: "#9aa3ad",
};
const BILLED = "#ffb547", BORNE = "#4dd0c1", SELECT = "#ffffff", PARTNER = "#ff6b6b", AFTER = "#4dd0c1", BEFORE = "#7d8794";

export function temeToScene(x: number, y: number, z: number, out = new THREE.Vector3()): THREE.Vector3 {
  return out.set(x * KM, z * KM, -y * KM);
}

function circleTexture(): THREE.Texture {
  const c = document.createElement("canvas"); c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,1)"); grad.addColorStop(0.45, "rgba(255,255,255,0.95)");
  grad.addColorStop(0.6, "rgba(255,255,255,0.25)"); grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

function labelSprite(text: string, color = "#e6edf5"): THREE.Sprite {
  const c = document.createElement("canvas"); const g = c.getContext("2d")!;
  g.font = "600 26px JetBrains Mono, Menlo, monospace";
  const w = Math.ceil(g.measureText(text).width) + 28; c.width = w; c.height = 44;
  g.font = "600 26px JetBrains Mono, Menlo, monospace";
  g.fillStyle = "rgba(5,7,10,0.72)"; g.fillRect(0, 0, w, 44);
  g.strokeStyle = "rgba(230,237,245,0.25)"; g.strokeRect(0.5, 0.5, w - 1, 43);
  g.fillStyle = color; g.textBaseline = "middle"; g.fillText(text, 14, 23);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false, transparent: true }));
  s.scale.set((w / 44) * 0.42, 0.42, 1); s.center.set(-0.08, 0.5); s.renderOrder = 20;
  return s;
}

const EARTH_VS = `
varying vec2 vUv; varying vec3 vN; varying vec3 vP;
void main(){ vUv = uv; vN = normalize(mat3(modelMatrix) * normal); vP = (modelMatrix * vec4(position,1.0)).xyz;
  gl_Position = projectionMatrix * viewMatrix * vec4(vP, 1.0); }`;
const EARTH_FS = `
uniform sampler2D dayMap, nightMap, specMap; uniform vec3 sunDir; uniform float darkSide, spot; uniform vec3 camPos;
varying vec2 vUv; varying vec3 vN; varying vec3 vP;
void main(){
  vec3 n = normalize(vN);
  float d = dot(n, sunDir);
  float lit = spot > 0.5 ? clamp(d, 0.0, 1.0) : 0.75;
  float k = spot > 0.5 ? smoothstep(-0.08, 0.22, d) : 1.0;
  vec3 day = texture2D(dayMap, vUv).rgb * (0.06 + 1.05 * lit);
  vec3 night = texture2D(nightMap, vUv).rgb * (darkSide > 0.5 ? 1.25 : 0.0) + texture2D(dayMap, vUv).rgb * 0.035;
  vec3 col = mix(night, day, k);
  vec3 v = normalize(camPos - vP); vec3 h = normalize(v + sunDir);
  float s = texture2D(specMap, vUv).r;
  col += vec3(0.55, 0.62, 0.7) * s * pow(max(dot(n, h), 0.0), 38.0) * k * spot * 0.7;
  gl_FragColor = vec4(col, 1.0);
}`;
const ATMO_VS = `varying vec3 vN; varying vec3 vP; void main(){ vN = normalize(mat3(modelMatrix)*normal); vP=(modelMatrix*vec4(position,1.0)).xyz; gl_Position = projectionMatrix*viewMatrix*vec4(vP,1.0);}`;
const ATMO_FS = `uniform vec3 camPos; uniform vec3 sunDir; varying vec3 vN; varying vec3 vP;
void main(){ vec3 v = normalize(camPos - vP); float f = pow(1.0 - max(dot(v, normalize(vN)), 0.0), 3.2);
  float lit = 0.35 + 0.65 * clamp(dot(normalize(vN), sunDir) + 0.35, 0.0, 1.0);
  gl_FragColor = vec4(vec3(0.35, 0.6, 1.0) * f * lit * 1.6, f * 0.9); }`;

export interface Pick { id: number; name: string }

export class GlobeScene {
  readonly scene = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  readonly renderer: THREE.WebGLRenderer;
  readonly controls: OrbitControls;
  readonly earth = new THREE.Group();              // rotates with GMST; ECEF children live here
  private earthMat!: THREE.ShaderMaterial;
  private atmoMat!: THREE.ShaderMaterial;
  private clouds!: THREE.Mesh;
  private atmo!: THREE.Mesh;
  private stars!: THREE.Points;
  private grid!: THREE.LineSegments;
  private countries: THREE.LineSegments | null = null;
  private sun = new THREE.DirectionalLight(0xffffff, 2.2);
  private sunDir = new THREE.Vector3(1, 0, 0);

  // catalogue
  objects: CatObject[] = [];
  private index = new Map<number, number>();
  private pts!: THREE.Points;
  private ptGeo = new THREE.BufferGeometry();
  private ptPos = new Float32Array(0);
  private ptCol = new Float32Array(0);
  private ptSize = new Float32Array(0);
  private basePos = new Float32Array(0);         // km, TEME, at stateT
  private baseVel = new Float32Array(0);
  private ok = new Uint8Array(0);
  private stateT = 0;
  private worker: Worker | null = null;
  private seq = 0;
  private busy = false;
  private lastTick = 0;
  private satrecs = new Map<number, SatRec>();

  // time
  simT = Date.now();
  speed = 1;
  playing = true;
  private lastFrame = performance.now();

  // overlays
  private overlay = new THREE.Group();
  private labels = new THREE.Group();
  private selectedId: number | null = null;
  private highlight: THREE.Sprite;
  private partnerLine: THREE.Line | null = null;
  private pairIds: [number, number] | null = null;
  private ghosts: { id: number; rec: SatRec; mesh: THREE.Sprite; from: number }[] = [];
  layers: Layers = { ...DEFAULT_LAYERS };
  onPick: ((p: Pick | null) => void) | null = null;
  onSeparation: ((km: number | null) => void) | null = null;
  private raycaster = new THREE.Raycaster();
  private raf = 0;
  private tex = circleTexture();

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.05;
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.01, 4000);
    this.camera.position.set(14, 7, 16);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true; this.controls.dampingFactor = 0.06;
    this.controls.minDistance = R_E * 1.08; this.controls.maxDistance = 120; this.controls.zoomSpeed = 0.8;
    this.scene.background = new THREE.Color(0x02030a);
    this.scene.add(this.earth, this.overlay, this.labels, this.sun, new THREE.AmbientLight(0xffffff, 0.12));
    this.highlight = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.tex, color: SELECT, depthTest: false, transparent: true, opacity: 0.95 }));
    this.highlight.scale.setScalar(0.42); this.highlight.visible = false; this.highlight.renderOrder = 10;
    this.scene.add(this.highlight);
    this.buildEarth(); this.buildStars(); this.buildGrid(); this.buildPoints();
    this.raycaster.params.Points = { threshold: 0.12 };
    canvas.addEventListener("pointerdown", (e) => { this.downAt = [e.clientX, e.clientY]; });
    canvas.addEventListener("pointerup", (e) => this.click(e));
    this.loop = this.loop.bind(this);
    this.raf = requestAnimationFrame(this.loop);
  }
  private downAt: [number, number] = [0, 0];

  // ── construction ──────────────────────────────────────────────────────────────────────
  private buildEarth() {
    const L = new THREE.TextureLoader();
    const day = L.load("/textures/earth_atmos_2048.jpg"), night = L.load("/textures/earth_lights_2048.png"),
      spec = L.load("/textures/earth_specular_2048.jpg"), cl = L.load("/textures/earth_clouds_1024.png");
    day.colorSpace = THREE.SRGBColorSpace; night.colorSpace = THREE.SRGBColorSpace;
    for (const t of [day, night, spec, cl]) t.anisotropy = 8;
    this.earthMat = new THREE.ShaderMaterial({
      vertexShader: EARTH_VS, fragmentShader: EARTH_FS,
      uniforms: { dayMap: { value: day }, nightMap: { value: night }, specMap: { value: spec }, sunDir: { value: this.sunDir },
                  darkSide: { value: 1 }, spot: { value: 1 }, camPos: { value: this.camera.position } },
    });
    const globe = new THREE.Mesh(new THREE.SphereGeometry(R_E, 128, 96), this.earthMat);
    this.earth.add(globe);
    this.clouds = new THREE.Mesh(new THREE.SphereGeometry(R_E * 1.006, 96, 72),
      new THREE.MeshLambertMaterial({ map: cl, transparent: true, opacity: 0.55, depthWrite: false }));
    this.earth.add(this.clouds);
    this.atmoMat = new THREE.ShaderMaterial({ vertexShader: ATMO_VS, fragmentShader: ATMO_FS, side: THREE.BackSide, transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false, uniforms: { camPos: { value: this.camera.position }, sunDir: { value: this.sunDir } } });
    this.atmo = new THREE.Mesh(new THREE.SphereGeometry(R_E * 1.045, 96, 72), this.atmoMat);
    this.scene.add(this.atmo);
  }
  private buildStars() {
    const n = 6000, p = new Float32Array(n * 3), c = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, r = 900;
      const s = Math.sqrt(1 - u * u);
      p[i * 3] = r * s * Math.cos(th); p[i * 3 + 1] = r * u; p[i * 3 + 2] = r * s * Math.sin(th);
      const b = 0.35 + Math.random() * 0.65, w = Math.random();
      c[i * 3] = b * (0.85 + 0.15 * w); c[i * 3 + 1] = b * (0.85 + 0.1 * w); c[i * 3 + 2] = b;
    }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(p, 3)); g.setAttribute("color", new THREE.BufferAttribute(c, 3));
    this.stars = new THREE.Points(g, new THREE.PointsMaterial({ size: 2.2, sizeAttenuation: false, vertexColors: true, map: this.tex, transparent: true, depthWrite: false }));
    this.scene.add(this.stars);
  }
  private buildGrid() {
    const v: number[] = [], R = R_E * 1.002;
    const push = (lat: number, lon: number) => { const la = lat * Math.PI / 180, lo = lon * Math.PI / 180; v.push(R * Math.cos(la) * Math.cos(lo), R * Math.sin(la), -R * Math.cos(la) * Math.sin(lo)); };
    for (let lat = -60; lat <= 60; lat += 30) for (let lon = -180; lon < 180; lon += 3) { push(lat, lon); push(lat, lon + 3); }
    for (let lon = -180; lon < 180; lon += 30) for (let lat = -90; lat < 90; lat += 3) { push(lat, lon); push(lat + 3, lon); }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(v, 3));
    this.grid = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x3a4b60, transparent: true, opacity: 0.5 }));
    this.grid.visible = false; this.earth.add(this.grid);
  }
  async loadCountries() {
    if (this.countries) return;
    const gj = await (await fetch("/data/countries-110m.geojson")).json();
    const v: number[] = [], R = R_E * 1.0015;
    const ring = (coords: number[][]) => {
      for (let i = 0; i + 1 < coords.length; i++) {
        for (const [lon, lat] of [coords[i], coords[i + 1]]) { const la = lat * Math.PI / 180, lo = lon * Math.PI / 180; v.push(R * Math.cos(la) * Math.cos(lo), R * Math.sin(la), -R * Math.cos(la) * Math.sin(lo)); }
      }
    };
    for (const f of gj.features) {
      const g = f.geometry; if (!g) continue;
      if (g.type === "Polygon") g.coordinates.forEach(ring);
      else if (g.type === "MultiPolygon") g.coordinates.forEach((p: number[][][]) => p.forEach(ring));
    }
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(v, 3));
    this.countries = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0x8fb3d9, transparent: true, opacity: 0.45 }));
    this.countries.visible = this.layers.countries; this.earth.add(this.countries);
  }
  private buildPoints() {
    this.pts = new THREE.Points(this.ptGeo, new THREE.PointsMaterial({ size: 3.6, sizeAttenuation: false, vertexColors: true, map: this.tex, transparent: true, depthWrite: false, alphaTest: 0.05 }));
    this.pts.frustumCulled = false; this.scene.add(this.pts);
  }

  // ── catalogue ─────────────────────────────────────────────────────────────────────────
  setCatalogue(objs: CatObject[]) {
    this.objects = objs; this.index.clear();
    objs.forEach((o, i) => this.index.set(o.id, i));
    const n = objs.length;
    this.ptPos = new Float32Array(n * 3); this.ptCol = new Float32Array(n * 3); this.ptSize = new Float32Array(n);
    this.basePos = new Float32Array(n * 3); this.baseVel = new Float32Array(n * 3); this.ok = new Uint8Array(n);
    this.ptGeo.setAttribute("position", new THREE.BufferAttribute(this.ptPos, 3));
    this.ptGeo.setAttribute("color", new THREE.BufferAttribute(this.ptCol, 3));
    this.recolour();
    this.worker?.terminate();
    this.worker = new PropWorker();
    this.worker.onmessage = (ev) => this.onWorker(ev.data);
    this.worker.postMessage({ type: "load", ids: objs.map((o) => o.id), omm: objs.map((o) => o.omm) });
    this.busy = false; this.lastTick = 0;
    // open on the sunlit side, a little above the equator
    this.updateSun();
    this.camera.position.copy(this.sunDir).multiplyScalar(26).add(new THREE.Vector3(0, 7, 0));
    this.controls.target.set(0, 0, 0);
  }
  recolour() {
    if (!this.objects.length || !this.ptGeo.getAttribute("color")) return;
    const c = new THREE.Color(), L = this.layers;
    for (let i = 0; i < this.objects.length; i++) {
      const o = this.objects[i];
      const show = L[o.role] && (!L.billedOnly || o.dv_imposed_mps > 0 || o.dv_borne_mps > 0);
      if (!show) { this.ptCol[i * 3] = this.ptCol[i * 3 + 1] = this.ptCol[i * 3 + 2] = 0; continue; }
      c.set(o.dv_imposed_mps > 0 ? BILLED : o.dv_borne_mps > 0 ? BORNE : ROLE_COLOR[o.role]);
      const dim = o.role === "debris" ? 0.72 : 1.0;
      this.ptCol[i * 3] = c.r * dim; this.ptCol[i * 3 + 1] = c.g * dim; this.ptCol[i * 3 + 2] = c.b * dim;
    }
    (this.ptGeo.getAttribute("color") as THREE.BufferAttribute).needsUpdate = true;
  }
  private onWorker(m: { type: string; seq?: number; t?: number; pos?: Float32Array<ArrayBuffer>; vel?: Float32Array<ArrayBuffer>; ok?: Uint8Array<ArrayBuffer> }) {
    if (m.type === "state" && m.pos && m.vel && m.ok && m.t !== undefined) {
      this.basePos = m.pos; this.baseVel = m.vel; this.ok = m.ok; this.stateT = m.t;
    }
    this.busy = false;
  }
  private tick(now: number) {
    if (!this.worker || this.busy || this.objects.length === 0) return;
    if (now - this.lastTick < 90) return;
    this.busy = true; this.lastTick = now;
    this.worker.postMessage({ type: "tick", t: this.simT, seq: ++this.seq });
  }
  private updatePositions() {
    if (!this.objects.length || !this.ptGeo.getAttribute("position")) return;
    const dt = (this.simT - this.stateT) / 1000, n = this.objects.length;
    for (let i = 0; i < n; i++) {
      if (!this.ok[i]) { this.ptPos[i * 3] = this.ptPos[i * 3 + 1] = this.ptPos[i * 3 + 2] = 1e6; continue; }
      const x = this.basePos[i * 3] + this.baseVel[i * 3] * dt, y = this.basePos[i * 3 + 1] + this.baseVel[i * 3 + 1] * dt, z = this.basePos[i * 3 + 2] + this.baseVel[i * 3 + 2] * dt;
      this.ptPos[i * 3] = x * KM; this.ptPos[i * 3 + 1] = z * KM; this.ptPos[i * 3 + 2] = -y * KM;
    }
    (this.ptGeo.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
  }
  positionOf(id: number, out = new THREE.Vector3()): THREE.Vector3 | null {
    const i = this.index.get(id); if (i === undefined || !this.ok[i]) return null;
    return out.set(this.ptPos[i * 3], this.ptPos[i * 3 + 1], this.ptPos[i * 3 + 2]);
  }
  private satrec(id: number): SatRec | null {
    let r = this.satrecs.get(id) ?? null;
    if (!r) { const o = this.objects[this.index.get(id) ?? -1]; if (!o) return null; try { r = json2satrec(o.omm as never); } catch { return null; } this.satrecs.set(id, r); }
    return r;
  }
  /** One orbit of `rec` around time t, as scene points. */
  orbitPoints(rec: SatRec, tMs: number, periodMin: number, n = 240): THREE.Vector3[] {
    const out: THREE.Vector3[] = [];
    for (let k = 0; k <= n; k++) {
      const pv = propagate(rec, new Date(tMs + (k / n) * periodMin * 60000));
      const p = pv?.position; if (!p || typeof p === "boolean") continue;
      out.push(temeToScene(p.x, p.y, p.z));
    }
    return out;
  }

  // ── overlays: selection, cluster, manoeuvre ──────────────────────────────────────────
  clearOverlay() {
    this.overlay.clear(); this.labels.clear(); this.pairIds = null; this.partnerLine = null; this.ghosts = [];
  }
  private addLine(points: THREE.Vector3[], color: string, opacity = 0.9, dashed = false): THREE.Line {
    const g = new THREE.BufferGeometry().setFromPoints(points);
    const m = dashed ? new THREE.LineDashedMaterial({ color, transparent: true, opacity, dashSize: 0.12, gapSize: 0.08 })
                     : new THREE.LineBasicMaterial({ color, transparent: true, opacity });
    const l = new THREE.Line(g, m); if (dashed) l.computeLineDistances(); this.overlay.add(l); return l;
  }
  private addMarker(p: THREE.Vector3, color: string, scale = 0.3, text?: string) {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.tex, color, depthTest: false, transparent: true }));
    s.position.copy(p); s.scale.setScalar(scale); s.renderOrder = 9; this.overlay.add(s);
    if (text) { const l = labelSprite(text, color); l.position.copy(p); this.labels.add(l); }
  }
  select(id: number | null) {
    this.selectedId = id;
    if (id === null) { this.highlight.visible = false; this.onPick?.(null); return; }
    const o = this.objects[this.index.get(id) ?? -1]; if (!o) return;
    this.onPick?.({ id, name: o.name });
  }
  /** The selected object's orbit and label. */
  drawSelected() {
    const id = this.selectedId; if (id === null) return;
    const o = this.objects[this.index.get(id)!], rec = this.satrec(id); if (!rec) return;
    if (this.layers.orbits) this.addLine(this.orbitPoints(rec, this.simT, o.period_min), SELECT, 0.55);
    const p = this.positionOf(id); if (p && this.layers.labels) { const l = labelSprite(o.name); l.position.copy(p); this.labels.add(l); }
  }
  /** A risk cluster: members labelled, conjunction edges drawn at their TCA positions. */
  drawCluster(geom: { members: number[]; keystone_id: number | null; max_pc_object_id: number | null;
                      edges: { primary_id: number; secondary_id: number; tca: string; miss_m: number; pc: number | null; critical: boolean; r_teme_km: number[] }[] }) {
    for (const m of geom.members) {
      const o = this.objects[this.index.get(m) ?? -1]; const rec = this.satrec(m); if (!o || !rec) continue;
      const col = m === geom.keystone_id ? BILLED : m === geom.max_pc_object_id ? PARTNER : ROLE_COLOR[o.role];
      if (this.layers.orbits) this.addLine(this.orbitPoints(rec, this.simT, o.period_min, 160), col, m === geom.keystone_id || m === geom.max_pc_object_id ? 0.6 : 0.22);
      const p = this.positionOf(m); if (p && this.layers.labels) { const l = labelSprite((m === geom.keystone_id ? "◆ " : m === geom.max_pc_object_id ? "● " : "") + o.name, col); l.position.copy(p); this.labels.add(l); }
    }
    for (const e of geom.edges) {
      const p = temeToScene(e.r_teme_km[0], e.r_teme_km[1], e.r_teme_km[2]);
      this.addMarker(p, e.critical ? PARTNER : "#e0a458", e.critical ? 0.34 : 0.2,
        e.critical ? `TCA ${e.tca.slice(5, 16)}Z · ${Math.round(e.miss_m)} m · Pc ${e.pc?.toExponential(1)}` : undefined);
    }
  }
  /** A manoeuvre: the mover's orbit before (grey, dashed) and after (teal), the burn point, and
   *  a ghost point that flies the post-burn element set so the two can be watched diverge. */
  drawStrategy(geom: { burns: { target_id: number; t_burn: string; magnitude_mps: number; r_teme_km: number[]; dv_rtn_mps: number[] }[]; omm_after: Record<string, Record<string, unknown>> }) {
    for (const b of geom.burns) {
      const o = this.objects[this.index.get(b.target_id) ?? -1]; const rec = this.satrec(b.target_id); if (!o || !rec) continue;
      const tb = Date.parse(b.t_burn);
      this.addLine(this.orbitPoints(rec, tb, o.period_min), BEFORE, 0.7, true);
      const p = temeToScene(b.r_teme_km[0], b.r_teme_km[1], b.r_teme_km[2]);
      const [r, t, n] = b.dv_rtn_mps;
      this.addMarker(p, AFTER, 0.36, `BURN ${o.name} · ${b.magnitude_mps.toFixed(3)} m/s · RTN(${r.toFixed(2)},${t.toFixed(2)},${n.toFixed(2)}) · ${b.t_burn.slice(5, 16)}Z`);
    }
    for (const [idStr, omm] of Object.entries(geom.omm_after)) {
      const id = Number(idStr), o = this.objects[this.index.get(id) ?? -1]; if (!o) continue;
      let rec: SatRec; try { rec = json2satrec(omm as never); } catch { continue; }
      const from = Math.min(...geom.burns.filter((b) => b.target_id === id).map((b) => Date.parse(b.t_burn)));
      this.addLine(this.orbitPoints(rec, Math.max(from, this.simT), o.period_min), AFTER, 0.95);
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.tex, color: AFTER, depthTest: false, transparent: true }));
      s.scale.setScalar(0.3); s.renderOrder = 11; this.overlay.add(s);
      this.ghosts.push({ id, rec, mesh: s, from });
    }
  }
  /** Watch two objects approach: a line between them and the live separation. */
  watchPair(a: number, b: number) {
    this.pairIds = [a, b];
    this.partnerLine = this.addLine([new THREE.Vector3(), new THREE.Vector3()], PARTNER, 0.9);
  }
  focus(id: number, distance = 2.2) {
    const p = this.positionOf(id); if (!p) return;
    this.controls.target.copy(p);
    const dir = p.clone().normalize();
    this.camera.position.copy(p.clone().add(dir.multiplyScalar(distance)).add(new THREE.Vector3(0.6, 0.9, 0.6)));
  }
  focusEarth() { this.controls.target.set(0, 0, 0); }

  // ── per frame ─────────────────────────────────────────────────────────────────────────
  private updateSun() {
    const d = new Date(this.simT);
    const jd = jday(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate(), d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds() + d.getUTCMilliseconds() / 1000);
    const { rsun } = sunPos(jd);
    temeToScene(rsun.x, rsun.y, rsun.z, this.sunDir).normalize();
    this.sun.position.copy(this.sunDir).multiplyScalar(100);
    this.earth.rotation.y = gstime(d);
    this.clouds.rotation.y = (this.simT / 1000) * 2.0e-6;   // slow drift relative to the ground
  }
  setLayers(L: Layers) {
    this.layers = { ...L };
    this.stars.visible = L.skybox; this.clouds.visible = L.clouds; this.grid.visible = L.grid; this.atmo.visible = L.atmosphere;
    if (this.countries) this.countries.visible = L.countries; else if (L.countries) void this.loadCountries();
    this.earthMat.uniforms.darkSide.value = L.darkSide ? 1 : 0; this.earthMat.uniforms.spot.value = L.spotlight ? 1 : 0;
    this.sun.intensity = L.spotlight ? 2.2 : 0.9;
    this.recolour();
  }
  private loop(now: number) {
    this.raf = requestAnimationFrame(this.loop);
    const dt = Math.min(now - this.lastFrame, 100); this.lastFrame = now;
    if (this.playing) this.simT += dt * this.speed;
    this.tick(now); this.updatePositions(); this.updateSun();
    if (this.selectedId !== null) { const p = this.positionOf(this.selectedId); if (p) { this.highlight.position.copy(p); this.highlight.visible = true; } }
    for (const g of this.ghosts) {
      if (this.simT < g.from) { g.mesh.visible = false; continue; }
      const pv = propagate(g.rec, new Date(this.simT)); const p = pv?.position;
      if (p && typeof p !== "boolean") { g.mesh.position.copy(temeToScene(p.x, p.y, p.z)); g.mesh.visible = true; }
    }
    if (this.pairIds && this.partnerLine) {
      const a = this.positionOf(this.pairIds[0]), b = this.positionOf(this.pairIds[1]);
      if (a && b) {
        const pos = this.partnerLine.geometry.getAttribute("position") as THREE.BufferAttribute;
        pos.setXYZ(0, a.x, a.y, a.z); pos.setXYZ(1, b.x, b.y, b.z); pos.needsUpdate = true;
        this.onSeparation?.(a.distanceTo(b) / KM);
      }
    }
    // labels follow their object when it moves (cluster labels are re-drawn on demand)
    const dist = this.camera.position.length();
    const s = THREE.MathUtils.clamp(dist / 30, 0.35, 1.6);
    this.labels.children.forEach((l) => { const sp = l as THREE.Sprite; sp.scale.set(sp.scale.x / (sp.userData.s ?? 1) * s, 0.42 * s, 1); sp.userData.s = s; });
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
  resize(w: number, h: number) {
    this.renderer.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }
  private click(e: PointerEvent) {
    const [x0, y0] = this.downAt; if (Math.hypot(e.clientX - x0, e.clientY - y0) > 4) return;
    const rect = (e.target as HTMLCanvasElement).getBoundingClientRect();
    const m = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(m, this.camera);
    this.raycaster.params.Points = { threshold: 0.05 * Math.max(1, this.camera.position.length() / 8) };
    const hits = this.raycaster.intersectObject(this.pts, false).filter((h) => h.index !== undefined && this.ok[h.index] && (this.ptCol[h.index * 3] + this.ptCol[h.index * 3 + 1] + this.ptCol[h.index * 3 + 2]) > 0);
    if (!hits.length) { this.select(null); return; }
    hits.sort((a, b) => (a.distanceToRay ?? 0) - (b.distanceToRay ?? 0));
    this.select(this.objects[hits[0].index!].id);
  }
  dispose() { cancelAnimationFrame(this.raf); this.worker?.terminate(); this.renderer.dispose(); this.controls.dispose(); }
}
