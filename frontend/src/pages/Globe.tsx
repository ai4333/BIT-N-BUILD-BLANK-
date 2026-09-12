/** S10 — the globe. Real catalogue, real clusters, and the recommended manoeuvre drawn as a
 *  before/after orbit you can watch fly. Every object here is one the screener screened. */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useRunState } from "../state";
import { DEFAULT_LAYERS, GlobeScene, ROLE_COLOR, type CatObject, type Layers, type Pick } from "../globe/scene";
import type { Cluster, StrategiesResponse } from "../api/types";
import "../styles/globe.css";

interface Catalogue { objects: CatObject[]; n: number; epoch: string; window_end: string; pc_threshold: number }
interface ClusterGeom {
  cluster_id: string; members: number[]; keystone_id: number | null; max_pc_object_id: number | null;
  edges: { conj_id: string; primary_id: number; secondary_id: number; tca: string; miss_m: number; pc: number | null; critical: boolean; rel_speed_mps: number; r_teme_km: number[] }[];
}
interface StrategyGeom {
  strategy_id: string; kind: string; label: string;
  burns: { target_id: number; t_burn: string; dv_rtn_mps: number[]; magnitude_mps: number; r_teme_km: number[] }[];
  omm_after: Record<string, Record<string, unknown>>;
  conjunctions_after: { conj_id: string; primary_id: number; secondary_id: number; tca: string; miss_m: number; pc: number | null; new: boolean }[];
  pc_after: { value: number | null } | null;
}

const LAYER_ROWS: [keyof Layers, string, string][] = [
  ["skybox", "Skybox", "rendering"], ["darkSide", "Dark side lights", "rendering"], ["atmosphere", "Atmosphere", "rendering"],
  ["clouds", "Clouds", "earth"], ["countries", "Countries", "earth"], ["grid", "Grid", "earth"], ["spotlight", "Spotlight (sun)", "earth"],
  ["orbits", "Orbits", "satellites"], ["labels", "Labels", "satellites"],
  ["active", "Active payloads", "population"], ["dead", "Dead payloads", "population"], ["rocket_body", "Rocket bodies", "population"], ["debris", "Debris", "population"],
  ["billedOnly", "Ledger objects only", "population"],
];
const SPEEDS = [1, 10, 60, 300, 1000, 3600];

function fmtUTC(ms: number) { return new Date(ms).toISOString().replace("T", " ").slice(0, 19) + "Z"; }

