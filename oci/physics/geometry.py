"""RTN frame, covariance rotation, encounter (B-)plane construction (SPEC §11.3, §11.4)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def rtn_basis(r: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rows are R̂, T̂, N̂ — the rotation matrix M (inertial → RTN), §11.3."""
    R = r / np.linalg.norm(r)
    h = np.cross(r, v)
    N = h / np.linalg.norm(h)
    T = np.cross(N, R)
    return np.vstack([R, T, N])


def rtn_to_inertial(vec_rtn: np.ndarray, r: np.ndarray, v: np.ndarray) -> np.ndarray:
    return rtn_basis(r, v).T @ vec_rtn


def covariance_inertial(sigma_rtn_m: tuple[float, float, float], r: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Σ_inertial = Mᵀ Σ_RTN M, in metres² (§11.3). Diagonal RTN covariance."""
    M = rtn_basis(r, v)
    S = np.diag([s * s for s in sigma_rtn_m])
    return M.T @ S @ M


@dataclass(frozen=True)
class EncounterPlane:
    """Relative geometry projected into the plane ⟂ v_rel at TCA."""
    ux: np.ndarray            # in-plane axis along the projected miss vector
    uy: np.ndarray            # in-plane axis
    uz: np.ndarray            # along v_rel
    miss_xy_m: np.ndarray     # (2,) projected miss vector, metres
    cov_xy_m2: np.ndarray     # (2,2) projected combined covariance, metres²
    miss_m: float
    v_rel_mps: float


def encounter_plane(rel_r_km: np.ndarray, rel_v_kmps: np.ndarray, cov_combined_m2: np.ndarray) -> EncounterPlane:
    """§11.4 — B-plane basis from the relative state; project the miss vector and covariance."""
    rel_r_m = rel_r_km * 1000.0
    v_rel = np.linalg.norm(rel_v_kmps)
    uz = rel_v_kmps / v_rel
    # remove the component of the miss vector along v_rel (it is ~0 at TCA by definition)
    perp = rel_r_m - np.dot(rel_r_m, uz) * uz
    if np.linalg.norm(perp) < 1e-9:
        # degenerate: pick any perpendicular direction
        trial = np.array([1.0, 0.0, 0.0]) if abs(uz[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        perp = trial - np.dot(trial, uz) * uz
    ux = perp / np.linalg.norm(perp)
    uy = np.cross(uz, ux)
    P = np.vstack([ux, uy])            # (2,3)
    return EncounterPlane(
        ux=ux, uy=uy, uz=uz,
        miss_xy_m=P @ rel_r_m,
        cov_xy_m2=P @ cov_combined_m2 @ P.T,
        miss_m=float(np.linalg.norm(rel_r_m)),
        v_rel_mps=float(v_rel * 1000.0),
    )


def mahalanobis(miss_xy_m: np.ndarray, cov_xy_m2: np.ndarray) -> float:
    return float(np.sqrt(miss_xy_m @ np.linalg.solve(cov_xy_m2, miss_xy_m)))
