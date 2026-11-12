#!/usr/bin/env python3

"""Create a PDF summary of simulation parameter plots."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import ast
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Use a modern, clean style
plt.style.use('seaborn-v0_8-whitegrid')
from matplotlib.patches import Patch
from matplotlib.backends.backend_pdf import PdfPages

THIS_FILE = Path(__file__).resolve()
DT_ROOT = next((parent for parent in THIS_FILE.parents if parent.name == "MINGO_DIGITAL_TWIN"), THIS_FILE.parents[3])
PLOTTER_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot simulation parameter summary to PDF.  The "
        "completed CSV is treated as the full dataset, and the mesh file "
        "indicates which entries are currently in-process (overlay)."
    )
    parser.add_argument(
        "--mesh",
        dest="mesh",
        default=str(DT_ROOT / "SIMULATION_OUTPUTS" / "INTERSTEPS" / "STEP_0_TO_1" / "param_mesh.csv"),
        help="Path to the in-process mesh CSV (e.g. STEP_0_TO_1/param_mesh.csv).",
    )
    parser.add_argument(
        "--completed",
        default=str(DT_ROOT / "SIMULATION_OUTPUTS" / "SIMULATED_DATA" / "step_final_simulation_params.csv"),
        help="Path to the full/completed simulation params CSV (step_final_simulation_params.csv).",
    )
    parser.add_argument(
        "--output",
        default=str(PLOTTER_DIR / "param_mesh_summary.pdf"),
        help="Output PDF path",
    )
    parser.add_argument(
        "--n-value",
        type=float,
        default=2.0,
        help="cos_n value used for the n-specific flux histogram (default: 2).",
    )
    parser.add_argument(
        "--pdf-dpi",
        type=int,
        default=300,
        help="Rasterization DPI used before embedding the figure into the output PDF (default: 300).",
    )
    return parser.parse_args()







def parse_efficiencies_column(df: pd.DataFrame) -> pd.DataFrame:
    if {"eff_p1", "eff_p2", "eff_p3", "eff_p4"}.issubset(df.columns):
        return df
    if "efficiencies" not in df.columns:
        raise ValueError("Missing efficiency columns (eff_p1..eff_p4 or efficiencies).")

    eff_series = df["efficiencies"]
    if eff_series.apply(lambda value: isinstance(value, (list, tuple))).any():
        eff_frame = pd.DataFrame(eff_series.tolist(), columns=["eff_p1", "eff_p2", "eff_p3", "eff_p4"])
    else:
        parsed = []
        for value in eff_series:
            if value is None or (isinstance(value, float) and np.isnan(value)):
                parsed.append([np.nan, np.nan, np.nan, np.nan])
                continue
            if isinstance(value, (list, tuple)):
                parsed.append(list(value))
                continue
            text = str(value).strip()
            if not text:
                parsed.append([np.nan, np.nan, np.nan, np.nan])
                continue
            try:
                result = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                result = None
            if isinstance(result, (list, tuple)) and len(result) >= 4:
                parsed.append(list(result[:4]))
            else:
                parts = [part.strip() for part in text.strip("[]").split(",")]
                if len(parts) >= 4:
                    parsed.append(parts[:4])
                else:
                    parsed.append([np.nan, np.nan, np.nan, np.nan])
        eff_frame = pd.DataFrame(parsed, columns=["eff_p1", "eff_p2", "eff_p3", "eff_p4"])

    for col in ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]:
        df[col] = pd.to_numeric(eff_frame[col], errors="coerce")
    return df


def normalize_step_params(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "z_plane_1": "z_p1",
        "z_plane_2": "z_p2",
        "z_plane_3": "z_p3",
        "z_plane_4": "z_p4",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df = parse_efficiencies_column(df)
    if "selected_rows" not in df.columns and "requested_rows" in df.columns:
        df["selected_rows"] = df["requested_rows"]
    for numeric_col in ("selected_rows", "requested_rows"):
        if numeric_col in df.columns:
            df[numeric_col] = pd.to_numeric(df[numeric_col], errors="coerce")
    return df


def expand_params(raw_params: list[str], base_df: pd.DataFrame) -> list[str]:
    """Expand config tokens into actual numeric column names present in base_df.

    Supported expansions:
    - "efficiencies" -> expands to ["eff_p1", "eff_p2", "eff_p3", "eff_p4"] if those
      columns exist and are numeric.
    - "eff_1" / "eff1" -> maps to "eff_p1" (supports indices 1..4).

    Returns a list of unique numeric column names that exist in base_df, preserving order.
    """
    expanded: list[str] = []
    for p in raw_params:
        if isinstance(p, str) and p.lower().startswith("eff"):
            # token formats: "efficiencies", "efficiencies", "eff_1", "eff1", "eff_p1"
            if p == "efficiencies":
                eff_cols = [c for c in ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]
                            if c in base_df.columns and pd.api.types.is_numeric_dtype(base_df[c])]
                expanded.extend(eff_cols)
                continue
            # match eff_1, eff1, eff-p1, eff_p1
            import re

            m = re.match(r"^eff[_\-]?([1-4])$", p, flags=re.IGNORECASE)
            if m:
                idx = int(m.group(1))
                col = f"eff_p{idx}"
                if col in base_df.columns and pd.api.types.is_numeric_dtype(base_df[col]):
                    expanded.append(col)
                continue
            # if user already specified eff_p1..eff_p4, we'll treat below in default branch
        # default: keep the token as-is (will be filtered later)
        expanded.append(p)

    # Final filter: only keep numeric columns that exist in base_df and preserve order/uniqueness
    final: list[str] = []
    for p in expanded:
        if p in base_df.columns and pd.api.types.is_numeric_dtype(base_df[p]):
            if p not in final:
                final.append(p)
    return final


def _next_nice_interval(raw_interval: int, allowed: list[int]) -> int:
    for interval in allowed:
        if raw_interval <= interval:
            return interval
    return allowed[-1]


def make_fixed_date_locator(values: pd.Series, max_ticks: int = 4) -> mdates.DateLocator:
    dt_values = pd.to_datetime(values, errors="coerce").dropna()
    if dt_values.empty:
        return mdates.DayLocator(interval=1)

    span_seconds = (dt_values.max() - dt_values.min()).total_seconds()
    if not np.isfinite(span_seconds) or span_seconds <= 0:
        return mdates.HourLocator(interval=1)

    tick_count = max(2, int(max_ticks))
    denominator = max(1, tick_count - 1)
    span_days = span_seconds / 86400.0

    if span_seconds <= 2 * 3600:
        raw_minutes = int(np.ceil((span_seconds / 60.0) / denominator))
        minutes = _next_nice_interval(max(1, raw_minutes), [1, 2, 5, 10, 15, 20, 30, 60])
        if minutes < 60:
            return mdates.MinuteLocator(interval=minutes)
        return mdates.HourLocator(interval=max(1, minutes // 60))

    if span_seconds <= 7 * 24 * 3600:
        raw_hours = int(np.ceil((span_seconds / 3600.0) / denominator))
        hours = _next_nice_interval(max(1, raw_hours), [1, 2, 3, 4, 6, 8, 12, 24, 48, 72])
        if hours < 24:
            return mdates.HourLocator(interval=hours)
        return mdates.DayLocator(interval=max(1, hours // 24))

    if span_days <= 120:
        raw_days = int(np.ceil(span_days / denominator))
        days = _next_nice_interval(max(1, raw_days), [1, 2, 3, 5, 7, 10, 14, 21, 30])
        return mdates.DayLocator(interval=days)

    if span_days <= 5 * 365:
        raw_months = int(np.ceil((span_days / 30.0) / denominator))
        months = _next_nice_interval(max(1, raw_months), [1, 2, 3, 4, 6, 12])
        return mdates.MonthLocator(interval=months)

    raw_years = int(np.ceil((span_days / 365.25) / denominator))
    years = _next_nice_interval(max(1, raw_years), [1, 2, 5, 10, 20, 50])
    return mdates.YearLocator(base=years)


def save_rasterized_pdf_page(pdf: PdfPages, fig: plt.Figure, *, dpi: int) -> None:
    """Render a figure to a high-resolution raster image and embed it into the PDF."""
    png_buffer = io.BytesIO()
    fig.savefig(
        png_buffer,
        format="png",
        dpi=int(dpi),
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    png_buffer.seek(0)
    image = plt.imread(png_buffer)
    png_buffer.close()

    raster_fig = plt.figure(figsize=fig.get_size_inches(), dpi=72)
    raster_ax = raster_fig.add_axes([0.0, 0.0, 1.0, 1.0])
    raster_ax.imshow(image, aspect="auto")
    raster_ax.axis("off")
    pdf.savefig(raster_fig)
    plt.close(raster_fig)




def main() -> None:

    args = parse_args()
    mesh_path = Path(args.mesh)
    completed_path = Path(args.completed)
    output_path = Path(args.output)
    pdf_dpi = max(72, int(args.pdf_dpi))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # load completed/full dataset first
    if not completed_path.exists():
        raise FileNotFoundError(f"Completed params file not found: {completed_path}")
    completed_df = pd.read_csv(completed_path)
    completed_df = normalize_step_params(completed_df)

    # load mesh and keep only rows currently in progress (done == 0)
    if not mesh_path.exists():
        raise FileNotFoundError(f"Mesh params file not found: {mesh_path}")
    mesh_df = pd.read_csv(mesh_path)
    mesh_df = normalize_step_params(mesh_df)
    if "done" in mesh_df.columns:
        done_series = pd.to_numeric(mesh_df["done"], errors="coerce").fillna(0).astype(int)
        pending_df = mesh_df.loc[done_series == 0].copy()
    else:
        print("[plot_param_mesh] mesh has no 'done' column; treating all mesh rows as in-progress", flush=True)
        pending_df = mesh_df.copy()

    if pending_df.empty:
        print("[plot_param_mesh] no done=0 rows in mesh; in-progress overlay is empty", flush=True)

    # Plot on a combined dataframe so ranges include pending points too.
    if pending_df.empty:
        df = completed_df.copy()
    else:
        df = pd.concat([completed_df, pending_df], ignore_index=True, sort=False)

    required = [
        "cos_n",
        "flux_cm2_min",
        "eff_p1",
        "eff_p2",
        "eff_p3",
        "eff_p4",
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    with PdfPages(output_path) as pdf:
        # --- Parameter matrix plot (pairplot style) ---
        import yaml
        config_path = PLOTTER_DIR / "plot_param_mesh_config.yaml"
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        raw_params = config.get("params", [])
        completed_color = "#2ca02c"
        pending_color = "#ff7f0e"

        def _column_or_empty(source_df: pd.DataFrame, col_name: str) -> pd.Series:
            if col_name not in source_df.columns:
                return pd.Series(dtype=float)
            return source_df[col_name].dropna()

        def _valid_xy(source_df: pd.DataFrame, x_col: str, y_col: str) -> tuple[pd.Series, pd.Series]:
            if x_col not in source_df.columns or y_col not in source_df.columns:
                return pd.Series(dtype=float), pd.Series(dtype=float)
            x_vals = source_df[x_col]
            y_vals = source_df[y_col]
            valid = x_vals.notna() & y_vals.notna()
            return x_vals[valid], y_vals[valid]

        # Expand tokens using the combined DataFrame so pending-only ranges are included.
        param_list = expand_params(raw_params, df)
        # if execution_time column exists, add a last-2-hours view and place
        # both datetime columns at the front in fixed order.
        exec_time_cols: list[str] = []
        if "execution_time" in df.columns:
            recent_col = "execution_time_last_2h"
            cutoff_utc = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)

            def _prepare_time_columns(source_df: pd.DataFrame) -> None:
                if "execution_time" not in source_df.columns:
                    return
                exec_time_utc = pd.to_datetime(source_df["execution_time"], errors="coerce", utc=True)
                # Matplotlib cannot scatter tz-aware datetime series containing NaT.
                source_df["execution_time"] = exec_time_utc.dt.tz_convert(None)
                source_df[recent_col] = exec_time_utc.where(
                    exec_time_utc >= cutoff_utc, pd.NaT
                ).dt.tz_convert(None)

            _prepare_time_columns(completed_df)
            _prepare_time_columns(pending_df)
            _prepare_time_columns(df)
            for col in ("execution_time", recent_col):
                if col in param_list:
                    param_list.remove(col)
            param_list.insert(0, "execution_time")
            param_list.insert(1, recent_col)
            exec_time_cols = ["execution_time", recent_col]
        n = len(param_list)
        if n > 0:
            # keep datetime columns wider for readable tick labels
            width_ratios = [3.0 if param_list[i] in exec_time_cols else 1.0 for i in range(n)]
            # Preserve the visual size of non-datetime cells even when datetime
            # columns are wider by scaling figure width with the ratio sum.
            base_cell_size = 2.8
            fig_width = base_cell_size * float(sum(width_ratios))
            fig_height = base_cell_size * n
            fig, axes = plt.subplots(
                n, n, figsize=(fig_width, fig_height), dpi=110,
                gridspec_kw={"width_ratios": width_ratios},
            )
            # Compute global axis limits for all parameters
            axis_limits = {}
            for idx, param in enumerate(param_list):
                col = df[param]
                if col.dtype.kind in {'M', 'O'}:
                    continue
                vmin = col.min()
                vmax = col.max()
                if vmin == vmax:
                    vmin -= 1
                    vmax += 1
                # add 5% padding around the range so scatter points are not
                # clipped at the edges; padding factor applies to both sides
                span = vmax - vmin
                pad = span * 0.05
                axis_limits[param] = (vmin - pad, vmax + pad)
            for i in range(n):
                for j in range(n):
                    ax = axes[i, j] if n > 1 else axes
                    x = df[param_list[j]]
                    y = df[param_list[i]]
                    # Set identical axis limits for off-diagonal plots only.  Diagonal
                    # panels are histograms; using the raw parameter range for y makes the
                    # bars nearly invisible when counts are much smaller than the value
                    # range.  We'll let matplotlib autoscale the histogram y-axis later.
                    if param_list[j] in axis_limits:
                        ax.set_xlim(axis_limits[param_list[j]])
                    if i != j and param_list[i] in axis_limits:
                        ax.set_ylim(axis_limits[param_list[i]])
                    # Clean, minimal style
                    ax.grid(True, linestyle=':', linewidth=0.4, alpha=0.3)
                    # draw a simple border around each subplot
                    for spine in ax.spines.values():
                        spine.set_visible(True)
                        spine.set_linewidth(0.7)
                        spine.set_color('black')
                    if i == j:
                        x_clean = x.dropna()
                        hist_bins = 16
                        if param_list[i] in {"selected_rows", "requested_rows"}:
                            unique_count = int(pd.Series(x_clean).nunique())
                            if unique_count > 0:
                                hist_bins = min(max(unique_count, 2), 40)
                        completed_vals = _column_or_empty(completed_df, param_list[i])
                        if not completed_vals.empty:
                            ax.hist(
                                completed_vals,
                                bins=hist_bins,
                                color=completed_color,
                                alpha=0.45,
                                edgecolor='white',
                                linewidth=0.5,
                            )
                        pending_vals = _column_or_empty(pending_df, param_list[i])
                        if not pending_vals.empty:
                            ax.hist(
                                pending_vals,
                                bins=hist_bins,
                                color=pending_color,
                                alpha=0.55,
                                edgecolor='white',
                                linewidth=0.5,
                            )
                        # put variable name above histogram
                        ax.set_title(param_list[i], fontsize=10, pad=4)
                        # ensure y limits fit the bars
                        ax.autoscale_view(scalex=False, scaley=True)
                    elif i > j:
                        x_completed, y_completed = _valid_xy(completed_df, param_list[j], param_list[i])
                        if not x_completed.empty:
                            ax.scatter(x_completed, y_completed, s=7, alpha=0.4, color=completed_color)
                        x_pending, y_pending = _valid_xy(pending_df, param_list[j], param_list[i])
                        if not x_pending.empty:
                            ax.scatter(
                                x_pending,
                                y_pending,
                                s=16,
                                alpha=0.8,
                                color=pending_color,
                                marker="x",
                                linewidths=0.8,
                            )
                        x_is_execution_time = param_list[j] in exec_time_cols
                        if x_is_execution_time:
                            # Keep execution-time X panels unconstrained for readable date axes.
                            ax.set_aspect("auto")
                        else:
                            # Keep individual non-execution-time scatter panels square.
                            # Axis limits remain shared per row/column via axis_limits above.
                            if hasattr(ax, "set_box_aspect"):
                                ax.set_box_aspect(1)
                            else:
                                ax.set_aspect("equal", adjustable="box")
                        # if this column is execution_time-like, connect points to form a
                        # time series line.  sorting ensures the line follows increasing
                        # time even if the DataFrame index isn't ordered.
                        if param_list[j] in exec_time_cols:
                            try:
                                if len(x_completed) > 1:
                                    order = np.argsort(x_completed.values)
                                    ax.plot(
                                        x_completed.values[order],
                                        y_completed.values[order],
                                        color=completed_color,
                                        alpha=0.7,
                                        linewidth=0.8,
                                    )
                                if len(x_pending) > 1:
                                    order = np.argsort(x_pending.values)
                                    ax.plot(
                                        x_pending.values[order],
                                        y_pending.values[order],
                                        color=pending_color,
                                        alpha=0.8,
                                        linewidth=0.8,
                                        linestyle="--",
                                    )
                            except Exception:
                                pass
                    else:
                        ax.axis("off")
                    # Remove axis labels except for outer plots and add labels
                    if i < n-1:
                        ax.set_xticklabels([])
                    else:
                        # bottom row: label x-axis with parameter
                        ax.set_xlabel(param_list[j], fontsize=10)
                    if j > 0:
                        ax.set_yticklabels([])
                    else:
                        # leftmost column: label y-axis
                        ax.set_ylabel(param_list[i], fontsize=10, rotation=90, labelpad=10)
                    ax.tick_params(axis='both', which='major', labelsize=9, width=1, length=3)
            fig.suptitle("Parameter Matrix (Completed + In-Progress Mesh)", fontsize=14, y=1.01)
            fig.subplots_adjust(left=0.07, right=0.93, top=0.93, bottom=0.07, wspace=0.03, hspace=0.03)
            legend_handles = [
                Patch(
                    facecolor=completed_color,
                    edgecolor="none",
                    alpha=0.6,
                    label="Completed (step_final_simulation_params.csv)",
                ),
            ]
            if not pending_df.empty:
                legend_handles.append(
                    Patch(
                        facecolor=pending_color,
                        edgecolor="none",
                        alpha=0.7,
                        label="In progress (param_mesh done=0)",
                    )
                )
            fig.legend(handles=legend_handles, loc="upper right", fontsize=9, frameon=True)
            # Datetime axis formatting for execution time columns
            if exec_time_cols:
                et_indices = [param_list.index(col) for col in exec_time_cols if col in param_list]
                date_fmt = mdates.DateFormatter("%Y-%m-%d %H:%M")
                for _i in range(n):
                    for _j in range(n):
                        _ax = axes[_i, _j] if n > 1 else axes
                        if _j in et_indices:
                            _ax.xaxis.set_major_formatter(date_fmt)
                            _ax.xaxis.set_major_locator(
                                make_fixed_date_locator(df[param_list[_j]], max_ticks=4)
                            )
                            # only label the lowest row
                            if _i == n-1:
                                plt.setp(_ax.xaxis.get_majorticklabels(), rotation=15, ha="right", fontsize=8)
                            else:
                                _ax.set_xticklabels([])
                        if _i in et_indices and _i != _j:
                            _ax.yaxis.set_major_formatter(date_fmt)
                            _ax.yaxis.set_major_locator(
                                make_fixed_date_locator(df[param_list[_i]], max_ticks=4)
                            )
                            plt.setp(_ax.yaxis.get_majorticklabels(), fontsize=8)
                now = pd.Timestamp.now(tz="UTC").tz_convert(None)
                for i in range(n):
                    for j in range(n):
                        ax = axes[i, j] if n > 1 else axes
                        if i < j or not ax.axison:
                            continue
                        if param_list[j] in exec_time_cols:
                            ax.axvline(now, color="red", linestyle="--", alpha=0.3, zorder=10)
                        if i > j and param_list[i] in exec_time_cols:
                            ax.axhline(now, color="red", linestyle="--", alpha=0.3, zorder=10)
            save_rasterized_pdf_page(pdf, fig, dpi=pdf_dpi)
            plt.close(fig)





if __name__ == "__main__":
    main()
