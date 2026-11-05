#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/CALCULATIONS_AND_TUNINGS/MUON_TOF_ENERGY_RECONSTRUCTION/muon_tof_energy_reconstruction.py
Purpose: Explore muon-energy reconstruction from time-of-flight measurements across equidistant detector planes.
Owner: DATAFLOW_v3 contributors
Sign-off: C. Soneira-Landín <cayesoneira@gmail.com>
Last Updated: 2026-10-22
Runtime: python3
Usage: python3 muon_tof_energy_reconstruction.py [--full-grid] [--mode quadrature|monte-carlo] [--samples N] [--output-dir DIR] [--no-show]
Inputs: Scan parameters defined in this script and optional CLI arguments.
Outputs: Four contour plots and a compressed NumPy file containing the evaluated scan grids.
Notes: Ancillary physics study; it is not part of the production MINGO analysis pipeline. Energies are total relativistic energies.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from numpy.polynomial.hermite import hermgauss

# -----------------------------------------------------------------------------
# Physics constants
# -----------------------------------------------------------------------------
MUON_MASS_EV = 105.66e6
C_M_S = 3.0e8
EPSILON = 1e-12

# Original scan ranges from the March-2025 study.
D_MIN_M, D_MAX_M = 0.5, 100.0
M_MIN, M_MAX = 4, 99
E_MIN_EV, E_MAX_EV = 0.32e9, 10.0e9
SIGMA_T_MIN_NS, SIGMA_T_MAX_NS = 0.010, 0.500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ancillary TOF study of muon-energy reconstruction. The default "
            "scan is reduced for interactive use; --full-grid restores the "
            "original 100 x 96 x 100 x 100 parameter grid."
        )
    )
    parser.add_argument(
        "--full-grid",
        action="store_true",
        help="Use the original dense scan grid. This is computationally expensive.",
    )
    parser.add_argument(
        "--mode",
        choices=("quadrature", "monte-carlo"),
        default="quadrature",
        help=(
            "quadrature computes the expected residual from the exact Gaussian "
            "OLS-slope distribution; monte-carlo samples that same distribution."
        ),
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10_000,
        help="Monte Carlo samples per parameter point when --mode monte-carlo is used.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=12345,
        help="Random seed used in Monte Carlo mode.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("muon_tof_outputs"),
        help="Directory for plots and the compressed numerical scan.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Save figures without opening interactive matplotlib windows.",
    )
    return parser.parse_args()


