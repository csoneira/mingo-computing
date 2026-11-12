#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Plot Task 4 metadata during TimTrack convergence scans."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

TS_FORMAT = "%Y-%m-%d_%H.%M.%S"
JOIN_KEYS = ["filename_base", "execution_timestamp", "param_hash"]
RELERR_BAND = 0.30
NORM_EVENTS = 1000.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build TimTrack quality scan plots from Task 4 metadata.",
    )
    parser.add_argument("--specific-csv", required=True, help="Path to task_4_metadata_specific.csv")
    parser.add_argument("--profiling-csv", required=True, help="Path to task_4_metadata_profiling.csv")
    parser.add_argument("--output-dir", required=True, help="Directory for plot/summary outputs")
    parser.add_argument(
        "--tail-rows",
        type=int,
        default=300,
        help="Use only the latest N merged rows (0 = all rows).",
    )
    parser.add_argument(
        "--scan-log",
        default="",
        help="Optional scan log CSV (for sanity printout only).",
    )
    parser.add_argument(
        "--run-reference-log",
        default="",
        help="Optional run-reference CSV written by run_timtrack_quality_scan.sh.",
    )
    parser.add_argument(
        "--run-back",
        type=int,
        default=0,
        help="Run selector from end: 0 latest, 1 previous, ... ; -1 disables run filtering.",
    )
    parser.add_argument(
        "--title-prefix",
        default="TimTrack scan",
        help="Title prefix for the generated figure.",
    )
    return parser.parse_args()


def ensure_join_keys(df: pd.DataFrame) -> pd.DataFrame:
    missing = [key for key in JOIN_KEYS if key not in df.columns]
    if not missing:
        return df
    return df.reindex(columns=[*df.columns, *missing], fill_value="")


