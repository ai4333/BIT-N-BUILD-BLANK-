/** The two things every screen needs: which run, and at what declared threshold.
 *  Both live in the URL so a screen can be linked to, and both are shown on every figure. */
import { useSearchParams } from "react-router-dom";

export const THRESHOLDS = [1e-4, 1e-5, 1e-6];

export function useRunState() {
  const [sp, setSp] = useSearchParams();
  const runId = sp.get("run") ?? undefined;
  const pcThreshold = Number(sp.get("thr") ?? 1e-5);
  const set = (patch: { run?: string; thr?: number }) => {
    const next = new URLSearchParams(sp);
    if (patch.run !== undefined) next.set("run", patch.run);
    if (patch.thr !== undefined) next.set("thr", String(patch.thr));
    setSp(next, { replace: true });
  };
  return { runId, pcThreshold, set };
}
