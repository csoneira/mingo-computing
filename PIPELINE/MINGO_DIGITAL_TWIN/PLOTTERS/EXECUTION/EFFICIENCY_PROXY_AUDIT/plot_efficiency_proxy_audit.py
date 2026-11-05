#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/EFFICIENCY_PROXY_AUDIT/plot_efficiency_proxy_audit.py
Purpose: Audit how configured plane efficiencies map into stagewise proxy observables without modifying the simulator.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-27
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/EFFICIENCY_PROXY_AUDIT/plot_efficiency_proxy_audit.py [options]
Inputs: Existing STEP 2 / STEP 3 / STEP 9 interstep chunk manifests and pickles.
Outputs: CSV, JSON summary, and PDF diagnostics under this plotter directory (or user-selected output dir).
Notes: Read-only diagnostic. Does not modify any simulation artifact.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd


PLANE_MISSING_TAG = {1: "234", 2: "134", 3: "124", 4: "123"}
STAGE_COLUMNS = [
    ("step2_geometry_proxy", "STEP 2 geometry proxy"),
    ("step3_cond_avalanche_on_cross1234", "STEP 3 P(avalanche_i | cross1234)"),
    ("step3_proxy", "STEP 3 avalanche proxy"),
    ("step9_trigger_proxy", "STEP 9 trigger proxy"),
]


@dataclass(frozen=True)
class RunInputs:
    step3_run: str
    step2_manifest: Path
    step3_manifest: Path
    step9_manifest: Path
    configured_efficiencies: tuple[float, float, float, float]
    flux_cm2_min: float | None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _intersteps_root() -> Path:
    return _repo_root() / "MINGO_DIGITAL_TWIN" / "SIMULATION_OUTPUTS" / "INTERSTEPS"


def _normalize_tt_values(values: Iterable[object]) -> np.ndarray:
    series = pd.Series(values, copy=False).astype("string").fillna("")
    series = series.str.strip().str.replace(r"\.0$", "", regex=True)
    series = series.replace({"0": "", "0.0": "", "nan": "", "<NA>": ""})
    return series.to_numpy(dtype=str)


def _tt_counts(values: np.ndarray) -> Counter[str]:
    counts = Counter(values.tolist())
    counts.pop("", None)
    return counts


def _plane_proxy(counts: Counter[str], plane: int) -> float:
    numerator = counts.get("1234", 0)
    denominator = numerator + counts.get(PLANE_MISSING_TAG[plane], 0)
    if denominator <= 0:
        return float("nan")
    return float(numerator) / float(denominator)


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


def _iter_chunk_paths(manifest_path: Path) -> list[Path]:
    manifest = _load_manifest(manifest_path)
    return [Path(chunk) for chunk in manifest.get("chunks", [])]


def _extract_flux_from_step3_metadata(step3_manifest_path: Path) -> float | None:
    metadata = _load_manifest(step3_manifest_path).get("metadata", {})
    upstream_step2 = metadata.get("upstream", {})
    upstream_step1 = upstream_step2.get("upstream", {})
    config_step1 = upstream_step1.get("config", {})
    flux = config_step1.get("flux_cm2_min")
    return None if flux is None else float(flux)


def _existing_run_inputs(sim_run_glob: str) -> list[RunInputs]:
    intersteps = _intersteps_root()
    step3_dirs = sorted((intersteps / "STEP_3_TO_4").glob(sim_run_glob))
    runs: list[RunInputs] = []
    for step3_dir in step3_dirs:
        step3_manifest = step3_dir / "step_3_chunks.chunks.json"
        if not step3_manifest.exists():
            continue
        step3_meta = _load_manifest(step3_manifest).get("metadata", {})
        effs = tuple(float(x) for x in step3_meta.get("config", {}).get("efficiencies", []))
        if len(effs) != 4:
            continue
        step3_run = step3_dir.name
        tokens = step3_run.split("_")
        if len(tokens) < 5:
            continue
        step2_run = "SIM_RUN_" + "_".join(tokens[2:4])
        step9_run = step3_run + "_001_001_001_001_001_001"
        step2_manifest = intersteps / "STEP_2_TO_3" / step2_run / "step_2_chunks.chunks.json"
        step9_manifest = intersteps / "STEP_9_TO_10" / step9_run / "step_9_chunks.chunks.json"
        if not step2_manifest.exists() or not step9_manifest.exists():
            continue
        runs.append(
            RunInputs(
                step3_run=step3_run,
                step2_manifest=step2_manifest,
                step3_manifest=step3_manifest,
                step9_manifest=step9_manifest,
                configured_efficiencies=effs,
                flux_cm2_min=_extract_flux_from_step3_metadata(step3_manifest),
            )
        )
    return runs


