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
  labels: true, atmosphere: true, active: true, dead: true, debris: true, rocket_body: true, billedOnly: true,
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

/** A small satellite glyph: bus, two panels, a boom — drawn once, used by every payload. */
function satelliteTexture(): THREE.Texture {
  const c = document.createElement("canvas"); c.width = c.height = 64;
  const g = c.getContext("2d")!;
  g.translate(32, 32); g.rotate(-Math.PI / 5);
  g.shadowColor = "rgba(255,255,255,0.9)"; g.shadowBlur = 5;
  g.fillStyle = "rgba(255,255,255,0.7)";
  g.fillRect(-27, -5, 19, 10); g.fillRect(8, -5, 19, 10);           // panels
  g.fillStyle = "#ffffff"; g.fillRect(-7, -7, 14, 14);              // bus
  g.fillRect(-1, -14, 2, 7);                                        // boom
  g.strokeStyle = "rgba(0,0,0,0.55)"; g.lineWidth = 1.2;
  g.strokeRect(-27, -5, 19, 10); g.strokeRect(8, -5, 19, 10); g.strokeRect(-7, -7, 14, 14);
  g.strokeStyle = "rgba(0,0,0,0.35)"; for (const x of [-21, -15, 14, 20]) { g.beginPath(); g.moveTo(x, -5); g.lineTo(x, 5); g.stroke(); }
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
  float lit = spot > 0.5 ? clamp(d, 0.0, 1.0) : 0.85;
  float k = spot > 0.5 ? smoothstep(-0.12, 0.25, d) : 1.0;
  vec3 tex = texture2D(dayMap, vUv).rgb;
  vec3 day = tex * (0.28 + 0.95 * lit);
  vec3 night = texture2D(nightMap, vUv).rgb * (darkSide > 0.5 ? 1.1 : 0.0) + tex * 0.16;
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
  private glyphs!: THREE.Points;                 // payloads drawn as satellite glyphs
  private glyphGeo = new THREE.BufferGeometry();
  private glyphIdx: number[] = [];               // glyph vertex → catalogue index
  private hidden = new Uint8Array(0);            // layer-hidden objects are moved off-screen, never drawn black
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
  /** The objects the current story is about (cluster members, the pair being watched…) —
   *  with "story objects only" on, these plus every ledger object and the stations are drawn. */
  storyIds = new Set<number>();
  onPick: ((p: Pick | null) => void) | null = null;
  onHover: ((h: { id: number; name: string; alt_km: number; speed_kms: number; x: number; y: number } | null) => void) | null = null;
  onTelemetry: ((t: { alt_km: number; speed_kms: number; lat: number; lon: number } | null) => void) | null = null;
  private track: THREE.Line | null = null;
  private satTex = satelliteTexture();
  private hoverAt = 0;
  private hoverId: number | null = null;
  private hoverGroup = new THREE.Group();
  private model: THREE.Group | null = null;      // 3D satellite on the selected object
  onSeparation: ((km: number | null) => void) | null = null;
  private raycaster = new THREE.Raycaster();
  private raf = 0;
  private tex = circleTexture();

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.35;
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.01, 4000);
    this.camera.position.set(14, 7, 16);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true; this.controls.dampingFactor = 0.06;
    this.controls.minDistance = R_E * 1.08; this.controls.maxDistance = 120; this.controls.zoomSpeed = 0.8;
    this.scene.background = new THREE.Color(0x02030a);
    this.scene.add(this.earth, this.overlay, this.labels, this.sun, new THREE.AmbientLight(0xffffff, 0.35));
    this.highlight = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.tex, color: SELECT, depthTest: false, transparent: true, opacity: 0.95 }));
    this.highlight.scale.setScalar(0.42); this.highlight.visible = false; this.highlight.renderOrder = 10;
    this.scene.add(this.highlight, this.hoverGroup);
    this.buildEarth(); this.buildStars(); this.buildGrid(); this.buildPoints();
    this.raycaster.params.Points = { threshold: 0.12 };
    canvas.addEventListener("pointerdown", (e) => { this.downAt = [e.clientX, e.clientY]; });
    canvas.addEventListener("pointerup", (e) => this.click(e));
    canvas.addEventListener("pointermove", (e) => this.hover(e));
    canvas.addEventListener("pointerleave", () => this.onHover?.(null));
    this.loop = this.loop.bind(this);
    this.raf = requestAnimationFrame(this.loop);
  }
  private downAt: [number, number] = [0, 0];

  // ── construction ──────────────────────────────────────────────────────────────────────
  private buildEarth() {
    const L = new THREE.TextureLoader();
    const day = L.load("/textures/world_5400.jpg"), night = L.load("/textures/earth_lights_2048.png"),
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
      new THREE.MeshLambertMaterial({ map: cl, transparent: true, opacity: 0.45, depthWrite: false, emissive: 0x9aa4b0, emissiveIntensity: 0.25 }));
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
    this.pts = new THREE.Points(this.ptGeo, new THREE.PointsMaterial({ size: 3.0, sizeAttenuation: false, vertexColors: true, map: this.tex, transparent: true, depthWrite: false, alphaTest: 0.05 }));
    this.pts.frustumCulled = false; this.scene.add(this.pts);
    this.glyphs = new THREE.Points(this.glyphGeo, new THREE.PointsMaterial({ size: 10, sizeAttenuation: false, vertexColors: true, map: this.satTex, transparent: true, depthWrite: false, alphaTest: 0.1 }));
    this.glyphs.frustumCulled = false; this.scene.add(this.glyphs);
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
    this.hidden = new Uint8Array(n);
    this.glyphIdx = objs.map((o, i) => (o.role === "active" || o.role === "dead" ? i : -1)).filter((i) => i >= 0);
    this.glyphGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(this.glyphIdx.length * 3), 3));
    this.glyphGeo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(this.glyphIdx.length * 3), 3));
    this.satrecs.clear();
    this.recolour();
    this.worker?.terminate();
    this.worker = new PropWorker();
    this.worker.onmessage = (ev) => this.onWorker(ev.data);
    this.worker.postMessage({ type: "load", ids: objs.map((o) => o.id), omm: objs.map((o) => o.omm) });
    this.busy = false; this.lastTick = 0;
    this.lookAtSunlitSide();
  }
  recolour() {
    if (!this.objects.length || !this.ptGeo.getAttribute("color")) return;
    const c = new THREE.Color(), L = this.layers;
    for (let i = 0; i < this.objects.length; i++) {
      const o = this.objects[i];
      // "story objects only": the cluster, the ledger objects (billing or paying) and the stations
      const inStory = this.storyIds.has(o.id) || o.dv_imposed_mps > 0 || o.dv_borne_mps > 0 || o.operator === "ISS" || /^(ISS|CSS|TIANHE)/.test(o.name);
      const show = L[o.role] && (!L.billedOnly || inStory);
      this.hidden[i] = show ? 0 : 1;
      c.set(o.dv_imposed_mps > 0 ? BILLED : o.dv_borne_mps > 0 ? BORNE : ROLE_COLOR[o.role]);
      const dim = o.role === "debris" ? 0.7 : 1.0;
      this.ptCol[i * 3] = c.r * dim; this.ptCol[i * 3 + 1] = c.g * dim; this.ptCol[i * 3 + 2] = c.b * dim;
    }
    const gc = this.glyphGeo.getAttribute("color") as THREE.BufferAttribute | undefined;
    if (gc) {
      for (let k = 0; k < this.glyphIdx.length; k++) {
        const i = this.glyphIdx[k];
        gc.setXYZ(k, this.ptCol[i * 3], this.ptCol[i * 3 + 1], this.ptCol[i * 3 + 2]);
      }
      gc.needsUpdate = true;
    }
    (this.ptGeo.getAttribute("color") as THREE.BufferAttribute).needsUpdate = true;
  }
  private isGlyph(i: number): boolean { const r = this.objects[i].role; return r === "active" || r === "dead"; }
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
    const gp = this.glyphGeo.getAttribute("position") as THREE.BufferAttribute | undefined;
    for (let i = 0; i < n; i++) {
      if (!this.ok[i] || this.hidden[i]) { this.ptPos[i * 3] = this.ptPos[i * 3 + 1] = this.ptPos[i * 3 + 2] = 1e6; continue; }
      const x = this.basePos[i * 3] + this.baseVel[i * 3] * dt, y = this.basePos[i * 3 + 1] + this.baseVel[i * 3 + 1] * dt, z = this.basePos[i * 3 + 2] + this.baseVel[i * 3 + 2] * dt;
      this.ptPos[i * 3] = x * KM; this.ptPos[i * 3 + 1] = z * KM; this.ptPos[i * 3 + 2] = -y * KM;
    }
    (this.ptGeo.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
    if (gp) {
      for (let k = 0; k < this.glyphIdx.length; k++) {
        const i = this.glyphIdx[k];
        gp.setXYZ(k, this.ptPos[i * 3], this.ptPos[i * 3 + 1], this.ptPos[i * 3 + 2]);
        // the glyph replaces the dot; park the dot where nobody sees it
        if (!this.hidden[i] && this.ok[i]) { this.ptPos[i * 3] = this.ptPos[i * 3 + 1] = this.ptPos[i * 3 + 2] = 1e6; }
      }
      gp.needsUpdate = true;
    }
  }
  speedOf(id: number): number | null {
    const i = this.index.get(id); if (i === undefined || !this.ok[i]) return null;
    return Math.hypot(this.baseVel[i * 3], this.baseVel[i * 3 + 1], this.baseVel[i * 3 + 2]);
  }
  /** Sub-satellite point (spherical) and altitude right now, from the ECI position and GMST. */
  latLonOf(id: number): { lat: number; lon: number; alt_km: number } | null {
    const p = this.rawPositionOf(id); if (!p) return null;
    const lat = Math.asin(p.y / p.length()) * 180 / Math.PI;
    let lon = (Math.atan2(-p.z, p.x) - this.earth.rotation.y) * 180 / Math.PI;
    lon = ((lon + 540) % 360) - 180;
    return { lat, lon, alt_km: p.length() / KM - 6378.137 };
  }
  /** Position regardless of layer visibility (the dot may be parked off-screen). */
  private rawPositionOf(id: number, out = new THREE.Vector3()): THREE.Vector3 | null {
    const i = this.index.get(id); if (i === undefined || !this.ok[i]) return null;
    const dt = (this.simT - this.stateT) / 1000;
    return out.set((this.basePos[i * 3] + this.baseVel[i * 3] * dt) * KM, (this.basePos[i * 3 + 2] + this.baseVel[i * 3 + 2] * dt) * KM, -(this.basePos[i * 3 + 1] + this.baseVel[i * 3 + 1] * dt) * KM);
  }
  positionOf(id: number, out = new THREE.Vector3()): THREE.Vector3 | null { return this.rawPositionOf(id, out); }
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
    if (this.track) { this.earth.remove(this.track); this.track = null; }
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
    if (id === null) { this.highlight.visible = false; if (this.model) this.model.visible = false; this.onPick?.(null); return; }
    const o = this.objects[this.index.get(id) ?? -1]; if (!o) return;
    this.onPick?.({ id, name: o.name });
  }
  /** The horizon circle an object at scene position p can see. */
  footprintRing(p: THREE.Vector3, color: THREE.ColorRepresentation, opacity: number): THREE.Line {
    const r = p.length(), ang = Math.acos(Math.min(1, R_E / r)), dir = p.clone().normalize();
    let u = new THREE.Vector3(0, 1, 0).cross(dir); if (u.lengthSq() < 1e-6) u = new THREE.Vector3(1, 0, 0).cross(dir); u.normalize();
    const v = dir.clone().cross(u).normalize();
    const ring: THREE.Vector3[] = [];
    for (let k = 0; k <= 96; k++) {
      const th = (k / 96) * Math.PI * 2;
      ring.push(dir.clone().multiplyScalar(Math.cos(ang)).add(u.clone().multiplyScalar(Math.sin(ang) * Math.cos(th))).add(v.clone().multiplyScalar(Math.sin(ang) * Math.sin(th))).multiplyScalar(R_E * 1.004));
    }
    return new THREE.Line(new THREE.BufferGeometry().setFromPoints(ring), new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
  }
  /** A low-poly satellite: bus, two solar wings, a dish and a boom. Sits on the selected object. */
  private buildModel(): THREE.Group {
    const g = new THREE.Group();
    const gold = new THREE.MeshStandardMaterial({ color: 0xc9a84c, metalness: 0.8, roughness: 0.35 });
    const grey = new THREE.MeshStandardMaterial({ color: 0xb8bec6, metalness: 0.6, roughness: 0.4 });
    const panel = new THREE.MeshStandardMaterial({ color: 0x1f3a6e, metalness: 0.3, roughness: 0.25, emissive: 0x0b1e44, emissiveIntensity: 0.4 });
    const bus = new THREE.Mesh(new THREE.BoxGeometry(1, 1.2, 1), gold); g.add(bus);
    for (const sx of [-1, 1]) {
      const wing = new THREE.Mesh(new THREE.BoxGeometry(3.2, 1.1, 0.06), panel); wing.position.set(sx * 2.3, 0, 0); g.add(wing);
      const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.4), grey); arm.rotation.z = Math.PI / 2; arm.position.set(sx * 1.0, 0, 0); g.add(arm);
      for (let k = 0; k < 4; k++) { const seam = new THREE.Mesh(new THREE.BoxGeometry(0.03, 1.1, 0.07), grey); seam.position.set(sx * (1.0 + 0.66 * (k + 0.5)), 0, 0); g.add(seam); }
    }
    const dish = new THREE.Mesh(new THREE.SphereGeometry(0.55, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2.6), grey);
    dish.position.set(0, 0.9, 0.3); dish.rotation.x = -Math.PI / 6; g.add(dish);
    const boom = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 1.6), grey); boom.position.set(0, -1.3, 0); g.add(boom);
    const ant = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.08, 0.5), grey); ant.position.set(0, -2.1, 0); g.add(ant);
    g.visible = false; this.scene.add(g); return g;
  }
  /** The selected object's orbit and label. */
  drawSelected() {
    const id = this.selectedId; if (id === null) return;
    const idx = this.index.get(id); if (idx === undefined) { this.selectedId = null; return; }
    const o = this.objects[idx], rec = this.satrec(id); if (!rec) return;
    if (this.layers.orbits) this.addLine(this.orbitPoints(rec, this.simT, o.period_min), SELECT, 0.6);
    const p = this.positionOf(id);
    if (p && this.layers.labels) {
      const ll = this.latLonOf(id), v = this.speedOf(id);
      const l = labelSprite(`${o.name}  ·  ${ll ? ll.alt_km.toFixed(0) : o.alt_km} km  ·  ${v ? v.toFixed(2) : "—"} km/s`); l.position.copy(p); this.labels.add(l);
    }
    // ground track for one orbit ahead: ECI → ECEF with GMST at each time, drawn on the surface
    const pts: THREE.Vector3[] = [];
    for (let k = 0; k <= 180; k++) {
      const t = this.simT + (k / 180) * o.period_min * 60000;
      const pv = propagate(rec, new Date(t)); const q = pv?.position; if (!q || typeof q === "boolean") continue;
      const g = gstime(new Date(t)); const c = Math.cos(-g), sn = Math.sin(-g);
      const X = q.x * c - q.y * sn, Y = q.x * sn + q.y * c, Z = q.z;      // ECEF, km
      pts.push(new THREE.Vector3(X * KM, Z * KM, -Y * KM).normalize().multiplyScalar(R_E * 1.003));
    }
    if (pts.length > 2) {
      const g = new THREE.BufferGeometry().setFromPoints(pts);
      this.track = new THREE.Line(g, new THREE.LineDashedMaterial({ color: SELECT, transparent: true, opacity: 0.55, dashSize: 0.06, gapSize: 0.05 }));
      this.track.computeLineDistances(); this.earth.add(this.track);
    }
    // horizon footprint: the cap of the Earth this object can see, and its cone
    if (p) {
      const ring = this.footprintRing(p, "#4dd0c1", 0.75); this.overlay.add(ring);
      const pts = (ring.geometry.getAttribute("position") as THREE.BufferAttribute);
      const segs: THREE.Vector3[] = [];
      for (let k = 0; k < pts.count; k += 8) segs.push(p.clone(), new THREE.Vector3(pts.getX(k), pts.getY(k), pts.getZ(k)));
      this.overlay.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(segs), new THREE.LineBasicMaterial({ color: "#4dd0c1", transparent: true, opacity: 0.16 })));
    }
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
  /** Open on the sunlit side, a little above the equator — the Earth people recognise. */
  lookAtSunlitSide(distance = 24) {
    this.updateSun();
    this.camera.position.copy(this.sunDir).multiplyScalar(distance).add(new THREE.Vector3(0, distance * 0.28, 0));
    this.controls.target.set(0, 0, 0);
  }

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
    if (!this.model) this.model = this.buildModel();
    if (this.selectedId !== null) {
      const p = this.positionOf(this.selectedId);
      if (p) {
        this.highlight.position.copy(p); this.highlight.visible = this.camera.position.distanceTo(p) > 4;
        const i = this.index.get(this.selectedId)!;
        const vel = new THREE.Vector3(this.baseVel[i * 3], this.baseVel[i * 3 + 2], -this.baseVel[i * 3 + 1]).normalize();
        this.model.position.copy(p);
        this.model.quaternion.setFromUnitVectors(new THREE.Vector3(1, 0, 0), vel);
        const dist = this.camera.position.distanceTo(p);
        this.model.scale.setScalar(THREE.MathUtils.clamp(dist * 0.012, 0.004, 0.25));
        this.model.visible = dist < 12;
      }
      if (((now / 16) | 0) % 10 === 0) { const ll = this.latLonOf(this.selectedId); this.onTelemetry?.(ll ? { ...ll, speed_kms: this.speedOf(this.selectedId) ?? 0 } : null); }
    }
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
    // glyphs grow as the camera closes in, so a wide shot stays readable and a close shot shows the satellite
    (this.glyphs.material as THREE.PointsMaterial).size = THREE.MathUtils.clamp(150 / dist, 5.5, 16);
    (this.pts.material as THREE.PointsMaterial).size = THREE.MathUtils.clamp(60 / dist, 2.2, 5);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
  resize(w: number, h: number) {
    this.renderer.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }
  private pickAt(e: PointerEvent): number | null {
    const rect = (e.target as HTMLCanvasElement).getBoundingClientRect();
    const m = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(m, this.camera);
    this.raycaster.params.Points = { threshold: 0.045 * Math.max(1, this.camera.position.length() / 8) };
    const hits = [...this.raycaster.intersectObject(this.glyphs, false).map((h) => ({ h, i: this.glyphIdx[h.index!] })),
                  ...this.raycaster.intersectObject(this.pts, false).map((h) => ({ h, i: h.index! }))]
      .filter(({ i }) => i !== undefined && this.ok[i] && !this.hidden[i]);
    if (!hits.length) return null;
    hits.sort((a, b) => (a.h.distanceToRay ?? 0) - (b.h.distanceToRay ?? 0));
    return this.objects[hits[0].i].id;
  }
  private hover(e: PointerEvent) {
    const now = performance.now(); if (now - this.hoverAt < 50) return; this.hoverAt = now;
    const id = this.pickAt(e);
    if (id === null) { this.onHover?.(null); if (this.hoverId !== null) { this.hoverId = null; this.hoverGroup.clear(); } return; }
    const o = this.objects[this.index.get(id)!];
    this.onHover?.({ id, name: o.name, alt_km: this.latLonOf(id)?.alt_km ?? o.alt_km, speed_kms: this.speedOf(id) ?? 0, x: e.clientX, y: e.clientY });
    if (id !== this.hoverId) {
      this.hoverId = id; this.hoverGroup.clear();
      const rec = this.satrec(id); const p = this.positionOf(id);
      if (rec) { const g = new THREE.BufferGeometry().setFromPoints(this.orbitPoints(rec, this.simT, o.period_min, 160)); this.hoverGroup.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 }))); }
      if (p) this.hoverGroup.add(this.footprintRing(p, 0xffffff, 0.35));
    }
  }
  private click(e: PointerEvent) {
    const [x0, y0] = this.downAt; if (Math.hypot(e.clientX - x0, e.clientY - y0) > 4) return;
    this.select(this.pickAt(e));
  }
  dispose() { cancelAnimationFrame(this.raf); this.worker?.terminate(); this.renderer.dispose(); this.controls.dispose(); }
}
