#!/usr/bin/env python3

"""Step 4: induce strip signals and measured hit quantities."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

_TWIN_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_TWIN_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_TWIN_BOOTSTRAP_ROOT))
from ORCHESTRATOR.lib.paths import digital_twin_root, repository_root
ROOT_DIR = digital_twin_root()
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))

from STEP_SHARED.sim_utils import (
    ensure_dir,
    find_latest_data_path,
    find_sim_run_dir,
    GEOMETRY_SCHEMA_VERSION,
    PlaneReadoutGeometry,
    RectBounds,
    build_readout_geometry,
    readout_geometry_to_dict,
    rect_bounds_to_dict,
    resolve_active_area_bounds,
    iter_input_frames,
    latest_sim_run,
    load_step_configs,
    load_with_metadata,
    now_iso,
    find_sim_run,
    build_sim_run_name,
    register_sim_run,
    extract_step_id_chain,
    select_next_step_id,
    random_sim_run,
    resolve_param_mesh,
    resolve_sim_run,
    reset_dir,
    save_with_metadata,
    select_param_row,
    extract_param_set,
)

ELEMENTARY_CHARGE_FC = 1.602176634e-4
LORENTZIAN_MIN_GAMMA_MM = 1.0e-6


def _active_area_from_metadata_lineage(meta: object) -> tuple[RectBounds, str] | None:
    cursor = meta
    while isinstance(cursor, dict):
        direct = cursor.get("active_area_bounds_mm")
        if isinstance(direct, dict):
            active_area_bounds, _ = resolve_active_area_bounds(
                {"active_area_bounds_mm": direct},
                warn_deprecated=False,
            )
            return active_area_bounds, "upstream_normalized_active_area"
        lineage_config = cursor.get("config")
        if isinstance(lineage_config, dict) and (
            "active_area_bounds_mm" in lineage_config or "bounds_mm" in lineage_config
        ):
            active_area_bounds, source = resolve_active_area_bounds(
                lineage_config,
                warn_deprecated=False,
            )
            return active_area_bounds, f"upstream_{source}"
        cursor = cursor.get("upstream")
    return None


def resolve_step4_active_area_bounds(
    config: dict,
    upstream_meta: dict | None,
) -> tuple[RectBounds, str]:
    # Direct Step-4 active bounds remain accepted only for old standalone workflows.
    if "active_area_bounds_mm" in config or "bounds_mm" in config:
        active_area_bounds, source = resolve_active_area_bounds(config)
        return active_area_bounds, f"step4_{source}"
    if isinstance(upstream_meta, dict):
        lineage_result = _active_area_from_metadata_lineage(upstream_meta)
        if lineage_result is not None:
            return lineage_result
    active_area_bounds, source = resolve_active_area_bounds({}, warn_deprecated=False)
    return active_area_bounds, source


def _readout_geometry_from_metadata_lineage(
    meta: object,
    active_area_bounds: RectBounds,
) -> tuple[dict[int, PlaneReadoutGeometry], str] | None:
    cursor = meta
    while isinstance(cursor, dict):
        lineage_config = cursor.get("config")
        if isinstance(lineage_config, dict) and "readout_geometry_mm" in lineage_config:
            geometry, _ = build_readout_geometry(
                lineage_config,
                legacy_active_area_bounds=active_area_bounds,
            )
            source = str(cursor.get("readout_geometry_source") or "metadata_config")
            return geometry, source
        cursor = cursor.get("upstream")
    return None


def resolve_step4_readout_geometry(
    config: dict,
    active_area_bounds: RectBounds,
    metadata: dict | None = None,
) -> tuple[dict[int, PlaneReadoutGeometry], str]:
    if "readout_geometry_mm" in config:
        return build_readout_geometry(
            config,
            legacy_active_area_bounds=active_area_bounds,
        )
    if isinstance(metadata, dict):
        lineage_result = _readout_geometry_from_metadata_lineage(metadata, active_area_bounds)
        if lineage_result is not None:
            return lineage_result
    return build_readout_geometry(
        config,
        legacy_active_area_bounds=active_area_bounds,
    )


def _recover_metadata_from_chunk_manifest(data_path: Path, meta: dict | None) -> dict | None:
    if isinstance(meta, dict) and meta:
        return meta
    parent = data_path.parent
    if not parent.name.endswith("_chunks"):
        return meta
    manifest_path = parent.parent / f"{parent.name}.chunks.json"
    if not manifest_path.exists():
        return meta
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return meta
    manifest_meta = payload.get("metadata")
    return manifest_meta if isinstance(manifest_meta, dict) else meta


def normalize_tt(series: pd.Series) -> pd.Series:
    tt = series.astype("string").fillna("")
    tt = tt.str.strip()
    tt = tt.str.replace(r"\.0$", "", regex=True)
    tt = tt.replace({"0": "", "0.0": "", "nan": "", "<NA>": ""})
    return tt


def is_random_value(value: object) -> bool:
    return isinstance(value, str) and value.lower() == "random"


def lorentzian_corner_angle(x_rel: np.ndarray, y_rel: np.ndarray, gamma: np.ndarray) -> np.ndarray:
    return np.arctan2(
        x_rel * y_rel,
        gamma * np.sqrt(x_rel ** 2 + y_rel ** 2 + gamma ** 2),
    )


def isotropic_lorentzian_rectangle_fraction(
    center_x: np.ndarray,
    center_y: np.ndarray,
    gammas: np.ndarray,
    x_lower: float,
    x_upper: float,
    y_lower: float,
    y_upper: float,
) -> np.ndarray:
    fractions = np.zeros_like(center_x, dtype=float)
    valid = (
        np.isfinite(center_x)
        & np.isfinite(center_y)
        & np.isfinite(gammas)
        & (gammas > 0)
    )
    if not np.any(valid):
        return fractions

    x0 = center_x[valid]
    y0 = center_y[valid]
    gamma = gammas[valid]
    x1 = x_lower - x0
    x2 = x_upper - x0
    y1 = y_lower - y0
    y2 = y_upper - y0
    solid_angle = (
        lorentzian_corner_angle(x2, y2, gamma)
        - lorentzian_corner_angle(x1, y2, gamma)
        - lorentzian_corner_angle(x2, y1, gamma)
        + lorentzian_corner_angle(x1, y1, gamma)
    )
    fractions[valid] = solid_angle / (2.0 * np.pi)
    return np.clip(fractions, 0.0, 1.0)


def isotropic_lorentzian_density_grid(
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    center_x: float,
    center_y: float,
    gamma_mm: float,
    total_charge_fc: float,
) -> np.ndarray:
    gamma = max(float(gamma_mm), LORENTZIAN_MIN_GAMMA_MM)
    x_grid, y_grid = np.meshgrid(x_axis, y_axis)
    radius_sq = (x_grid - center_x) ** 2 + (y_grid - center_y) ** 2
    return float(total_charge_fc) * gamma / (2.0 * np.pi * (radius_sq + gamma ** 2) ** 1.5)


def induce_signal(
    df: pd.DataFrame,
    x_noise: float,
    time_sigma_ns: float,
    lorentzian_gamma_mm: float,
    induced_charge_fraction: float,
    readout_geometry: dict[int, PlaneReadoutGeometry],
    rng: np.random.Generator,
    debug_event_index: int | None,
    debug_points: dict | None,
) -> pd.DataFrame:
    out = df.copy()
    n = len(df)
    tt_array = np.full(n, "", dtype=object)

    for plane_idx in range(1, 5):
        aval_e_col = f"avalanche_size_electrons_{plane_idx}"
        aval_x_col = f"avalanche_x_{plane_idx}"
        aval_y_col = f"avalanche_y_{plane_idx}"
        aval_electrons = df.get(aval_e_col, pd.Series(np.zeros(n))).to_numpy(dtype=float)
        aval_x = df.get(aval_x_col, pd.Series(np.full(n, np.nan))).to_numpy(dtype=float)
        aval_y = df.get(aval_y_col, pd.Series(np.full(n, np.nan))).to_numpy(dtype=float)
        t_sum_col = f"T_sum_{plane_idx}_ns"
        t_sum_vals = df[t_sum_col].to_numpy(dtype=float) if t_sum_col in df.columns else None
        gap_charge_fc = np.where(aval_electrons > 0, aval_electrons * ELEMENTARY_CHARGE_FC, 0.0)
        induced_charge_total_fc = gap_charge_fc * induced_charge_fraction
        plane_geometry = readout_geometry[plane_idx]
        plane_y_lower = plane_geometry.y_min
        plane_y_upper = plane_geometry.y_max
        gamma_mm = np.where(induced_charge_total_fc > 0, float(lorentzian_gamma_mm), 0.0)
        valid = (
            np.isfinite(aval_x)
            & np.isfinite(aval_y)
            & (induced_charge_total_fc > 0)
            & (gamma_mm > 0)
        )
        readout_bounding_fraction = isotropic_lorentzian_rectangle_fraction(
            aval_x,
            aval_y,
            np.where(valid, gamma_mm, np.nan),
            plane_geometry.x_min,
            plane_geometry.x_max,
            plane_y_lower,
            plane_y_upper,
        )
        out[f"avalanche_size_electrons_{plane_idx}"] = aval_electrons.astype(np.float32, copy=False)
        out[f"avalanche_gap_charge_fc_{plane_idx}"] = gap_charge_fc.astype(np.float32, copy=False)
        out[f"induced_charge_total_fc_{plane_idx}"] = induced_charge_total_fc.astype(np.float32, copy=False)
        out[f"lorentzian_gamma_mm_{plane_idx}"] = gamma_mm.astype(np.float32, copy=False)

        plane_detected = np.zeros(n, dtype=bool)
        if (
            debug_event_index is not None
            and 0 <= debug_event_index < n
            and valid[debug_event_index]
        ):
            if debug_points is not None:
                debug_points[plane_idx] = {
                    "center_x": float(aval_x[debug_event_index]),
                    "center_y": float(aval_y[debug_event_index]),
                    "gamma_mm": float(gamma_mm[debug_event_index]),
                    "gap_charge_fc": float(gap_charge_fc[debug_event_index]),
                    "induced_charge_fc": float(induced_charge_total_fc[debug_event_index]),
                    "readout_bounding_fraction": float(readout_bounding_fraction[debug_event_index]),
                }

        readout_assigned_fraction = np.zeros(n, dtype=np.float32)
        for strip in plane_geometry.strips:
            strip_idx = strip.strip_index - 1
            frac = isotropic_lorentzian_rectangle_fraction(
                aval_x,
                aval_y,
                np.where(valid, gamma_mm, np.nan),
                strip.x_min,
                strip.x_max,
                strip.y_min,
                strip.y_max,
            ).astype(np.float32, copy=False)
            readout_assigned_fraction += frac
            qsum = (frac * induced_charge_total_fc).astype(np.float32, copy=False)
            out[f"Y_mea_{plane_idx}_s{strip_idx + 1}"] = qsum
            hit_mask = qsum > 0
            plane_detected |= hit_mask
            if (
                debug_event_index is not None
                and 0 <= debug_event_index < n
                and valid[debug_event_index]
                and debug_points is not None
                and plane_idx in debug_points
            ):
                debug_points[plane_idx][f"strip_{strip_idx + 1}_fraction"] = float(frac[debug_event_index])
                debug_points[plane_idx][f"strip_{strip_idx + 1}_charge_fc"] = float(qsum[debug_event_index])

            x_strip = np.full(n, np.nan, dtype=np.float32)
            if hit_mask.any():
                x_strip[hit_mask] = (
                    aval_x[hit_mask] + rng.normal(0.0, x_noise, hit_mask.sum())
                ).astype(np.float32, copy=False)
            out[f"X_mea_{plane_idx}_s{strip_idx + 1}"] = x_strip

            if t_sum_vals is not None:
                t_strip = np.full(n, np.nan, dtype=np.float32)
                t_valid = hit_mask & ~np.isnan(t_sum_vals)
                if t_valid.any():
                    t_strip[t_valid] = (
                        t_sum_vals[t_valid] + rng.normal(0.0, time_sigma_ns, t_valid.sum())
                    ).astype(np.float32, copy=False)
                out[f"T_sum_meas_{plane_idx}_s{strip_idx + 1}"] = t_strip
        readout_assigned_fraction = np.clip(readout_assigned_fraction, 0.0, 1.0)
        readout_gap_fraction = np.clip(
            readout_bounding_fraction - readout_assigned_fraction,
            0.0,
            1.0,
        )
        readout_outside_fraction = np.clip(1.0 - readout_bounding_fraction, 0.0, 1.0)
        out[f"readout_bounding_fraction_{plane_idx}"] = readout_bounding_fraction.astype(
            np.float32,
            copy=False,
        )
        out[f"readout_assigned_fraction_{plane_idx}"] = readout_assigned_fraction
        out[f"readout_gap_fraction_{plane_idx}"] = readout_gap_fraction.astype(
            np.float32,
            copy=False,
        )
        out[f"readout_outside_fraction_{plane_idx}"] = readout_outside_fraction.astype(
            np.float32,
            copy=False,
        )
        if (
            debug_event_index is not None
            and 0 <= debug_event_index < n
            and valid[debug_event_index]
            and debug_points is not None
            and plane_idx in debug_points
        ):
            debug_points[plane_idx]["readout_assigned_fraction"] = float(
                readout_assigned_fraction[debug_event_index]
            )
            debug_points[plane_idx]["readout_gap_fraction"] = float(
                readout_gap_fraction[debug_event_index]
            )
            debug_points[plane_idx]["readout_outside_fraction"] = float(
                readout_outside_fraction[debug_event_index]
            )
        tt_array[plane_detected] = tt_array[plane_detected] + str(plane_idx)

    out["tt_hit"] = pd.Series(tt_array, dtype="string").replace("", pd.NA)
    return out


def plot_hit_summary(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    counts = normalize_tt(df["tt_hit"]).value_counts().sort_index()
    bars = ax.bar(counts.index, counts.values, color="steelblue", alpha=0.8)
    for patch in bars:
        patch.set_rasterized(True)
    ax.set_title("tt_hit counts")
    ax.set_xlabel("tt_hit")
    ax.set_ylabel("Counts")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_step4_summary(
    df: pd.DataFrame,
    pdf: PdfPages,
    include_thrown_points: bool,
    thrown_points: dict | None,
    active_area_bounds: RectBounds,
    readout_geometry: dict[int, PlaneReadoutGeometry],
    examples_df: pd.DataFrame | None = None,
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()

    counts = normalize_tt(df["tt_hit"]).value_counts().sort_index()
    bars = axes[0].bar(counts.index, counts.values, color="steelblue", alpha=0.8)
    for patch in bars:
        patch.set_rasterized(True)
    axes[0].set_title("tt_hit")

    qsum_cols = [c for c in df.columns if c.startswith("Y_mea_") and "_s" in c]
    qsum_vals = df[qsum_cols].to_numpy(dtype=float).ravel() if qsum_cols else np.array([])
    qsum_vals = qsum_vals[qsum_vals > 0]
    axes[1].hist(qsum_vals, bins=60, color="seagreen", alpha=0.8)
    axes[1].set_title("qsum (all strips)")

    x_cols = [c for c in df.columns if c.startswith("X_mea_") and "_s" in c]
    x_vals = df[x_cols].to_numpy(dtype=float).ravel() if x_cols else np.array([])
    x_vals = x_vals[~np.isnan(x_vals)]
    axes[2].hist(x_vals, bins=60, color="darkorange", alpha=0.8)
    axes[2].set_title("X_mea (all strips)")

    t_cols = [c for c in df.columns if c.startswith("T_sum_meas_") and "_s" in c]
    t_vals = df[t_cols].to_numpy(dtype=float).ravel() if t_cols else np.array([])
    t_vals = t_vals[~np.isnan(t_vals)]
    axes[3].hist(t_vals, bins=60, color="slateblue", alpha=0.8)
    axes[3].set_title("T_sum_meas (all strips)")

    for ax in axes:
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    if "Theta_gen" in df.columns and "Phi_gen" in df.columns and "tt_hit" in df.columns:
        tt_series = normalize_tt(df["tt_hit"]).dropna().astype(str)
        for tt_value in sorted(tt_series.unique()):
            tt_df = df[df["tt_hit"] == tt_value]
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            axes[0].scatter(
                tt_df["Theta_gen"],
                tt_df["Phi_gen"],
                s=6,
                alpha=0.25,
                rasterized=True,
            )
            axes[0].set_title(f"Theta vs Phi (tt_hit={tt_value})")
            axes[0].set_xlabel("Theta (rad)")
            axes[0].set_ylabel("Phi (rad)")
            axes[0].set_xlim(0, np.pi / 2)
            axes[0].set_ylim(-np.pi, np.pi)

            axes[1].hist2d(tt_df["Theta_gen"], tt_df["Phi_gen"], bins=60, cmap="magma")
            axes[1].set_title(f"Theta vs Phi density (tt_hit={tt_value})")
            axes[1].set_xlabel("Theta (rad)")
            axes[1].set_ylabel("Phi (rad)")
            axes[1].set_xlim(0, np.pi / 2)
            axes[1].set_ylim(-np.pi, np.pi)
            fig.tight_layout()
            pdf.savefig(fig, dpi=150)
            plt.close(fig)

    strip_cols_all = [col for col in df.columns if col.startswith("Y_mea_") and "_s" in col]
    examples_source = examples_df if examples_df is not None else df
    if strip_cols_all and examples_source is not None and not examples_source.empty:
        rng = np.random.default_rng(0)
        fig, axes = plt.subplots(5, 3, figsize=(12, 14), sharex=True, sharey=False)
        strip_positions = np.arange(1, 5)
        for ax in axes.flatten():
            plane = int(rng.integers(1, 5))
            strip_cols = [f"Y_mea_{plane}_s{s}" for s in range(1, 5)]
            if not all(col in examples_source.columns for col in strip_cols):
                ax.axis("off")
                continue
            qsum_matrix = examples_source[strip_cols].to_numpy(dtype=float)
            aval_col = f"avalanche_size_electrons_{plane}"
            if aval_col in examples_source.columns:
                aval_mask = examples_source[aval_col].to_numpy(dtype=float) >= 1.0
            else:
                aval_mask = np.ones(len(examples_source), dtype=bool)
            if "tt_hit" in examples_source.columns:
                tt_series = normalize_tt(examples_source["tt_hit"]).astype(str)
                tt_mask = tt_series == "1234"
            else:
                tt_series = None
                tt_mask = np.ones(len(examples_source), dtype=bool)
            hit_mask = (qsum_matrix > 0).any(axis=1) & aval_mask & tt_mask
            hit_indices = np.where(hit_mask)[0]
            if len(hit_indices) == 0:
                ax.axis("off")
                continue
            idx = int(rng.choice(hit_indices))
            vals = examples_source.loc[idx, strip_cols].to_numpy(dtype=float)
            bars = ax.bar(strip_positions, vals, width=0.6, alpha=0.8)
            for patch in bars:
                patch.set_rasterized(True)
            tt_label = tt_series.iloc[idx] if tt_series is not None else ""
            ax.set_title(f"P{plane} row {idx} tt={tt_label}")
            ax.set_xticks(strip_positions)
            ax.set_xlabel("Strip")
        axes[0, 0].set_ylabel("qsum [fC]")
        fig.suptitle("Charge sharing examples (single plane per event)")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    for plane_idx, ax in enumerate(axes, start=1):
        aval_col = f"induced_charge_total_fc_{plane_idx}"
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if aval_col not in df.columns or not strip_cols:
            ax.axis("off")
            continue
        aval_vals = df[aval_col].to_numpy(dtype=float)
        strip_vals = df[strip_cols].to_numpy(dtype=float)
        qsum_total = strip_vals.sum(axis=1)
        mask = (aval_vals > 0) & (qsum_total > 0)
        ratios = np.zeros_like(aval_vals)
        ratios[mask] = qsum_total[mask] / aval_vals[mask]
        ratios = ratios[ratios > 0]
        if len(ratios) == 0:
            ax.axis("off")
            continue
        ax.hist(ratios, bins=80, color="steelblue", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} detector charge / induced charge")
        ax.set_xlim(left=0)
        for patch in ax.patches:
            patch.set_rasterized(True)
    axes[-1].set_xlabel("qsum total / induced charge")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    # Geometry overview: active gas and readout rectangles are intentionally independent.
    fig, axes = plt.subplots(2, 2, figsize=(10, 9))
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        plane_geometry = readout_geometry[plane_idx]
        x_min = min(active_area_bounds.x_min, plane_geometry.x_min)
        x_max = max(active_area_bounds.x_max, plane_geometry.x_max)
        y_min = min(active_area_bounds.y_min, plane_geometry.y_min)
        y_max = max(active_area_bounds.y_max, plane_geometry.y_max)
        x_pad = max(0.03 * (x_max - x_min), 1.0)
        y_pad = max(0.03 * (y_max - y_min), 1.0)
        ax.add_patch(
            Rectangle(
                (active_area_bounds.x_min, active_area_bounds.y_min),
                active_area_bounds.x_max - active_area_bounds.x_min,
                active_area_bounds.y_max - active_area_bounds.y_min,
                fill=False,
                edgecolor="black",
                linestyle="--",
                linewidth=1.8,
                label="active gas area",
            )
        )
        for gap_index in range(len(plane_geometry.strips) - 1):
            gap_y_min = plane_geometry.strips[gap_index].y_max
            gap_y_max = plane_geometry.strips[gap_index + 1].y_min
            if gap_y_max > gap_y_min:
                ax.add_patch(
                    Rectangle(
                        (plane_geometry.x_min, gap_y_min),
                        plane_geometry.x_max - plane_geometry.x_min,
                        gap_y_max - gap_y_min,
                        facecolor="gray",
                        edgecolor="none",
                        alpha=0.2,
                        hatch="///",
                        label="inactive gap" if gap_index == 0 else None,
                    )
                )
        for strip in plane_geometry.strips:
            ax.add_patch(
                Rectangle(
                    (strip.x_min, strip.y_min),
                    strip.x_max - strip.x_min,
                    strip.y_max - strip.y_min,
                    fill=False,
                    edgecolor=f"C{strip.strip_index - 1}",
                    linewidth=1.5,
                    label=f"strip {strip.strip_index}",
                )
            )
        avalanche_x_col = f"avalanche_x_{plane_idx}"
        avalanche_y_col = f"avalanche_y_{plane_idx}"
        if avalanche_x_col in df.columns and avalanche_y_col in df.columns:
            avalanche_x = df[avalanche_x_col].to_numpy(dtype=float)
            avalanche_y = df[avalanche_y_col].to_numpy(dtype=float)
            valid_avalanche = np.isfinite(avalanche_x) & np.isfinite(avalanche_y)
            ax.scatter(
                avalanche_x[valid_avalanche],
                avalanche_y[valid_avalanche],
                s=4,
                color="magenta",
                alpha=0.25,
                rasterized=True,
                label="avalanches",
            )
        ax.set_xlim(x_min - x_pad, x_max + x_pad)
        ax.set_ylim(y_min - y_pad, y_max + y_pad)
        ax.set_aspect("equal")
        ax.set_title(f"Plane {plane_idx}: active area and readout")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.legend(fontsize=7, loc="best")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    if include_thrown_points and thrown_points:
        fig, axes = plt.subplots(2, 2, figsize=(10, 9))
        for plane_idx in range(1, 5):
            ax = axes[(plane_idx - 1) // 2, (plane_idx - 1) % 2]
            points = thrown_points.get(plane_idx)
            if not points:
                ax.axis("off")
                continue
            plane_geometry = readout_geometry[plane_idx]
            center_x = points["center_x"]
            center_y = points["center_y"]
            gamma_mm = points["gamma_mm"]
            gap_charge = points.get("gap_charge_fc")
            induced_charge = points.get("induced_charge_fc")
            x_min = min(active_area_bounds.x_min, plane_geometry.x_min)
            x_max = max(active_area_bounds.x_max, plane_geometry.x_max)
            y_min = min(active_area_bounds.y_min, plane_geometry.y_min)
            y_max = max(active_area_bounds.y_max, plane_geometry.y_max)
            x_axis = np.linspace(x_min, x_max, 240)
            y_axis = np.linspace(y_min, y_max, 240)
            density = isotropic_lorentzian_density_grid(
                x_axis,
                y_axis,
                center_x,
                center_y,
                gamma_mm,
                induced_charge,
            )
            norm_density = density / max(float(np.max(density)), 1.0e-12)
            ax.imshow(
                norm_density,
                origin="lower",
                extent=(x_axis[0], x_axis[-1], y_axis[0], y_axis[-1]),
                cmap="magma",
                aspect="equal",
                alpha=0.9,
            )
            ax.add_patch(
                Rectangle(
                    (active_area_bounds.x_min, active_area_bounds.y_min),
                    active_area_bounds.x_max - active_area_bounds.x_min,
                    active_area_bounds.y_max - active_area_bounds.y_min,
                    fill=False,
                    edgecolor="white",
                    linestyle="--",
                    linewidth=1.5,
                )
            )
            for gap_index in range(len(plane_geometry.strips) - 1):
                gap_y_min = plane_geometry.strips[gap_index].y_max
                gap_y_max = plane_geometry.strips[gap_index + 1].y_min
                if gap_y_max > gap_y_min:
                    ax.add_patch(
                        Rectangle(
                            (plane_geometry.x_min, gap_y_min),
                            plane_geometry.x_max - plane_geometry.x_min,
                            gap_y_max - gap_y_min,
                            facecolor="gray",
                            edgecolor="none",
                            alpha=0.35,
                            hatch="///",
                        )
                    )
            for strip in plane_geometry.strips:
                ax.add_patch(
                    Rectangle(
                        (strip.x_min, strip.y_min),
                        strip.x_max - strip.x_min,
                        strip.y_max - strip.y_min,
                        fill=False,
                        edgecolor="cyan",
                        linewidth=1.0,
                    )
                )
            ax.scatter([center_x], [center_y], s=35, color="lime", marker="x")
            strip_text = "\n".join(
                f"S{i}={points.get(f'strip_{i}_charge_fc', 0.0):.2f} fC"
                for i in range(1, 5)
            )
            assigned = points.get("readout_assigned_fraction")
            gap_fraction = points.get("readout_gap_fraction")
            outside_fraction = points.get("readout_outside_fraction")
            if assigned is not None:
                strip_text = (
                    f"Fassigned={assigned:.4f}\nFgap={gap_fraction:.4f}\n"
                    f"Foutside={outside_fraction:.4f}\n" + strip_text
                )
            if gap_charge is not None and induced_charge is not None:
                ax.set_title(
                    f"Plane {plane_idx} Lorentzian "
                    f"(Qgap={gap_charge:,.1f} fC, Qind={induced_charge:,.1f} fC, gamma={gamma_mm:,.1f} mm)"
                )
            else:
                ax.set_title(f"Plane {plane_idx} isotropic 2D Lorentzian")
            ax.set_xlabel("X (mm)")
            ax.set_ylabel("Y (mm)")
            ax.set_xlim(x_min, x_max)
            ax.set_ylim(y_min, y_max)
            ax.text(
                0.03,
                0.97,
                strip_text,
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=8,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.7, "edgecolor": "none"},
            )
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    for plane_idx, ax in enumerate(axes, start=1):
        aval_col = f"induced_charge_total_fc_{plane_idx}"
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if aval_col not in df.columns or not strip_cols:
            ax.axis("off")
            continue
        aval_vals = df[aval_col].to_numpy(dtype=float)
        strip_vals = df[strip_cols].to_numpy(dtype=float)
        qsum_total = strip_vals.sum(axis=1)
        mask = (aval_vals > 0) & (qsum_total > 0)
        qsum_total = qsum_total[mask]
        aval_vals = aval_vals[mask]
        ax.hist(qsum_total, bins=120, color="seagreen", alpha=0.8, label="qsum total")
        ax.hist(aval_vals, bins=120, color="darkorange", alpha=0.5, label="induced total")
        ax.set_title(f"Plane {plane_idx} qsum total vs induced charge")
        ax.set_xlim(left=0)
        ax.legend()
        for patch in ax.patches:
            patch.set_rasterized(True)
    axes[-1].set_xlabel("charge [fC]")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    for plane_idx, ax in enumerate(axes, start=1):
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if not strip_cols:
            ax.axis("off")
            continue
        strip_vals = df[strip_cols].to_numpy(dtype=float)
        qsum_total = strip_vals.sum(axis=1)
        qsum_total = qsum_total[qsum_total > 0]
        if len(qsum_total) == 0:
            ax.axis("off")
            continue
        median_val = np.median(qsum_total)
        zoom_vals = qsum_total[qsum_total <= median_val]
        ax.hist(zoom_vals, bins=80, color="teal", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} qsum total (0 to median)")
        ax.set_xlim(0, median_val)
        for patch in ax.patches:
            patch.set_rasterized(True)
    axes[-1].set_xlabel("induced charge [fC]")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    for plane_idx, ax in enumerate(axes, start=1):
        aval_col = f"induced_charge_total_fc_{plane_idx}"
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if aval_col not in df.columns or not strip_cols:
            ax.axis("off")
            continue
        aval_vals = df[aval_col].to_numpy(dtype=float)
        strip_vals = df[strip_cols].to_numpy(dtype=float)
        qsum_total = strip_vals.sum(axis=1)
        mask = (aval_vals > 0) & (qsum_total > 0)
        aval_vals = aval_vals[mask]
        qsum_total = qsum_total[mask]
        if len(aval_vals) == 0:
            ax.axis("off")
            continue
        ax.scatter(
            aval_vals,
            qsum_total,
            s=2,
            alpha=0.2,
            rasterized=True,
        )
        ax.set_title(f"Plane {plane_idx} qsum total vs induced charge")
        ax.set_xlabel("induced total charge [fC]")
        ax.set_ylabel("qsum total [fC]")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    for plane_idx, ax in enumerate(axes, start=1):
        col = f"avalanche_size_electrons_{plane_idx}"
        if col not in df.columns:
            ax.axis("off")
            continue
        vals = df[col].to_numpy(dtype=float)
        vals = vals[vals > 0]
        ax.hist(vals, bins=80, color="darkorange", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} avalanche size")
        ax.set_xlim(left=0)
        for patch in ax.patches:
            patch.set_rasterized(True)
    axes[-1].set_xlabel("avalanche size (electrons)")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    for plane_idx, ax in enumerate(axes, start=1):
        col = f"lorentzian_gamma_mm_{plane_idx}"
        if col not in df.columns:
            ax.axis("off")
            continue
        vals = df[col].to_numpy(dtype=float)
        vals = vals[vals > 0]
        ax.hist(vals, bins=80, color="seagreen", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} Lorentzian gamma")
        ax.set_xlim(left=0)
        for patch in ax.patches:
            patch.set_rasterized(True)
    axes[-1].set_xlabel("gamma (mm)")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if not strip_cols:
            ax.axis("off")
            continue
        vals = df[strip_cols].to_numpy(dtype=float).sum(axis=1)
        vals = vals[vals > 0]
        ax.hist(vals, bins=120, color="seagreen", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} qsum total")
        ax.set_xlabel("qsum total")
    for ax in axes.flatten():
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 4, figsize=(12, 10))
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            ax = axes[plane_idx - 1, strip_idx - 1]
            col = f"Y_mea_{plane_idx}_s{strip_idx}"
            if col not in df.columns:
                ax.axis("off")
                continue
            vals = df[col].to_numpy(dtype=float)
            vals = vals[vals > 0]
            ax.hist(vals, bins=80, color="seagreen", alpha=0.8)
            ax.set_title(f"P{plane_idx} S{strip_idx}")
            ax.set_xlabel("qsum")
    for ax in axes.flatten():
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        strip_cols = [c for c in df.columns if c.startswith(f"X_mea_{plane_idx}_s")]
        if not strip_cols:
            ax.axis("off")
            continue
        vals = df[strip_cols].to_numpy(dtype=float).ravel()
        vals = vals[~np.isnan(vals)]
        ax.hist(vals, bins=80, color="darkorange", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} X_mea")
        ax.set_xlabel("X_mea (mm)")
    for ax in axes.flatten():
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 4, figsize=(12, 10))
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            ax = axes[plane_idx - 1, strip_idx - 1]
            col = f"X_mea_{plane_idx}_s{strip_idx}"
            if col not in df.columns:
                ax.axis("off")
                continue
            vals = df[col].to_numpy(dtype=float)
            vals = vals[~np.isnan(vals)]
            ax.hist(vals, bins=80, color="darkorange", alpha=0.8)
            ax.set_title(f"P{plane_idx} S{strip_idx}")
            ax.set_xlabel("X_mea (mm)")
    for ax in axes.flatten():
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        strip_cols = [c for c in df.columns if c.startswith(f"T_sum_meas_{plane_idx}_s")]
        if not strip_cols:
            ax.axis("off")
            continue
        vals = df[strip_cols].to_numpy(dtype=float).ravel()
        vals = vals[~np.isnan(vals)]
        ax.hist(vals, bins=80, color="slateblue", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} T_sum_meas")
        ax.set_xlabel("T_sum_meas (ns)")
    for ax in axes.flatten():
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 4, figsize=(12, 10))
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            ax = axes[plane_idx - 1, strip_idx - 1]
            col = f"T_sum_meas_{plane_idx}_s{strip_idx}"
            if col not in df.columns:
                ax.axis("off")
                continue
            vals = df[col].to_numpy(dtype=float)
            vals = vals[~np.isnan(vals)]
            ax.hist(vals, bins=80, color="slateblue", alpha=0.8)
            ax.set_title(f"P{plane_idx} S{strip_idx}")
            ax.set_xlabel("T_sum_meas (ns)")
    for ax in axes.flatten():
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def select_step4_input_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Retain every upstream column needed by signal induction and provenance."""
    needed = {
        "event_id", "T_thick_s", "X_gen", "Y_gen", "Theta_gen", "Phi_gen",
        "crossing_mask",
    }
    for plane_idx in range(1, 5):
        needed.update(
            {
                f"avalanche_size_electrons_{plane_idx}",
                f"avalanche_x_{plane_idx}",
                f"avalanche_y_{plane_idx}",
                f"T_sum_{plane_idx}_ns",
            }
        )
    return df[[column for column in df.columns if column in needed]]


