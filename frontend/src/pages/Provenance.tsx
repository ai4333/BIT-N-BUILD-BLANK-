/** S9 — the provenance panel's standing page (§13.8): the whole assumption register, the
 *  label legend, and the config fingerprint. The per-number panel opens from any figure. */
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Intro } from "../components/Intro";
import { Plate } from "../components/Plate";
import { ErrorBox, Loading } from "../components/Bits";

interface Resp {
  block: Record<string, unknown>;
  register: { n: number; id: string; assumption: string; label: string; impact: string }[];
  config_hash: string;
}

const LEGEND: [string, string][] = [
  ["OBSERVED", "read directly from the source data"],
  ["COMPUTED", "derived from inputs by the named function — no fitting"],
  ["MODELLED", "from a model; the assumptions are what it rests on"],
  ["INDICATIVE", "order-of-magnitude, to make a trade-off comparable — never a price"],
];

export default function Provenance() {
  const q = useQuery({ queryKey: ["assumptions"], queryFn: () => api.get<Resp>("/assumptions") });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox e={q.error} />;
  const d = q.data!.data;

  return (
    <div className="grid cols-2" style={{ alignItems: "start" }}>
      <Intro q="What is every number built on?" a="The assumption block that travels with every API response, the label legend, and the function that produced any figure you click. Nothing on these screens is a silent default." />
      <div className="grid" style={{ gap: 10 }}>
        <Plate title="label legend" sub="§13.1 rule 5">
          {LEGEND.map(([l, why]) => (
            <div key={l} style={{ marginBottom: 5 }}>
              <span className={`chip ${l}`} style={{ marginLeft: 0 }}>{l}</span>
              <span className="note" style={{ marginLeft: 8 }}>{why}</span>
            </div>
          ))}
          <div className="note quote" style={{ marginTop: 10 }}>
            A missing value renders as <span className="na">—</span> with its reason, never as 0.
            A silent zero is how a project lies by accident.
          </div>
        </Plate>

        <Plate title="assumption block" sub={`config ${d.config_hash}`}>
          <div className="kv">
            {Object.entries(d.block).map(([k, v]) => (
              <div key={k} style={{ display: "contents" }}>
                <div className="k">{k}</div>
                <div className="v" style={{ textAlign: "left", color: "var(--fg-1)" }}>
                  {typeof v === "object" ? JSON.stringify(v) : String(v)}
                </div>
              </div>
            ))}
          </div>
          <div className="note" style={{ marginTop: 10 }}>
            This block travels on every API response and every export, so a figure quoted
            elsewhere carries what it rests on with it.
          </div>
        </Plate>
      </div>

      <Plate title="assumption register" sub={`${d.register.length} entries · §18.1`} flush>
        <div className="t-wrap" style={{ maxHeight: "72vh" }}>
          <table className="data">
            <thead>
              <tr><th style={{ width: 32 }}>id</th><th>assumption</th><th>label</th><th>if wrong</th></tr>
            </thead>
            <tbody>
              {d.register.map((r) => (
                <tr key={r.n}>
                  <td className="mono" style={{ color: "var(--fg-3)" }}>{r.id}</td>
                  <td style={{ whiteSpace: "normal", minWidth: 180 }}>{r.assumption}</td>
                  <td><span className={`chip ${r.label}`} style={{ marginLeft: 0 }}>{r.label}</span></td>
                  <td style={{ whiteSpace: "normal", color: "var(--fg-2)", fontSize: 11.5 }}>{r.impact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Plate>
    </div>
  );
}
