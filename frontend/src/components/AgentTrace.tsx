/** S7 — the planner's tool trace (§13.9). Every call: tool, one-line summary, elapsed.
 *  Rejections in red, guard status at the top. The point of showing this is the suspicion every
 *  judge now carries about LLM demos — the planner reasons only through tools, and the guard
 *  checks every number in its explanation against the tool results (§14.6). */
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { useRunState } from "../state";
import { Plate } from "./Plate";
import { ErrorBox, Loading } from "./Bits";
import type { AgentTrace } from "../api/types";

export function AgentTracePanel({ runId, clusterId }: { runId?: string; clusterId: string }) {
  const { pcThreshold } = useRunState();
  const m = useMutation({
    mutationFn: () => api.post<AgentTrace>("/agent/analyse", { run_id: runId, cluster_id: clusterId, mc_samples: 25, pc_threshold: pcThreshold }),
  });
  const t = m.data?.data;

  return (
    <Plate
      title="S7 agent trace"
      sub={t ? `${t.driver} · ${t.n_tool_calls} tool calls · ${t.elapsed_s.toFixed(1)} s` : "not run"}
      right={
        <>
          {t && (
            <span className={`pill ${t.guard_passed ? "APPROVED" : "REJECTED"}`}>
              GUARD {t.guard_passed ? "PASSED" : "FAILED"}
            </span>
          )}
          <button className="btn primary" style={{ marginLeft: 8 }} onClick={() => m.mutate()} disabled={m.isPending}>
            {m.isPending ? "planning…" : t ? "re-run planner" : "run planner"}
          </button>
        </>
      }
    >
      {m.isPending && <Loading what="the planner is calling its tools" />}
      {m.error && <ErrorBox e={m.error} />}
      {!t && !m.isPending && !m.error && (
        <div className="note">
          The planner may only act through the eight tools of §14.2 — it cannot compute physics,
          only propose. Every burn it proposes goes to the deterministic validator, and the
          rejections below are the validator's, not a script.
        </div>
      )}
      {t && (
        <div className="grid cols-s2">
          <div>
            <div className="t-wrap" style={{ maxHeight: 300 }}>
              <table className="data">
                <thead>
                  <tr><th style={{ width: 24 }}>#</th><th>tool</th><th>result</th><th className="r">s</th></tr>
                </thead>
                <tbody>
                  {t.tool_calls.map((c, i) => (
                    <tr key={i} className={c.ok ? "" : "zero"}>
                      <td className="num" style={{ color: "var(--fg-3)" }}>{i + 1}</td>
                      <td className="mono" style={{ color: c.ok ? "var(--accent)" : "var(--danger)", fontSize: 11 }}>
                        {c.tool}
                      </td>
                      <td style={{
                        fontSize: 11,
                        color: c.summary?.startsWith("REJECTED") || c.summary?.startsWith("ERROR")
                          ? "var(--danger)" : "var(--fg-1)",
                      }}>
                        {c.summary}
                      </td>
                      <td className="num r" style={{ color: "var(--fg-3)" }}>{c.elapsed_s.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {t.rejections.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div className="k" style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--danger)", letterSpacing: "0.08em" }}>
                  THE PLANNER'S OWN PROPOSALS, REJECTED ({t.rejections.length})
                </div>
                {t.rejections.map((r, i) => (
                  <div key={i} style={{ marginTop: 4, paddingLeft: 7, borderLeft: "2px solid var(--danger)", fontSize: 11 }}>
                    <span className="mono" style={{ color: "var(--fg-1)" }}>{String(r.action ?? r.strategy_id ?? "proposal")}</span>
                    <div style={{ color: "var(--fg-2)" }}>{String(r.reason ?? r.validator_reason ?? "")}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <div className="k" style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--fg-3)", letterSpacing: "0.08em", marginBottom: 4 }}>
              EXPLANATION — every figure checked against the tool results (§14.6)
            </div>
            <pre
              style={{
                margin: 0, padding: 9, background: "var(--bg-sunk)", border: "1px solid var(--line-1)",
                borderRadius: 2, fontFamily: "var(--mono)", fontSize: 10.5, lineHeight: 1.55,
                color: "var(--fg-1)", whiteSpace: "pre-wrap", maxHeight: 320, overflow: "auto",
              }}
            >
              {t.explanation}
            </pre>
            {t.guard_violations.length > 0 && (
              <div className="err" style={{ marginTop: 8 }}>
                <div className="title">fabricated figures caught</div>
                {t.guard_violations.join(", ")}
              </div>
            )}
          </div>
        </div>
      )}
    </Plate>
  );
}
