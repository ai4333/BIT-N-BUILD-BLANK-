"""Traced values and provenance labels (SPEC §9.2, §9.3, §10.14).

Every number that can reach a display surface is a `Traced`, never a bare float. The label
says how much to trust it, `function` says who produced it, `assumptions` says what it rests
on, and `na_reason` is mandatory whenever `value` is None. A silent zero is forbidden.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

Label = Literal["OBSERVED", "COMPUTED", "MODELLED", "INDICATIVE"]


class Traced(BaseModel):
    """A number with provenance. `value is None` means "could not compute", and then
    `na_reason` must explain why."""

    value: Optional[float]
    unit: str
    label: Label
    function: str
    assumptions: dict[str, Any] = Field(default_factory=dict)
    na_reason: Optional[str] = None

    @model_validator(mode="after")
    def _na_needs_reason(self) -> "Traced":
        if self.value is None and not self.na_reason:
            raise ValueError("Traced value is None but na_reason is empty (SPEC §9.3)")
        if self.value is not None and self.na_reason:
            raise ValueError("Traced has both a value and an na_reason")
        return self

    # -- convenience -----------------------------------------------------------------
    @property
    def is_na(self) -> bool:
        return self.value is None

    def __float__(self) -> float:
        if self.value is None:
            raise ValueError(f"Traced value is N/A: {self.na_reason}")
        return float(self.value)

    def fmt(self, digits: int = 3) -> str:
        if self.value is None:
            return f"— ({self.na_reason})"
        v = self.value
        if abs(v) >= 1000 or (abs(v) < 1e-3 and v != 0):
            s = f"{v:.{digits}g}"
        else:
            s = f"{v:.{digits}f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v)}"
        tag = "" if self.label in ("OBSERVED", "COMPUTED") else f" ({self.label[:3]})"
        return f"{s} {self.unit}{tag}".strip()


def traced(value: Optional[float], unit: str, label: Label, function: str, **assumptions: Any) -> Traced:
    """Shorthand constructor for a value that exists."""
    return Traced(value=None if value is None else float(value), unit=unit, label=label,
                  function=function, assumptions=assumptions)


def na(unit: str, label: Label, function: str, reason: str, **assumptions: Any) -> Traced:
    """A value that could not be computed, with the reason attached."""
    return Traced(value=None, unit=unit, label=label, function=function,
                  assumptions=assumptions, na_reason=reason)


def walk_for_bare_floats(obj: Any, path: str = "$") -> list[str]:
    """Return JSON paths where a bare float sits in a display field instead of a Traced.

    Used by `test_no_bare_floats_in_api_response`. Keys listed in `STRUCTURAL_KEYS` are
    allowed to be raw numbers because they are identifiers or configuration, not results.
    """
    bad: list[str] = []
    if isinstance(obj, dict):
        if set(obj.keys()) >= {"value", "unit", "label", "function"}:
            return bad  # a serialised Traced
        for k, v in obj.items():
            if k in STRUCTURAL_KEYS:
                continue
            bad.extend(walk_for_bare_floats(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad.extend(walk_for_bare_floats(v, f"{path}[{i}]"))
    elif isinstance(obj, float):
        bad.append(path)
    return bad


STRUCTURAL_KEYS = frozenset({
    "norad_id", "primary_id", "secondary_id", "shell_id", "rank", "n", "count", "total",
    "limit", "offset", "seed", "window_days", "pc_threshold", "horizon_h", "mc_samples",
    "assumptions", "weights", "params", "inputs", "tca", "epoch", "alt_km", "alt_low_km",
    "alt_high_km", "members", "keystone_id", "max_pc_object_id", "id", "version",
})
