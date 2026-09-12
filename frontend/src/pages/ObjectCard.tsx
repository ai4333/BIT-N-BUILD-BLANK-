/** S2 — one object, its entire bill (§13.4). The screen the demo opens on.
 *  The BORNE column sitting at zero next to a non-zero IMPOSED column is the thesis; §13.4
 *  says explicitly not to remove it to save space, so it holds its own pane at every width. */
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Plate } from "../components/Plate";
import { TracedNumber, fmt } from "../components/TracedNumber";
import { ErrorBox, Loading, Empty } from "../components/Bits";
import { EncounterPlane } from "../components/EncounterPlane";
import { useRunState } from "../state";
import type { Conjunction, LedgerEntry, ObjectSummary, Traced } from "../api/types";
import { useState } from "react";

interface Detail {
  object: ObjectSummary;
  ledger_entry: LedgerEntry | null;
  decay_lifetime_yr: Traced;
  n_conjunctions: number;
  conjunctions: Conjunction[];
  pc_threshold: number;
}

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="row" style={{ marginBottom: 3 }}>
      <span style={{ color: "var(--fg-2)", fontSize: 12 }}>{label}</span>
      <span className="dotted" />
      <span className="mono">{children}</span>
    </div>
  );
}

export default function ObjectCard() {
  const { id } = useParams();
  const { runId, pcThreshold } = useRunState();
  const [sel, setSel] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["object", id, runId, pcThreshold],
    queryFn: () => api.get<Detail>(`/objects/${id}`, { run_id: runId, pc_threshold: pcThreshold }),
  });

  if (q.isLoading) return <Loading what="loading object" />;
  if (q.error) return <ErrorBox e={q.error} />;
  const d = q.data!.data;
  const o = d.object;
  const e = d.ledger_entry;
  const bearers = e?.bearers ?? [];

  const byOp = new Map<string, { dv: number; n: number }>();
  for (const b of bearers) {
    const cur = byOp.get(b.bearer_operator) ?? { dv: 0, n: 0 };
    cur.dv += b.dv_mps ?? 0;
    cur.n += b.n_maneuvers;
    byOp.set(b.bearer_operator, cur);
  }
  const ops = [...byOp.entries()].sort((a, b) => b[1].dv - a[1].dv);
  const maxOp = Math.max(...ops.map(([, v]) => v.dv), 1e-9);
  const selected = d.conjunctions.find((c) => c.conj_id === sel) ?? d.conjunctions[0];

  return (
    <div className="grid" style={{ gap: 10 }}>
      <Plate
        title={`NORAD ${o.norad_id} — ${o.object_name}`}
        sub={o.object_type}
        right={
          <>
            <span className={`pill ${o.is_active ? "live" : "dead"}`}>{o.is_active ? "ACTIVE" : "DEAD"}</span>
            <span className={`pill ${o.is_maneuverable ? "live" : "dead"}`} style={{ marginLeft: 6 }}>
              {o.is_maneuverable ? "MANEUVERABLE" : "NON-MANEUVERABLE"}
            </span>
            {o.stale && <span className="pill warn" style={{ marginLeft: 6 }}>STALE ELEMENTS</span>}
            <Link to={`/ledger?run=${runId ?? ""}&thr=${pcThreshold}`} className="btn" style={{ marginLeft: 8 }}>
              ← ledger
            </Link>
          </>
        }
      >
        <div className="mono" style={{ fontSize: 12, color: "var(--fg-1)" }}>
          launched {o.launch_date ?? "—"} · {o.country ?? "—"} · {o.operator} ·{" "}
          {o.mean_alt_km.toFixed(0)} km ({o.perigee_alt_km.toFixed(0)}–{o.apogee_alt_km.toFixed(0)}) ·{" "}
          {o.inclination_deg.toFixed(1)}° · period {o.period_min.toFixed(1)} min · RCS {o.rcs_size ?? "—"}
        </div>
        <div className="mono" style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 4 }}>
          elements {o.epoch.slice(0, 16)}Z from {o.source} · covariance {o.covariance_source} · mass{" "}
          <TracedNumber t={o.mass_kg_est} digits={0} showUnit />
        </div>
      </Plate>

      <div className="grid cols-2">
        <Plate title="imposed on others" sub={`${d.pc_threshold.toExponential(0)} · ${e?.window_days.toFixed(1) ?? "—"} d`}>
          {e ? (
            <>
              <Line label="Close approaches"><TracedNumber t={e.conjunctions_generated} digits={0} showChip={false} /></Line>
              <Line label="Manoeuvres forced"><TracedNumber t={e.maneuvers_forced} digits={2} /></Line>
              <Line label="Δv extracted"><TracedNumber t={e.dv_imposed_mps} digits={3} showUnit /></Line>
              <Line label="Mission-days consumed"><TracedNumber t={e.mission_days_imposed} digits={1} /></Line>
              <Line label="Operators affected"><TracedNumber t={e.operators_affected} digits={0} showChip={false} /></Line>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--line-2)" }}>
                <Line label="NET EXTERNALITY">
                  <span style={{ color: "var(--warn)", fontWeight: 700 }}>
                    +{fmt((e.dv_imposed_mps.value ?? 0) - (e.dv_spent_mps.value ?? 0), 3)} m/s
                  </span>
                </Line>
              </div>
            </>
          ) : (
            <Empty>Not in the ledger at this threshold.</Empty>
          )}
        </Plate>

        <Plate title="borne by itself" sub="what it pays">
          {e ? (
            <>
              <Line label="Manoeuvres"><TracedNumber t={e.maneuvers_performed} digits={0} showChip={false} /></Line>
              <Line label="Δv spent"><TracedNumber t={e.dv_spent_mps} digits={3} showUnit /></Line>
              {!o.is_maneuverable && (
                <div className="note quote" style={{ marginTop: 12, color: "var(--dead)" }}>
                  This object cannot manoeuvre. It bears none of the cost it creates, and it will
                  keep creating it for as long as it stays in orbit — which the projection below
                  puts at{" "}
                  <span className="mono">{fmt(e.decay_lifetime_yr_est.value, 0)} years</span>.
                  Nobody has ever sent it a bill.
                </div>
              )}
            </>
          ) : (
            <Empty>—</Empty>
          )}
        </Plate>
      </div>

      <div className="grid cols-2">
        <Plate title="projection" sub="over its remaining life">
          {e && (
            <>
              <Line label="Est. decay lifetime"><TracedNumber t={e.decay_lifetime_yr_est} digits={0} showUnit /></Line>
              <Line label="Projected lifetime Δv"><TracedNumber t={e.projected_lifetime_dv} digits={0} showUnit /></Line>
              <Line label="Indicative fee"><TracedNumber t={e.implied_fee_usd_yr} digits={0} showUnit /></Line>
              <Line label="CAB (conjunction-attributed burden)"><TracedNumber t={e.cab} digits={3} showUnit /></Line>
              <div className="note" style={{ marginTop: 10 }}>
                The fee is <span className="chip INDICATIVE">IND</span> — calibrated to
                Rao-Burgess-Kaffine (2020) to make the trade-off comparable, never to be quoted as
                a price.
              </div>
            </>
          )}
        </Plate>

        <Plate title="who pays" sub={`${ops.length} operators`} flush>
          {ops.length === 0 ? (
            <Empty>No attributed bearers at this threshold.</Empty>
          ) : (
            <div className="t-wrap" style={{ maxHeight: 240 }}>
              <table className="data">
                <thead>
                  <tr><th>operator</th><th className="r">mnvr</th><th className="r">Δv m/s</th><th style={{ width: "40%" }}></th></tr>
                </thead>
                <tbody>
                  {ops.map(([op, v]) => (
                    <tr key={op}>
                      <td>{op}</td>
                      <td className="num r">{v.n.toFixed(1)}</td>
                      <td className="num r">{fmt(v.dv, 3)}</td>
                      <td><div className="bar"><i style={{ width: `${(v.dv / maxOp) * 100}%` }} /></div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Plate>
      </div>

      <div className="grid cols-s2">
        <Plate title="conjunctions" sub={`${d.n_conjunctions} in this run`} flush style={{ minHeight: 260 }}>
          <div className="t-wrap" style={{ maxHeight: 300 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>partner</th><th>TCA</th><th className="r">miss m</th>
                  <th className="r">v rel m/s</th><th className="r">Pc</th><th>class</th>
                </tr>
              </thead>
              <tbody>
                {d.conjunctions.map((c) => {
                  const other = c.primary_id === o.norad_id ? c.secondary_id : c.primary_id;
                  const name = c.primary_id === o.norad_id ? c.secondary_name : c.primary_name;
                  return (
                    <tr
                      key={c.conj_id}
                      className={`click ${selected?.conj_id === c.conj_id ? "sel" : ""}`}
                      onClick={() => setSel(c.conj_id)}
                    >
                      <td>
                        <Link to={`/object/${other}?run=${runId ?? ""}&thr=${pcThreshold}`}>{name ?? other}</Link>{" "}
                        <span className="mono" style={{ color: "var(--fg-3)", fontSize: 11 }}>{other}</span>
                      </td>
                      <td className="num" style={{ color: "var(--fg-1)" }}>{c.tca.slice(5, 16).replace("T", " ")}</td>
                      <td className="r"><TracedNumber t={c.miss_distance_m} digits={0} showChip={false} /></td>
                      <td className="r"><TracedNumber t={c.rel_speed_mps} digits={0} showChip={false} /></td>
                      <td className="r">
                        <span style={{ color: (c.pc.value ?? 0) >= d.pc_threshold ? "var(--danger)" : "var(--fg-0)" }}>
                          <TracedNumber t={c.pc} digits={2} showChip={false} />
                        </span>
                      </td>
                      <td style={{ color: "var(--fg-2)", fontSize: 11 }}>{c.pair_class}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Plate>

        <Plate title="S4 encounter geometry" sub={selected ? selected.conj_id : "—"}>
          {selected ? (
            <EncounterPlane conjId={selected.conj_id} runId={runId} />
          ) : (
            <Empty>Select a conjunction.</Empty>
          )}
        </Plate>
      </div>
    </div>
  );
}