def _conditional_avalanche_counts(df2: pd.DataFrame, df3: pd.DataFrame) -> tuple[int, np.ndarray]:
    tt2 = _normalize_tt_values(df2["tt_crossing"])
    if len(df2) == len(df3) and np.array_equal(df2["event_id"].to_numpy(), df3["event_id"].to_numpy()):
        cross1234_mask = tt2 == "1234"
        cross1234_count = int(cross1234_mask.sum())
        avalanche_counts = np.zeros(4, dtype=np.int64)
        if cross1234_count > 0:
            for plane in range(1, 5):
                avalanche_counts[plane - 1] = int(
                    pd.to_numeric(df3.loc[cross1234_mask, f"avalanche_exists_{plane}"], errors="coerce")
                    .fillna(0)
                    .astype(int)
                    .sum()
                )
        return cross1234_count, avalanche_counts

    left = df2[["event_id", "tt_crossing"]].copy()
    right = df3[
        ["event_id", "avalanche_exists_1", "avalanche_exists_2", "avalanche_exists_3", "avalanche_exists_4"]
    ].copy()
    merged = left.merge(right, on="event_id", how="inner", sort=False)
    cross1234_mask = _normalize_tt_values(merged["tt_crossing"]) == "1234"
    cross1234_count = int(cross1234_mask.sum())
    avalanche_counts = np.zeros(4, dtype=np.int64)
    if cross1234_count > 0:
        for plane in range(1, 5):
            avalanche_counts[plane - 1] = int(
                pd.to_numeric(merged.loc[cross1234_mask, f"avalanche_exists_{plane}"], errors="coerce")
                .fillna(0)
                .astype(int)
                .sum()
            )
    return cross1234_count, avalanche_counts


def _compute_run_rows(run: RunInputs) -> list[dict]:
    step2_counts: Counter[str] = Counter()
    step3_counts: Counter[str] = Counter()
    step9_counts: Counter[str] = Counter()
    cross1234_count = 0
    avalanche_counts = np.zeros(4, dtype=np.int64)

    step2_chunks = _iter_chunk_paths(run.step2_manifest)
    step3_chunks = _iter_chunk_paths(run.step3_manifest)
    step9_chunks = _iter_chunk_paths(run.step9_manifest)

    if len(step2_chunks) != len(step3_chunks):
        raise RuntimeError(
            f"Mismatched STEP 2 / STEP 3 chunk counts for {run.step3_run}: {len(step2_chunks)} vs {len(step3_chunks)}"
        )

    for step2_chunk, step3_chunk in zip(step2_chunks, step3_chunks):
        df2 = pd.read_pickle(step2_chunk)
        df3 = pd.read_pickle(step3_chunk)

        tt2 = _normalize_tt_values(df2["tt_crossing"])
        tt3 = _normalize_tt_values(df3["tt_avalanche"])
        step2_counts.update(_tt_counts(tt2))
        step3_counts.update(_tt_counts(tt3))

        chunk_cross1234, chunk_avalanche_counts = _conditional_avalanche_counts(df2, df3)
        cross1234_count += chunk_cross1234
        avalanche_counts += chunk_avalanche_counts

    for step9_chunk in step9_chunks:
        df9 = pd.read_pickle(step9_chunk)
        tt9 = _normalize_tt_values(df9["tt_trigger"])
        step9_counts.update(_tt_counts(tt9))

    rows: list[dict] = []
    for plane in range(1, 5):
        rows.append(
            {
                "step3_run": run.step3_run,
                "plane": plane,
                "flux_cm2_min": run.flux_cm2_min,
                "configured_eff": run.configured_efficiencies[plane - 1],
                "step2_geometry_proxy": _plane_proxy(step2_counts, plane),
                "step3_cond_avalanche_on_cross1234": (
                    float("nan") if cross1234_count <= 0 else float(avalanche_counts[plane - 1]) / float(cross1234_count)
                ),
                "step3_proxy": _plane_proxy(step3_counts, plane),
                "step9_trigger_proxy": _plane_proxy(step9_counts, plane),
                "step2_1234_count": int(step2_counts.get("1234", 0)),
                "step3_1234_count": int(step3_counts.get("1234", 0)),
                "step9_1234_count": int(step9_counts.get("1234", 0)),
                "step2_missing_plane_count": int(step2_counts.get(PLANE_MISSING_TAG[plane], 0)),
                "step3_missing_plane_count": int(step3_counts.get(PLANE_MISSING_TAG[plane], 0)),
                "step9_missing_plane_count": int(step9_counts.get(PLANE_MISSING_TAG[plane], 0)),
            }
        )
    return rows


