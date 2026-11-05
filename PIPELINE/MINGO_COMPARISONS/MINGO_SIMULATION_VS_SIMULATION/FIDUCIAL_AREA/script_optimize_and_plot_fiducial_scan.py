#!/usr/bin/env python3
"""
Optimize and optionally plot fiducial-region scan tables.

Purpose:
- read one or more fiducial-region scan tables,
- compare measured robust efficiencies against simulated reference efficiencies,
- choose the optimum fiducial scan point independently for planes 1..4,
- write one per-table optimum CSV,
- optionally generate grouped and contour diagnostic figures.

Inputs:
- one explicit scan table via `--table`, or
- all `fiducial_scan_table.csv` files found recursively under the default
  `TASK4_FIDUCIAL_SCAN` root or a custom `--input-root`.

Outputs per scan table:
- `<scan_table_parent>/optimization/fiducial_region_optimum.csv`
- `<scan_table_parent>/plots/fiducial_scan_vs_theta_max_4x5.png`
- `<scan_table_parent>/plots/fiducial_scan_vs_r_max_4x5.png`
- `<scan_table_parent>/plots/fiducial_scan_theta_vs_r_error_1x4.png`
- `<scan_table_parent>/plots/fiducial_scan_theta_vs_r_fiducial_percent.png`

Example usage:
- `python script_optimize_and_plot_fiducial_scan.py`
- `python script_optimize_and_plot_fiducial_scan.py --table /path/to/fiducial_scan_table.csv`
- `python script_optimize_and_plot_fiducial_scan.py --input-root /path/to/TASK4_FIDUCIAL_SCAN --no-plots`
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
from matplotlib.colors import TwoSlopeNorm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm import tqdm
import yaml


CURRENT_PATH = Path(__file__).resolve()
REPO_ROOT = None
for parent in CURRENT_PATH.parents:
    if parent.name == "MINGO_ANALYSIS_SCRIPTS":
        REPO_ROOT = parent.parent.parent
        break
if REPO_ROOT is None:
    REPO_ROOT = CURRENT_PATH.parents[-1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))


SCRIPT_CONFIG_PATH = CURRENT_PATH.with_name("script_optimize_and_plot_fiducial_scan_config.yaml")
DEFAULT_INPUT_ROOT = (
    REPO_ROOT
    / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"
    / "ANCILLARY"
    / "CALCULATIONS"
    / "TASK4_FIDUCIAL_SCAN"
)
REQUIRED_COLUMNS = [
    "filename_base",
    "execution_timestamp",
    "param_hash",
    "theta_max",
    "r_max",
    "P1_eff_robust_xyphi",
    "P2_eff_robust_xyphi",
    "P3_eff_robust_xyphi",
    "P4_eff_robust_xyphi",
    "fiducial_1234_percent_of_total",
    "eff_p1",
    "eff_p2",
    "eff_p3",
    "eff_p4",
]
PLANE_SPECS = {
    1: ("P1_eff_robust_xyphi", "eff_p1"),
    2: ("P2_eff_robust_xyphi", "eff_p2"),
    3: ("P3_eff_robust_xyphi", "eff_p3"),
    4: ("P4_eff_robust_xyphi", "eff_p4"),
}
ROW_METRICS = [
    ("fiducial_1234_percent_of_total", "Fiducial 1234 used [%]"),
    ("abs_error_1", "Abs. error P1"),
    ("abs_error_2", "Abs. error P2"),
    ("abs_error_3", "Abs. error P3"),
    ("abs_error_4", "Abs. error P4"),
]
OPTIMIZATION_RULE = (
    "minimize relative_error_N; break ties by maximizing "
    "fiducial_1234_percent_of_total"
)
DEFAULT_PLOT_CONFIG = {
    "theta_r_error_contour_mode": "absolute_error",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table",
        action="append",
        default=[],
        help="Explicit fiducial scan table CSV. Repeatable.",
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help="Root searched recursively for fiducial_scan_table.csv files when --table is not used.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Optional override root for outputs. When set, each table writes to "
            "<output-dir>/<scan_table_parent_name>/{optimization,plots}/."
        ),
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip plot generation and write only the optimum CSV.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing optimization CSVs and plots.",
    )
    return parser.parse_args()


def load_plot_config(config_path: Path) -> dict[str, str]:
    loaded: dict[str, object] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle)
        if isinstance(parsed, dict):
            loaded = parsed

    raw_mode = loaded.get("theta_r_error_contour_mode", DEFAULT_PLOT_CONFIG["theta_r_error_contour_mode"])
    mode = str(raw_mode).strip().lower()
    aliases = {
        "absolute": "absolute_error",
        "abs": "absolute_error",
        "absolute_error": "absolute_error",
        "signed": "signed_error",
        "signed_error": "signed_error",
    }
    resolved_mode = aliases.get(mode)
    if resolved_mode is None:
        raise ValueError(
            f"Unsupported theta_r_error_contour_mode={raw_mode!r} in {config_path}. "
            "Use 'absolute_error' or 'signed_error'."
        )
    return {
        "theta_r_error_contour_mode": resolved_mode,
    }


def find_scan_tables(explicit_tables: list[str], input_root: Path) -> list[Path]:
    if explicit_tables:
        paths = [Path(item).expanduser().resolve() for item in explicit_tables]
        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Explicit scan tables not found: {missing}")
        return sorted(paths)

    root = input_root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Input root does not exist: {root}")
    return sorted(root.rglob("fiducial_scan_table.csv"))


def load_scan_table(table_path: Path) -> pd.DataFrame:
    return pd.read_csv(table_path)


def validate_required_columns(df: pd.DataFrame, table_path: Path) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        if "r_max" in missing and {"x_abs_max", "y_abs_max"}.issubset(df.columns):
            raise ValueError(
                f"{table_path} uses the older rectangular fiducial schema "
                "(x_abs_max/y_abs_max). Regenerate the scan table with the newer circular r_max scan first."
            )
        raise ValueError(f"{table_path} is missing required columns: {missing}")


def add_efficiency_comparison_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["fiducial_1234_percent_of_total"] = pd.to_numeric(
        out["fiducial_1234_percent_of_total"],
        errors="coerce",
    )

    for plane, (measured_col, reference_col) in PLANE_SPECS.items():
        measured = pd.to_numeric(out[measured_col], errors="coerce")
        reference = pd.to_numeric(out[reference_col], errors="coerce")
        signed = measured - reference
        abs_error = signed.abs()
        reference_abs = reference.abs()
        relative = pd.Series(np.nan, index=out.index, dtype=float)
        nonzero_reference = np.isfinite(reference_abs) & (reference_abs > 0.0)
        relative.loc[nonzero_reference] = (
            abs_error.loc[nonzero_reference] / reference_abs.loc[nonzero_reference]
        )

        out[f"measured_{plane}"] = measured
        out[f"reference_{plane}"] = reference
        out[f"signed_error_{plane}"] = signed
        out[f"abs_error_{plane}"] = abs_error
        out[f"relative_error_{plane}"] = relative

    return out


def resolve_output_base(table_path: Path, output_dir: Path | None) -> Path:
    if output_dir is None:
        return table_path.parent
    return output_dir.expanduser().resolve() / table_path.parent.name


def optimize_plane(
    df: pd.DataFrame,
    *,
    plane: int,
    table_path: Path,
) -> tuple[dict[str, object], dict[str, object] | None]:
    measured_col, reference_col = PLANE_SPECS[plane]
    relative_col = f"relative_error_{plane}"
    abs_col = f"abs_error_{plane}"
    signed_col = f"signed_error_{plane}"

    valid_mask = (
        np.isfinite(pd.to_numeric(df["theta_max"], errors="coerce"))
        & np.isfinite(pd.to_numeric(df["r_max"], errors="coerce"))
        & np.isfinite(pd.to_numeric(df[measured_col], errors="coerce"))
        & np.isfinite(pd.to_numeric(df[reference_col], errors="coerce"))
        & np.isfinite(pd.to_numeric(df[relative_col], errors="coerce"))
        & np.isfinite(pd.to_numeric(df["fiducial_1234_percent_of_total"], errors="coerce"))
        & (pd.to_numeric(df["fiducial_1234_percent_of_total"], errors="coerce") >= 0.0)
    )
    valid_df = df.loc[valid_mask].copy()
    n_valid = int(len(valid_df))

    if n_valid == 0:
        row = {
            "filename_base": str(df["filename_base"].iloc[0]) if not df.empty else "",
            "source_scan_table": str(table_path.resolve()),
            "execution_timestamp": str(df["execution_timestamp"].iloc[0]) if not df.empty else "",
            "param_hash": str(df["param_hash"].iloc[0]) if not df.empty else "",
            "efficiency_index": plane,
            "measured_efficiency_column": measured_col,
            "reference_efficiency_column": reference_col,
            "theta_max": np.nan,
            "r_max": np.nan,
            "eff_robust_xyphi_value": np.nan,
            "eff_reference_value": np.nan,
            "signed_error": np.nan,
            "abs_error": np.nan,
            "relative_error": np.nan,
            "fiducial_1234_percent_of_total": np.nan,
            "optimization_rule": OPTIMIZATION_RULE,
            "number_of_valid_scan_points": n_valid,
        }
        return row, None

    sorted_df = valid_df.sort_values(
        by=[relative_col, "fiducial_1234_percent_of_total"],
        ascending=[True, False],
        kind="mergesort",
    )
    best = sorted_df.iloc[0]
    best_row = {
        "filename_base": str(best["filename_base"]),
        "source_scan_table": str(table_path.resolve()),
        "execution_timestamp": str(best["execution_timestamp"]),
        "param_hash": str(best["param_hash"]),
        "efficiency_index": plane,
        "measured_efficiency_column": measured_col,
        "reference_efficiency_column": reference_col,
        "theta_max": float(best["theta_max"]),
        "r_max": float(best["r_max"]),
        "eff_robust_xyphi_value": float(best[measured_col]),
        "eff_reference_value": float(best[reference_col]),
        "signed_error": float(best[signed_col]),
        "abs_error": float(best[abs_col]),
        "relative_error": float(best[relative_col]),
        "fiducial_1234_percent_of_total": float(best["fiducial_1234_percent_of_total"]),
        "optimization_rule": OPTIMIZATION_RULE,
        "number_of_valid_scan_points": n_valid,
    }
    return best_row, best.to_dict()


def write_optimum_table(optimum_df: pd.DataFrame, output_path: Path, overwrite: bool) -> bool:
    if output_path.exists() and not overwrite:
        print(f"[skip] Optimum CSV exists and --overwrite was not set: {output_path}")
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    optimum_df.to_csv(output_path, index=False)
    print(f"[write] {output_path}")
    return True


def _format_legend_value(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def make_grouped_scan_figure(
    df: pd.DataFrame,
    *,
    optimum_rows: dict[int, dict[str, object] | None],
    varying_column: str,
    fixed_columns: tuple[str, ...],
    x_label: str,
    figure_title: str,
    output_png: Path,
    overwrite: bool,
) -> bool:
    if output_png.exists() and not overwrite:
        print(f"[skip] Plot exists and --overwrite was not set: {output_png}")
        return False
    output_pdf = output_png.with_suffix(".pdf")
    if overwrite and output_pdf.exists():
        output_pdf.unlink()

    unique_groups = (
        df.loc[:, list(fixed_columns)]
        .drop_duplicates()
        .sort_values(list(fixed_columns), kind="mergesort")
    )
    group_records = unique_groups.to_dict("records")
    colors = plt.cm.tab20(np.linspace(0, 1, max(len(group_records), 1)))

    fig, axes = plt.subplots(
        nrows=5,
        ncols=4,
        figsize=(22, 20),
        sharex="col",
        constrained_layout=True,
    )

    legend_handles = []
    legend_labels = []
    for group_index, group_record in enumerate(group_records):
        mask = np.ones(len(df), dtype=bool)
        for column_name in fixed_columns:
            mask &= np.isclose(
                pd.to_numeric(df[column_name], errors="coerce").to_numpy(dtype=float),
                float(group_record[column_name]),
                equal_nan=False,
            )
        group_df = df.loc[mask].copy()
        if group_df.empty:
            continue
        group_df = group_df.sort_values(varying_column, kind="mergesort")
        color = colors[group_index]
        legend_label = ", ".join(
            f"{column_name}={_format_legend_value(float(group_record[column_name]))}"
            for column_name in fixed_columns
        )

        for col_idx in range(4):
            for row_idx, (metric_col, _) in enumerate(ROW_METRICS):
                ax = axes[row_idx, col_idx]
                y_values = pd.to_numeric(group_df[metric_col], errors="coerce")
                x_values = pd.to_numeric(group_df[varying_column], errors="coerce")
                if not np.isfinite(y_values).any():
                    continue
                line, = ax.plot(
                    x_values,
                    y_values,
                    marker="o",
                    ms=3.0,
                    lw=1.1,
                    alpha=0.95,
                    color=color,
                    label=legend_label,
                )
                if row_idx == 0 and col_idx == 0:
                    legend_handles.append(line)
                    legend_labels.append(legend_label)

    for plane in range(1, 5):
        plane_title = f"Plane {plane}"
        axes[0, plane - 1].set_title(plane_title)
        optimum = optimum_rows.get(plane)
        if optimum is None:
            continue

        optimum_x = float(optimum[varying_column])
        optimum_percent = float(optimum["fiducial_1234_percent_of_total"])
        axes[0, plane - 1].scatter(
            [optimum_x],
            [optimum_percent],
            marker="*",
            s=130,
            color="black",
            edgecolor="white",
            linewidth=0.8,
            zorder=6,
        )

        abs_row_idx = plane
        abs_value = float(optimum[f"abs_error_{plane}"])
        axes[abs_row_idx, plane - 1].scatter(
            [optimum_x],
            [abs_value],
            marker="*",
            s=130,
            color="black",
            edgecolor="white",
            linewidth=0.8,
            zorder=6,
        )

    for row_idx, (_, y_label) in enumerate(ROW_METRICS):
        for col_idx in range(4):
            ax = axes[row_idx, col_idx]
            ax.grid(True, alpha=0.3)
            if col_idx == 0:
                ax.set_ylabel(y_label)
            if row_idx == 4:
                ax.set_xlabel(x_label)

    if legend_handles:
        unique_by_label = {}
        for handle, label in zip(legend_handles, legend_labels):
            unique_by_label.setdefault(label, handle)
        axes[0, 3].legend(
            list(unique_by_label.values()),
            list(unique_by_label.keys()),
            fontsize=8,
            loc="upper right",
            frameon=True,
        )

    fig.suptitle(figure_title)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=200)
    plt.close(fig)
    print(f"[write] {output_png}")
    return True


def _build_theta_r_pivot(df: pd.DataFrame, value_column: str) -> pd.DataFrame:
    plot_df = df.loc[:, ["theta_max", "r_max", value_column]].copy()
    plot_df["theta_max"] = pd.to_numeric(plot_df["theta_max"], errors="coerce")
    plot_df["r_max"] = pd.to_numeric(plot_df["r_max"], errors="coerce")
    plot_df[value_column] = pd.to_numeric(plot_df[value_column], errors="coerce")
    plot_df = plot_df.loc[
        np.isfinite(plot_df["theta_max"])
        & np.isfinite(plot_df["r_max"])
        & np.isfinite(plot_df[value_column])
    ].copy()
    if plot_df.empty:
        return pd.DataFrame()
    pivot = plot_df.pivot_table(
        index="r_max",
        columns="theta_max",
        values=value_column,
        aggfunc="mean",
    )
    return pivot.sort_index(axis=0).sort_index(axis=1)


def make_theta_r_error_contour_figure(
    df: pd.DataFrame,
    *,
    optimum_rows: dict[int, dict[str, object] | None],
    error_mode: str,
    output_png: Path,
    overwrite: bool,
) -> bool:
    if output_png.exists() and not overwrite:
        print(f"[skip] Plot exists and --overwrite was not set: {output_png}")
        return False

    if error_mode == "absolute_error":
        value_columns = {plane: f"abs_error_{plane}" for plane in range(1, 5)}
        color_map = "viridis"
        color_bar_label = "Absolute error = |eff_robust_xyphi - eff_reference|"
        figure_title = "Theta vs radius absolute-error contour"
        zero_centered = False
    else:
        value_columns = {plane: f"signed_error_{plane}" for plane in range(1, 5)}
        color_map = "coolwarm"
        color_bar_label = "Signed error = eff_robust_xyphi - eff_reference"
        figure_title = "Theta vs radius signed-error contour"
        zero_centered = True

    pivots = {
        plane: _build_theta_r_pivot(df, value_columns[plane])
        for plane in range(1, 5)
    }
    finite_values: list[np.ndarray] = []
    for pivot in pivots.values():
        if not pivot.empty:
            arr = pivot.to_numpy(dtype=float)
            finite = arr[np.isfinite(arr)]
            if finite.size:
                finite_values.append(np.abs(finite))
    if not finite_values:
        print(f"[skip] No finite {error_mode} values available for contour plot: {output_png}")
        return False

    norm = None
    if zero_centered:
        max_abs = float(max(np.max(values) for values in finite_values))
        if not np.isfinite(max_abs) or max_abs <= 0.0:
            max_abs = 1.0
        norm = TwoSlopeNorm(vmin=-max_abs, vcenter=0.0, vmax=max_abs)

    fig, axes = plt.subplots(
        nrows=2,
        ncols=2,
        figsize=(13.5, 10.0),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    axes_flat = axes.ravel()

    contour_artist = None
    for plane in range(1, 5):
        ax = axes_flat[plane - 1]
        pivot = pivots[plane]
        ax.set_title(f"Plane {plane}")
        ax.set_xlabel("theta_max")
        if plane in (1, 3):
            ax.set_ylabel("r_max")
        ax.grid(True, alpha=0.25)

        if pivot.empty:
            ax.text(0.5, 0.5, f"No finite {error_mode} data", ha="center", va="center", transform=ax.transAxes)
            continue

        theta_values = pivot.columns.to_numpy(dtype=float)
        r_values = pivot.index.to_numpy(dtype=float)
        residual_grid = pivot.to_numpy(dtype=float)
        theta_mesh, r_mesh = np.meshgrid(theta_values, r_values)

        if len(theta_values) >= 2 and len(r_values) >= 2:
            contour_artist = ax.contourf(
                theta_mesh,
                r_mesh,
                np.ma.masked_invalid(residual_grid),
                levels=21,
                cmap=color_map,
                norm=norm,
            )
            ax.contour(
                theta_mesh,
                r_mesh,
                np.ma.masked_invalid(residual_grid),
                levels=10,
                colors="black",
                linewidths=0.35,
                alpha=0.3,
            )
        else:
            contour_artist = ax.scatter(
                theta_mesh.ravel(),
                r_mesh.ravel(),
                c=residual_grid.ravel(),
                cmap=color_map,
                norm=norm,
                s=60,
                edgecolors="black",
                linewidths=0.3,
            )

        optimum = optimum_rows.get(plane)
        if optimum is not None:
            ax.scatter(
                [float(optimum["theta_max"])],
                [float(optimum["r_max"])],
                marker="*",
                s=160,
                color="gold",
                edgecolor="black",
                linewidth=0.8,
                zorder=6,
            )

    if contour_artist is not None:
        cbar = fig.colorbar(contour_artist, ax=axes_flat, shrink=0.95)
        cbar.set_label(color_bar_label)

    fig.suptitle(figure_title)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=200)
    plt.close(fig)
    print(f"[write] {output_png}")
    return True


def make_theta_r_percent_contour_figure(
    df: pd.DataFrame,
    *,
    optimum_rows: dict[int, dict[str, object] | None],
    output_png: Path,
    overwrite: bool,
) -> bool:
    if output_png.exists() and not overwrite:
        print(f"[skip] Plot exists and --overwrite was not set: {output_png}")
        return False

    pivot = _build_theta_r_pivot(df, "fiducial_1234_percent_of_total")
    if pivot.empty:
        print(f"[skip] No finite fiducial percentage data available for contour plot: {output_png}")
        return False

    theta_values = pivot.columns.to_numpy(dtype=float)
    r_values = pivot.index.to_numpy(dtype=float)
    percent_grid = pivot.to_numpy(dtype=float)
    theta_mesh, r_mesh = np.meshgrid(theta_values, r_values)

    fig, ax = plt.subplots(figsize=(8.5, 7.0), constrained_layout=True)
    if len(theta_values) >= 2 and len(r_values) >= 2:
        contour_artist = ax.contourf(
            theta_mesh,
            r_mesh,
            np.ma.masked_invalid(percent_grid),
            levels=21,
            cmap="viridis",
        )
        ax.contour(
            theta_mesh,
            r_mesh,
            np.ma.masked_invalid(percent_grid),
            levels=10,
            colors="white",
            linewidths=0.4,
            alpha=0.5,
        )
    else:
        contour_artist = ax.scatter(
            theta_mesh.ravel(),
            r_mesh.ravel(),
            c=percent_grid.ravel(),
            cmap="viridis",
            s=70,
            edgecolors="black",
            linewidths=0.3,
        )

    plane_colors = plt.cm.tab10(np.linspace(0, 1, 4))
    for plane in range(1, 5):
        optimum = optimum_rows.get(plane)
        if optimum is None:
            continue
        ax.scatter(
            [float(optimum["theta_max"])],
            [float(optimum["r_max"])],
            marker="*",
            s=170,
            color=plane_colors[plane - 1],
            edgecolor="white",
            linewidth=0.8,
            zorder=6,
            label=f"Plane {plane} optimum",
        )

    ax.set_title("Theta vs radius fiducial 1234 fraction")
    ax.set_xlabel("theta_max")
    ax.set_ylabel("r_max")
    ax.grid(True, alpha=0.25)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        unique = dict(zip(labels, handles))
        ax.legend(unique.values(), unique.keys(), loc="best", fontsize=8, frameon=True)
    cbar = fig.colorbar(contour_artist, ax=ax, shrink=0.95)
    cbar.set_label("fiducial_1234_percent_of_total")

    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=200)
    plt.close(fig)
    print(f"[write] {output_png}")
    return True


def plot_single_table(
    df: pd.DataFrame,
    *,
    optimum_rows: dict[int, dict[str, object] | None],
    plot_config: dict[str, str],
    plots_dir: Path,
    overwrite: bool,
) -> None:
    if overwrite:
        for stale_name in (
            "fiducial_scan_vs_x_abs_max_4x5.png",
            "fiducial_scan_vs_y_abs_max_4x5.png",
            "fiducial_scan_vs_x_abs_max_4x5.pdf",
            "fiducial_scan_vs_y_abs_max_4x5.pdf",
            "fiducial_scan_theta_vs_r_residual_1x4.png",
        ):
            stale_path = plots_dir / stale_name
            if stale_path.exists():
                stale_path.unlink()
    make_grouped_scan_figure(
        df,
        optimum_rows=optimum_rows,
        varying_column="theta_max",
        fixed_columns=("r_max",),
        x_label="theta_max",
        figure_title="Fiducial scan vs theta_max",
        output_png=plots_dir / "fiducial_scan_vs_theta_max_4x5.png",
        overwrite=overwrite,
    )
    make_grouped_scan_figure(
        df,
        optimum_rows=optimum_rows,
        varying_column="r_max",
        fixed_columns=("theta_max",),
        x_label="r_max",
        figure_title="Fiducial scan vs r_max",
        output_png=plots_dir / "fiducial_scan_vs_r_max_4x5.png",
        overwrite=overwrite,
    )
    make_theta_r_error_contour_figure(
        df,
        optimum_rows=optimum_rows,
        error_mode=plot_config["theta_r_error_contour_mode"],
        output_png=plots_dir / "fiducial_scan_theta_vs_r_error_1x4.png",
        overwrite=overwrite,
    )
    make_theta_r_percent_contour_figure(
        df,
        optimum_rows=optimum_rows,
        output_png=plots_dir / "fiducial_scan_theta_vs_r_fiducial_percent.png",
        overwrite=overwrite,
    )


def optimize_single_table(
    table_path: Path,
    *,
    output_dir: Path | None,
    make_plots: bool,
    plot_config: dict[str, str],
    overwrite: bool,
) -> None:
    print(f"[process] {table_path}")
    df = load_scan_table(table_path)
    validate_required_columns(df, table_path)
    analysis_df = add_efficiency_comparison_columns(df)

    print(f"[rows] {len(analysis_df)} rows")
    optimum_rows_list: list[dict[str, object]] = []
    optimum_plot_rows: dict[int, dict[str, object] | None] = {}
    for plane in range(1, 5):
        optimum_row, optimum_plot_row = optimize_plane(analysis_df, plane=plane, table_path=table_path)
        optimum_rows_list.append(optimum_row)
        optimum_plot_rows[plane] = optimum_plot_row
        print(
            f"[plane {plane}] valid={optimum_row['number_of_valid_scan_points']} "
            f"theta_max={optimum_row['theta_max']} r_max={optimum_row['r_max']} "
            f"relative_error={optimum_row['relative_error']} "
            f"abs_error={optimum_row['abs_error']} "
            f"fiducial_1234_percent_of_total={optimum_row['fiducial_1234_percent_of_total']}"
        )

    optimum_df = pd.DataFrame(optimum_rows_list)
    output_base = resolve_output_base(table_path, output_dir)
    optimization_dir = output_base / "optimization"
    plots_dir = output_base / "plots"

    write_optimum_table(
        optimum_df,
        optimization_dir / "fiducial_region_optimum.csv",
        overwrite=overwrite,
    )

    if make_plots:
        plot_single_table(
            analysis_df,
            optimum_rows=optimum_plot_rows,
            plot_config=plot_config,
            plots_dir=plots_dir,
            overwrite=overwrite,
        )


def main() -> int:
    args = parse_args()
    plot_config = load_plot_config(SCRIPT_CONFIG_PATH)
    scan_tables = find_scan_tables(args.table, args.input_root)
    print(
        f"[config] {SCRIPT_CONFIG_PATH} "
        f"theta_r_error_contour_mode={plot_config['theta_r_error_contour_mode']}"
    )
    print(f"[found] {len(scan_tables)} scan table(s)")
    for table_path in scan_tables:
        print(f"  - {table_path}")
    if not scan_tables:
        print("[done] No scan tables found.")
        return 0

    progress_bar = tqdm(
        scan_tables,
        desc="Processing scan tables",
        unit="table",
        dynamic_ncols=True,
    )
    n_success = 0
    failures: list[tuple[Path, str]] = []
    for table_path in progress_bar:
        progress_bar.set_postfix_str(table_path.parent.name)
        try:
            optimize_single_table(
                table_path,
                output_dir=args.output_dir,
                make_plots=not args.no_plots,
                plot_config=plot_config,
                overwrite=args.overwrite,
            )
            n_success += 1
        except Exception as exc:  # pragma: no cover - best effort for batch processing
            failures.append((table_path, str(exc)))
            print(f"[error] {table_path}: {exc}")
    progress_bar.close()

    if failures:
        print(f"[warn] {len(failures)} table(s) failed:")
        for table_path, message in failures:
            print(f"  - {table_path}: {message}")
    if n_success == 0 and failures:
        print("[done] No scan tables were processed successfully.")
        return 1

    print("[done] Fiducial scan optimization finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
