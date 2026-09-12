"""D1 — CelesTrak GP catalogue, D3 — SOCRATES, D5 — public SATCAT (SPEC §6.2, §6.4, §6.5).

Etiquette (§6.2): every download is cached to disk with a timestamp; a group is fetched at
most once per `min_refresh_h`; a descriptive User-Agent is sent; `offline=True` reads only
from cache and never touches the network. **Use offline mode for the demo.**
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

CACHE_DIR = Path("data/cache")
USER_AGENT = "OCI-hackathon/0.1 (Orbital Capacity Intelligence research prototype)"
GP_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json"
SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
SOCRATES_URL = "https://celestrak.org/socrates/table-socrates.php?NAME=,&ORDER={order}&MAX={n}"
MIN_REFRESH_H = 2.0


class OfflineCacheMiss(FileNotFoundError):
    pass


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def _age_h(p: Path) -> float:
    return (time.time() - p.stat().st_mtime) / 3600.0


def _fetch_text(url: str, dest: Path, offline: bool, min_refresh_h: float = MIN_REFRESH_H, timeout: float = 120.0) -> tuple[str, str]:
    """Returns (text, source) where source ∈ {cache, network}. Never re-fetches inside the refresh window."""
    if dest.exists() and (offline or _age_h(dest) < min_refresh_h):
        return dest.read_text(), "cache"
    if offline:
        raise OfflineCacheMiss(f"offline mode and no cache at {dest}")
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        if dest.exists():   # fall back to a stale cache, loudly (§10.1 failure modes)
            print(f"[celestrak] WARNING: fetch failed ({e}); using stale cache {dest} ({_age_h(dest):.1f} h old)")
            return dest.read_text(), "cache-stale"
        raise
    dest.write_text(r.text)
    return r.text, "network"


# ── D1 GP catalogue ───────────────────────────────────────────────────────────────────────
def fetch_gp_group(group: str = "active", offline: bool = False) -> tuple[list[dict], dict]:
    text, source = _fetch_text(GP_URL.format(group=group), _cache_path(f"gp_{group}.json"), offline)
    recs = json.loads(text)
    meta = {"group": group, "source": source, "n": len(recs),
            "cached_at": datetime.fromtimestamp(_cache_path(f"gp_{group}.json").stat().st_mtime, timezone.utc).isoformat()}
    return recs, meta


# ── D5 SATCAT ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SatcatRow:
    norad_id: int
    object_name: str
    object_id: str
    object_type: str          # PAYLOAD | ROCKET_BODY | DEBRIS | UNKNOWN
    ops_status: str           # CelesTrak status code: + P B S X D ? …
    owner: str
    launch_date: Optional[str]
    decay_date: Optional[str]
    rcs_m2: Optional[float]
    rcs_size: Optional[str]   # SMALL <0.1 | MEDIUM 0.1–1 | LARGE >1 (Space-Track buckets)
    orbit_type: str


_TYPE = {"PAY": "PAYLOAD", "R/B": "ROCKET_BODY", "DEB": "DEBRIS", "UNK": "UNKNOWN"}


def _rcs_bucket(rcs: Optional[float]) -> Optional[str]:
    if rcs is None:
        return None
    return "SMALL" if rcs < 0.1 else ("MEDIUM" if rcs < 1.0 else "LARGE")


def load_satcat(offline: bool = False) -> dict[int, SatcatRow]:
    text, _ = _fetch_text(SATCAT_URL, _cache_path("satcat.csv"), offline, min_refresh_h=24.0)
    out: dict[int, SatcatRow] = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            nid = int(row["NORAD_CAT_ID"])
        except (ValueError, KeyError):
            continue
        rcs = float(row["RCS"]) if row.get("RCS") else None
        out[nid] = SatcatRow(
            norad_id=nid, object_name=row["OBJECT_NAME"], object_id=row["OBJECT_ID"],
            object_type=_TYPE.get(row["OBJECT_TYPE"], "UNKNOWN"), ops_status=row.get("OPS_STATUS_CODE", "") or "",
            owner=row.get("OWNER", "") or "", launch_date=row.get("LAUNCH_DATE") or None,
            decay_date=row.get("DECAY_DATE") or None, rcs_m2=rcs, rcs_size=_rcs_bucket(rcs),
            orbit_type=row.get("ORBIT_TYPE", "") or "",
        )
    return out


# ── D3 SOCRATES ───────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SocratesRow:
    norad_1: int
    name_1: str
    norad_2: int
    name_2: str
    tca: datetime
    min_range_km: float
    rel_speed_kmps: float
    max_prob: float
    dilution_km: float


@dataclass
class SocratesReport:
    rows: list[SocratesRow]
    data_current: Optional[str]
    interval_start: Optional[datetime]
    interval_stop: Optional[datetime]
    n_primaries: Optional[int]
    n_secondaries: Optional[int]
    n_conjunctions_total: Optional[int]
    order: str
    source: str


def _strip(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", cell)).replace("\xa0", " ").strip()


def fetch_socrates(order: str = "MINRANGE", n: int = 1000, offline: bool = False) -> SocratesReport:
    """SOCRATES publishes at most 1,000 rows per query. Rows come in pairs (object 1, object 2)."""
    text, source = _fetch_text(SOCRATES_URL.format(order=order, n=n), _cache_path(f"socrates_{order}_{n}.html"), offline, min_refresh_h=8.0)
    rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S)
    parsed: list[list[str]] = [[_strip(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)] for r in rows_html]
    header = next((r[0] for r in parsed if r and r[0].startswith("Data current as of")), "")
    m = re.search(r"Start = (\d{4} \w{3} \d{2} \d{2}:\d{2}:\d{2}) UTC, Stop = (\d{4} \w{3} \d{2} \d{2}:\d{2}:\d{2}) UTC", header)
    fmt = "%Y %b %d %H:%M:%S"
    t0 = datetime.strptime(m.group(1), fmt).replace(tzinfo=timezone.utc) if m else None
    t1 = datetime.strptime(m.group(2), fmt).replace(tzinfo=timezone.utc) if m else None
    m2 = re.search(r"Considering: ([\d,]+) Primaries, ([\d,]+) Secondaries \(([\d,]+) Conjunctions\)", header)
    cur = re.search(r"Data current as of (.*?) UTC", header)
    out: list[SocratesRow] = []
    i = 0
    while i < len(parsed) - 1:
        a, b = parsed[i], parsed[i + 1]
        # object-1 line: [GP Data, norad, name, dse, tca, range, speed]
        # object-2 line: [graph links, norad, name, dse, maxprob, dilution]
        if len(a) >= 7 and a[0] == "GP Data" and a[1].isdigit() and len(b) >= 6 and b[1].isdigit():
            try:
                out.append(SocratesRow(
                    norad_1=int(a[1]), name_1=a[2], norad_2=int(b[1]), name_2=b[2],
                    tca=datetime.strptime(a[4], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc),
                    min_range_km=float(a[5]), rel_speed_kmps=float(a[6]),
                    max_prob=float(b[4].replace("E", "e")), dilution_km=float(b[5]),
                ))
                i += 2
                continue
            except (ValueError, IndexError):
                pass
        i += 1
    return SocratesReport(rows=out, data_current=cur.group(1) if cur else None, interval_start=t0, interval_stop=t1,
                          n_primaries=int(m2.group(1).replace(",", "")) if m2 else None,
                          n_secondaries=int(m2.group(2).replace(",", "")) if m2 else None,
                          n_conjunctions_total=int(m2.group(3).replace(",", "")) if m2 else None,
                          order=order, source=source)
