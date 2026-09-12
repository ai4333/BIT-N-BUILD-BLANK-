"""`python -m oci <command>` — the terminal entry point.

demo               full pipeline on a synthetic scenario (SPEC §16.2 block 0)
ingest             pull (or read from cache with --offline) the public catalogue; print the ingest report
screen             screen a real altitude shell over a window; cache the run
ledger             compute the externality ledger for a cached screening run; print the ranking
validate-socrates  cross-validate the screener against CelesTrak SOCRATES (§17.3)
assumptions        regenerate docs/ASSUMPTIONS.md from oci/config.py
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEBRIS_GROUPS = ("cosmos-1408-debris", "fengyun-1c-debris", "iridium-33-debris", "cosmos-2251-debris")
RUNS = Path("data/cache/runs")


def _now_hour() -> datetime:
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def cmd_ingest(a) -> int:
    from oci.data.ingest import ingest
    objs, rep = ingest(a.group, offline=a.offline, extra_groups=DEBRIS_GROUPS if a.debris else ())
    print(f"INGEST {rep.group}{' + debris groups' if a.debris else ''}: {rep.n_ingested}/{rep.n_raw} objects · source {rep.source} · "
          f"rejected {rep.n_rejected} · stale (> {7} d) {rep.n_stale} · SATCAT misses {rep.n_satcat_miss} · unmatched operator {rep.n_unknown_operator}")
    print("  by type:", rep.by_type)
    print("  top operators:", ", ".join(f"{k} {v}" for k, v in rep.by_operator_top[:10]))
    for nid, why in rep.rejects[:5]:
        print("  reject:", nid, why)
    return 0


def cmd_screen(a) -> int:
    from oci.data.ingest import ingest, shell_filter
    from oci.physics.screen import screen
    objs, rep = ingest("active", offline=a.offline, extra_groups=DEBRIS_GROUPS)
    shell = shell_filter(objs, a.alt_low, a.alt_high)
    t0 = _now_hour() if a.start is None else datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=a.hours)
    print(f"SHELL {a.alt_low:.0f}–{a.alt_high:.0f} km: {len(shell)} objects ({sum(o.is_active for o in shell)} active, "
          f"{sum(not o.is_active for o in shell)} dead) · window {t0:%Y-%m-%d %H:%M}Z + {a.hours:.0f} h")
    t = time.perf_counter()
    res = screen(shell, t0, t1)
    r = res.run
    from collections import Counter
    cls = Counter(c.pair_class for c in res.conjunctions)
    print(f"SCREEN {r.run_id}: pairs {r.n_pairs_total:,} → stage1 {r.n_pairs_after_stage1:,} → index {r.n_pairs_after_stage2:,} → dips {r.n_candidates_stage3:,} → "
          f"conjunctions {r.n_conjunctions:,} in {time.perf_counter() - t:.0f} s · excluded {len(r.excluded)} · formation pairs dropped {r.n_formation_pairs_dropped}")
    print(f"  pair classes: {dict(cls)} · intra-constellation {sum(c.intra_constellation for c in res.conjunctions)} · "
          f"Pc ≥ 1e-4: {sum(1 for c in res.conjunctions if c.pc.value and c.pc.value >= 1e-4)} · Pc ≥ 1e-5: {sum(1 for c in res.conjunctions if c.pc.value and c.pc.value >= 1e-5)}")
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / f"{r.run_id}.pkl"
    pickle.dump({"objects": {o.norad_id: o for o in shell}, "result": res, "shell": (a.alt_low, a.alt_high)}, open(out, "wb"))
    print(f"  cached → {out}")
    return 0


def cmd_ledger(a) -> int:
    from oci.ledger.compute import compute_ledger
    runs = sorted(RUNS.glob("*.pkl"))
    if not runs:
        print("no cached screening run; run `python -m oci screen` first"); return 1
    path = Path(a.run) if a.run else runs[-1]
    d = pickle.load(open(path, "rb"))
    res, objs = d["result"], d["objects"]
    window_days = (res.run.window_end - res.run.window_start).total_seconds() / 86400.0
    t = time.perf_counter()
    led = compute_ledger(res.conjunctions, objs, window_days, pc_threshold=a.threshold)
    print(f"LEDGER {res.run.run_id} · shell {d['shell'][0]:.0f}–{d['shell'][1]:.0f} km · window {window_days:.1f} d · Pc* = {a.threshold:g} · "
          f"{led.n_conjunctions_used} conjunctions used, {led.n_conjunctions_intra_excluded} intra-constellation excluded · {time.perf_counter() - t:.0f} s")
    print(f"  share of Δv imposed by DEAD objects: {led.share_of_dv_from_dead.fmt(2)}")
    print(f"  {'#':>2} {'NORAD':>6} {'OBJECT':24s} {'TYPE':11s} {'ALT':>5} {'CONJ':>4} {'MNVR':>5} {'Δv IMPOSED':>12} {'DAYS':>6} {'OPS':>3} {'TOP BEARER':14s} {'BORNE':>6} {'LIFE':>5} {'FEE/yr':>9}")
    for e in led.entries[: a.top]:
        print(f"  {e.rank_by_dv_imposed:>2} {e.norad_id:>6} {e.object_name[:24]:24s} {e.object_type[:11]:11s} {e.mean_alt_km:>5.0f} {int(e.conjunctions_generated.value):>4d} "
              f"{e.maneuvers_forced.value:>5.1f} {e.dv_imposed_mps.fmt():>12s} {e.mission_days_imposed.value:>6.1f} {int(e.operators_affected.value):>3d} "
              f"{(e.top_bearer or '—')[:14]:14s} {e.dv_spent_mps.value:>5.2f}{'*' if not e.is_maneuverable else ' '} {e.decay_lifetime_yr_est.value:>5.0f} "
              f"{('$' + f'{e.implied_fee_usd_yr.value/1000:.0f}k' if e.implied_fee_usd_yr.value is not None else '—'):>9s}")
    print("  * = cannot manoeuvre · MNVR/Δv/DAYS/LIFE MODELLED · FEE INDICATIVE · covariance: " + ", ".join(sorted({o.covariance_source for o in objs.values()})))
    RUNS.mkdir(parents=True, exist_ok=True)
    pickle.dump(led, open(RUNS / f"{res.run.run_id}_ledger_{a.threshold:g}.pkl", "wb"))
    return 0


def cmd_validate_socrates(a) -> int:
    from oci.data.celestrak import fetch_socrates
    from oci.data.ingest import ingest
    from oci.data.socrates import cross_validate_current_elements, cross_validate_same_elements, fetch_socrates_elements
    rep = fetch_socrates("MINRANGE", 1000, offline=a.offline)
    print(f"SOCRATES run current as of {rep.data_current} UTC · interval {rep.interval_start:%m-%d %H:%M} → {rep.interval_stop:%m-%d %H:%M} · "
          f"{rep.n_conjunctions_total:,} conjunctions at 5 km over {rep.n_primaries:,} primaries × {rep.n_secondaries:,} secondaries · {len(rep.rows)} rows fetched")
    import random
    random.seed(a.seed)
    sample = rep.rows[: a.n // 3] + random.sample(rep.rows[a.n // 3:], a.n - a.n // 3)
    got = fetch_socrates_elements(sample, offline=a.offline)
    print(f"  element sets cached for {got}/{len(sample)} sampled pairs")
    cv1 = cross_validate_same_elements(sample, rep, offline=True)
    print("  " + cv1.summary())
    objs, _ = ingest("active", offline=a.offline, extra_groups=DEBRIS_GROUPS)
    cv2 = cross_validate_current_elements(rep.rows, rep, {o.norad_id: o for o in objs})
    print("  " + cv2.summary())
    print("  recall by day from SOCRATES run (current elements): " + ", ".join(f"d{k} {h}/{n}" for k, (h, n) in sorted(cv2.by_day.items())))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="oci")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="full pipeline on a synthetic scenario, terminal output")
    d.add_argument("--scenario", default="keystone_cluster", choices=["two_body_head_on", "keystone_cluster", "dead_rocket_body", "voi_event"])
    d.add_argument("--mc", type=int, default=100); d.add_argument("--seed", type=int, default=42); d.add_argument("--no-validate", action="store_true")
    i = sub.add_parser("ingest"); i.add_argument("--group", default="active"); i.add_argument("--debris", action="store_true"); i.add_argument("--offline", action="store_true")
    s = sub.add_parser("screen"); s.add_argument("--alt-low", type=float, default=700); s.add_argument("--alt-high", type=float, default=900)
    s.add_argument("--hours", type=float, default=24); s.add_argument("--start", default=None); s.add_argument("--offline", action="store_true")
    l = sub.add_parser("ledger"); l.add_argument("--run", default=None); l.add_argument("--threshold", type=float, default=1e-4); l.add_argument("--top", type=int, default=25)
    v = sub.add_parser("validate-socrates"); v.add_argument("--n", type=int, default=120); v.add_argument("--seed", type=int, default=3); v.add_argument("--offline", action="store_true")
    b = sub.add_parser("bench", help="baselines B1–B4 vs OCI on the scenario set (SPEC §15)")
    b.add_argument("--scenario", default=None); b.add_argument("--mc", type=int, default=100); b.add_argument("--seed", type=int, default=42)
    sub.add_parser("assumptions", help="regenerate docs/ASSUMPTIONS.md from oci/config.py")
    args = ap.parse_args(argv)
    if args.cmd == "bench":
        from oci.bench.harness import SCENARIO_SET, render, run_scenario
        for sid in ([args.scenario] if args.scenario else SCENARIO_SET):
            r = run_scenario(sid, seed=args.seed, n_mc=args.mc)
            Path("data/fixtures/bench").mkdir(parents=True, exist_ok=True)
            Path(f"data/fixtures/bench/bench_{sid}_seed{args.seed}.json").write_text(r.to_json())
            sys.stdout.write(render(r) + "\n")
        return 0
    if args.cmd == "assumptions":
        from oci.assumptions_doc import write_assumptions_doc
        print("wrote", write_assumptions_doc()); return 0
    if args.cmd == "demo":
        from oci.pipeline import render_report, run_pipeline
        t = time.perf_counter()
        result = run_pipeline(args.scenario, n_mc=args.mc, seed=args.seed, validate_all=not args.no_validate)
        sys.stdout.write(render_report(result)); sys.stdout.write(f"\n[pipeline wall time {time.perf_counter() - t:.1f} s]\n"); return 0
    return {"ingest": cmd_ingest, "screen": cmd_screen, "ledger": cmd_ledger, "validate-socrates": cmd_validate_socrates}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
