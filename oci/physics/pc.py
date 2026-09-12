"""Probability of collision (SPEC §11.4): Foster 2D, maximum-Pc, dilution detection.

Pc is only ever computed over a stated covariance with a stated HBR. With no covariance the
answer is None + na_reason, never zero (§12.5).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from oci.config import CONFIG
from oci.labels import Traced, na, traced

_FN = "physics.pc.foster_2d@0.1.0"


def foster_2d(miss_xy_m: np.ndarray, cov_xy_m2: np.ndarray, hbr_m: float,
              n_r: int | None = None, n_theta: int | None = None) -> float:
    """Integrate the bivariate normal over the disk of radius HBR centred on the miss vector.

    Polar quadrature in (ρ, θ): midpoint in ρ (weighted by ρ), uniform in θ. Verified
    against Monte Carlo in tests/test_pc.py.
    """
    n_r = n_r or CONFIG.pc.quadrature_n_r
    n_theta = n_theta or CONFIG.pc.quadrature_n_theta
    det = float(np.linalg.det(cov_xy_m2))
    if det <= 0:
        raise ValueError("covariance is not positive definite")
    inv = np.linalg.inv(cov_xy_m2)
    rho = (np.arange(n_r) + 0.5) * (hbr_m / n_r)
    theta = (np.arange(n_theta) + 0.5) * (2.0 * np.pi / n_theta)
    RHO, TH = np.meshgrid(rho, theta, indexing="ij")
    X = RHO * np.cos(TH) - miss_xy_m[0]
    Y = RHO * np.sin(TH) - miss_xy_m[1]
    q = inv[0, 0] * X * X + 2.0 * inv[0, 1] * X * Y + inv[1, 1] * Y * Y
    dens = np.exp(-0.5 * q) / (2.0 * np.pi * np.sqrt(det))
    dA = (hbr_m / n_r) * (2.0 * np.pi / n_theta)
    return float(np.sum(dens * RHO) * dA)


def foster_2d_batch(miss_xy_m: np.ndarray, cov_xy_m2: np.ndarray, hbr_m: float,
                    n_r: int | None = None, n_theta: int | None = None) -> np.ndarray:
    """foster_2d for many miss vectors (shape (n, 2)) against one covariance — the same
    quadrature, evaluated once for all samples. Used by the Monte Carlo (§10.6)."""
    n_r = n_r or CONFIG.pc.quadrature_n_r
    n_theta = n_theta or CONFIG.pc.quadrature_n_theta
    det = float(np.linalg.det(cov_xy_m2))
    if det <= 0:
        raise ValueError("covariance is not positive definite")
    inv = np.linalg.inv(cov_xy_m2)
    rho = (np.arange(n_r) + 0.5) * (hbr_m / n_r)
    theta = (np.arange(n_theta) + 0.5) * (2.0 * np.pi / n_theta)
    RHO, TH = np.meshgrid(rho, theta, indexing="ij")
    gx, gy = (RHO * np.cos(TH)).ravel(), (RHO * np.sin(TH)).ravel()          # (G,)
    X = gx[None, :] - miss_xy_m[:, 0:1]                                       # (n, G)
    Y = gy[None, :] - miss_xy_m[:, 1:2]
    q = inv[0, 0] * X * X + 2.0 * inv[0, 1] * X * Y + inv[1, 1] * Y * Y
    dens = np.exp(-0.5 * q) / (2.0 * np.pi * np.sqrt(det))
    dA = (hbr_m / n_r) * (2.0 * np.pi / n_theta)
    return np.sum(dens * RHO.ravel()[None, :], axis=1) * dA


def pc_maximum(miss_xy_m: np.ndarray, cov_xy_m2: np.ndarray, hbr_m: float) -> tuple[float, float]:
    """Max over covariance scaling factors (§11.4 'maximum probability'). Returns (Pc_max, k*)."""
    best, best_k = 0.0, 1.0
    for k in CONFIG.pc.max_pc_scaling_grid:
        p = foster_2d(miss_xy_m, cov_xy_m2 * k, hbr_m)
        if p > best:
            best, best_k = p, k
    return best, best_k


def dilution_flag(miss_xy_m: np.ndarray, cov_xy_m2: np.ndarray, hbr_m: float) -> bool:
    """True when inflating σ would LOWER Pc — the dilution region, where a low Pc is not reassuring."""
    base = foster_2d(miss_xy_m, cov_xy_m2, hbr_m)
    for k in CONFIG.pc.dilution_check_scales:
        if k == 1.0:
            continue
        if foster_2d(miss_xy_m, cov_xy_m2 * k, hbr_m) < base * 0.999:
            return True
    return False


@dataclass(frozen=True)
class PcResult:
    pc: Traced
    pc_max: Traced
    method: str
    covariance_source: str
    hbr_m: float
    mahalanobis: Optional[float]
    dilution: bool
    sigma_rtn_combined_m: Optional[tuple[float, float, float]]


def compute_pc(miss_xy_m: Optional[np.ndarray], cov_xy_m2: Optional[np.ndarray],
               covariance_source: str, hbr_m: float | None = None,
               sigma_rtn_combined_m: Optional[tuple[float, float, float]] = None) -> PcResult:
    hbr = hbr_m if hbr_m is not None else CONFIG.pc.hard_body_radius_m
    assumptions = {"hbr_m": hbr, "covariance_source": covariance_source, "pc_method": CONFIG.pc.method}
    if cov_xy_m2 is None or miss_xy_m is None or covariance_source == "none":
        reason = "no covariance available (TLE carries none; covariance_source='none')"
        return PcResult(
            pc=na("probability", "MODELLED", _FN, reason, **assumptions),
            pc_max=na("probability", "MODELLED", "physics.pc.maximum@0.1.0", reason, **assumptions),
            method="none", covariance_source=covariance_source, hbr_m=hbr,
            mahalanobis=None, dilution=False, sigma_rtn_combined_m=None,
        )
    p = foster_2d(miss_xy_m, cov_xy_m2, hbr)
    pmax, kstar = pc_maximum(miss_xy_m, cov_xy_m2, hbr)
    from oci.physics.geometry import mahalanobis
    return PcResult(
        pc=traced(p, "probability", "MODELLED", _FN, **assumptions),
        pc_max=traced(pmax, "probability", "MODELLED", "physics.pc.maximum@0.1.0", k_star=kstar, **assumptions),
        method=CONFIG.pc.method, covariance_source=covariance_source, hbr_m=hbr,
        mahalanobis=mahalanobis(miss_xy_m, cov_xy_m2),
        dilution=dilution_flag(miss_xy_m, cov_xy_m2, hbr),
        sigma_rtn_combined_m=sigma_rtn_combined_m,
    )
