/** §13.1 rule 3 / §10.14 — always visible, never a modal. What every number on screen rests on. */
import type { Assumptions } from "../api/types";

export function AssumptionStrip({ a }: { a: Assumptions | undefined }) {
  if (!a) return <div className="assumptions"><span className="lead">ASSUMPTIONS</span><span className="k">loading…</span></div>;
  const items: [string, string][] = [
    ["cov", a.covariance_source],
    ["Pc thr", `${a.pc_threshold.toExponential(0)} (${a.pc_threshold_source})`],
    ["HBR", `${a.hard_body_radius_m} m MODELLED`],
    ["prop", a.propagator],
    ["screen vol", `${a.screening_volume_m} m`],
    ["step", `${(a.coarse_step_min * 60).toFixed(0)} s · k=${a.gate_k}`],
    ["Pc", a.pc_method],
    ["horizon", `${a.horizon_h} h`],
    ["MC", String(a.mc_samples)],
    ["intra-constellation", a.intra_constellation_excluded ? `excluded (c=${a.c_intra})` : "included"],
    ["rules", a.attribution_rules.join(",")],
    ["weights", Object.entries(a.weights).map(([k, v]) => `${k[0]}${v}`).join(" ")],
  ];
  return (
    <div className="assumptions" title={a.covariance_note}>
      <span className="lead">ASSUMPTIONS</span>
      {items.map(([k, v]) => (
        <span key={k}>
          <span className="k">{k}:</span> <span className="v">{v}</span>
        </span>
      ))}
    </div>
  );
}
