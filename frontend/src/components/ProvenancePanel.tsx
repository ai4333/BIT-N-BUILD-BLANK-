/** S9 — "show the math" (§13.8). Opened by clicking any number. Every field it shows travels
 *  on the Traced itself, so the panel cannot drift from the figure it explains. */
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { Plate } from "./Plate";
import { fmt } from "./TracedNumber";
import type { Traced } from "../api/types";

const Ctx = createContext<(t: Traced) => void>(() => {});
export const useProvenance = () => useContext(Ctx);

export function ProvenanceProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<Traced | null>(null);
  const open = useCallback((x: Traced) => setT(x), []);
  return (
    <Ctx.Provider value={open}>
      {children}
      {t && <Panel t={t} onClose={() => setT(null)} />}
    </Ctx.Provider>
  );
}

const CAVEATS: Record<string, string> = {
  MODELLED: "This figure comes from a model, not an observation. The assumptions above are what it rests on; change them and the number changes.",
  INDICATIVE: "Order-of-magnitude only. It exists to make a trade-off comparable, not to be quoted as a price.",
  COMPUTED: "Computed from the inputs listed, by the function named. No fitting, no calibration.",
  OBSERVED: "Read directly from the source data — not derived.",
};

function Panel({ t, onClose }: { t: Traced; onClose: () => void }) {
  const fn = t.function.split("@");
  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <Plate
          title="show the math"
          right={
            <>
              <span className={`chip ${t.label}`}>{t.label}</span>
              <button className="btn" onClick={onClose} style={{ marginLeft: 8 }}>ESC</button>
            </>
          }
        >
          <div style={{ fontFamily: "var(--mono)", fontSize: 20, marginBottom: 12 }}>
            {t.value === null ? (
              <span className="na">— not available</span>
            ) : (
              <>
                {fmt(t.value, 4)} <span style={{ color: "var(--fg-2)", fontSize: 13 }}>{t.unit}</span>
              </>
            )}
          </div>

          {t.na_reason && (
            <div className="err" style={{ marginBottom: 12 }}>
              <div className="title">not computed</div>
              {t.na_reason}
            </div>
          )}

          <div className="kv" style={{ marginBottom: 12 }}>
            <div className="k">function</div>
            <div className="v" style={{ textAlign: "left" }}>{fn[0]}</div>
            <div className="k">version</div>
            <div className="v" style={{ textAlign: "left" }}>{fn[1] ?? "—"}</div>
            <div className="k">label</div>
            <div className="v" style={{ textAlign: "left" }}>{t.label}</div>
            <div className="k">trace id</div>
            <div className="v" style={{ textAlign: "left", color: "var(--fg-2)" }}>{t.trace_id}</div>
          </div>

          {Object.keys(t.assumptions ?? {}).length > 0 && (
            <>
              <div
                style={{
                  fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.09em",
                  color: "var(--fg-3)", textTransform: "uppercase", margin: "12px 0 5px",
                }}
              >
                rests on
              </div>
              <div className="kv">
                {Object.entries(t.assumptions).map(([k, v]) => (
                  <div key={k} style={{ display: "contents" }}>
                    <div className="k">{k}</div>
                    <div className="v" style={{ textAlign: "left" }}>
                      {typeof v === "object" ? JSON.stringify(v) : String(v)}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="note quote" style={{ marginTop: 14 }}>{CAVEATS[t.label]}</div>
        </Plate>
      </div>
    </div>
  );
}
