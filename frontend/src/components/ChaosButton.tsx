/** The judge's button (§13.9, M14). Inject a perturbation; every recommendation recomputes.
 *  Because the pipeline is a pure function of state, this is a replan rather than a replay —
 *  and the {was, now, why} diff is what proves it. */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { Plate } from "./Plate";
import { ErrorBox } from "./Bits";
import type { ChaosResult } from "../api/types";

const KINDS: [string, string][] = [
  ["NEW_OBJECT", "a fresh fragment on the post-burn path"],
  ["COVARIANCE_SPIKE", "tracking degrades 5×"],
  ["THIRD_PARTY_MANEUVER", "someone else burns, unannounced"],
  ["TRACKING_GAP", "time passes, σ does not shrink"],
  ["REFUSE_COORDINATION", "the partner operator says no"],
  ["UPLINK_DELAY", "180 min before you can command"],
  ["CONSTELLATION_INSERT", "12 new satellites arrive"],
];

export function ChaosButton({ runId, clusterId, onReplan }: { runId?: string; clusterId: string; onReplan: () => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState(KINDS[0][0]);

  const m = useMutation({
    mutationFn: () => api.post<ChaosResult>("/chaos", { run_id: runId, injection: kind, mc_samples: 25 }),
    onSuccess: () => onReplan(),
  });
  const d = m.data?.data;

  return (
    <>
      <button className="btn danger" onClick={() => setOpen(true)}>⚡ CHAOS</button>
      {open && (
        <div className="scrim" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <Plate
              title="chaos mode"
              sub="inject a perturbation — everything recomputes"
              right={<button className="btn" onClick={() => setOpen(false)}>close</button>}
            >
              <div className="ctl" style={{ marginBottom: 10 }}>
                <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ flex: 1 }}>
                  {KINDS.map(([k, why]) => (
                    <option key={k} value={k}>{k} — {why}</option>
                  ))}
                </select>
                <button className="btn danger" onClick={() => m.mutate()} disabled={m.isPending}>
                  {m.isPending ? "replanning…" : "inject"}
                </button>
              </div>

              {m.isPending && (
                <div className="note">
                  Re-screening the perturbed state, re-validating the standing recommendation and
                  re-optimising. Budget is 10 s.
                </div>
              )}
              {m.error && <ErrorBox e={m.error} />}

              {d && (
                <div>
                  <div className="kv" style={{ marginBottom: 10 }}>
                    <div className="k">replan time</div>
                    <div className="v" style={{ color: d.elapsed_s < 10 ? "var(--ok)" : "var(--warn)" }}>
                      {d.elapsed_s.toFixed(1)} s
                    </div>
                    <div className="k">previous plan</div>
                    <div className="v">
                      <span className={`pill ${d.still_valid ? "APPROVED" : "REJECTED"}`}>
                        {d.still_valid ? "STILL VALID" : "INVALIDATED"}
                      </span>
                    </div>
                  </div>

                  {!d.still_valid && (
                    <div className="err" style={{ marginBottom: 10 }}>
                      <div className="title">why it no longer holds</div>
                      {d.invalidation_reason}
                    </div>
                  )}

                  <div className="k" style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--fg-3)", letterSpacing: "0.08em", marginBottom: 4 }}>
                    DIFF
                  </div>
                  <div className="kv">
                    <div className="k">was</div>
                    <div className="v changed" style={{ textAlign: "left", color: "var(--fg-2)", textDecoration: d.still_valid ? "none" : "line-through" }}>
                      {String(d.diff.was ?? "—")}
                    </div>
                    <div className="k">now</div>
                    <div className="v changed" style={{ textAlign: "left", color: "var(--accent)" }}>
                      {String(d.diff.now ?? "—")}
                    </div>
                    <div className="k">why</div>
                    <div className="v" style={{ textAlign: "left", color: "var(--fg-1)" }}>
                      {String(d.diff.why ?? "—")}
                    </div>
                  </div>

                  <div className="note" style={{ marginTop: 10 }}>
                    Injected: <span className="mono">{JSON.stringify(d.applied).slice(0, 220)}</span>
                  </div>
                </div>
              )}
            </Plate>
          </div>
        </div>
      )}
    </>
  );
}
