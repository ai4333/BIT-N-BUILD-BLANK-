/** SGP4 for the whole catalogue, off the main thread. The main thread sends the OMM records
 *  once and a simulated time whenever it moves; the worker answers with TEME positions and
 *  velocities (km, km/s) in one transferable buffer. Same mean elements, same propagator
 *  family as the backend — what the globe draws is what the screener screened. */
import { json2satrec, propagate, type SatRec } from "satellite.js";

interface LoadMsg { type: "load"; ids: number[]; omm: Record<string, unknown>[] }
interface TickMsg { type: "tick"; t: number; seq: number }

let recs: (SatRec | null)[] = [];
let ids: number[] = [];

self.onmessage = (ev: MessageEvent<LoadMsg | TickMsg>) => {
  const m = ev.data;
  if (m.type === "load") {
    ids = m.ids;
    recs = m.omm.map((o) => {
      try {
        return json2satrec(o as never);
      } catch {
        return null;
      }
    });
    (self as unknown as Worker).postMessage({ type: "loaded", n: recs.length, bad: recs.filter((r) => !r).length });
    return;
  }
  const date = new Date(m.t);
  const n = recs.length;
  const pos = new Float32Array(n * 3);
  const vel = new Float32Array(n * 3);
  const ok = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const r = recs[i];
    if (!r) continue;
    const pv = propagate(r, date);
    const p = pv?.position, v = pv?.velocity;
    if (!p || typeof p === "boolean" || !v || typeof v === "boolean" || !Number.isFinite(p.x)) continue;
    pos[i * 3] = p.x; pos[i * 3 + 1] = p.y; pos[i * 3 + 2] = p.z;
    vel[i * 3] = v.x; vel[i * 3 + 1] = v.y; vel[i * 3 + 2] = v.z;
    ok[i] = 1;
  }
  (self as unknown as Worker).postMessage({ type: "state", seq: m.seq, t: m.t, ids, pos, vel, ok }, [pos.buffer, vel.buffer, ok.buffer]);
};
