/** S5 — the shell map (§13.7). One chart, two curves, opposite gradients: the altitude that
 *  costs you most operationally is not the altitude that harms the environment most. */
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api/client";
import { Plate } from "../components/Plate";
import { ErrorBox, Loading, Empty } from "../components/Bits";
import { fmt } from "../components/TracedNumber";
import { useRunState } from "../state";

interface ShellsResp {
  pc_threshold: number;
  c_intra: number;
  workload_peak_alt_km: number | null;
  hazard_peak_alt_km: number | null;
  peaks_differ: boolean | null;
  calibration_shells: string[];
  notes: string[];
  shells: Record<string, any>[];
}

const num = (x: any): number | null => {
  if (x === null || x === undefined) return null;
  if (typeof x === "number") return x;
  if (typeof x === "object" && "value" in x) return x.value as number | null;
  return null;
};

export default function Shells() {
  const { runId, pcThreshold } = useRunState();
  const q = useQuery({
    queryKey: ["shells", runId, pcThreshold],
    queryFn: () => api.get<ShellsResp>("/shells", { run_id: runId, pc_threshold: pcThreshold, min_objects: 10 }),
  });

  if (q.isLoading) return <Loading what="partitioning the catalogue into shells" />;
  if (q.error) return <ErrorBox e={q.error} />;
  const d = q.data!.data;
  const viability = q.data!.assumptions.m_viability_per_sat_yr;

  const rows = d.shells
    .map((s) => ({
      alt: num(s.alt_mid_km) ?? num(s.alt_low_km) ?? 0,
      burden: num(s.maneuver_burden_per_sat_yr) ?? num(s.m_per_sat_yr) ?? num(s.M_per_yr),
      hazard: num(s.hazard_index),
      ocs: num(s.ocs),
      n: num(s.n_objects) ?? 0,
      active: num(s.n_active) ?? 0,
      dead: num(s.n_dead) ?? 0,
      life: num(s.decay_lifetime_yr),
      kappa: num(s.kappa),
      regime: s.regime ?? null,
      id: s.shell_id,
    }))
    .filter((r) => r.alt > 0)
    .sort((a, b) => a.alt - b.alt);

  if (!rows.length) return <Empty>No shell has enough objects to report.</Empty>;

  const lo = Math.min(d.workload_peak_alt_km ?? 0, d.hazard_peak_alt_km ?? 0);
  const hi = Math.max(d.workload_peak_alt_km ?? 0, d.hazard_peak_alt_km ?? 0);

  return (
    <div className="grid" style={{ gap: 10 }}>
      <Plate
        title="the two peaks"
        sub={`Pc* ${d.pc_threshold.toExponential(0)} · c_intra ${d.c_intra}`}
        right={
          d.peaks_differ ? (
            <span className="pill warn">OPTIMA DISAGREE</span>
          ) : (
            <span className="pill">peaks coincide</span>
          )
        }
      >
        <div style={{ height: 340 }}>
          <ResponsiveContainer>
            <ComposedChart data={rows} margin={{ top: 8, right: 54, bottom: 24, left: 8 }}>
              <CartesianGrid stroke="var(--line-1)" strokeDasharray="2 4" />
              <XAxis
                dataKey="alt" type="number" domain={["dataMin", "dataMax"]}
                tick={{ fill: "var(--fg-2)", fontSize: 10, fontFamily: "var(--mono)" }}
                stroke="var(--line-2)"
                label={{ value: "altitude km", position: "insideBottom", offset: -14, fill: "var(--fg-3)", fontSize: 10 }}
              />
              <YAxis
                yAxisId="l" tick={{ fill: "var(--warn)", fontSize: 10, fontFamily: "var(--mono)" }}
                stroke="var(--line-2)"
                label={{ value: "manoeuvres / sat-yr", angle: -90, position: "insideLeft", fill: "var(--warn)", fontSize: 10 }}
              />
              <YAxis
                yAxisId="r" orientation="right" tick={{ fill: "var(--dead)", fontSize: 10, fontFamily: "var(--mono)" }}
                stroke="var(--line-2)"
                label={{ value: "hazard index", angle: 90, position: "insideRight", fill: "var(--dead)", fontSize: 10 }}
              />
              {lo > 0 && hi > lo && (
                <ReferenceLine
                  yAxisId="l" segment={[{ x: lo, y: 0 }, { x: hi, y: 0 }]}
                  stroke="var(--accent)" strokeWidth={0}
                />
              )}
              <ReferenceLine
                yAxisId="l" y={viability} stroke="var(--danger)" strokeDasharray="4 3"
                label={{ value: `viability ${viability}/sat-yr`, fill: "var(--danger)", fontSize: 9, position: "insideTopLeft" }}
              />
              {d.workload_peak_alt_km && (
                <ReferenceLine yAxisId="l" x={d.workload_peak_alt_km} stroke="var(--warn)" strokeDasharray="3 3"
                  label={{ value: "workload peak", fill: "var(--warn)", fontSize: 9, angle: -90, position: "insideTopRight" }} />
              )}
              {d.hazard_peak_alt_km && (
                <ReferenceLine yAxisId="r" x={d.hazard_peak_alt_km} stroke="var(--dead)" strokeDasharray="3 3"
                  label={{ value: "hazard peak", fill: "var(--dead)", fontSize: 9, angle: -90, position: "insideTopRight" }} />
              )}
              <Tooltip
                contentStyle={{
                  background: "var(--bg-2)", border: "1px solid var(--line-2)", borderRadius: 3,
                  fontFamily: "var(--mono)", fontSize: 11,
                }}
                labelStyle={{ color: "var(--accent)" }}
                formatter={(v: any, n: any) => [typeof v === "number" ? v.toFixed(2) : v, n]}
                labelFormatter={(l) => `${l} km`}
              />
              <Legend wrapperStyle={{ fontFamily: "var(--mono)", fontSize: 10 }} />
              <Line yAxisId="l" type="monotone" dataKey="burden" name="manoeuvre burden / sat-yr"
                stroke="var(--warn)" strokeWidth={1.8} dot={{ r: 2 }} />
              <Line yAxisId="r" type="monotone" dataKey="hazard" name="hazard index (persistence-weighted)"
                stroke="var(--dead)" strokeWidth={1.8} dot={{ r: 2 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="note quote" style={{ marginTop: 8 }}>
          The altitude that costs you most operationally is not the altitude that harms the
          environment most. There is no single optimum without a stated weighting.
        </div>
        <div className="mono" style={{ fontSize: 10.5, color: "var(--fg-3)", marginTop: 6 }}>
          workload peak {d.workload_peak_alt_km ?? "—"} km · hazard peak {d.hazard_peak_alt_km ?? "—"} km ·
          q calibrated against the pairwise screener in {d.calibration_shells.length} shells; MODELLED elsewhere
        </div>
      </Plate>

      <Plate title="shells" sub={`${rows.length} bands`} flush>
        <div className="t-wrap" style={{ maxHeight: 340 }}>
          <table className="data">
            <thead>
              <tr>
                <th>shell</th><th className="r">objects</th><th className="r">active</th><th className="r">dead</th>
                <th className="r">burden /sat-yr</th><th className="r">OCS</th><th className="r">hazard</th>
                <th className="r">life yr</th><th className="r">κ</th><th>regime</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={r.burden !== null && r.burden > viability ? "" : ""}>
                  <td className="mono">{r.id}</td>
                  <td className="num r">{r.n.toLocaleString()}</td>
                  <td className="num r">{r.active.toLocaleString()}</td>
                  <td className="num r" style={{ color: "var(--dead)" }}>{r.dead.toLocaleString()}</td>
                  <td className="num r" style={{ color: r.burden !== null && r.burden > viability ? "var(--danger)" : undefined }}>
                    {fmt(r.burden, 2)}
                  </td>
                  <td className="num r">{fmt(r.ocs, 1)}</td>
                  <td className="num r">{fmt(r.hazard, 2)}</td>
                  <td className="num r">{fmt(r.life, 0)}</td>
                  <td className="num r">{fmt(r.kappa, 2)}</td>
                  <td style={{ color: "var(--fg-2)", fontSize: 11 }}>{r.regime ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {d.notes.length > 0 && (
          <div style={{ padding: "6px 10px", borderTop: "1px solid var(--line-2)", background: "var(--bg-2)", fontSize: 10.5, color: "var(--fg-2)" }}>
            {d.notes.join(" · ")}
          </div>
        )}
      </Plate>
    </div>
  );
}