def _plot_overview(pdf: PdfPages, summary: dict) -> None:
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    lines = [
        "Efficiency Proxy Audit",
        "",
        f"Processed STEP_3 runs: {summary['processed_runs']}",
        f"Available STEP_3 directories: {summary['available_step3_dirs']}",
        f"High-eff threshold: {summary['high_eff_threshold']:.3f}",
        "",
        "Metrics:",
        "  STEP 2 geometry proxy = N1234_cross / (N1234_cross + N_missing_i_cross)",
        "  STEP 3 P(avalanche_i | cross1234) isolates plane response once all four planes are geometrically available",
        "  STEP 3 avalanche proxy = N1234_aval / (N1234_aval + N_missing_i_aval)",
        "  STEP 9 trigger proxy = N1234_trig / (N1234_trig + N_missing_i_trig)",
        "",
        "Interpretation:",
        "  If the ceiling appears already in STEP 2, it is geometric acceptance/systematic, not an avalanche bug.",
        "  If STEP 3 conditional avalanche tracks the configured efficiency but STEP 3 / STEP 9 proxies do not,",
        "  then the empirical proxy is mixing geometry/trigger selection with true plane efficiency.",
        "",
        "Note:",
        "  STEP 8 intermediates are not available in the current cleaned INTERSTEPS tree,",
        "  so this audit uses STEP 2, STEP 3, and STEP 9 only.",
    ]
    ax.text(0.03, 0.98, "\n".join(lines), ha="left", va="top", family="monospace", fontsize=10)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def _scatter_grid(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, axes = plt.subplots(4, len(STAGE_COLUMNS), figsize=(4.2 * len(STAGE_COLUMNS), 13), sharex=True)
    if len(STAGE_COLUMNS) == 1:
        axes = np.array([[axes]])
    for row_idx, plane in enumerate(range(1, 5)):
        plane_df = df[df["plane"] == plane].copy()
        plane_df = plane_df.sort_values("configured_eff")
        for col_idx, (column, title) in enumerate(STAGE_COLUMNS):
            ax = axes[row_idx, col_idx]
            x = plane_df["configured_eff"].to_numpy(dtype=float)
            y = plane_df[column].to_numpy(dtype=float)
            flux = plane_df["flux_cm2_min"].to_numpy(dtype=float)
            valid = np.isfinite(x) & np.isfinite(y)
            if not valid.any():
                ax.axis("off")
                continue
            sc = ax.scatter(
                x[valid],
                y[valid],
                c=flux[valid] if np.isfinite(flux[valid]).any() else None,
                cmap="viridis",
                s=26,
                alpha=0.85,
                edgecolors="none",
            )
            if column != "step2_geometry_proxy":
                lo = max(0.0, float(np.nanmin(np.r_[x[valid], y[valid]])) - 0.02)
                hi = min(1.02, float(np.nanmax(np.r_[x[valid], y[valid]])) + 0.02)
                ax.plot([lo, hi], [lo, hi], linestyle="--", linewidth=1.0, color="gray", alpha=0.7)
                ax.set_xlim(lo, hi)
                ax.set_ylim(lo, hi)
            else:
                ax.set_xlim(0.58, 1.02)
                ax.set_ylim(0.40, 1.02)
            if row_idx == 0:
                ax.set_title(title)
            if col_idx == 0:
                ax.set_ylabel(f"Plane {plane}")
            if row_idx == 3:
                ax.set_xlabel("Configured efficiency")
            ax.grid(alpha=0.20)
            corr = plane_df["configured_eff"].corr(plane_df[column])
            ax.text(
                0.03,
                0.96,
                f"r={corr:.3f}" if pd.notna(corr) else "r=nan",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
            )
            if row_idx == 0 and col_idx == len(STAGE_COLUMNS) - 1 and np.isfinite(flux[valid]).any():
                colorbar = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
                colorbar.set_label("flux_cm2_min")
    fig.suptitle("Configured efficiency vs stagewise proxy")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.97))
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def _high_eff_delta_plots(df: pd.DataFrame, pdf: PdfPages, high_eff_threshold: float) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True, sharey=True)
    stage_colors = {
        "step2_geometry_proxy": "tab:blue",
        "step3_cond_avalanche_on_cross1234": "tab:green",
        "step3_proxy": "tab:orange",
        "step9_trigger_proxy": "tab:red",
    }
    for plane, ax in zip(range(1, 5), axes.flatten()):
        plane_df = df[(df["plane"] == plane) & (df["configured_eff"] >= high_eff_threshold)].copy()
        plane_df = plane_df.sort_values("configured_eff")
        if plane_df.empty:
            ax.axis("off")
            continue
        x = plane_df["configured_eff"].to_numpy(dtype=float)
        for column, label in STAGE_COLUMNS:
            y = plane_df[column].to_numpy(dtype=float) - x
            ax.plot(
                x,
                y,
                marker="o",
                linewidth=1.4,
                markersize=4,
                color=stage_colors[column],
                label=label,
            )
        ax.axhline(0.0, linestyle="--", linewidth=1.0, color="gray", alpha=0.8)
        ax.set_title(f"Plane {plane}")
        ax.set_xlabel("Configured efficiency")
        ax.set_ylabel("proxy - configured")
        ax.grid(alpha=0.20)
        ax.legend(loc="lower left", fontsize=8)
    fig.suptitle(f"High-efficiency regime (configured_eff >= {high_eff_threshold:.2f})")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def _summary_json(df: pd.DataFrame, processed_runs: int, available_step3_dirs: int, high_eff_threshold: float) -> dict:
    summary: dict[str, object] = {
        "processed_runs": processed_runs,
        "available_step3_dirs": available_step3_dirs,
        "high_eff_threshold": high_eff_threshold,
        "planes": {},
    }
    for plane in range(1, 5):
        plane_df = df[df["plane"] == plane].copy()
        high_df = plane_df[plane_df["configured_eff"] >= high_eff_threshold].copy()
        plane_summary = {
            "run_count": int(len(plane_df)),
            "high_eff_run_count": int(len(high_df)),
        }
        for column, _ in STAGE_COLUMNS:
            corr = plane_df["configured_eff"].corr(plane_df[column])
            plane_summary[f"{column}_corr"] = None if pd.isna(corr) else float(corr)
            if len(high_df) > 0:
                delta = high_df[column] - high_df["configured_eff"]
                plane_summary[f"{column}_high_eff_median"] = float(np.nanmedian(high_df[column].to_numpy(dtype=float)))
                plane_summary[f"{column}_high_eff_delta_median"] = float(np.nanmedian(delta.to_numpy(dtype=float)))
            else:
                plane_summary[f"{column}_high_eff_median"] = None
                plane_summary[f"{column}_high_eff_delta_median"] = None
        summary["planes"][str(plane)] = plane_summary
    return summary