def numeric_or_nan(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    col_list = list(columns)
    missing = [col for col in col_list if col not in df.columns]
    if missing:
        df = df.reindex(columns=[*df.columns, *missing], fill_value=np.nan)
    converted = df.loc[:, col_list].apply(pd.to_numeric, errors="coerce")
    df.loc[:, col_list] = converted
    return df


def profile_label(df: pd.DataFrame) -> pd.Series:
    d0 = df["timtrack_d0"].map(lambda v: "nan" if pd.isna(v) else f"{v:g}")
    cocut = df["timtrack_cocut"].map(lambda v: "nan" if pd.isna(v) else f"{v:g}")
    itmx = df["timtrack_iter_max"].map(lambda v: "nan" if pd.isna(v) else f"{v:g}")
    return "d0=" + d0 + "|cocut=" + cocut + "|iter=" + itmx


def add_time_normalization(df: pd.DataFrame) -> pd.DataFrame:
    if "tt_events_total_n" not in df.columns:
        df["tt_events_total_n"] = np.nan
    if "timtrack_attempted_fit_n" not in df.columns:
        df["timtrack_attempted_fit_n"] = np.nan

    tt_events = pd.to_numeric(df["tt_events_total_n"], errors="coerce")
    attempted_events = pd.to_numeric(df["timtrack_attempted_fit_n"], errors="coerce")
    norm_events = np.where(np.isfinite(tt_events) & (tt_events > 0), tt_events, np.nan)
    norm_events = np.where(
        np.isfinite(norm_events),
        norm_events,
        np.where(np.isfinite(attempted_events) & (attempted_events > 0), attempted_events, np.nan),
    )
    norm_events = np.asarray(norm_events, dtype=float)

    def per_k(series: pd.Series) -> np.ndarray:
        vals = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        return np.divide(
            vals * NORM_EVENTS,
            norm_events,
            out=np.full(vals.shape, np.nan, dtype=float),
            where=np.isfinite(norm_events) & (norm_events > 0),
        )

    return df.assign(
        normalization_events_n=norm_events,
        s_timtrack_fitting_per_1k_events_s=per_k(df["s_timtrack_fitting_s"]),
        s_tt_main_fit_per_1k_events_s=per_k(df["s_tt_main_fit_s"]),
        s_tt_residual_loo_per_1k_events_s=per_k(df["s_tt_residual_loo_s"]),
        total_per_1k_events_s=per_k(df["total_s"]),
    )


def load_merged_metadata(specific_csv: Path, profiling_csv: Path) -> pd.DataFrame:
    specific_df = pd.read_csv(specific_csv, low_memory=False)
    profiling_df = pd.read_csv(profiling_csv, low_memory=False)
    specific_df = ensure_join_keys(specific_df)
    profiling_df = ensure_join_keys(profiling_df)

    merged = specific_df.merge(profiling_df, on=JOIN_KEYS, how="inner", suffixes=("_spec", "_prof"))
    if merged.empty:
        raise ValueError("No overlapping rows found between specific and profiling metadata.")

    merged = merged.assign(
        execution_dt=pd.to_datetime(merged["execution_timestamp"], format=TS_FORMAT, errors="coerce")
    )
    merged = merged.dropna(subset=["execution_dt"]).sort_values("execution_dt").reset_index(drop=True)
    if merged.empty:
        raise ValueError("No valid execution_timestamp rows after datetime parsing.")

    merged = numeric_or_nan(
        merged,
        [
            "timtrack_d0",
            "timtrack_cocut",
            "timtrack_iter_max",
            "fit_compare_median_relerr_detached_s_to_1_over_c",
            "fit_compare_median_relerr_timtrack_s_to_1_over_c",
            "timtrack_itermax_runout_ratio",
            "timtrack_converged_on_cocut_ratio",
            "s_timtrack_fitting_s",
            "s_tt_intro_s",
            "s_tt_main_fit_s",
            "s_tt_residual_s",
            "s_tt_residual_loo_s",
            "s_tt_writeback_s",
            "total_s",
            "tt_events_total_n",
            "timtrack_attempted_fit_n",
        ],
    )

    merged = merged.assign(
        fit_compare_median_absrelerr_detached_s_to_1_over_c=np.abs(
            merged["fit_compare_median_relerr_detached_s_to_1_over_c"]
        ),
        fit_compare_median_absrelerr_timtrack_s_to_1_over_c=np.abs(
            merged["fit_compare_median_relerr_timtrack_s_to_1_over_c"]
        ),
        profile_label=profile_label(merged),
        scan_index=np.arange(len(merged), dtype=int),
    )
    merged = add_time_normalization(merged)

    # Consolidate blocks after column preparation to avoid fragmentation warnings.
    return merged.copy()


def parse_basenames(raw: object) -> List[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    return [chunk.strip() for chunk in text.split(";") if chunk.strip()]


def select_run_reference(
    run_reference_log: Path,
    run_back: int,
) -> tuple[list[str], dict]:
    if run_back < 0 or not run_reference_log.exists():
        return [], {}

    run_df = pd.read_csv(run_reference_log, low_memory=False)
    if run_df.empty or "basenames" not in run_df.columns:
        return [], {}

    # Prefer explicit run_id grouping if available; otherwise infer runs from
    # contiguous numeric cycle blocks (1,2,3,...) produced by one launcher run.
    groups: list[pd.DataFrame] = []
    if "run_id" in run_df.columns and run_df["run_id"].fillna("").astype(str).str.strip().any():
        run_df = run_df.copy()
        run_df["run_id"] = run_df["run_id"].fillna("").astype(str).str.strip()
        run_df = run_df[run_df["run_id"] != ""]
        if run_df.empty:
            return [], {}
        seen_ids: list[str] = []
        for rid in run_df["run_id"]:
            if rid not in seen_ids:
                seen_ids.append(rid)
        groups = [run_df[run_df["run_id"] == rid] for rid in seen_ids]
    else:
        run_df = run_df.copy().reset_index(drop=True)
        cycles = pd.to_numeric(run_df["cycle"], errors="coerce")
        group_idx = np.zeros(len(run_df), dtype=int)
        g = 0
        prev = np.nan
        for i, cyc in enumerate(cycles):
            if i == 0:
                group_idx[i] = g
                prev = cyc
                continue
            contiguous = np.isfinite(cyc) and np.isfinite(prev) and int(cyc) == int(prev) + 1
            if not contiguous:
                g += 1
            group_idx[i] = g
            prev = cyc
        run_df["run_group"] = group_idx
        groups = [grp for _, grp in run_df.groupby("run_group", sort=True)]

    if not groups:
        return [], {}
    selected_group_index = len(groups) - 1 - run_back
    if selected_group_index < 0:
        return [], {}
    run_rows = groups[selected_group_index]

    seen_bases: set[str] = set()
    basenames: list[str] = []
    for raw in run_rows["basenames"].tolist():
        for base in parse_basenames(raw):
            if base in seen_bases:
                continue
            seen_bases.add(base)
            basenames.append(base)

    if not basenames:
        return [], {}

    first = run_rows.iloc[0]
    last = run_rows.iloc[-1]
    info = {
        "run_timestamp": str(first.get("run_timestamp", "")),
        "cycle": f"{first.get('cycle', '')}->{last.get('cycle', '')}",
        "profile_id": str(last.get("profile_id", "")),
        "station": str(last.get("station", "")),
        "basename_count": int(len(basenames)),
        "rows_in_run": int(len(run_rows)),
    }
    return basenames, info


def build_group_summary(merged: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "fit_compare_median_relerr_detached_s_to_1_over_c",
        "fit_compare_median_relerr_timtrack_s_to_1_over_c",
        "fit_compare_median_absrelerr_detached_s_to_1_over_c",
        "fit_compare_median_absrelerr_timtrack_s_to_1_over_c",
        "timtrack_itermax_runout_ratio",
        "timtrack_converged_on_cocut_ratio",
        "s_timtrack_fitting_s",
        "s_timtrack_fitting_per_1k_events_s",
        "s_tt_main_fit_s",
        "s_tt_main_fit_per_1k_events_s",
        "s_tt_residual_loo_per_1k_events_s",
        "total_s",
        "total_per_1k_events_s",
        "normalization_events_n",
    ]

    group_cols = ["profile_label", "timtrack_d0", "timtrack_cocut", "timtrack_iter_max"]
    out_rows: List[dict] = []
    for group_vals, group_df in merged.groupby(group_cols, dropna=False):
        row = {
            "profile_label": group_vals[0],
            "timtrack_d0": group_vals[1],
            "timtrack_cocut": group_vals[2],
            "timtrack_iter_max": group_vals[3],
            "n_rows": int(len(group_df)),
            "first_timestamp": str(group_df["execution_timestamp"].iloc[0]),
            "last_timestamp": str(group_df["execution_timestamp"].iloc[-1]),
        }
        for metric in metrics:
            vals = pd.to_numeric(group_df[metric], errors="coerce").to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            row[f"{metric}_median"] = float(np.median(vals)) if vals.size else np.nan
            row[f"{metric}_mean"] = float(np.mean(vals)) if vals.size else np.nan
        out_rows.append(row)

    summary_df = pd.DataFrame(out_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(["timtrack_d0", "timtrack_cocut", "timtrack_iter_max"])
    return summary_df


def make_figure(
    merged: pd.DataFrame,
    output_png: Path,
    title_prefix: str,
    run_context: str = "",
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)

    x = merged["scan_index"].to_numpy(dtype=int)

    ax = axes[0, 0]
    ax.plot(
        x,
        merged["s_timtrack_fitting_per_1k_events_s"],
        marker="o",
        linewidth=1.0,
        label="s_timtrack_fitting per 1k events",
    )
    ax.plot(
        x,
        merged["s_tt_main_fit_per_1k_events_s"],
        marker="o",
        linewidth=1.0,
        label="s_tt_main_fit per 1k events",
    )
    ax.plot(
        x,
        merged["total_per_1k_events_s"],
        marker="o",
        linewidth=1.0,
        label="total_s per 1k events",
    )
    ax.set_title("Execution Time Normalized by Event Count")
    ax.set_xlabel("Merged row index")
    ax.set_ylabel("seconds per 1k events")
    ax.grid(alpha=0.25)
    ax.legend(loc="best", fontsize=8)

    ax = axes[0, 1]
    det_abs = pd.to_numeric(
        merged["fit_compare_median_absrelerr_detached_s_to_1_over_c"],
        errors="coerce",
    ).to_numpy(dtype=float)
    tim_abs = pd.to_numeric(
        merged["fit_compare_median_absrelerr_timtrack_s_to_1_over_c"],
        errors="coerce",
    ).to_numpy(dtype=float)
    ax.fill_between(
        x,
        0.0,
        RELERR_BAND,
        color="#72B7B2",
        alpha=0.2,
        label=f"{int(RELERR_BAND * 100)}% band (|relerr| <= {RELERR_BAND:.2f})",
    )
    ax.plot(
        x,
        det_abs,
        marker="o",
        linewidth=1.0,
        label="detached |relerr(s,1/c)| (fixed baseline)",
    )
    ax.plot(
        x,
        tim_abs,
        marker="o",
        linewidth=1.0,
        label="timtrack |relerr(s,1/c)|",
    )
    ax.axhline(
        RELERR_BAND,
        linestyle="--",
        linewidth=1.0,
        color="#2E8B57",
        alpha=0.9,
        label=f"{int(RELERR_BAND * 100)}% threshold",
    )
    finite_max = np.nanmax(np.concatenate([det_abs, tim_abs])) if np.isfinite(np.concatenate([det_abs, tim_abs])).any() else 0.02
    ax.set_ylim(0.0, max(RELERR_BAND * 1.05, float(finite_max) * 1.1))
    ax.set_title("Absolute Slowness Relative Error to 1/c\nDetached = fixed baseline (not cycled)")
    ax.set_xlabel("Merged row index")
    ax.set_ylabel("|relative error|")
    ax.grid(alpha=0.25)
    ax.legend(loc="best", fontsize=8)

    ax = axes[1, 0]
    ax.plot(
        x,
        merged["timtrack_itermax_runout_ratio"],
        marker="o",
        linewidth=1.0,
        label="itermax_runout_ratio",
    )
    ax.plot(
        x,
        merged["timtrack_converged_on_cocut_ratio"],
        marker="o",
        linewidth=1.0,
        label="converged_on_cocut_ratio",
    )
    ax.set_title("Convergence Ratios")
    ax.set_xlabel("Merged row index")
    ax.set_ylabel("ratio")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(alpha=0.25)
    ax.legend(loc="best", fontsize=8)

    ax = axes[1, 1]
    grouped = (
        merged.groupby("profile_label", dropna=False)["total_s"]
        .median()
        .sort_values(ascending=False)
    )
    if len(grouped) > 12:
        grouped = grouped.head(12)
    ax.bar(np.arange(len(grouped)), grouped.to_numpy(dtype=float), color="#4C78A8")
    ax.set_xticks(np.arange(len(grouped)))
    ax.set_xticklabels(grouped.index.tolist(), rotation=45, ha="right", fontsize=8)
    ax.set_title("Median total_s by profile (absolute)")
    ax.set_ylabel("seconds")
    ax.grid(axis="y", alpha=0.25)

    ts_min = merged["execution_timestamp"].iloc[0]
    ts_max = merged["execution_timestamp"].iloc[-1]
    title = f"{title_prefix} | rows={len(merged)} | {ts_min} -> {ts_max}"
    if run_context:
        title = f"{title} | {run_context}"
    fig.suptitle(title, fontsize=12)
    fig.savefig(output_png, dpi=150)
    plt.close(fig)


def make_cocut_tradeoff_figure(
    merged_df: pd.DataFrame,
    output_png: Path,
    title_prefix: str,
) -> pd.DataFrame:
    filtered = merged_df.copy()
    required_cols = [
        "execution_timestamp",
        "filename_base",
        "timtrack_d0",
        "timtrack_cocut",
        "timtrack_iter_max",
        "timtrack_converged_on_cocut_ratio",
        "normalization_events_n",
        "s_timtrack_fitting_s",
        "s_timtrack_fitting_per_1k_events_s",
        "total_s",
        "total_per_1k_events_s",
        "fit_compare_median_absrelerr_detached_s_to_1_over_c",
        "fit_compare_median_absrelerr_timtrack_s_to_1_over_c",
    ]
    missing = [col for col in required_cols if col not in filtered.columns]
    if missing:
        filtered = filtered.reindex(columns=[*filtered.columns, *missing], fill_value=np.nan)

    conv = pd.to_numeric(filtered["timtrack_converged_on_cocut_ratio"], errors="coerce")
    filtered = filtered[conv >= 1.0 - 1e-12].copy()

    sort_cols = ["timtrack_cocut"]
    if "execution_dt" in filtered.columns:
        sort_cols.append("execution_dt")
    filtered = filtered.sort_values(sort_cols, kind="stable").reset_index(drop=True)

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, constrained_layout=True)

    if filtered.empty:
        for ax in axes:
            ax.text(
                0.5,
                0.5,
                "No points with converged_on_cocut_ratio == 1",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            ax.set_axis_off()
    else:
        x = pd.to_numeric(filtered["timtrack_cocut"], errors="coerce").to_numpy(dtype=float)
        y_fit = pd.to_numeric(
            filtered["s_timtrack_fitting_per_1k_events_s"],
            errors="coerce",
        ).to_numpy(dtype=float)
        y_total = pd.to_numeric(
            filtered["total_per_1k_events_s"],
            errors="coerce",
        ).to_numpy(dtype=float)
        y_det = pd.to_numeric(
            filtered["fit_compare_median_absrelerr_detached_s_to_1_over_c"],
            errors="coerce",
        ).to_numpy(dtype=float)
        y_tim = pd.to_numeric(
            filtered["fit_compare_median_absrelerr_timtrack_s_to_1_over_c"],
            errors="coerce",
        ).to_numpy(dtype=float)

        ax = axes[0]
        ax.scatter(x, y_fit, s=28, color="#4C78A8", alpha=0.85, label="s_timtrack_fitting per 1k events")
        ax.plot(x, y_fit, linewidth=0.8, color="#4C78A8", alpha=0.35)
        ax.scatter(x, y_total, s=24, color="#9D755D", alpha=0.75, label="total_s per 1k events")
        ax.plot(x, y_total, linewidth=0.8, color="#9D755D", alpha=0.35)
        ax.set_title("Timings vs cocut (normalized by events)")
        ax.set_ylabel("seconds per 1k events")
        ax.grid(alpha=0.25)
        ax.legend(loc="best", fontsize=8)

        ax = axes[1]
        x_finite = x[np.isfinite(x)]
        if x_finite.size:
            x_band = np.sort(np.unique(x_finite))
            ax.fill_between(
                x_band,
                0.0,
                RELERR_BAND,
                color="#72B7B2",
                alpha=0.2,
                label=f"{int(RELERR_BAND * 100)}% band",
            )
        ax.scatter(
            x,
            y_det,
            s=28,
            color="#F58518",
            alpha=0.85,
            label="detached |relerr(s,1/c)| (fixed baseline)",
        )
        ax.scatter(
            x,
            y_tim,
            s=28,
            color="#54A24B",
            alpha=0.85,
            label="timtrack |relerr(s,1/c)|",
        )
        ax.axhline(
            RELERR_BAND,
            linestyle="--",
            linewidth=1.0,
            color="#2E8B57",
            alpha=0.9,
            label=f"{int(RELERR_BAND * 100)}% threshold",
        )
        ymax = np.nanmax(np.concatenate([y_det, y_tim])) if np.isfinite(np.concatenate([y_det, y_tim])).any() else 0.02
        ax.set_ylim(0.0, max(RELERR_BAND * 1.05, float(ymax) * 1.1))
        ax.set_xlabel("cocut")
        ax.set_ylabel("|relative error|")
        ax.set_title("Slowness |relative error| vs cocut\nDetached = fixed baseline (not cycled)")
        ax.grid(alpha=0.25)
        ax.legend(loc="best", fontsize=8)

    fig.suptitle(f"{title_prefix} | cocut tradeoff view", fontsize=12)
    fig.savefig(output_png, dpi=150)
    plt.close(fig)

    return filtered[required_cols].copy()


def main() -> None:
    args = parse_args()
    specific_csv = Path(args.specific_csv).expanduser().resolve()
    profiling_csv = Path(args.profiling_csv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not specific_csv.exists():
        raise FileNotFoundError(f"Specific metadata not found: {specific_csv}")
    if not profiling_csv.exists():
        raise FileNotFoundError(f"Profiling metadata not found: {profiling_csv}")

    merged = load_merged_metadata(specific_csv, profiling_csv)

    run_context = ""
    run_ref_raw = str(args.run_reference_log).strip()
    run_ref_path = Path(run_ref_raw).expanduser().resolve() if run_ref_raw else None
    basenames: list[str] = []
    selected_run_info: dict = {}

    if run_ref_path is not None:
        basenames, selected_run_info = select_run_reference(run_ref_path, args.run_back)
        if basenames:
            base_set = set(basenames)
            filtered = merged[merged["filename_base"].astype(str).isin(base_set)].copy()
            if not filtered.empty:
                merged = filtered.sort_values("execution_dt").reset_index(drop=True)
                merged["scan_index"] = np.arange(len(merged), dtype=int)
                run_context = (
                    f"run_ts={selected_run_info.get('run_timestamp', '')} "
                    f"profile={selected_run_info.get('profile_id', '')} "
                    f"cycle={selected_run_info.get('cycle', '')}"
                )
            else:
                print(
                    "[timtrack_quality_scan_plotter] Run filter found no matching rows; "
                    "falling back to row-based selection."
                )

    # Tail-rows is applied only when run filtering is not active.
    if not run_context and args.tail_rows > 0 and len(merged) > args.tail_rows:
        merged = merged.tail(args.tail_rows).reset_index(drop=True)
        merged["scan_index"] = np.arange(len(merged), dtype=int)

    summary_df = build_group_summary(merged)

    summary_csv = output_dir / "timtrack_quality_scan_summary.csv"
    merged_tail_csv = output_dir / "timtrack_quality_scan_merged_tail.csv"
    figure_png = output_dir / "timtrack_quality_scan_overview.png"
    cocut_figure_png = output_dir / "timtrack_quality_scan_cocut_tradeoff.png"
    cocut_summary_csv = output_dir / "timtrack_quality_scan_cocut_tradeoff_summary.csv"

    summary_df.to_csv(summary_csv, index=False)
    merged.to_csv(merged_tail_csv, index=False)
    make_figure(merged, figure_png, args.title_prefix, run_context=run_context)
    cocut_df = make_cocut_tradeoff_figure(merged, cocut_figure_png, args.title_prefix)
    cocut_df.to_csv(cocut_summary_csv, index=False)

    print(f"[timtrack_quality_scan_plotter] Saved: {summary_csv}")
    print(f"[timtrack_quality_scan_plotter] Saved: {merged_tail_csv}")
    print(f"[timtrack_quality_scan_plotter] Saved: {figure_png}")
    print(f"[timtrack_quality_scan_plotter] Saved: {cocut_figure_png}")
    print(f"[timtrack_quality_scan_plotter] Saved: {cocut_summary_csv}")
    if run_context:
        print(f"[timtrack_quality_scan_plotter] Applied run filter: {run_context}")

    scan_log_raw = str(args.scan_log).strip()
    if scan_log_raw:
        scan_log = Path(scan_log_raw).expanduser().resolve()
        if scan_log.exists():
            print(f"[timtrack_quality_scan_plotter] Scan log detected: {scan_log}")


if __name__ == "__main__":
    main()