def build_scan(full_grid: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return distance, plane-count, total-energy and timing-resolution grids."""
    if full_grid:
        d_total_values = np.linspace(D_MIN_M, D_MAX_M, 100)
        m_values = np.arange(M_MIN, M_MAX + 1, dtype=int)
        energies_values = np.logspace(np.log10(E_MIN_EV), np.log10(E_MAX_EV), 100)
        sigma_t_values = np.linspace(SIGMA_T_MIN_NS, SIGMA_T_MAX_NS, 100)
    else:
        # Same physical range as the original study, but small enough for routine use.
        d_total_values = np.linspace(D_MIN_M, D_MAX_M, 20)
        m_values = np.unique(np.rint(np.linspace(M_MIN, M_MAX, 20)).astype(int))
        energies_values = np.logspace(np.log10(E_MIN_EV), np.log10(E_MAX_EV), 40)
        sigma_t_values = np.linspace(SIGMA_T_MIN_NS, SIGMA_T_MAX_NS, 40)

    return d_total_values, m_values, energies_values, sigma_t_values


def true_tof_slope_ns_per_m(energies_ev: np.ndarray) -> np.ndarray:
    """True dt/dx slope in ns/m for muons of the supplied total energies."""
    v_true = C_M_S * np.sqrt(1.0 - (MUON_MASS_EV / energies_ev) ** 2)
    return 1.0e9 / v_true


def sxx_equidistant(d_total_m: np.ndarray, m_values: np.ndarray) -> np.ndarray:
    """
    Return Sxx = sum((x_i - x_bar)^2) for m equidistant planes from 0 to d.

    For m equally spaced positions spanning d:
        Sxx = d^2 * m * (m + 1) / [12 * (m - 1)].
    """
    d = d_total_m[:, None]
    m = m_values[None, :].astype(float)
    return d**2 * m * (m + 1.0) / (12.0 * (m - 1.0))


def energy_from_slope(slopes_ns_per_m: np.ndarray) -> np.ndarray:
    """Convert fitted TOF slopes to reconstructed total muon energy in eV."""
    v_sim = 1.0 / (slopes_ns_per_m * 1.0e-9)
    denom = np.maximum(1.0 - (v_sim / C_M_S) ** 2, EPSILON)
    return MUON_MASS_EV / np.sqrt(denom)


def relative_residual_percent(energy_true_ev: np.ndarray, energy_reco_ev: np.ndarray) -> np.ndarray:
    """Absolute relative residual in percent."""
    return np.abs(energy_true_ev - energy_reco_ev) / energy_true_ev * 100.0


def expected_residual_grid_quadrature(
    slope_true: np.ndarray,
    sigma_slope: np.ndarray,
    energies_ev: np.ndarray,
    order: int = 24,
) -> np.ndarray:
    """
    Expected |E_true-E_reco|/E_true using Gauss-Hermite quadrature.

    Under independent Gaussian per-plane timing errors, the OLS fitted slope is
    exactly Gaussian with sigma_slope = sigma_T / sqrt(Sxx). This is the same
    fitted-slope distribution produced by the original explicit plane-by-plane
    Monte Carlo, but avoids allocating m x num_samples timing matrices.
    """
    nodes, weights = hermgauss(order)
    weights = weights / np.sqrt(np.pi)

    result = np.zeros(sigma_slope.shape + (energies_ev.size,), dtype=float)
    slope_true_expanded = slope_true.reshape((1,) * sigma_slope.ndim + (energies_ev.size,))
    energy_true_expanded = energies_ev.reshape((1,) * sigma_slope.ndim + (energies_ev.size,))

    for node, weight in zip(nodes, weights):
        slopes = slope_true_expanded + np.sqrt(2.0) * sigma_slope[..., None] * node
        energy_reco = energy_from_slope(slopes)
        result += weight * relative_residual_percent(energy_true_expanded, energy_reco)

    return result


def expected_residual_grid_monte_carlo(
    slope_true: np.ndarray,
    sigma_slope: np.ndarray,
    energies_ev: np.ndarray,
    samples: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Monte Carlo expectation using the exact Gaussian OLS-slope distribution.

    This preserves the stochastic character of the original code while being
    substantially cheaper than generating a timing value for every plane.
    """
    if samples <= 0:
        raise ValueError("--samples must be positive")

    result = np.empty(sigma_slope.shape + (energies_ev.size,), dtype=float)

    for index in np.ndindex(sigma_slope.shape):
        noise = rng.normal(size=(samples, 1))
        slopes = slope_true[None, :] + sigma_slope[index] * noise
        energy_reco = energy_from_slope(slopes)
        residual = relative_residual_percent(energies_ev[None, :], energy_reco)
        result[index] = np.nanmean(residual, axis=0)

    return result


def evaluate_scan(
    d_total_values: np.ndarray,
    m_values: np.ndarray,
    energies_values: np.ndarray,
    sigma_t_values: np.ndarray,
    mode: str,
    samples: int,
    seed: int,
) -> np.ndarray:
    """Evaluate the four-dimensional relative-residual scan."""
    slope_true = true_tof_slope_ns_per_m(energies_values)
    sxx = sxx_equidistant(d_total_values, m_values)

    # Shape: distance x planes x sigma_T.
    sigma_slope = sigma_t_values[None, None, :] / np.sqrt(sxx[:, :, None])

    if mode == "quadrature":
        residual4d = expected_residual_grid_quadrature(
            slope_true=slope_true,
            sigma_slope=sigma_slope,
            energies_ev=energies_values,
        )
    else:
        rng = np.random.default_rng(seed)
        residual4d = expected_residual_grid_monte_carlo(
            slope_true=slope_true,
            sigma_slope=sigma_slope,
            energies_ev=energies_values,
            samples=samples,
            rng=rng,
        )

    # Preserve the original plotting convention: residuals >= 50% saturate.
    return np.clip(residual4d, 0.0, 50.0)


def project_for_plots(residual4d: np.ndarray) -> dict[str, np.ndarray]:
    """
    Reduce the 4-D scan to the four intended 2-D plots.

    The original script passed repeated (x, y) coordinates with different z
    values directly to tricontourf. Here the two unused variables are averaged,
    producing one unambiguous residual value per plotted coordinate.
    """
    return {
        "energy_sigma": residual4d.mean(axis=(0, 1)),
        "energy_planes": residual4d.mean(axis=(0, 2)),
        "sigma_planes": residual4d.mean(axis=(0, 3)),
        "distance_planes": residual4d.mean(axis=(2, 3)).T,
    }


def save_contour(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    xlabel: str,
    ylabel: str,
    title: str,
    path: Path,
    show: bool,
) -> None:
    fig = plt.figure(figsize=(8, 6))
    contour = plt.contourf(x, y, z, levels=50, cmap="viridis_r", extend="both")
    plt.colorbar(contour, label="Mean Energy Residual (%)")
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    if show:
        plt.show()
    plt.close(fig)


def detector_figure_of_merit(d_m: float, m: int, sigma_t_ns: float) -> float:
    """Leading TOF detector figure of merit d*sqrt(m)/sigma_T."""
    return d_m * np.sqrt(m) / sigma_t_ns


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    d_values, m_values, energies, sigma_t_values = build_scan(args.full_grid)

    total_points = len(d_values) * len(m_values) * len(sigma_t_values) * len(energies)
    print(f"Scan grid: {len(d_values)} x {len(m_values)} x {len(sigma_t_values)} x {len(energies)}")
    print(f"Parameter points: {total_points:,}")
    print(f"Evaluation mode: {args.mode}")
    if args.full_grid:
        print("WARNING: --full-grid restores the original dense 96-million-point scan.")

    residual4d = evaluate_scan(
        d_total_values=d_values,
        m_values=m_values,
        energies_values=energies,
        sigma_t_values=sigma_t_values,
        mode=args.mode,
        samples=args.samples,
        seed=args.seed,
    )
    projected = project_for_plots(residual4d)

    np.savez_compressed(
        args.output_dir / "muon_tof_scan.npz",
        d_total_values=d_values,
        m_values=m_values,
        energies_values=energies,
        sigma_t_values=sigma_t_values,
        rel_residuals=residual4d,
    )

    show = not args.no_show
    save_contour(
        energies / 1e9,
        sigma_t_values,
        projected["energy_sigma"],
        "Muon Energy (GeV)",
        "Timing Resolution σ_T (ns)",
        "Energy Residual vs Energy and Timing Resolution",
        args.output_dir / "1_energy_vs_timing.png",
        show,
    )
    save_contour(
        energies / 1e9,
        m_values,
        projected["energy_planes"],
        "Muon Energy (GeV)",
        "Number of Planes",
        "Energy Residual vs Energy and Number of Planes",
        args.output_dir / "2_energy_vs_planes.png",
        show,
    )
    save_contour(
        sigma_t_values,
        m_values,
        projected["sigma_planes"],
        "Timing Resolution σ_T (ns)",
        "Number of Planes",
        "Energy Residual vs Timing Resolution and Number of Planes",
        args.output_dir / "3_timing_vs_planes.png",
        show,
    )
    save_contour(
        d_values,
        m_values,
        projected["distance_planes"],
        "Distance (m)",
        "Number of Planes",
        "Energy Residual vs Detector Distance and Number of Planes",
        args.output_dir / "4_distance_vs_planes.png",
        show,
    )

    # For equidistant planes, sigma(slope) = sigma_T/sqrt(Sxx), with
    # Sxx = d^2*m(m+1)/(12(m-1)). At moderate/large m this becomes
    # sigma(slope) ~ sqrt(12)*sigma_T/(d*sqrt(m)).
    print("\nLeading detector scaling:")
    print("  slope precision ∝ d*sqrt(m)/sigma_T")
    print("  equivalently, sigma_slope ≈ sqrt(12)*sigma_T/[d*sqrt(m)]")
    print(
        "  example FOM at d=2 m, m=4, sigma_T=0.1 ns: "
        f"{detector_figure_of_merit(2.0, 4, 0.1):.1f} m/ns"
    )
    print(f"\nOutputs written to: {args.output_dir}")


if __name__ == "__main__":
    main()
