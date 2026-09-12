/** Small shared pieces: loading, empty, error. §13.10 — an error is rendered, not hidden. */
import { ApiError } from "../api/client";

export function Loading({ what = "computing" }: { what?: string }) {
  return <div className="loading">{what}</div>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ e }: { e: unknown }) {
  if (e instanceof ApiError) {
    return (
      <div className="err">
        <div className="title">{e.problem.title}</div>
        <div>{e.problem.detail}</div>
        <div style={{ marginTop: 6, fontFamily: "var(--mono)", fontSize: 10, color: "var(--fg-3)" }}>
          {e.problem.type} · {e.problem.status}
        </div>
      </div>
    );
  }
  return (
    <div className="err">
      <div className="title">request failed</div>
      <div>{String((e as Error)?.message ?? e)}</div>
      <div style={{ marginTop: 6, fontSize: 11, color: "var(--fg-2)" }}>
        Is the API running? <code>make api</code>
      </div>
    </div>
  );
}

export function Stat({ cap, value, unit }: { cap: string; value: React.ReactNode; unit?: string }) {
  return (
    <div className="stat">
      <div className="cap">{cap}</div>
      <div>
        <span className="big">{value}</span>
        {unit && <span className="unit">{unit}</span>}
      </div>
    </div>
  );
}
