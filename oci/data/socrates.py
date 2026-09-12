"""D3 — SOCRATES cross-validation of the screening engine (SPEC §6.4, §17.3).

Two comparisons, both reported:
  * `same_elements`  — screen each SOCRATES pair with the exact element sets SOCRATES used
                       (its per-conjunction GP link). Tests the *engine*. Target ≥ 85 %.
  * `current_elements` — screen with today's catalogue. Tests the engine + data drift; recall
                       decays with horizon because operators manoeuvre between element updates.
Formation / docked pairs (v_rel < 50 m/s) are dropped by policy and reported separately.
"""
from __future__ import annotations

import csv
import io
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

from oci.config import CONFIG
from oci.data.celestrak import CACHE_DIR, USER_AGENT, SocratesReport, SocratesRow, fetch_socrates, load_satcat
from oci.data.ingest import normalise
from oci.physics.screen import screen

GP_DIR = CACHE_DIR / "socrates_gp"


@dataclass
class CrossValidation:
    mode: str
    n_pairs: int
    n_hits: int
    n_policy_excluded: int
    n_formation: int
    recall_on_encounters: float
    recall_raw: float
    tca_abs_err_s: list[float] = field(default_factory=list)
    miss_err_m: list[float] = field(default_factory=list)
    misses: list[tuple[int, int, str]] = field(default_factory=list)
    by_day: dict[int, tuple[int, int]] = field(default_factory=dict)

    def summary(self) -> str:
        t = np.asarray(self.tca_abs_err_s) if self.tca_abs_err_s else np.zeros(1)
        m = np.asarray(self.miss_err_m) if self.miss_err_m else np.zeros(1)
        return (f"[{self.mode}] recall on encounters {self.n_hits}/{self.n_pairs - self.n_policy_excluded - self.n_formation} "
                f"= {self.recall_on_encounters:.1%} (raw {self.recall_raw:.1%}; {self.n_policy_excluded} policy-excluded, "
                f"{self.n_formation} formation pairs) · TCA |Δ| median {np.median(t):.3f} s p95 {np.percentile(t, 95):.2f} s · "
                f"miss |Δ| median {np.median(np.abs(m)):.1f} m p95 {np.percentile(np.abs(m), 95):.1f} m")


def fetch_socrates_elements(rows: list[SocratesRow], offline: bool = False, sleep_s: float = 1.0) -> int:
    """Cache the element sets SOCRATES used for each pair. Throttled; never re-fetches."""
    GP_DIR.mkdir(parents=True, exist_ok=True)
    got = 0
    for r in rows:
        f = GP_DIR / f"{r.norad_1}_{r.norad_2}.csv"
        if f.exists():
            got += 1
            continue
        if offline:
            continue
        resp = httpx.get(f"https://celestrak.org/SOCRATES/data.php?CATNR={r.norad_1},{r.norad_2}",
                         headers={"User-Agent": USER_AGENT}, timeout=60)
        body = re.sub(r"<[^>]+>", "\n", resp.text)
        lines = [l.strip() for l in body.splitlines()
                 if l.strip().startswith("OBJECT_NAME,") or re.match(r"^[^,]+,\d{4}-\d{3}[A-Z]+,\d{4}-", l.strip())]
        if len(lines) >= 3:
            f.write_text("\n".join(lines[:1] + [l for l in lines[1:] if not l.startswith("OBJECT_NAME")]))
            got += 1
        time.sleep(sleep_s)
    return got


def _is_formation(r: SocratesRow) -> bool:
    return r.rel_speed_kmps * 1000.0 < CONFIG.screening.formation_v_rel_floor_mps


def cross_validate_same_elements(rows: list[SocratesRow], rep: SocratesReport, offline: bool = True) -> CrossValidation:
    satcat = load_satcat(offline=offline)
    cv = CrossValidation("same_elements", len(rows), 0, 0, 0, 0.0, 0.0)
    for r in rows:
        f = GP_DIR / f"{r.norad_1}_{r.norad_2}.csv"
        if not f.exists():
            cv.n_policy_excluded += 1
            cv.misses.append((r.norad_1, r.norad_2, "no cached element set"))
            continue
        if _is_formation(r):
            cv.n_formation += 1
            continue
        recs = list(csv.DictReader(io.StringIO(f.read_text())))
        objs = {int(x["NORAD_CAT_ID"]): normalise(x, satcat, "active", rep.interval_start) for x in recs}
        if r.norad_1 not in objs or r.norad_2 not in objs:
            cv.n_policy_excluded += 1
            cv.misses.append((r.norad_1, r.norad_2, "element set not parseable"))
            continue
        res = screen([objs[r.norad_1], objs[r.norad_2]], r.tca - timedelta(hours=2), r.tca + timedelta(hours=2))
        if res.run.excluded:
            cv.n_policy_excluded += 1
            cv.misses.append((r.norad_1, r.norad_2, "; ".join(res.run.excluded.values())))
            continue
        best = min(res.conjunctions, key=lambda c: abs((c.tca - r.tca).total_seconds()), default=None)
        if best is not None and abs((best.tca - r.tca).total_seconds()) < 60:
            cv.n_hits += 1
            cv.tca_abs_err_s.append(abs((best.tca - r.tca).total_seconds()))
            cv.miss_err_m.append(best.miss_m - r.min_range_km * 1000.0)
        else:
            cv.misses.append((r.norad_1, r.norad_2, "not found"))
    denom = max(cv.n_pairs - cv.n_policy_excluded - cv.n_formation, 1)
    cv.recall_on_encounters = cv.n_hits / denom
    cv.recall_raw = cv.n_hits / max(cv.n_pairs, 1)
    return cv


def cross_validate_current_elements(rows: list[SocratesRow], rep: SocratesReport, objects: dict) -> CrossValidation:
    usable = [r for r in rows if r.norad_1 in objects and r.norad_2 in objects and not _is_formation(r)]
    ids = sorted({r.norad_1 for r in usable} | {r.norad_2 for r in usable})
    res = screen([objects[i] for i in ids], rep.interval_start, rep.interval_stop,
                 pairs_override=[(r.norad_1, r.norad_2) for r in usable])
    found: dict = {}
    for c in res.conjunctions:
        found.setdefault(c.key(), []).append(c)
    cv = CrossValidation("current_elements", len(usable), 0, 0, sum(_is_formation(r) for r in rows), 0.0, 0.0)
    for r in usable:
        key = (min(r.norad_1, r.norad_2), max(r.norad_1, r.norad_2))
        best = min(found.get(key, []), key=lambda c: abs((c.tca - r.tca).total_seconds()), default=None)
        day = int((r.tca - rep.interval_start).total_seconds() // 86400)
        h, n = cv.by_day.get(day, (0, 0))
        hit = best is not None and abs((best.tca - r.tca).total_seconds()) < 120
        cv.by_day[day] = (h + int(hit), n + 1)
        if hit:
            cv.n_hits += 1
            cv.tca_abs_err_s.append(abs((best.tca - r.tca).total_seconds()))
            cv.miss_err_m.append(best.miss_m - r.min_range_km * 1000.0)
        else:
            cv.misses.append((r.norad_1, r.norad_2, "drifted or manoeuvred since the SOCRATES run"))
    cv.recall_on_encounters = cv.n_hits / max(len(usable), 1)
    cv.recall_raw = cv.recall_on_encounters
    return cv