def _write_pdf(df: pd.DataFrame, pdf_path: Path, summary: dict) -> None:
    with PdfPages(pdf_path) as pdf:
        _plot_overview(pdf, summary)
        _scatter_grid(df, pdf)
        _high_eff_delta_plots(df, pdf, high_eff_threshold=float(summary["high_eff_threshold"]))


def parse_args() -> argparse.Namespace:
    default_output_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Audit configured efficiencies against stagewise digital-twin proxies.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory where the PDF/CSV/JSON outputs will be written.",
    )
    parser.add_argument(
        "--sim-run-glob",
        default="SIM_RUN_*",
        help="Glob used to select STEP_3_TO_4 SIM_RUN directories.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Optional cap on the number of processed STEP_3 runs.",
    )
    parser.add_argument(
        "--high-eff-threshold",
        type=float,
        default=0.95,
        help="Threshold used to define the high-efficiency regime in the summary pages.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    run_inputs = _existing_run_inputs(args.sim_run_glob)
    available_step3_dirs = len(sorted((_intersteps_root() / "STEP_3_TO_4").glob(args.sim_run_glob)))
    if args.max_runs is not None:
        run_inputs = run_inputs[: max(args.max_runs, 0)]
    if not run_inputs:
        raise SystemExit("No matching STEP_3 runs with existing STEP_2 and STEP_9 manifests were found.")

    all_rows: list[dict] = []
    for run in run_inputs:
        all_rows.extend(_compute_run_rows(run))

    summary_df = pd.DataFrame(all_rows)
    summary_df.sort_values(["plane", "configured_eff", "step3_run"], inplace=True)

    summary_json = _summary_json(
        summary_df,
        processed_runs=len(run_inputs),
        available_step3_dirs=available_step3_dirs,
        high_eff_threshold=float(args.high_eff_threshold),
    )

    csv_path = args.output_dir / "efficiency_proxy_stage_summary.csv"
    json_path = args.output_dir / "efficiency_proxy_stage_summary.json"
    pdf_path = args.output_dir / "efficiency_proxy_stage_audit.pdf"

    summary_df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(summary_json, indent=2))
    _write_pdf(summary_df, pdf_path, summary_json)

    print(f"[OK] processed STEP_3 runs: {len(run_inputs)}")
    print(f"[OK] wrote {csv_path}")
    print(f"[OK] wrote {json_path}")
    print(f"[OK] wrote {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
