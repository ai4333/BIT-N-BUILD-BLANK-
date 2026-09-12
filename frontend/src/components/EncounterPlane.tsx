/** S4 — the 2D B-plane view (§13.5). Plain SVG, no 3D library.
 *
 *  Why this and not a globe: a globe shows *where*, which the thesis does not need; the
 *  encounter plane shows *why* a burn helps. Combined covariance at 1σ/2σ/3σ, the miss vector,
 *  the hard-body circle labelled MODELLED, and the dilution banner when growing σ would lower
 *  Pc — the trap that signals whether anyone read the literature.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { TracedNumber, fmt } from "./TracedNumber";
import { ErrorBox, Loading, Empty } from "./Bits";
import type { Conjunction } from "../api/types";

const W = 330;
const H = 300;

export function EncounterPlane({ conjId, runId }: { conjId: string; runId?: string }) {
  const q = useQuery({
    queryKey: ["conj", conjId, runId],
    queryFn: () => api.get<Conjunction>(`/conjunctions/${conjId}`, { run_id: runId }),
  });

  if (q.isLoading) return <Loading what="projecting the encounter plane" />;
  if (q.error) return <ErrorBox e={q.error} />;
  const c = q.data!.data;
  const ep = c.encounter_plane;
  if (!ep?.available) {
    return (
      <Empty>
        No encounter plane: {ep?.na_reason ?? "covariance unavailable"}.
        <br />
        <br />
        Pc is reported as <span className="na">—</span>, never as 0.
      </Empty>
    );
  }

  const sMaj = ep.sigma_major_m ?? 1;
  const sMin = ep.sigma_minor_m ?? 1;
  const miss = ep.miss_xy_m ?? [ep.miss_m ?? 0, 0];
  const hbr = ep.hard_body_radius_m ?? 5;
  const rot = ep.orientation_deg ?? 0;

  // scale so 3σ and the miss vector both fit with margin
  const extent = Math.max(sMaj * 3.2, Math.hypot(miss[0], miss[1]) * 1.35, hbr * 4) || 1;
  const k = (Math.min(W, H) / 2 - 26) / extent;
  const cx = W / 2;
  const cy = H / 2;
  const px = (x: number) => cx + x * k;
  const py = (y: number) => cy - y * k;

  return (
    <div>
      {ep.dilution && (
        <div className="err" style={{ marginBottom: 8, borderColor: "var(--warn)", background: "rgba(224,164,88,0.07)" }}>
          <div className="title" style={{ color: "var(--warn)" }}>dilution region</div>
          The covariance is large relative to the miss distance. Here a <em>bigger</em> uncertainty
          would report a <em>lower</em> Pc — so a low number is not reassurance. Better tracking,
          not a burn, is the response.
        </div>
      )}

      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ background: "var(--bg-sunk)", border: "1px solid var(--line-1)", borderRadius: 2 }}>
        <defs>
          <marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <path d="M0,0 L7,3.5 L0,7 z" fill="var(--accent)" />
          </marker>
        </defs>

        {/* axes */}
        <line x1={cx} y1={10} x2={cx} y2={H - 10} stroke="var(--line-1)" strokeDasharray="2 3" />
        <line x1={10} y1={cy} x2={W - 10} y2={cy} stroke="var(--line-1)" strokeDasharray="2 3" />
        <text x={cx + 5} y={16} fill="var(--fg-3)" fontSize="8.5" fontFamily="var(--mono)">cross-track</text>
        <text x={W - 12} y={cy - 5} fill="var(--fg-3)" fontSize="8.5" fontFamily="var(--mono)" textAnchor="end">in-track</text>

        {/* combined covariance at 1σ / 2σ / 3σ, centred on the secondary */}
        <g transform={`translate(${px(miss[0])},${py(miss[1])}) rotate(${-rot})`}>
          {[3, 2, 1].map((n) => (
            <ellipse
              key={n}
              rx={sMaj * n * k}
              ry={sMin * n * k}
              fill="var(--accent)"
              fillOpacity={n === 1 ? 0.14 : n === 2 ? 0.07 : 0.035}
              stroke="var(--accent)"
              strokeOpacity={0.45}
              strokeWidth={n === 1 ? 1.1 : 0.6}
              strokeDasharray={n === 1 ? undefined : "3 3"}
            />
          ))}
        </g>

        {/* miss vector, primary at origin */}
        <line x1={cx} y1={cy} x2={px(miss[0])} y2={py(miss[1])} stroke="var(--accent)" strokeWidth="1.2" markerEnd="url(#arrow)" />

        {/* hard-body circle — MODELLED */}
        <circle cx={cx} cy={cy} r={Math.max(hbr * k, 2.5)} fill="none" stroke="var(--warn)" strokeWidth="1.1" />
        <circle cx={cx} cy={cy} r={2.2} fill="var(--fg-0)" />
        <circle cx={px(miss[0])} cy={py(miss[1])} r={2.8} fill="var(--danger)" />

        <text x={cx + 6} y={cy + 13} fill="var(--warn)" fontSize="8.5" fontFamily="var(--mono)">
          HBR {hbr} m (MODELLED)
        </text>
        <text x={px(miss[0]) + 6} y={py(miss[1]) - 6} fill="var(--danger)" fontSize="8.5" fontFamily="var(--mono)">
          secondary @ TCA
        </text>
      </svg>

      <div className="kv" style={{ marginTop: 9 }}>
        <div className="k">miss distance</div>
        <div className="v"><TracedNumber t={c.miss_distance_m} digits={0} showUnit /></div>
        <div className="k">relative speed</div>
        <div className="v"><TracedNumber t={c.rel_speed_mps} digits={0} showUnit /></div>
        <div className="k">Pc</div>
        <div className="v"><TracedNumber t={c.pc} digits={2} /></div>
        <div className="k">Pc max</div>
        <div className="v"><TracedNumber t={c.pc_max} digits={2} /></div>
        <div className="k">σ combined (R,T,N)</div>
        <div className="v" style={{ color: "var(--fg-1)" }}>
          {c.sigma_rtn_combined_m ? c.sigma_rtn_combined_m.map((s) => fmt(s, 0)).join(" / ") + " m" : "—"}
        </div>
        <div className="k">covariance</div>
        <div className="v" style={{ color: "var(--fg-1)" }}>{c.covariance_source}</div>
        <div className="k">1σ ellipse</div>
        <div className="v" style={{ color: "var(--fg-1)" }}>{fmt(sMaj, 0)} × {fmt(sMin, 0)} m</div>
      </div>
    </div>
  );
}
