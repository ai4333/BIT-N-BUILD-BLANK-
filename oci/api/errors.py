"""RFC 7807 problem+json (SPEC §12.5)."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class Problem(Exception):
    def __init__(self, type_: str, title: str, status: int, detail: str):
        super().__init__(detail)
        self.type, self.title, self.status, self.detail = f"/errors/{type_}", title, status, detail


def problem_response(request: Request, exc: Problem) -> JSONResponse:
    return JSONResponse(status_code=exc.status, media_type="application/problem+json",
                        content={"type": exc.type, "title": exc.title, "status": exc.status, "detail": exc.detail,
                                 "instance": str(request.url.path) + (f"?{request.url.query}" if request.url.query else "")})


def run_not_found(run_id: str) -> Problem:
    return Problem("run-not-found", "Screening run not found", 404, f"No run '{run_id}'. GET /api/v1/screening-runs lists the runs available.")


def object_not_found(nid) -> Problem:
    return Problem("object-not-found", "Object not found", 404, f"NORAD {nid} is not in this run's catalogue.")


def threshold_not_declared() -> Problem:
    return Problem("threshold-not-declared", "Pc threshold is required", 422,
                   "Burden is meaningless without a declared Pc threshold. Pass pc_threshold=1e-4 (or 1e-5, 1e-6).")


def insufficient_covariance(primary_id: int, secondary_id: int) -> Problem:
    return Problem("insufficient-covariance", "Cannot compute Pc", 422,
                   f"No covariance available for NORAD {primary_id} / {secondary_id} and covariance_source is "
                   "'none'. Pc is undefined — it is returned as null with an na_reason, never as 0.0. "
                   "Use geometry-only screening or set covariance_source='assumed'.")


def window_too_large(hours: float) -> Problem:
    return Problem("window-too-large", "Screening window too large", 422,
                   f"{hours:.0f} h exceeds the 14-day ceiling. Element sets are flagged stale after 7 days; "
                   "beyond that the propagated positions are not worth screening.")


def screening_timeout(run_id: str, budget_s: float) -> Problem:
    return Problem("screening-timeout", "Screening exceeded its budget", 504,
                   f"Run {run_id} passed the {budget_s:.0f} s ceiling (SPEC §12.6). Narrow the shell or the window.")


def validator_infeasible(reason: str) -> Problem:
    return Problem("validator-infeasible", "Proposed manoeuvre is infeasible", 422,
                   f"The deterministic validator rejected the burn before simulation: {reason}")


def agent_tool_limit_exceeded(n: int) -> Problem:
    return Problem("agent-tool-limit-exceeded", "Planner exceeded its tool budget", 429,
                   f"The planner made {n} tool calls without reaching a recommendation. "
                   "Raise max_tool_calls or narrow the cluster.")


def demo_safe_refusal(what: str) -> Problem:
    return Problem("demo-safe-refusal", "Refused in demo-safe mode", 409,
                   f"OCI_DEMO_SAFE=1 is set, so {what} is refused — the demo serves committed fixtures and "
                   "cached runs only, and must never touch the network.")
