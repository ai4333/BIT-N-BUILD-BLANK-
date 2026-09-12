/** S3 — the event console (§13.6). Three panes: cluster → strategies → recommendation and
 *  validator. Plus S7 (the agent's tool trace) and the judge's ChaosButton.
 *
 *  The "⚠ differ" badge fires when the graph's keystone is not the max-Pc object — the moment
 *  the graph earns its place. It is read off the data; if it never fires we say so. */
import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Intro } from "../components/Intro";
import { Plate } from "../components/Plate";
import { TracedNumber, fmt } from "../components/TracedNumber";
import { ErrorBox, Loading, Empty } from "../components/Bits";
import { AgentTracePanel } from "../components/AgentTrace";
import { ChaosButton } from "../components/ChaosButton";
import { useRunState } from "../state";
import type { Cluster, StrategiesResponse, Strategy } from "../api/types";

export default function EventConsole() {
  const { runId, pcThreshold } = useRunState();
  const [cid, setCid] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);

  const clusters = useQuery({
    queryKey: ["clusters", runId, pcThreshold],
    queryFn: () => api.get<{ clusters: Cluster[]; n_disagreement: number }>("/graph/clusters", { run_id: runId, min_size: 2, pc_threshold: pcThreshold }),
  });

  const list = clusters.data?.data.clusters ?? [];
  useEffect(() => {
    if (!cid && list.length) {
      // open on a cluster where the keystone differs — that is the one worth looking at
      // open on the most actionable cluster: conjunctions above Pc* and a keystone that differs
      setCid((list.find((c) => c.critical_conjunctions > 0 && c.keystone_differs_from_max_pc) ?? list[0]).cluster_id);
    }
  }, [list, cid]);

  const strat = useMutation({
    mutationFn: (clusterId: string) =>
      api.post<StrategiesResponse>(`/clusters/${clusterId}/strategies`, { mc_samples: 100, pc_threshold: pcThreshold }),
  });

  useEffect(() => {
    if (cid) { setSel(null); strat.mutate(cid); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cid]);

  if (clusters.isLoading) return <Loading what="building the interaction graph" />;
  if (clusters.error) return <ErrorBox e={clusters.error} />;
  if (!list.length) return <Empty>This run produced no risk cluster of two or more objects.</Empty>;

  const d = strat.data?.data;
  const cluster = d?.cluster ?? list.find((c) => c.cluster_id === cid);
  const rec = d?.recommendation;
  const best = d?.strategies.find((s) => s.strategy_id === (sel ?? rec?.expected_value_optimum)) ?? d?.strategies[0];

  return (
    <div className="grid" style={{ gap: 10 }}>
      <Intro q="What should this satellite operator do right now?" a="One risk cluster: the object holding it together (keystone) is often not the one in the worst pass. Forty candidate actions — hold, wait for better tracking, observe, burn, coordinate — are simulated, checked by a deterministic validator that rejects infeasible burns, and ranked by expected cost and regret." />
      <div className="grid cols-s3" style={{ alignItems: "start" }}>
        {/* ── pane 1: the cluster ─────────────────────────────────────────────────── */}
        <Plate
          title="cluster"
          sub={`${list.length} in run`}
          right={
            <select value={cid ?? ""} onChange={(e) => setCid(e.target.value)}>
              {list.map((c) => (
                <option key={c.cluster_id} value={c.cluster_id}>
                  {c.cluster_id} ({c.n_objects})
                </option>
              ))}
            </select>
          }
        >
          {cluster && (
            <>
              <div className="kv" style={{ marginBottom: 10 }}>
                <div className="k">objects</div><div className="v">{cluster.n_objects}</div>
                <div className="k">edges</div><div className="v">{cluster.n_edges}</div>
                <div className="k">critical</div><div className="v">{cluster.critical_conjunctions}</div>
                <div className="k">keystone</div><div className="v">{cluster.keystone_id ?? "—"}</div>
                <div className="k">max-Pc object</div><div className="v">{cluster.max_pc_object_id ?? "—"}</div>
                <div className="k">max Pc</div><div className="v">{fmt(cluster.max_pc, 2)}</div>
              </div>

              {cluster.keystone_differs_from_max_pc ? (
                <div className="err" style={{ borderColor: "var(--warn)", background: "rgba(224,164,88,0.07)" }}>
                  <div className="title" style={{ color: "var(--warn)" }}>⚠ keystone ≠ max-Pc</div>
                  The obvious move is to shift the satellite in the worst single conjunction
                  ({cluster.max_pc_object_id}). The graph says the object holding this cluster
                  together is {cluster.keystone_id}, selected by {cluster.keystone_selected_by}.
                </div>
              ) : (
                <div className="note">
                  Keystone and max-Pc object agree here. On this cluster the graph adds nothing —
                  said plainly rather than manufactured.
                </div>
              )}

              <div style={{ marginTop: 10 }}>
                <div className="k" style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--fg-3)", letterSpacing: "0.08em" }}>
                  MEMBERS
                </div>
                {cluster.members.map((m) => (
                  <div key={m} className="mono" style={{ fontSize: 11.5, padding: "1px 0" }}>
                    <span style={{ color: m === cluster.keystone_id ? "var(--accent)" : m === cluster.max_pc_object_id ? "var(--danger)" : "var(--fg-1)" }}>
                      {m === cluster.keystone_id ? "◆" : m === cluster.max_pc_object_id ? "●" : "·"} {m}
                    </span>{" "}
                    <span style={{ color: "var(--fg-3)" }}>{cluster.member_names[String(m)] ?? ""}</span>
                  </div>
                ))}
                <div style={{ marginTop: 6, fontSize: 10, color: "var(--fg-3)", fontFamily: "var(--mono)" }}>
                  ◆ keystone · ● max-Pc
                </div>
              </div>
            </>
          )}
        </Plate>

        {/* ── pane 2: strategies ──────────────────────────────────────────────────── */}
        <Plate
          title="strategies"
          sub={d ? `${d.strategies.length} approved · ${d.rejected.length} rejected · MC ${d.mc_samples}` : ""}
          flush
          style={{ minHeight: 320 }}
        >
          {strat.isPending && <Loading what="simulating, sampling and validating" />}
          {strat.error && <div style={{ padding: 10 }}><ErrorBox e={strat.error} /></div>}
          {d && (
            <div className="t-wrap" style={{ maxHeight: 360 }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>strategy</th><th className="r">Pc after</th><th className="r">future</th>
                    <th className="r">Δv</th><th className="r">E[J]</th><th className="r">p95</th>
                    <th className="r">regret</th><th className="r">safe</th><th>verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {d.strategies.map((s) => (
                    <tr
                      key={s.strategy_id}
                      className={`click ${best?.strategy_id === s.strategy_id ? "sel" : ""}`}
                      onClick={() => setSel(s.strategy_id)}
                    >
                      <td>
                        {rec?.expected_value_optimum === s.strategy_id && <span style={{ color: "var(--accent)" }}>▶ </span>}
                        <span style={{ fontSize: 11.5 }}>{s.label}</span>
                        {s.proposed_by === "agent" && <span className="pill" style={{ marginLeft: 5, color: "var(--info)", borderColor: "var(--info)" }}>agent</span>}
                      </td>
                      <td className="r"><TracedNumber t={s.pc_after} digits={2} showChip={false} /></td>
                      <td className="r"><TracedNumber t={s.future_conjunctions} digits={0} showChip={false} /></td>
                      <td className="r"><TracedNumber t={s.dv_mps} digits={3} showChip={false} /></td>
                      <td className="r"><TracedNumber t={s.expected_cost} digits={3} showChip={false} /></td>
                      <td className="r"><TracedNumber t={s.p95_cost} digits={3} showChip={false} /></td>
                      <td className="r"><TracedNumber t={s.max_regret} digits={3} showChip={false} /></td>
                      <td className="r"><TracedNumber t={s.mc_safe_fraction} digits={2} showChip={false} /></td>
                      <td><span className={`pill ${s.validator_verdict ?? ""}`}>{s.validator_verdict ?? "—"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Plate>

        {/* ── pane 3: recommendation + validator ──────────────────────────────────── */}
        <Plate
          title="recommendation"
          right={cid && <ChaosButton runId={runId} clusterId={cid} onReplan={() => cid && strat.mutate(cid)} />}
        >
          {!d && <Loading />}
          {d && rec && (
            <>
              <div style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--accent)", marginBottom: 8 }}>
                {d.strategies.find((s) => s.strategy_id === rec.expected_value_optimum)?.label ?? "—"}
              </div>
              <div className="kv" style={{ marginBottom: 10 }}>
                <div className="k">EV optimum</div><div className="v">{rec.expected_value_optimum ?? "—"}</div>
                <div className="k">regret optimum</div><div className="v">{rec.minimax_regret_optimum ?? "—"}</div>
              </div>
              {rec.optima_agree ? (
                <div className="note">Both rankings choose the same action. → agree</div>
              ) : (
                <div className="err" style={{ borderColor: "var(--warn)", background: "rgba(224,164,88,0.07)" }}>
                  <div className="title" style={{ color: "var(--warn)" }}>optima disagree</div>
                  {rec.note}
                </div>
              )}

              {best && (
                <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--line-2)" }}>
                  <div className="k" style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--fg-3)", letterSpacing: "0.08em", marginBottom: 5 }}>
                    VALIDATOR — {best.strategy_id}
                  </div>
                  <span className={`pill ${best.validator_verdict ?? ""}`}>{best.validator_verdict}</span>
                  {best.validator_reason && (
                    <div className="note" style={{ marginTop: 6 }}>{best.validator_reason}</div>
                  )}
                </div>
              )}

              {d.rejected.length > 0 && (
                <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--line-2)" }}>
                  <div className="k" style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--danger)", letterSpacing: "0.08em", marginBottom: 5 }}>
                    REJECTED ({d.rejected.length})
                  </div>
                  {d.rejected.slice(0, 6).map((s) => (
                    <Rejected key={s.strategy_id} s={s} />
                  ))}
                  <div className="note" style={{ marginTop: 6, fontSize: 10.5 }}>
                    Deterministic code rejects; nothing here is advisory. If this list were always
                    empty the loop would be theatre.
                  </div>
                </div>
              )}
            </>
          )}
        </Plate>
      </div>

      {cid && <AgentTracePanel runId={runId} clusterId={cid} />}
    </div>
  );
}

function Rejected({ s }: { s: Strategy }) {
  return (
    <div style={{ marginBottom: 6, paddingLeft: 7, borderLeft: "2px solid var(--danger)" }}>
      <div className="mono" style={{ fontSize: 11 }}>{s.label}</div>
      <div style={{ fontSize: 11, color: "var(--fg-2)" }}>{s.validator_reason}</div>
    </div>
  );
}
