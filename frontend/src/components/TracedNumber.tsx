/** §13.9 — every displayed figure: value, label chip, click for provenance (§13.8).
 *  A null value renders "—" with its na_reason, never a 0 (§13.1 rule 6). */
import { useProvenance } from "./ProvenancePanel";
import type { Traced } from "../api/types";

export function fmt(v: number | null, digits = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  if (v !== 0 && (a >= 1e5 || a < 1e-3)) return v.toExponential(Math.max(1, digits - 2));
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(a >= 100 ? 1 : a >= 1 ? digits - 1 : digits);
}

export function NaValue({ reason }: { reason: string | null }) {
  return <span className="na" title={reason ?? "not available"}>—</span>;
}

interface Props {
  t: Traced | null | undefined;
  digits?: number;
  showUnit?: boolean;
  showChip?: boolean;
  scale?: number;
}

export function TracedNumber({ t, digits = 3, showUnit = false, showChip = true, scale = 1 }: Props) {
  const open = useProvenance();
  if (!t) return <span className="na" title="not computed for this row">—</span>;
  if (t.value === null) return <NaValue reason={t.na_reason} />;
  const shown = t.value * scale;
  return (
    <span className="mono">
      <span
        className="traced"
        onClick={() => open(t)}
        title={`${t.function} — click for the math`}
      >
        {fmt(shown, digits)}
      </span>
      {showUnit && <span style={{ color: "var(--fg-2)", marginLeft: 3 }}>{t.unit}</span>}
      {showChip && <span className={`chip ${t.label}`}>{t.label.slice(0, 3)}</span>}
    </span>
  );
}
