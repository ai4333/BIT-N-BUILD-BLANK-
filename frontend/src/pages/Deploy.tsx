/** S6 — the deployment planner (§13.2). Where should the next 5,000 satellites go?
 *  §12.3 calls this response the single most important JSON object in the project, and says
 *  not to collapse optima_disagree into one number to make the UI tidier. It is not collapsed. */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { Plate } from "../components/Plate";
import { ErrorBox, Loading, Stat } from "../components/Bits";
import { TracedNumber, fmt } from "../components/TracedNumber";
import { useRunState } from "../state";
import type { Traced } from "../api/types";

interface AltEval {
  alt_km: number;
  shell_id: string;
  ocs: Traced;
  ocs_before: Traced;
  maneuver_burden_per_sat_yr: Traced;
  months_above_viability_threshold: Traced;
  burden_imposed_on_incumbents_mps_yr: Traced;
  hazard_index: Traced;
  hazard_index_before: Traced;
  decay_lifetime_yr: Traced;
  persistence_after_pmd_failure_yr: Traced;
  workload_rank: number | null;
  hazard_rank: number | null;
}

interface Resp {
  baseline: AltEval;
  alternatives: AltEval[];
  two_peaks_finding: {
    workload_optimal_alt_km: number;
    hazard_optimal_alt_km: number;
    optima_disagree: boolean;
    explanation: string;
  };
  recommendation: Record<string, any>;
  honest_note: string;
  [k: string]: any;
}

export default function Deploy() {
  const { runId } = useRunState();
  const [n, setN] = useState(5000);
  const [alt, setAlt] = useState(550);
  const [inc, setInc] = useState(53);

  const m = useMutation({
    mutationFn: () =>
      api.post<Resp>("/deployment/evaluate", {
        run_id: runId, n_satellites: n, target_alt_km: alt, inclination_deg: inc,
        alternatives_km: [450, 500, 550, 600, 650, 700, 750, 800],
      }),
  });
  const d = m.data?.data;
  const rows = d ? [d.baseline, ...d.alternatives.filter((a) => a.alt_km !== d.baseline.alt_km)]
    .sort((a, b) => a.alt_km - b.alt_km) : [];

  return (
    <div className="grid" style={{ gap: 10 }}>
      <Plate title="deployment planner" sub="marginal capacity consumption of a proposed constellation">
        <div className="ctl">
          <label>satellites</label>
          <input type="number" value={n} onChange={(e) => setN(+e.target.value)} style={{ width: 90 }} />
          <label>target alt km</label>
          <input type="number" value={alt} onChange={(e) => setAlt(+e.target.value)} style={{ width: 80 }} />
          <label>inclination °</label>
          <input type="number" value={inc} onChange={(e) => setInc(+e.target.value)} style={{ width: 70 }} />
          <button className="btn primary" onClick={() => m.mutate()} disabled={m.isPending}>
            {m.isPending ? "evaluating…" : "evaluate"}
          </button>
        </div>
      </Plate>

      {m.isPending && <Loading what="pricing the trade-off" />}
      {m.error && <ErrorBox e={m.error} />}

      {d && (
        <>
          <Plate
            title="the two-peaks finding"
            right={d.two_peaks_finding.optima_disagree
              ? <span className="pill warn">OPTIMA DISAGREE</span>
              : <span className="pill">optima agree</span>}
          >
            <div className="grid cols-3" style={{ marginBottom: 10 }}>
              <Stat cap="if your priority is operations" value={d.recommendation.if_priority_is_operations ?? "—"} unit="km" />
              <Stat cap="if your priority is the environment" value={d.recommendation.if_priority_is_environment ?? "—"} unit="km" />
              <Stat cap="balanced, under the stated weights" value={d.recommendation.balanced_under_stated_weights ?? "—"} unit="km" />
            </div>
            <div className="note">{d.two_peaks_finding.explanation}</div>
            <div className="note quote" style={{ marginTop: 8 }}>
              {d.recommendation.honest_note ?? d.honest_note}
            </div>
          </Plate>

          <Plate title="altitude sweep" sub={`${n.toLocaleString()} satellites at ${inc}°`} flush>
            <div className="t-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>alt km</th><th>shell</th><th className="r">OCS before</th><th className="r">OCS after</th>
                    <th className="r">burden /sat-yr</th><th className="r">months over viability</th>
                    <th className="r">Δv imposed on incumbents</th><th className="r">hazard</th>
                    <th className="r">decay yr</th><th className="r">persists after PMD fail</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const isBase = r.alt_km === d.baseline.alt_km;
                    const wOpt = r.alt_km === d.two_peaks_finding.workload_optimal_alt_km;
                    const hOpt = r.alt_km === d.two_peaks_finding.hazard_optimal_alt_km;
                    return (
                      <tr key={r.alt_km} className={isBase ? "sel" : ""}>
                        <td className="mono">
                          {r.alt_km}
                          {isBase && <span className="pill" style={{ marginLeft: 5 }}>proposed</span>}
                          {wOpt && <span className="pill warn" style={{ marginLeft: 4 }}>ops-best</span>}
                          {hOpt && <span className="pill dead" style={{ marginLeft: 4 }}>env-best</span>}
                        </td>
                        <td className="mono" style={{ color: "var(--fg-3)" }}>{r.shell_id}</td>
                        <td className="r"><TracedNumber t={r.ocs_before} digits={1} showChip={false} /></td>
                        <td className="r"><TracedNumber t={r.ocs} digits={1} showChip={false} /></td>
                        <td className="r"><TracedNumber t={r.maneuver_burden_per_sat_yr} digits={2} showChip={false} /></td>
                        <td className="r"><TracedNumber t={r.months_above_viability_threshold} digits={1} showChip={false} /></td>
                        <td className="r"><TracedNumber t={r.burden_imposed_on_incumbents_mps_yr} digits={0} showChip={false} /></td>
                        <td className="r"><TracedNumber t={r.hazard_index} digits={2} showChip={false} /></td>
                        <td className="r"><TracedNumber t={r.decay_lifetime_yr} digits={0} showChip={false} /></td>
                        <td className="r"><TracedNumber t={r.persistence_after_pmd_failure_yr} digits={0} showChip={false} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ padding: "6px 10px", borderTop: "1px solid var(--line-2)", background: "var(--bg-2)", fontSize: 10.5, color: "var(--fg-2)" }}>
              Every figure MODELLED from the kinetic-gas flux model (§11.13) over the public
              catalogue. Click any number for its assumptions.
            </div>
          </Plate>
        </>
      )}
    </div>
  );
}