def prune_step4(df: pd.DataFrame) -> pd.DataFrame:
    keep = {
        "event_id", "T_thick_s", "X_gen", "Y_gen", "Theta_gen", "Phi_gen",
        "tt_hit", "crossing_mask",
    }
    for plane_idx in range(1, 5):
        keep.add(f"avalanche_gap_charge_fc_{plane_idx}")
        keep.add(f"induced_charge_total_fc_{plane_idx}")
        keep.add(f"avalanche_x_{plane_idx}")
        keep.add(f"avalanche_y_{plane_idx}")
        keep.add(f"readout_bounding_fraction_{plane_idx}")
        keep.add(f"readout_assigned_fraction_{plane_idx}")
        keep.add(f"readout_gap_fraction_{plane_idx}")
        keep.add(f"readout_outside_fraction_{plane_idx}")
        for strip_idx in range(1, 5):
            keep.add(f"Y_mea_{plane_idx}_s{strip_idx}")
            keep.add(f"X_mea_{plane_idx}_s{strip_idx}")
            keep.add(f"T_sum_meas_{plane_idx}_s{strip_idx}")
    keep_cols = [col for col in df.columns if col in keep]
    return df[keep_cols]


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 4: avalanche -> induced signal (hit vectors).")
    parser.add_argument("--config", default="config_step_4_physics.yaml", help="Path to step physics config YAML")
    parser.add_argument(
        "--runtime-config",
        default=None,
        help="Path to step runtime config YAML (defaults to *_runtime.yaml)",
    )
    parser.add_argument("--plot-only", action="store_true", help="Only generate plots from existing outputs")
    parser.add_argument("--no-plots", action="store_true", help="Skip plot generation")
    parser.add_argument("--force", action="store_true", help="Recompute even if sim_run exists")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent / config_path
    runtime_path = Path(args.runtime_config) if args.runtime_config else None
    if runtime_path is not None and not runtime_path.is_absolute():
        runtime_path = Path(__file__).resolve().parent / runtime_path

    physics_cfg, runtime_cfg, cfg, runtime_path = load_step_configs(config_path, runtime_path)

    input_dir = Path(cfg["input_dir"])
    if not input_dir.is_absolute():
        input_dir = Path(__file__).resolve().parent / input_dir
    output_dir = Path(cfg["output_dir"])
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parent / output_dir
    ensure_dir(output_dir)

    output_format = str(cfg.get("output_format", "pkl")).lower()
    chunk_rows = cfg.get("chunk_rows")
    plot_sample_rows = cfg.get("plot_sample_rows")
    x_noise = float(cfg.get("x_noise_mm", 0.0))
    time_sigma_ns = float(cfg.get("time_sigma_ns", 0.0))
    lorentzian_gamma_mm = cfg.get("lorentzian_gamma_mm")
    if lorentzian_gamma_mm in (None, ""):
        legacy_fwhm = float(cfg.get("avalanche_width_mm", 40.0))
        lorentzian_gamma_mm = 0.5 * legacy_fwhm
    lorentzian_gamma_mm = float(lorentzian_gamma_mm)
    if lorentzian_gamma_mm <= 0:
        raise ValueError("lorentzian_gamma_mm must be > 0.")
    induced_charge_fraction = float(cfg.get("induced_charge_fraction", 1.0))
    if not (0.0 <= induced_charge_fraction <= 1.0):
        raise ValueError("induced_charge_fraction must be in [0, 1].")
    rng = np.random.default_rng(cfg.get("seed"))

    input_glob = cfg.get("input_glob", "**/step_3_chunks.chunks.json")
    input_sim_run = cfg.get("input_sim_run", "latest")

    print("\n-----\nStep 4 starting...\n-----")
    print(f"Input dir: {input_dir}")
    print(f"Output dir: {output_dir}")
    print(f"input_sim_run: {input_sim_run}")

    if args.plot_only:
        if args.no_plots:
            print("Plot-only requested with --no-plots; skipping plots.")
            return
        latest_path = find_latest_data_path(output_dir)
        if latest_path is None:
            raise FileNotFoundError(f"No existing outputs found in {output_dir} for plot-only.")
        df, plot_meta = load_with_metadata(latest_path)
        plot_meta = _recover_metadata_from_chunk_manifest(latest_path, plot_meta)
        active_area_bounds, active_area_geometry_source = resolve_step4_active_area_bounds(cfg, plot_meta)
        readout_geometry, readout_geometry_source = resolve_step4_readout_geometry(
            {}, active_area_bounds, plot_meta
        )
        print(
            "Using active area "
            f"({active_area_geometry_source}): x=[{active_area_bounds.x_min:.3f}, {active_area_bounds.x_max:.3f}] mm, "
            f"y=[{active_area_bounds.y_min:.3f}, {active_area_bounds.y_max:.3f}] mm"
        )
        sim_run_dir = find_sim_run_dir(latest_path)
        plot_dir = (sim_run_dir or latest_path.parent) / "PLOTS"
        ensure_dir(plot_dir)
        plot_path = plot_dir / f"{latest_path.stem}_plots.pdf"
        with PdfPages(plot_path) as pdf:
            plot_hit_summary(df, pdf)
            plot_step4_summary(
                df,
                pdf,
                include_thrown_points=False,
                thrown_points=None,
                active_area_bounds=active_area_bounds,
                readout_geometry=readout_geometry,
                examples_df=df,
            )
        print(f"Saved {plot_path}")
        return

    input_sim_run_mode = input_sim_run
    if "**" in input_glob:
        candidates = sorted(input_dir.rglob(input_glob.replace("**/", "")))
    else:
        candidates = sorted(input_dir.rglob(input_glob))
    if input_sim_run_mode not in ("latest", "random"):
        input_run_dir = input_dir / str(input_sim_run_mode)
        candidates = [path for path in candidates if input_run_dir in path.parents]
        if not candidates:
            raise FileNotFoundError(
                f"No inputs found for {input_glob} under {input_run_dir}."
            )
    def normalize_stem(path: Path) -> str:
        name = path.name
        if name.endswith(".chunks.json"):
            name = name[: -len(".chunks.json")]
        stem = Path(name).stem
        return stem.replace(".chunks", "")

    if not candidates:
        raise FileNotFoundError(f"No inputs found for {input_glob} under {input_dir}.")

    if input_sim_run_mode == "latest":
        candidates = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)
    elif input_sim_run_mode == "random":
        rng.shuffle(candidates)

    input_iter = None
    upstream_meta = None
    chunked_input = False
    step_chain = None
    step_4_id = None
    input_path = None
    mesh_dir = Path(cfg.get("param_mesh_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
    if not mesh_dir.is_absolute():
        mesh_dir = Path(__file__).resolve().parent / mesh_dir

    for candidate in candidates:
        candidate_iter, candidate_meta, candidate_chunked = iter_input_frames(candidate, chunk_rows)
        candidate_chain = extract_step_id_chain(candidate_meta)
        if not candidate_chain:
            continue
        candidate_step_4_id = select_next_step_id(
            output_dir,
            mesh_dir,
            cfg.get("param_mesh_sim_run", "none"),
            "step_4_id",
            candidate_chain,
            cfg.get("seed"),
            physics_cfg.get("step_4_id"),
        )
        if candidate_step_4_id is None:
            continue
        input_path = candidate
        input_iter = candidate_iter
        upstream_meta = candidate_meta
        chunked_input = candidate_chunked
        step_chain = candidate_chain
        step_4_id = candidate_step_4_id
        break

    if input_path is None or input_iter is None or upstream_meta is None or step_chain is None or step_4_id is None:
        print("Skipping STEP_4: all step_4_id combinations already exist.")
        return

    active_area_bounds, active_area_geometry_source = resolve_step4_active_area_bounds(cfg, upstream_meta)
    readout_geometry, readout_geometry_source = resolve_step4_readout_geometry(
        cfg, active_area_bounds
    )
    normalized_active_area = rect_bounds_to_dict(active_area_bounds)
    normalized_readout_geometry = readout_geometry_to_dict(readout_geometry, detailed=True)
    physics_cfg["geometry_schema_version"] = GEOMETRY_SCHEMA_VERSION
    physics_cfg["readout_geometry_mm"] = readout_geometry_to_dict(
        readout_geometry, detailed=False
    )
    print(
        "Using active area "
        f"({active_area_geometry_source}): x=[{active_area_bounds.x_min:.3f}, {active_area_bounds.x_max:.3f}] mm, "
        f"y=[{active_area_bounds.y_min:.3f}, {active_area_bounds.y_max:.3f}] mm"
    )
    print(f"Using readout geometry ({readout_geometry_source}) with four strips per plane.")

    normalized_stem = normalize_stem(input_path)
    print(f"Processing: {input_path}")
    sim_run = build_sim_run_name(step_chain + [step_4_id])
    sim_run_dir = output_dir / sim_run
    if not args.force and sim_run_dir.exists():
        print(f"SIM_RUN {sim_run} already exists; skipping (use --force to regenerate).")
        return
    print("Inducing strip signals...")

    physics_cfg["step_4_id"] = step_4_id
    sim_run, sim_run_dir, config_hash, upstream_hash, _ = register_sim_run(
        output_dir, "STEP_4", config_path, physics_cfg, upstream_meta, sim_run
    )
    print(f"Resolved output sim_run: {sim_run}")
    reset_dir(sim_run_dir)
    print(f"Output dir reset: {sim_run_dir}")

    out_stem_base = "step_4"
    out_stem = f"{out_stem_base}_chunks" if chunk_rows else out_stem_base
    metadata = {
        "created_at": now_iso(),
        "step": "STEP_4",
        "geometry_schema_version": GEOMETRY_SCHEMA_VERSION,
        "active_area_bounds_mm": normalized_active_area,
        "active_area_geometry_source": active_area_geometry_source,
        "readout_geometry_mm": normalized_readout_geometry,
        "readout_geometry_source": readout_geometry_source,
        "config": physics_cfg,
        "runtime_config": runtime_cfg,
        "sim_run": sim_run,
        "config_hash": config_hash,
        "upstream_hash": upstream_hash,
        "source_dataset": str(input_path),
        "upstream": upstream_meta,
        "step_4_id": step_4_id,
    }
    def select_debug_event(frame: pd.DataFrame, chooser: np.random.Generator) -> int | None:
        required_cols = [f"avalanche_size_electrons_{i}" for i in range(1, 5)]
        for col in required_cols:
            if col not in frame.columns:
                return None
        mask = np.ones(len(frame), dtype=bool)
        for col in required_cols:
            mask &= frame[col].to_numpy(dtype=float) > 0
        if not mask.any():
            return None
        indices = np.where(mask)[0]
        return int(chooser.choice(indices))

    def prepare_chunk(
        chunk: pd.DataFrame,
        debug_state: dict,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        chunk = select_step4_input_columns(chunk)
        debug_event_index = None
        if not debug_state["captured"]:
            debug_event_index = select_debug_event(chunk, debug_rng)
        out_full = induce_signal(
            chunk,
            x_noise,
            time_sigma_ns,
            lorentzian_gamma_mm,
            induced_charge_fraction,
            readout_geometry,
            rng,
            debug_event_index,
            debug_state["points"] if debug_event_index is not None else None,
        )
        plot_cols = [
            col
            for col in out_full.columns
            if col == "tt_hit"
            or col.startswith(("Y_mea_", "X_mea_", "T_sum_meas_"))
            or col.startswith(
                (
                    "avalanche_size_electrons_",
                    "avalanche_gap_charge_fc_",
                    "induced_charge_total_fc_",
                    "lorentzian_gamma_mm_",
                    "readout_bounding_fraction_",
                    "readout_assigned_fraction_",
                    "readout_gap_fraction_",
                    "readout_outside_fraction_",
                    "avalanche_x_",
                    "avalanche_y_",
                )
            )
        ]
        plot_df = out_full[plot_cols]
        if debug_event_index is not None and debug_state["points"]:
            debug_state["captured"] = True
            debug_state["plot_df"] = plot_df
        return prune_step4(out_full), plot_df

    debug_state = {"captured": False, "points": {}, "plot_df": None}
    debug_rng = np.random.default_rng()

    if chunk_rows:
        chunks_dir = sim_run_dir / (out_stem if out_stem.endswith("_chunks") else f"{out_stem}_chunks")
        ensure_dir(chunks_dir)
        chunk_paths = []
        buffer_full = []
        buffer_plot = []
        buffered_rows = 0
        full_chunks = 0
        last_plot_df = None

        def flush_chunk(out_df: pd.DataFrame, plot_df: pd.DataFrame) -> None:
            nonlocal full_chunks, last_plot_df
            chunk_path = chunks_dir / f"part_{full_chunks:04d}.{output_format}"
            if output_format == "csv":
                out_df.to_csv(chunk_path, index=False)
            elif output_format == "pkl":
                out_df.to_pickle(chunk_path)
            else:
                raise ValueError(f"Unsupported output_format: {output_format}")
            chunk_paths.append(str(chunk_path))
            full_chunks += 1
            last_plot_df = plot_df

        def maybe_flush_buffer() -> None:
            nonlocal buffer_full, buffer_plot, buffered_rows
            while buffered_rows >= int(chunk_rows):
                full_df = pd.concat(buffer_full, ignore_index=True)
                plot_full = pd.concat(buffer_plot, ignore_index=True)
                out_df = full_df.iloc[: int(chunk_rows)].copy()
                plot_df = plot_full.iloc[: int(chunk_rows)].copy()
                remainder_full = full_df.iloc[int(chunk_rows):].copy()
                remainder_plot = plot_full.iloc[int(chunk_rows):].copy()
                flush_chunk(out_df, plot_df)
                buffer_full = [remainder_full] if not remainder_full.empty else []
                buffer_plot = [remainder_plot] if not remainder_plot.empty else []
                buffered_rows = len(remainder_full)

        total_rows = 0
        for chunk in input_iter:
            out_chunk, plot_chunk = prepare_chunk(chunk, debug_state)
            if out_chunk.empty:
                continue
            total_rows += len(out_chunk)
            buffer_full.append(out_chunk)
            buffer_plot.append(plot_chunk)
            buffered_rows += len(out_chunk)
            maybe_flush_buffer()

        if buffered_rows > 0:
            full_df = pd.concat(buffer_full, ignore_index=True)
            plot_full = pd.concat(buffer_plot, ignore_index=True)
            flush_chunk(full_df, plot_full)
            buffered_rows = 0
            buffer_full = []
            buffer_plot = []

        row_count = total_rows
        manifest = {
            "version": 1,
            "chunks": chunk_paths,
            "row_count": row_count,
            "metadata": metadata,
        }
        manifest_path = sim_run_dir / f"{out_stem}.chunks.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print("Signal induction complete.")
        print(f"Saved data: {manifest_path}")

        plot_df = debug_state["plot_df"] if debug_state["plot_df"] is not None else last_plot_df
        plot_df_examples = plot_df
        if plot_sample_rows and plot_df is not None:
            sample_n = len(plot_df) if plot_sample_rows is True else int(plot_sample_rows)
            sample_n = min(sample_n, len(plot_df))
            plot_df = plot_df.sample(n=sample_n, random_state=cfg.get("seed"))

        if not args.no_plots and plot_df is not None:
            plot_dir = sim_run_dir / "PLOTS"
            ensure_dir(plot_dir)
            plot_path = plot_dir / f"{out_stem_base}_plots.pdf"
            print("Plotting plots...")
            with PdfPages(plot_path) as pdf:
                plot_hit_summary(plot_df, pdf)
                plot_step4_summary(
                    plot_df,
                    pdf,
                    include_thrown_points=True,
                    thrown_points=debug_state["points"],
                    active_area_bounds=active_area_bounds,
                    readout_geometry=readout_geometry,
                    examples_df=plot_df_examples,
                )
            print(f"Saved plots: {plot_path}")
    else:
        df, upstream_meta = load_with_metadata(input_path)
        print(f"Loaded {len(df):,} rows from {input_path.name}")
        df = select_step4_input_columns(df)
        debug_event_index = select_debug_event(df, debug_rng)
        out_full = induce_signal(
            df,
            x_noise,
            time_sigma_ns,
            lorentzian_gamma_mm,
            induced_charge_fraction,
            readout_geometry,
            rng,
            debug_event_index,
            debug_state["points"] if debug_event_index is not None else None,
        )
        print("Signal induction complete.")

        out = prune_step4(out_full)
        out_path = sim_run_dir / f"{out_stem}.{output_format}"
        plot_cols = [
            col
            for col in out_full.columns
            if col == "tt_hit"
            or col.startswith(("Y_mea_", "X_mea_", "T_sum_meas_"))
            or col.startswith(
                (
                    "avalanche_size_electrons_",
                    "avalanche_gap_charge_fc_",
                    "induced_charge_total_fc_",
                    "lorentzian_gamma_mm_",
                    "readout_bounding_fraction_",
                    "readout_assigned_fraction_",
                    "readout_gap_fraction_",
                    "readout_outside_fraction_",
                    "avalanche_x_",
                    "avalanche_y_",
                )
            )
        ]
        plot_df = out_full[plot_cols]
        plot_df_examples = plot_df
        plot_sample_size = cfg.get("plot_sample_size", 200000)
        if plot_sample_size:
            plot_sample_size = int(plot_sample_size)
            if 0 < plot_sample_size < len(plot_df):
                plot_df = plot_df.sample(n=plot_sample_size, random_state=cfg.get("seed"))
                print(f"Plotting with sample size: {len(plot_df):,}")

        save_with_metadata(out, out_path, metadata, output_format)
        print(f"Saved data: {out_path}")
        del df
        del out
        gc.collect()

        if not args.no_plots:
            plot_dir = sim_run_dir / "PLOTS"
            ensure_dir(plot_dir)
            plot_path = plot_dir / f"{out_path.stem}_plots.pdf"
            print("Plotting plots...")
            with PdfPages(plot_path) as pdf:
                plot_hit_summary(plot_df, pdf)
                plot_step4_summary(
                    plot_df,
                    pdf,
                    include_thrown_points=True,
                    thrown_points=debug_state["points"],
                    active_area_bounds=active_area_bounds,
                    readout_geometry=readout_geometry,
                    examples_df=plot_df_examples,
                )
            print(f"Saved plots: {plot_path}")
        print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
