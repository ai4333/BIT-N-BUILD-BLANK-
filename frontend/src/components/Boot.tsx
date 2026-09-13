/** The opening. Covers the real load — catalogue fetch, SGP4 warm-up, graph — with a radar
 *  sweep over concentric orbits, the object counter climbing, and one line that says what the
 *  system is. Dismisses when the data is actually ready, never on a timer alone. */
import { useEffect, useState } from "react";
import "../styles/boot.css";

export interface BootStage { label: string; done: boolean }

export function Boot({ stages, ready, nObjects, onDone }: { stages: BootStage[]; ready: boolean; nObjects: number; onDone: () => void }) {
  const [count, setCount] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const [t0] = useState(() => performance.now());

  // the counter climbs toward the real object count as it becomes known
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      setCount((c) => {
        const target = nObjects || 5745;
        const next = c + Math.max(1, Math.ceil((target - c) * 0.045));
        return next >= target ? target : next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [nObjects]);

  // leave only once the data is ready AND the opening has had its 2.6 s
  useEffect(() => {
    if (!ready || leaving) return;
    const wait = Math.max(0, 2600 - (performance.now() - t0));
    const id = setTimeout(() => { setLeaving(true); setTimeout(onDone, 700); }, wait);
    return () => clearTimeout(id);
  }, [ready, leaving, onDone, t0]);

  const done = stages.filter((s) => s.done).length;
  return (
    <div className={"boot" + (leaving ? " leaving" : "")}>
      <div className="boot-scene">
        <svg viewBox="-200 -200 400 400" className="boot-radar" aria-hidden>
          <defs>
            <radialGradient id="sweep" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="scale(190)">
              <stop offset="0" stopColor="#4dd0c1" stopOpacity="0.55" /><stop offset="1" stopColor="#4dd0c1" stopOpacity="0" />
            </radialGradient>
          </defs>
          {[60, 95, 130, 165].map((r, i) => (
            <circle key={r} r={r} className="boot-ring" style={{ animationDelay: `${i * 0.25}s` }} />
          ))}
          <ellipse rx="150" ry="52" className="boot-orbit" transform="rotate(-28)" />
          <ellipse rx="120" ry="112" className="boot-orbit" transform="rotate(62)" />
          <g className="boot-sweep"><path d="M0 0 L190 0 A190 190 0 0 0 134 -134 Z" fill="url(#sweep)" /><line x1="0" y1="0" x2="190" y2="0" stroke="#4dd0c1" strokeWidth="1.2" /></g>
          <circle r="4" className="boot-sat a" /><circle r="3" className="boot-sat b" /><circle r="3" className="boot-sat c" />
          <circle r="16" fill="#0a0e14" stroke="#2a3542" /><circle r="9" fill="#12314a" />
        </svg>
        <div className="boot-text">
          <div className="boot-brand">ORBITAL CAPACITY <span>INTELLIGENCE</span></div>
          <div className="boot-line">Every object in orbit. Who it makes move. What that costs.</div>
          <div className="boot-count"><b>{count.toLocaleString()}</b> tracked objects</div>
          <ul className="boot-stages">
            {stages.map((s, i) => (
              <li key={s.label} className={s.done ? "done" : i === done ? "active" : ""}>
                <i /> {s.label}
              </li>
            ))}
          </ul>
          <div className="boot-foot">public catalogue · SGP4 · Foster Pc · Kelvins-fitted covariance · offline-safe</div>
        </div>
      </div>
    </div>
  );
}