export default function Globe() {
  const { runId, pcThreshold } = useRunState();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<GlobeScene | null>(null);
  const [layers, setLayers] = useState<Layers>(DEFAULT_LAYERS);
  const [pick, setPick] = useState<Pick | null>(null);
  const [simT, setSimT] = useState(Date.now());
  const [speed, setSpeed] = useState(60);
  const [playing, setPlaying] = useState(true);
  const [sep, setSep] = useState<number | null>(null);
  const [clusterId, setClusterId] = useState<string | null>(null);
  const [strategyId, setStrategyId] = useState<string | null>(null);
  const [status, setStatus] = useState("loading catalogue…");

  const cat = useQuery({
    queryKey: ["globe-cat", runId, pcThreshold],
    queryFn: () => api.get<Catalogue>("/globe/catalogue", { run_id: runId, pc_threshold: pcThreshold }),
    staleTime: Infinity,
  });
  const clusters = useQuery({
    queryKey: ["clusters", runId, pcThreshold],
    queryFn: () => api.get<{ clusters: Cluster[] }>("/graph/clusters", { run_id: runId, min_size: 2, pc_threshold: pcThreshold }),
  });
  const clusterGeom = useQuery({
    queryKey: ["globe-cluster", clusterId, pcThreshold],
    queryFn: () => api.get<ClusterGeom>(`/globe/cluster/${clusterId}`, { pc_threshold: pcThreshold }),
    enabled: !!clusterId,
  });
  const strat = useMutation({
    mutationFn: (cid: string) => api.post<StrategiesResponse>(`/clusters/${cid}/strategies`, { mc_samples: 50, pc_threshold: pcThreshold }),
  });
  const stratGeom = useQuery({
    queryKey: ["globe-strategy", strategyId],
    queryFn: () => api.get<StrategyGeom>(`/globe/strategy/${strategyId}`),
    enabled: !!strategyId,
  });

  // mount the scene once
  useEffect(() => {
    const canvas = canvasRef.current!, wrap = wrapRef.current!;
    const g = new GlobeScene(canvas);
    sceneRef.current = g;
    g.onPick = setPick;
    g.onSeparation = setSep;
    const ro = new ResizeObserver(() => g.resize(wrap.clientWidth, wrap.clientHeight));
    ro.observe(wrap); g.resize(wrap.clientWidth, wrap.clientHeight);
    const clock = setInterval(() => setSimT(g.simT), 250);
    return () => { clearInterval(clock); ro.disconnect(); g.dispose(); sceneRef.current = null; };
  }, []);

  // catalogue → scene; clock starts at the run's epoch (that is when the elements are valid)
  useEffect(() => {
    const g = sceneRef.current, d = cat.data?.data; if (!g || !d) return;
    g.setCatalogue(d.objects);
    g.simT = Date.parse(d.epoch) + 60_000; g.speed = speed; g.playing = playing;
    setStatus(`${d.n.toLocaleString()} objects · SGP4 in a worker · elements from the run`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cat.data]);
  useEffect(() => { const g = sceneRef.current; if (g) g.setLayers(layers); }, [layers]);
  useEffect(() => { const g = sceneRef.current; if (g) { g.speed = speed; g.playing = playing; } }, [speed, playing]);

  // first actionable cluster by default
  const list = clusters.data?.data.clusters ?? [];
  useEffect(() => {
    if (!clusterId && list.length) setClusterId((list.find((c) => c.critical_conjunctions > 0 && c.keystone_differs_from_max_pc) ?? list[0]).cluster_id);
  }, [list, clusterId]);

  // redraw overlays whenever selection / cluster / strategy / layers change
  const redraw = () => {
    const g = sceneRef.current; if (!g || !g.objects.length) return;
    g.clearOverlay();
    const cg = clusterGeom.data?.data;
    if (cg) {
      g.drawCluster(cg);
      const crit = cg.edges.find((e) => e.critical) ?? cg.edges[0];
      if (crit) g.watchPair(crit.primary_id, crit.secondary_id);
    }
    const sg = stratGeom.data?.data;
    if (sg) g.drawStrategy(sg);
    g.drawSelected();
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(redraw, [clusterGeom.data, stratGeom.data, pick, layers.orbits, layers.labels, cat.data]);

  const cg = clusterGeom.data?.data;
  const crit = cg?.edges.find((e) => e.critical) ?? cg?.edges[0];
  const jumpTo = (iso: string, minutesBefore: number, sp = 10) => {
    const g = sceneRef.current; if (!g) return;
    g.simT = Date.parse(iso) - minutesBefore * 60_000; g.playing = true; g.speed = sp; setPlaying(true); setSpeed(sp);
    setTimeout(redraw, 400);
  };
  const focusOn = (id: number) => { const g = sceneRef.current; if (!g) return; g.select(id); g.focus(id); };
  const selected = useMemo(() => pick ? cat.data?.data.objects.find((o) => o.id === pick.id) : undefined, [pick, cat.data]);
  const sr = strat.data?.data;
  const rec = sr ? (sr.strategies.find((s) => s.strategy_id === sr.recommendation.expected_value_optimum) ?? sr.strategies[0]) : undefined;

  return (
    <div className="globe" ref={wrapRef}>
      <canvas ref={canvasRef} />

      {/* ── left: view toggles ─────────────────────────────────────────────── */}
      <div className="gpanel left">
        <div className="ghead">VIEW</div>
        {(["rendering", "earth", "satellites", "population"] as const).map((grp) => (
          <div key={grp} className="ggroup">
            <div className="gcap">{grp}</div>
            {LAYER_ROWS.filter(([, , g]) => g === grp).map(([k, label]) => (
              <label key={k} className="gtoggle">
                <input type="checkbox" checked={layers[k]} onChange={(e) => setLayers({ ...layers, [k]: e.target.checked })} />
                <span>{label}</span>
                {k in ROLE_COLOR && <i style={{ background: ROLE_COLOR[k as keyof typeof ROLE_COLOR] }} />}
              </label>
            ))}
          </div>
        ))}
        <div className="ggroup">
          <div className="gcap">legend</div>
          <div className="glegend"><i style={{ background: "#ffb547" }} /> bills others (ledger, Pc* {pcThreshold.toExponential(0)})</div>
          <div className="glegend"><i style={{ background: "#4dd0c1" }} /> pays (borne) · post-burn orbit</div>
          <div className="glegend"><i style={{ background: "#ff6b6b" }} /> critical conjunction · max-Pc object</div>
        </div>
      </div>

      {/* ── bottom: time ───────────────────────────────────────────────────── */}
      <div className="gtime">
        <span className="gclock">{fmtUTC(simT)}</span>
        <button className="btn" onClick={() => setPlaying(!playing)}>{playing ? "❚❚" : "▶"}</button>
        <span className="seg">
          {SPEEDS.map((s) => <button key={s} className={s === speed ? "on" : ""} onClick={() => setSpeed(s)}>{s}×</button>)}
        </span>
        {cat.data && <button className="btn" onClick={() => { const g = sceneRef.current; if (g) g.simT = Date.parse(cat.data.data.epoch); }}>run epoch</button>}
        <button className="btn" onClick={() => { const g = sceneRef.current; if (g) g.simT = Date.now(); }}>now</button>
        <span className="gstatus">{cat.isError ? "catalogue failed — is the API up?" : status}</span>
      </div>

      {/* ── right: selection + the OCI overlay ─────────────────────────────── */}
      <div className="gpanel right">
        <div className="ghead">SELECTION <span className="sub">click a point</span></div>
        {selected ? (
          <div className="gsel">
            <div className="gname" style={{ color: ROLE_COLOR[selected.role] }}>{selected.name}</div>
            <div className="grow"><span>NORAD</span><b>{selected.id}</b></div>
            <div className="grow"><span>role</span><b>{selected.role.replace("_", " ")}{selected.maneuverable ? " · manoeuvrable" : ""}</b></div>
            <div className="grow"><span>operator</span><b>{selected.operator}</b></div>
            <div className="grow"><span>altitude</span><b>{selected.alt_km} km</b></div>
            <div className="grow"><span>inclination</span><b>{selected.inc_deg}°</b></div>
            <div className="grow"><span>period</span><b>{selected.period_min} min</b></div>
            <div className="grow"><span>Δv imposed on others</span><b style={{ color: selected.dv_imposed_mps > 0 ? "#ffb547" : undefined }}>{selected.dv_imposed_mps.toFixed(3)} m/s</b></div>
            <div className="grow"><span>Δv borne</span><b>{selected.dv_borne_mps.toFixed(3)} m/s</b></div>
            <div className="gbtns">
              <button className="btn" onClick={() => focusOn(selected.id)}>follow</button>
              <Link className="btn" to={`/object/${selected.id}?run=${runId ?? ""}&thr=${pcThreshold}`}>ledger card →</Link>
            </div>
          </div>
        ) : <div className="gmuted">No object selected. Amber points are the ones billing everybody else.</div>}

        <div className="ghead" style={{ marginTop: 10 }}>EVENT <span className="sub">risk cluster</span></div>
        <select className="gselect" value={clusterId ?? ""} onChange={(e) => { setClusterId(e.target.value); setStrategyId(null); strat.reset(); }}>
          {list.slice(0, 60).map((c) => (
            <option key={c.cluster_id} value={c.cluster_id}>
              {c.cluster_id} · {c.n_objects} obj · {c.critical_conjunctions} critical{c.keystone_differs_from_max_pc ? " · ⚠ keystone≠max-Pc" : ""}
            </option>
          ))}
        </select>
        {cg && (
          <div className="gsel">
            <div className="grow"><span>keystone ◆</span><b className="link" onClick={() => cg.keystone_id && focusOn(cg.keystone_id)}>{cg.keystone_id ?? "—"}</b></div>
            <div className="grow"><span>max-Pc object ●</span><b className="link" onClick={() => cg.max_pc_object_id && focusOn(cg.max_pc_object_id)}>{cg.max_pc_object_id ?? "—"}</b></div>
            {crit && (
              <>
                <div className="grow"><span>worst pass</span><b>{crit.primary_id} ↔ {crit.secondary_id}</b></div>
                <div className="grow"><span>TCA</span><b>{crit.tca.slice(0, 16).replace("T", " ")}Z</b></div>
                <div className="grow"><span>miss · Pc</span><b>{Math.round(crit.miss_m)} m · {crit.pc?.toExponential(2) ?? "—"}</b></div>
                <div className="grow"><span>separation now</span><b style={{ color: sep !== null && sep < 50 ? "#ff6b6b" : undefined }}>{sep === null ? "—" : sep < 100 ? `${(sep * 1000).toFixed(0)} m` : `${sep.toFixed(0)} km`}</b></div>
                <div className="gbtns">
                  <button className="btn" onClick={() => { focusOn(crit.primary_id); jumpTo(crit.tca, 12, 10); }}>▶ fly to the encounter</button>
                  <button className="btn" onClick={() => jumpTo(crit.tca, 0.5, 1)}>TCA −30 s</button>
                </div>
              </>
            )}
            <div className="gbtns">
              <button className="btn accent" disabled={strat.isPending} onClick={() => clusterId && strat.mutate(clusterId)}>
                {strat.isPending ? "simulating 40 strategies…" : sr ? "re-run strategies" : "compute the recommendation"}
              </button>
              <Link className="btn" to={`/cluster/${clusterId}?run=${runId ?? ""}&thr=${pcThreshold}`}>event console →</Link>
            </div>
          </div>
        )}
        {sr && (
          <div className="gsel">
            <div className="gcap">recommendation</div>
            <div className="grec">{rec?.label}</div>
            <div className="gmuted">E[J] {rec?.expected_cost?.value?.toFixed(3)} · Pc after {rec?.pc_after?.value?.toExponential(1)} · {sr.rejected.length} rejected by the validator</div>
            <select className="gselect" value={strategyId ?? ""} onChange={(e) => setStrategyId(e.target.value || null)}>
              <option value="">— draw a strategy on the globe —</option>
              {sr.strategies.filter((s) => s.kind !== "HOLD").slice(0, 25).map((s) => (
                <option key={s.strategy_id} value={s.strategy_id}>{s.strategy_id === rec?.strategy_id ? "★ " : ""}{s.label.slice(0, 70)}</option>
              ))}
            </select>
            {stratGeom.data && (
              <div className="gbtns">
                {stratGeom.data.data.burns[0] && (
                  <button className="btn accent" onClick={() => { const b = stratGeom.data!.data.burns[0]; focusOn(b.target_id); jumpTo(b.t_burn, 2, 60); }}>▶ watch the burn</button>
                )}
                <span className="gmuted">grey dashed = orbit before · teal = after the burn · teal point flies the new orbit</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
