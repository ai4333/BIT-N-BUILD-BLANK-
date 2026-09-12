"""§14.6 — number-fabrication guard. Every numeric literal in the planner's prose must appear in
some tool result (within rounding tolerance). Otherwise the output is not displayed."""
from __future__ import annotations

import math
import re
from typing import Any, Iterable

_NUM = re.compile(r"(?<![\w.])[-+]?(?:\d+\.\d+|\.\d+|\d+)(?:[eE][-+]?\d+)?(?!\w|\.\d)")
# tokens that are structural, not claims: list numbering, headings, NORAD/strategy ids, dates
_SKIP = re.compile(r"^\s*\d+\.\s|NORAD\s*\d+|agent_\d+|str_\d+|clu_\d+|\d{4}-\d{2}-\d{2}|\d{2}:\d{2}|C\d\b|R\d\b|S\d\b|\d+\s*(?:σ|sigma)")


def collect_numeric_values(tool_results: Iterable[Any]) -> list[float]:
    out: list[float] = []

    def walk(x: Any) -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)) and math.isfinite(x):
            out.append(float(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            for m in _NUM.finditer(x):
                try:
                    out.append(float(m.group(0)))
                except ValueError:
                    pass
    for r in tool_results:
        walk(r)
    return out


def extract_numbers(text: str) -> list[tuple[float, str]]:
    found = []
    for line in text.splitlines():
        for m in _NUM.finditer(line):
            ctx = line[max(0, m.start() - 12): m.end() + 12]
            if _SKIP.search(ctx):
                continue
            try:
                found.append((float(m.group(0)), m.group(0)))
            except ValueError:
                pass
    return found


def _display_tolerance(lit: str) -> float:
    """Half a unit in the last displayed digit: '42.7' → 0.05, '85' → 0.5, '1.28e-03' → 5e-6."""
    m = re.match(r"[-+]?(\d*)(?:\.(\d*))?(?:[eE]([-+]?\d+))?$", lit)
    if not m:
        return 0.0
    decimals = len(m.group(2) or "")
    exp = int(m.group(3) or 0)
    return 0.5 * 10.0 ** (exp - decimals)


def _permitted(n: float, lit: str, permitted: list[float]) -> bool:
    """`n` (written as `lit`) is permitted when some tool value equals it within display rounding
    (half a unit in the last digit shown, or 2 % relative), or is an integer percentage of a
    fraction (85 for 0.8523), or a ×1000 unit change (km → m)."""
    if n in (0.0, 1.0, 2.0, 3.0, 100.0):          # unitless counts/percent bases are not physics claims
        return True
    tol = _display_tolerance(lit) * 1.01
    is_int = float(n).is_integer()
    for p in permitted:
        if abs(n - p) <= max(tol, 0.02 * abs(p)):
            return True
        if is_int and 0.0 <= p <= 1.0 and abs(n - p * 100.0) <= 0.5:
            return True                              # integer percentage of a fraction
        if p != 0 and abs(n - p * 1000.0) <= max(tol, 0.02 * abs(p * 1000.0)):
            return True                              # unit change (km → m, m/s → mm/s)
    return False


def check_no_fabricated_numbers(agent_output: str, tool_results: list[Any]) -> list[str]:
    """Return the literals in `agent_output` that no tool result supports."""
    permitted = collect_numeric_values(tool_results)
    return [lit for n, lit in extract_numbers(agent_output) if not _permitted(n, lit, permitted)]
