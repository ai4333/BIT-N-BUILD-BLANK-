/** S1 — the ledger (§13.3). The ranking nobody publishes: objects sorted by the fuel they
 *  extract from other operators. The imposed↔borne toggle is the whole thesis in one click —
 *  flip to "borne" and every dead object drops to zero. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Plate } from "../components/Plate";
import { TracedNumber, fmt } from "../components/TracedNumber";
import { ErrorBox, Loading, Empty, Stat } from "../components/Bits";
import { useRunState } from "../state";
import type { LedgerPage } from "../api/types";

type View = "imposed" | "borne" | "net";

const COLS: { key: string; label: string; sortable?: boolean; r?: boolean }[] = [
  { key: "rank", label: "#" },
  { key: "object", label: "object" },
  { key: "type", label: "type" },
  { key: "alt", label: "alt km", r: true },
  { key: "conjunctions_generated", label: "conj", sortable: true, r: true },
  { key: "maneuvers_forced", label: "mnvr forced", sortable: true, r: true },
  { key: "dv_imposed_mps", label: "Δv imposed", sortable: true, r: true },
  { key: "dv_spent_mps", label: "Δv borne", sortable: true, r: true },
  { key: "operators_affected", label: "ops", sortable: true, r: true },
  { key: "top_bearer", label: "top bearer" },
  { key: "implied_fee_usd_yr", label: "fee/yr", sortable: true, r: true },
];

export default function Ledger() {
  const { runId, pcThreshold } = useRunState();
  const nav = useNavigate();
  const [sort, setSort] = useState("dv_imposed_mps");
  const [view, setView] = useState<View>("imposed");
  const [type, setType] = useState("");
  const [nonzero, setNonzero] = useState(true);

  const q = useQuery({
    queryKey: ["ledger", runId, pcThreshold, sort, type, nonzero],
    queryFn: () =>
      api.get<LedgerPage>("/ledger", {
        run_id: runId, pc_threshold: pcThreshold, sort, order: "desc",
        object_type: type || undefined, nonzero_only: nonzero, limit: 200,
      }),
  });

  if (q.isLoading) return <Loading what="computing the ledger" />;
  if (q.error) return <ErrorBox e={q.error} />;
  const d = q.data!.data;
  const maxImposed = Math.max(...d.entries.map((e) => e.dv_imposed_mps.value ?? 0), 1e-9);

  return (
    <div className="grid" style={{ gridTemplateRows: "auto 1fr", height: "100%" }}>
      <div className="grid cols-3">
        <Plate title="the headline" sub={`Pc* ${pcThreshold.toExponential(0)} · ${d.window_days.toFixed(1)} d`}>
          <Stat
            cap="Δv imposed by DEAD objects"
            value={
              d.share_of_dv_from_dead.value === null
                ? "—"
                : `${(d.share_of_dv_from_dead.value * 100).toFixed(0)}%`
            }
          />
          <div className="note" style={{ marginTop: 8 }}>
            of all avoidance burden in this shell. Dead objects cannot manoeuvre, so the cost of
            avoiding them falls entirely on operators who can.
          </div>
        </Plate>
        <Plate title="total extracted" sub="across every billed object">
          <Stat
            cap="Δv taken from other operators"
            value={fmt(d.total_dv_imposed_mps.value, 3)}
            unit="m/s"
          />
          <div className="note" style={{ marginTop: 8 }}>
            <span className="mono">{d.n_entries_nonzero}</span> of{" "}
            <span className="mono">{d.total_all.toLocaleString()}</span> objects impose a measurable
            cost at this threshold. Lower Pc* to widen the net.
          </div>
        </Plate>
        <Plate title="what this ranks by" sub="§5.3">
          <div className="note">
            Existing most-concerning lists rank by debris-generating hazard — probability × mass.
            This ranks by <strong>propellant extracted from other operators</strong>. Different
            question, different answer. A <span className="flag">⚑</span> marks a top-20 object
            that is <em>not</em> on the published hazard list.
          </div>
        </Plate>
      </div>

      <Plate
        title="who is making whom burn fuel"
        sub={`${d.total.toLocaleString()} of ${d.total_all.toLocaleString()} objects`}
        right={
          <div className="ctl">
            <span className="seg">
              {(["imposed", "borne", "net"] as View[]).map((v) => (
                <button key={v} className={view === v ? "on" : ""} onClick={() => setView(v)}>
                  {v}
                </button>
              ))}
            </span>
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">all types</option>
              <option value="DEBRIS">debris</option>
              <option value="ROCKET BODY">rocket body</option>
              <option value="PAYLOAD">payload</option>
            </select>
            <button className={nonzero ? "btn primary" : "btn"} onClick={() => setNonzero((v) => !v)}>
              {nonzero ? "billed only" : "all rows"}
            </button>
          </div>
        }
        flush
        style={{ minHeight: 380 }}
      >
        {d.entries.length === 0 ? (
          <Empty>
            No object imposes a measurable burden at Pc* {pcThreshold.toExponential(0)} over{" "}
            {d.window_days.toFixed(1)} days.
            <br />
            <br />
            That is a real result, not a failure: attribution needs a conjunction above threshold
            between a dead object and an <em>active, steerable</em> one. Lower the threshold, or
            screen a longer window.
          </Empty>
        ) : (
          <div className="t-wrap">
            <table className="data">
              <thead>
                <tr>
                  {COLS.map((c) => (
                    <th
                      key={c.key}
                      className={[c.sortable ? "sortable" : "", c.r ? "r" : "", sort === c.key ? "on" : ""].join(" ")}
                      onClick={() => c.sortable && setSort(c.key)}
                    >
                      {c.label}
                      {sort === c.key ? " ▾" : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.entries.map((e) => {
                  const imposed = e.dv_imposed_mps.value ?? 0;
                  const borne = e.dv_spent_mps.value ?? 0;
                  const flag = !e.on_published_top50 && (e.rank_by_dv_imposed ?? 99) <= 20;
                  return (
                    <tr
                      key={e.norad_id}
                      className={`click ${imposed === 0 ? "zero" : ""}`}
                      onClick={() => nav(`/object/${e.norad_id}?run=${runId ?? ""}&thr=${pcThreshold}`)}
                    >
                      <td className="num" style={{ color: "var(--fg-3)" }}>{e.rank_by_dv_imposed ?? "—"}</td>
                      <td>
                        <span style={{ color: e.is_active ? "var(--fg-0)" : "var(--dead)" }}>
                          {e.object_name}
                        </span>{" "}
                        <span className="mono" style={{ color: "var(--fg-3)", fontSize: 11 }}>
                          {e.norad_id}
                        </span>
                        {flag && <span className="flag" title="not on the published top-50 most-concerning list"> ⚑</span>}
                      </td>
                      <td>
                        <span className={`pill ${e.is_active ? "live" : "dead"}`}>
                          {e.is_active ? "ACTIVE" : "DEAD"}
                        </span>{" "}
                        <span style={{ color: "var(--fg-2)", fontSize: 11 }}>{e.object_type}</span>
                      </td>
                      <td className="num r">{e.mean_alt_km.toFixed(0)}</td>
                      <td className="r"><TracedNumber t={e.conjunctions_generated} showChip={false} digits={0} /></td>
                      <td className="r"><TracedNumber t={e.maneuvers_forced} showChip={false} digits={2} /></td>
                      <td className="r" style={{ minWidth: 150 }}>
                        {view === "borne" ? (
                          <TracedNumber t={e.dv_spent_mps} showChip={false} digits={3} />
                        ) : view === "net" ? (
                          <span className="mono">{fmt(imposed - borne, 3)}</span>
                        ) : (
                          <>
                            <TracedNumber t={e.dv_imposed_mps} showChip={false} digits={3} />
                            <div className="bar" style={{ marginTop: 2 }}>
                              <i className={e.is_active ? "" : "dead"} style={{ width: `${(imposed / maxImposed) * 100}%` }} />
                            </div>
                          </>
                        )}
                      </td>
                      <td className="r">
                        <TracedNumber t={e.dv_spent_mps} showChip={false} digits={2} />
                        {!e.is_maneuverable && (
                          <span title="cannot manoeuvre" style={{ color: "var(--dead)" }}> *</span>
                        )}
                      </td>
                      <td className="num r">{fmt(e.operators_affected.value, 0)}</td>
                      <td style={{ color: "var(--fg-1)" }}>{e.top_bearer ?? "—"}</td>
                      <td className="r"><TracedNumber t={e.implied_fee_usd_yr} showChip={false} digits={0} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <div
          style={{
            padding: "6px 10px", borderTop: "1px solid var(--line-2)", background: "var(--bg-2)",
            fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--fg-2)",
            display: "flex", gap: 18, flexWrap: "wrap",
          }}
        >
          <span><span className="flag">⚑</span> not on the published top-50 most-concerning list</span>
          <span><span style={{ color: "var(--dead)" }}>*</span> cannot manoeuvre — bears nothing, by construction</span>
          <span>every figure at Pc* {pcThreshold.toExponential(0)} over {d.window_days.toFixed(1)} d</span>
          <span>click any number for the math</span>
        </div>
      </Plate>
    </div>
  );
}
