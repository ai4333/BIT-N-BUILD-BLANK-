"""`python -m oci <command>` — the terminal entry point.

demo    run the full pipeline on a synthetic scenario and print every stage (SPEC §16.2 block 0)
"""
from __future__ import annotations

import argparse
import sys
import time

from oci.pipeline import run_pipeline, render_report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="oci")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="full pipeline on a synthetic scenario, terminal output")
    d.add_argument("--scenario", default="keystone_cluster",
                   choices=["two_body_head_on", "keystone_cluster", "dead_rocket_body", "voi_event"])
    d.add_argument("--mc", type=int, default=100, help="Monte Carlo samples per strategy (0 = off)")
    d.add_argument("--seed", type=int, default=42)
    d.add_argument("--no-validate", action="store_true")
    sub.add_parser("assumptions", help="regenerate docs/ASSUMPTIONS.md from oci/config.py")
    args = ap.parse_args(argv)
    if args.cmd == "assumptions":
        from oci.assumptions_doc import write_assumptions_doc
        print("wrote", write_assumptions_doc())
        return 0
    if args.cmd == "demo":
        t = time.perf_counter()
        result = run_pipeline(args.scenario, n_mc=args.mc, seed=args.seed, validate_all=not args.no_validate)
        sys.stdout.write(render_report(result))
        sys.stdout.write(f"\n[pipeline wall time {time.perf_counter() - t:.1f} s]\n")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
