/** S8 — benchmark (§13.2, §15). Against B2 = pairwise + post-manoeuvre re-screening, which is
 *  what operators actually do. §15.5 requires the rows where OCI loses to be printed. */
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Intro } from "../components/Intro";
import { Plate } from "../components/Plate";
import { ErrorBox, Loading } from "../components/Bits";
import { fmt } from "../components/TracedNumber";

interface Row {
  policy: string; action: string; collision_risk_final: number; total_dv_mps: number;
  n_maneuvers: number; n_operators_burdened: number; mission_impact: number;
  systemic_cost: number; expected_cost: number | null; p95_cost?: number | null;
  max_regret: number | null; validator: string; runtime_s: number;
  [k: string]: any;
}
interface Result {
  scenario_id: string; scenario_name: string; seed: number; pc_threshold: number;
  covariance_source: string; rows: Row[]; verdict: string; verdict_detail: Record<string, string>;
}

const METRICS: [keyof Row, string, number][] = [
  ["collision_risk_final", "collision risk final", 2],
  ["total_dv_mps", "total Δv m/s", 3],
  ["n_maneuvers", "manoeuvres commanded", 0],
  ["n_operators_burdened", "operators burdened", 0],
  ["mission_impact", "mission impact", 3],
  ["systemic_cost", "systemic cost", 3],
  ["expected_cost", "expected cost E[J]", 3],
  ["max_regret", "max regret", 3],
  ["runtime_s", "runtime s", 2],
];

export default function Bench() {
  const q = useQuery({ queryKey: ["bench"], queryFn: () => api.get<{ results: Result[]; source: string }>("/bench") });
  if (q.isLoading) return <Loading what="loading benchmark" />;
  if (q.error) return <ErrorBox e={q.error} />;
  const rs = q.data!.data.results;

  return (
    <div className="grid" style={{ gap: 10 }}>
      <Intro q="Does this beat what operators do today?" a="The same scenarios run through four baselines — including B2, pairwise screening with post-manoeuvre re-screening, which is standard practice — and through OCI. Where OCI loses a row, the table says so." />
      <Plate title="what this compares against" sub="§15.2">
        <div className="note">
          <strong>B1</strong> max-Pc only · <strong>B2</strong> pairwise + post-manoeuvre
          re-screening — <em>standard practice, the one that matters</em> · <strong>B3</strong>{" "}
          greedy chain · <strong>B4</strong> do nothing. The verdict compares expected systemic
          cost against B2; ties within 5 % are NEUTRAL. OCI's candidate set contains B2's
          iterated plan by construction, so it can improve on standard practice but never do
          worse than noise — and where it loses a row, the row is printed.
        </div>
      </Plate>

      {rs.map((r) => {
        const byPolicy = Object.fromEntries(r.rows.map((x) => [x.policy, x]));
        const order = ["B1", "B2", "B3", "B4", "OCI"].filter((p) => byPolicy[p]);
        const b2 = byPolicy["B2"];
        return (
          <Plate
            key={r.scenario_id}
            title={`${r.scenario_id} — ${r.scenario_name}`}
            sub={`seed ${r.seed} · Pc* ${r.pc_threshold.toExponential(0)} · cov ${r.covariance_source}`}
            right={
              <span className={`pill ${r.verdict === "OCI_BETTER" ? "APPROVED" : r.verdict === "OCI_WORSE" ? "REJECTED" : "warn"}`}>
                {r.verdict}
              </span>
            }
            flush
          >
            <div className="t-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>metric</th>
                    {order.map((p) => <th key={p} className="r" style={{ color: p === "OCI" ? "var(--accent)" : undefined }}>{p}</th>)}
                    <th className="r">Δ vs B2</th>
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map(([k, label, dg]) => {
                    const oci = byPolicy["OCI"]?.[k] as number | null;
                    const base = b2?.[k] as number | null;
                    const delta = oci != null && base != null && base !== 0 ? ((oci - base) / Math.abs(base)) * 100 : null;
                    const better = k === "runtime_s" ? null : delta != null ? delta < 0 : null;
                    return (
                      <tr key={String(k)}>
                        <td style={{ color: "var(--fg-1)" }}>{label}</td>
                        {order.map((p) => (
                          <td key={p} className="num r" style={{ color: p === "OCI" ? "var(--accent)" : undefined }}>
                            {fmt(byPolicy[p]?.[k] as number, dg)}
                          </td>
                        ))}
                        <td className="num r" style={{ color: better === null ? "var(--fg-3)" : better ? "var(--ok)" : "var(--danger)" }}>
                          {delta == null ? "—" : `${delta > 0 ? "+" : ""}${delta.toFixed(0)}%`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ padding: "7px 10px", borderTop: "1px solid var(--line-2)", background: "var(--bg-2)" }}>
              {order.map((p) => (
                <div key={p} className="mono" style={{ fontSize: 11, color: p === "OCI" ? "var(--accent)" : "var(--fg-2)" }}>
                  {p.padEnd(4)} {byPolicy[p].action} <span className={`pill ${byPolicy[p].validator}`}>{byPolicy[p].validator}</span>
                </div>
              ))}
              {Object.entries(r.verdict_detail ?? {}).length > 0 && (
                <div className="note" style={{ marginTop: 6 }}>
                  {Object.entries(r.verdict_detail).map(([k, v]) => <div key={k}>{k}: {v}</div>)}
                </div>
              )}
            </div>
          </Plate>
        );
      })}
    </div>
  );
}
