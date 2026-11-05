#!/usr/bin/env python3
"""Compare one study file against a small cos_n-varied MINGO00 reference group."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm

REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")

station_of_study = 2
MAX_REFERENCE_SIMULATION_FILES = 20

BASE = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS"
SIMULATION_PARAMS_FILE = REPO_ROOT / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv"
PLOT_OUTPUT_DIR = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/SIMULATION_TUNING/ANGULAR_DISTRIBUTION/PLOTS"
PLOT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
EXECUTION_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

EFF_COLS = [
    "P1_eff_robust_xyphi",
    "P2_eff_robust_xyphi",
    "P3_eff_robust_xyphi",
    "P4_eff_robust_xyphi",
]
Z_COLS = ["P1_z", "P2_z", "P3_z", "P4_z"]

FIT_TT_COL = "fit_tt"
THETA_COL = "theta"
PHI_COL = "phi"

THETA_PHI_FIT_TT_VALUE = 1234
THETA_PHI_BINS = 30
THETA_PHI_LOG_SCALE = False

ONE_D_HIST_DENSITY = True
ONE_D_HIST_BINS = 40
ONE_D_HIST_NCOLS = 3

RATIO_HIST_BINS = 20
RATIO_DENOMINATOR_FIT_TT = 1234
RATIO_NUMERATOR_FIT_TT_VALUES = [123, 124, 134, 234]


def station_root(station: int) -> Path:
    return BASE / f"MINGO{station:02d}" / "STAGE_1/EVENT_DATA/STEP_1"


def task4_metadata_file(station: int) -> Path:
    return station_root(station) / "TASK_4/METADATA/task_4_metadata_robust_efficiency.csv"


def task5_metadata_file(station: int) -> Path:
    return station_root(station) / "TASK_5/METADATA/task_5_metadata_specific.csv"


def completed_directory(station: int) -> Path:
    return station_root(station) / "TASK_5/INPUT_FILES/COMPLETED_DIRECTORY"


def canonical_z(value: object) -> int | float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        raise ValueError("NaN found in z position column")
    numeric = float(numeric)
    return int(numeric) if numeric.is_integer() else numeric


def add_z_tuple(dataframe: pd.DataFrame) -> pd.DataFrame:
    out = dataframe.copy()
    for column in Z_COLS:
        out[column] = out[column].map(canonical_z)
    out["z_tuple"] = list(out[Z_COLS].itertuples(index=False, name=None))
    return out


def load_simulation_lookup() -> pd.DataFrame:
    dataframe = pd.read_csv(SIMULATION_PARAMS_FILE, low_memory=False)
    dataframe["filename_base"] = dataframe["file_name"].astype(str).map(lambda value: Path(value).stem)
    dataframe["cos_n"] = pd.to_numeric(dataframe["cos_n"], errors="coerce")
    dataframe = dataframe.dropna(subset=["filename_base", "cos_n"]).copy()
    dataframe = dataframe.sort_values(["filename_base", "execution_time"]).drop_duplicates(
        subset=["filename_base"], keep="last"
    )
    return dataframe[["filename_base", "cos_n"]].reset_index(drop=True)


def read_station_table(station: int) -> pd.DataFrame:
    df_eff = pd.read_csv(task4_metadata_file(station), low_memory=False)
    df_z = pd.read_csv(task5_metadata_file(station), low_memory=False)

    df_eff["filename_base"] = df_eff["filename_base"].astype(str)
    df_z["filename_base"] = df_z["filename_base"].astype(str)
    df_z = add_z_tuple(df_z)

    merged = df_eff.merge(
        df_z[["filename_base", *Z_COLS, "z_tuple"]],
        on="filename_base",
        how="inner",
    )

    for column in EFF_COLS:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")

    return merged.dropna(subset=EFF_COLS).copy()


def completed_files(station: int) -> list[Path]:
    return sorted(path for path in completed_directory(station).iterdir() if path.is_file())


def keep_only_completed(dataframe: pd.DataFrame, files: list[Path]) -> pd.DataFrame:
    completed_names = [path.name for path in files]
    mask = dataframe["filename_base"].map(
        lambda filename_base: any(str(filename_base) in name for name in completed_names)
    )
    return dataframe.loc[mask].copy()


def find_completed_file(filename_base: str, files: list[Path]) -> Path:
    matches = [path for path in files if str(filename_base) in path.name]
    if len(matches) != 1:
        raise RuntimeError(
            f"Could not identify a unique completed file for filename_base={filename_base}. "
            f"Found {len(matches)} matches."
        )
    return matches[0]


def format_efficiencies(values: np.ndarray) -> str:
    return "[" + ", ".join(f"{float(value):.4f}" for value in values) + "]"


def select_reference_group(
    df_ref: pd.DataFrame,
    df_study: pd.DataFrame,
    *,
    max_reference_files: int,
) -> dict[str, object]:
    best: dict[str, object] | None = None

    for _, study_row in df_study.iterrows():
        same_z = df_ref[df_ref["z_tuple"].map(lambda value: value == study_row["z_tuple"])].copy()
        if same_z.empty:
            continue

        study_eff = study_row[EFF_COLS].to_numpy(dtype=float)
        ref_eff = same_z[EFF_COLS].to_numpy(dtype=float)
        same_z["distance_to_study"] = np.linalg.norm(ref_eff - study_eff, axis=1)
        same_z["cos_n"] = pd.to_numeric(same_z["cos_n"], errors="coerce")
        same_z = same_z.loc[np.isfinite(same_z["cos_n"]) & np.isfinite(same_z["distance_to_study"])].copy()
        if same_z.empty:
            continue

        same_z = same_z.sort_values(["distance_to_study", "filename_base"]).drop_duplicates(
            subset=["cos_n"], keep="first"
        )
        selected_refs = same_z.nsmallest(int(max_reference_files), "distance_to_study").copy()
        if selected_refs.empty:
            continue

        total_distance = float(selected_refs["distance_to_study"].sum())
        max_distance = float(selected_refs["distance_to_study"].max())
        score = (
            int(len(selected_refs)),
            -total_distance,
            -max_distance,
        )

        if best is None or score > best["score"]:
            best = {
                "score": score,
                "z_tuple": study_row["z_tuple"],
                "study_filename_base": str(study_row["filename_base"]),
                "study_efficiencies": study_eff,
                "study_row": study_row.copy(),
                "references": selected_refs.sort_values("distance_to_study").reset_index(drop=True),
                "distance_sum": total_distance,
                "distance_max": max_distance,
                "distance_mean": float(selected_refs["distance_to_study"].mean()),
            }

    if best is None:
        raise RuntimeError("Could not build a reference group with distinct cos_n values.")

    return best


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file extension for {path}")


def select_fit_tt(dataframe: pd.DataFrame, fit_tt_value: int) -> pd.DataFrame:
    mask = pd.to_numeric(dataframe[FIT_TT_COL], errors="coerce") == int(fit_tt_value)
    return dataframe.loc[mask].copy()


def finite_column(dataframe: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(dataframe[column], errors="coerce")
    return values[np.isfinite(values)]


def finite_xy(dataframe: pd.DataFrame, x_col: str, y_col: str) -> pd.DataFrame:
    out = dataframe[[x_col, y_col]].copy()
    out[x_col] = pd.to_numeric(out[x_col], errors="coerce")
    out[y_col] = pd.to_numeric(out[y_col], errors="coerce")
    return out.loc[np.isfinite(out[x_col]) & np.isfinite(out[y_col])].copy()


def common_edges_many(series_list: list[pd.Series], bins: int) -> np.ndarray:
    values = pd.concat(series_list, ignore_index=True).to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise RuntimeError("Could not build histogram edges from empty data.")
    return np.linspace(float(np.nanmin(values)), float(np.nanmax(values)), int(bins) + 1)


def build_datasets(
    selection: dict[str, object],
    files_ref: list[Path],
    files_study: list[Path],
) -> tuple[list[dict[str, object]], Path]:
    study_file = find_completed_file(str(selection["study_filename_base"]), files_study)
    datasets: list[dict[str, object]] = [
        {
            "kind": "study",
            "station": station_of_study,
            "label": f"MINGO{station_of_study:02d} data",
            "legend_label": f"MINGO{station_of_study:02d} data",
            "panel_title": f"MINGO{station_of_study:02d} data",
            "filename_base": str(selection["study_filename_base"]),
            "file": study_file,
            "efficiencies": np.asarray(selection["study_efficiencies"], dtype=float),
            "cos_n": np.nan,
            "distance_to_study": 0.0,
            "events": read_table(study_file),
            "color": "black",
        }
    ]

    ref_colors = plt.get_cmap("tab10")(np.linspace(0.0, 1.0, max(len(selection["references"]), 1)))
    for color, (_, ref_row) in zip(ref_colors, selection["references"].iterrows()):
        ref_file = find_completed_file(str(ref_row["filename_base"]), files_ref)
        datasets.append(
            {
                "kind": "reference",
                "station": 0,
                "label": f"cos_n={float(ref_row['cos_n']):.6g}",
                "legend_label": (
                    f"MINGO00 cos_n={float(ref_row['cos_n']):.6g} | "
                    f"d_eff={float(ref_row['distance_to_study']):.5g}"
                ),
                "panel_title": (
                    f"MINGO00 cos_n={float(ref_row['cos_n']):.6g}\n"
                    f"d_eff={float(ref_row['distance_to_study']):.5g}"
                ),
                "filename_base": str(ref_row["filename_base"]),
                "file": ref_file,
                "efficiencies": ref_row[EFF_COLS].to_numpy(dtype=float),
                "cos_n": float(ref_row["cos_n"]),
                "distance_to_study": float(ref_row["distance_to_study"]),
                "events": read_table(ref_file),
                "color": color,
            }
        )

    return datasets, study_file


def selection_summary_text(selection: dict[str, object]) -> str:
    cos_n_text = ", ".join(
        f"{float(row['cos_n']):.6g}" for _, row in selection["references"].iterrows()
    )
    return (
        f"Study: MINGO{station_of_study:02d} {selection['study_filename_base']}"
        f" | z={selection['z_tuple']}"
        f" | study eff={format_efficiencies(np.asarray(selection['study_efficiencies'], dtype=float))}\n"
        f"Selected MINGO00 refs ({len(selection['references'])} distinct cos_n): [{cos_n_text}]"
        f" | mean d_eff={float(selection['distance_mean']):.5g}"
        f" | max d_eff={float(selection['distance_max']):.5g}"
    )


def plot_theta_phi_histograms(
    datasets: list[dict[str, object]],
    selection: dict[str, object],
    *,
    x_col: str,
    y_col: str,
    fit_tt_value: int,
    bins: int,
    log_scale: bool,
) -> Path:
    selected_xy = []
    for dataset in datasets:
        selected_xy.append(finite_xy(select_fit_tt(dataset["events"], fit_tt_value), x_col, y_col))

    x_edges = common_edges_many([frame[x_col] for frame in selected_xy], bins)
    y_edges = common_edges_many([frame[y_col] for frame in selected_xy], bins)

    histograms = [
        np.histogram2d(frame[x_col], frame[y_col], bins=[x_edges, y_edges])[0]
        for frame in selected_xy
    ]
    max_count = max(float(hist.max()) for hist in histograms) if histograms else 0.0
    norm = LogNorm(vmin=1, vmax=max_count) if log_scale and max_count >= 1.0 else None

    nplots = len(datasets)
    ncols = min(3, nplots)
    nrows = math.ceil(nplots / ncols)
    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(5.1 * ncols, 4.1 * nrows),
        constrained_layout=True,
        sharex=True,
        sharey=True,
    )
    axes = np.atleast_1d(axes).ravel()

    last_image = None
    for ax, dataset, frame in zip(axes, datasets, selected_xy):
        hist_output = ax.hist2d(
            frame[x_col],
            frame[y_col],
            bins=[x_edges, y_edges],
            norm=norm,
        )
        last_image = hist_output[3]
        ax.set_title(
            f"{dataset['panel_title']}\n{Path(dataset['file']).name}\nfit_tt == {fit_tt_value}, N={len(frame)}",
            fontsize=8,
        )
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)

    for ax in axes[nplots:]:
        ax.axis("off")

    if last_image is not None:
        colorbar = fig.colorbar(last_image, ax=axes[:nplots], shrink=0.92)
        colorbar.set_label("Counts per bin")

    fig.suptitle(
        f"{x_col} vs {y_col} | fit_tt == {fit_tt_value}\n{selection_summary_text(selection)}",
        fontsize=11,
    )

    output_path = (
        PLOT_OUTPUT_DIR
        / f"{EXECUTION_STAMP}__{x_col}_vs_{y_col}_fit_tt_{fit_tt_value}__study_{selection['study_filename_base']}__refs_{len(datasets)-1}.png"
    )
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_1d_histograms_by_fit_tt(
    datasets: list[dict[str, object]],
    selection: dict[str, object],
    *,
    variable_col: str,
    bins: int,
    density: bool,
    ncols: int,
) -> Path:
    fit_tt_values: set[int] = set()
    all_series: list[pd.Series] = []
    for dataset in datasets:
        fit_values = pd.to_numeric(dataset["events"][FIT_TT_COL], errors="coerce").dropna().astype(int)
        fit_tt_values.update(fit_values.tolist())
        all_series.append(finite_column(dataset["events"], variable_col))

    if not fit_tt_values:
        raise RuntimeError(f"No valid {FIT_TT_COL} values were found.")

    hist_edges = common_edges_many(all_series, bins)
    fit_tt_values_sorted = sorted(fit_tt_values)
    nplots = len(fit_tt_values_sorted)
    nrows = math.ceil(nplots / ncols)

    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(5.1 * ncols, 3.9 * nrows),
        constrained_layout=True,
        sharex=True,
    )
    axes = np.atleast_1d(axes).ravel()

    for ax, fit_tt_value in zip(axes, fit_tt_values_sorted):
        for dataset in datasets:
            values = finite_column(select_fit_tt(dataset["events"], fit_tt_value), variable_col)
            ax.hist(
                values,
                bins=hist_edges,
                histtype="step",
                linewidth=1.6 if dataset["kind"] == "study" else 1.2,
                density=density,
                color=dataset["color"],
                label=f"{dataset['legend_label']} | N={len(values)}",
            )
        ax.set_title(f"{variable_col}, fit_tt == {fit_tt_value}", fontsize=8)
        ax.set_xlabel(variable_col)
        ax.set_ylabel("Density" if density else "Counts")
        ax.grid(alpha=0.25)

    for ax in axes[nplots:]:
        ax.axis("off")

    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper right", fontsize=7)

    fig.suptitle(
        f"{variable_col} distributions by fit_tt\n{selection_summary_text(selection)}",
        fontsize=11,
    )

    output_path = (
        PLOT_OUTPUT_DIR
        / f"{EXECUTION_STAMP}__{variable_col}_histograms_by_fit_tt__study_{selection['study_filename_base']}__refs_{len(datasets)-1}.png"
    )
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def histogram_counts_for_fit_tt(
    dataframe: pd.DataFrame,
    variable_col: str,
    fit_tt_value: int,
    bin_edges: np.ndarray,
) -> tuple[np.ndarray, int]:
    values = finite_column(select_fit_tt(dataframe, fit_tt_value), variable_col)
    counts, _ = np.histogram(values, bins=bin_edges)
    return counts.astype(float), int(len(values))


def ratio_with_nan(numerator_counts: np.ndarray, denominator_counts: np.ndarray) -> np.ndarray:
    ratio = np.full_like(numerator_counts, np.nan, dtype=float)
    np.divide(numerator_counts, denominator_counts, out=ratio, where=denominator_counts > 0)
    return ratio


def plot_fit_tt_ratio_histograms(
    datasets: list[dict[str, object]],
    selection: dict[str, object],
    *,
    variable_col: str,
    numerator_fit_tt_values: list[int],
    denominator_fit_tt_value: int,
    bins: int,
) -> Path:
    all_values = [finite_column(dataset["events"], variable_col) for dataset in datasets]
    bin_edges = common_edges_many(all_values, bins)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

    nplots = len(numerator_fit_tt_values)
    ncols = 2
    nrows = math.ceil(nplots / ncols)
    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(6.2 * ncols, 4.5 * nrows),
        constrained_layout=True,
        sharex=True,
        sharey=True,
    )
    axes = np.atleast_1d(axes).ravel()

    for ax, numerator_fit_tt in zip(axes, numerator_fit_tt_values):
        for dataset in datasets:
            numerator_counts, numerator_n = histogram_counts_for_fit_tt(
                dataset["events"],
                variable_col,
                numerator_fit_tt,
                bin_edges,
            )
            denominator_counts, denominator_n = histogram_counts_for_fit_tt(
                dataset["events"],
                variable_col,
                denominator_fit_tt_value,
                bin_edges,
            )
            ratio = ratio_with_nan(numerator_counts, denominator_counts)
            ax.plot(
                bin_centers,
                ratio,
                marker="o",
                linestyle="-",
                markersize=3.2,
                linewidth=1.2 if dataset["kind"] == "study" else 1.0,
                color=dataset["color"],
                label=(
                    f"{dataset['legend_label']} | "
                    f"N{numerator_fit_tt}={numerator_n}, N{denominator_fit_tt_value}={denominator_n}"
                ),
            )

        ax.axhline(1.0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
        ax.set_ylim(0.0, 2.0)
        ax.set_title(
            f"{variable_col}: fit_tt {numerator_fit_tt} / {denominator_fit_tt_value}",
            fontsize=8,
        )
        ax.set_xlabel(variable_col)
        ax.set_ylabel(f"Counts({numerator_fit_tt}) / Counts({denominator_fit_tt_value})")
        ax.grid(alpha=0.25)

    for ax in axes[nplots:]:
        ax.axis("off")

    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper right", fontsize=7)

    fig.suptitle(
        f"{variable_col} fit_tt count ratios\n{selection_summary_text(selection)}",
        fontsize=11,
    )

    output_path = (
        PLOT_OUTPUT_DIR
        / f"{EXECUTION_STAMP}__{variable_col}_fit_tt_count_ratios__study_{selection['study_filename_base']}__refs_{len(datasets)-1}.png"
    )
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main() -> None:
    df_ref = read_station_table(0)
    df_study = read_station_table(station_of_study)
    simulation_lookup = load_simulation_lookup()
    df_ref = df_ref.merge(simulation_lookup, on="filename_base", how="inner")

    files_ref = completed_files(0)
    files_study = completed_files(station_of_study)
    df_ref = keep_only_completed(df_ref, files_ref)
    df_study = keep_only_completed(df_study, files_study)

    print("MINGO00 rows after merge, cos_n join and completed-file filter:", len(df_ref))
    print(f"MINGO{station_of_study:02d} rows after merge and completed-file filter:", len(df_study))

    ref_z = set(df_ref["z_tuple"])
    study_z = set(df_study["z_tuple"])
    common_z = ref_z & study_z
    print("MINGO00 unique z tuples:", len(ref_z), ref_z)
    print(f"MINGO{station_of_study:02d} unique z tuples:", len(study_z), study_z)
    print("Common z tuples:", len(common_z))

    if not common_z:
        raise RuntimeError("No common z tuple found after numeric canonicalization.")

    selection = select_reference_group(
        df_ref,
        df_study,
        max_reference_files=MAX_REFERENCE_SIMULATION_FILES,
    )
    datasets, study_file = build_datasets(selection, files_ref, files_study)

    print()
    print("Selected study file")
    print("-------------------")
    print(f"z tuple: {selection['z_tuple']}")
    print(f"MINGO{station_of_study:02d} filename_base: {selection['study_filename_base']}")
    print(f"MINGO{station_of_study:02d} file: {study_file}")
    print(f"MINGO{station_of_study:02d} efficiencies: {format_efficiencies(np.asarray(selection['study_efficiencies'], dtype=float))}")
    print()
    print(f"Selected MINGO00 simulation references (distinct cos_n, max {MAX_REFERENCE_SIMULATION_FILES})")
    print("-----------------------------------------------------------------------")
    for idx, (_, ref_row) in enumerate(selection["references"].iterrows(), start=1):
        ref_file = find_completed_file(str(ref_row["filename_base"]), files_ref)
        print(
            f"{idx}. cos_n={float(ref_row['cos_n']):.8g} | "
            f"d_eff={float(ref_row['distance_to_study']):.8g} | "
            f"filename_base={ref_row['filename_base']} | file={ref_file}"
        )
        print(f"   efficiencies: {format_efficiencies(ref_row[EFF_COLS].to_numpy(dtype=float))}")

    print()
    for dataset in datasets:
        print(f"Loaded {dataset['legend_label']}: {len(dataset['events'])} events from {Path(dataset['file']).name}")

    theta_phi_path = plot_theta_phi_histograms(
        datasets,
        selection,
        x_col=PHI_COL,
        y_col=THETA_COL,
        fit_tt_value=THETA_PHI_FIT_TT_VALUE,
        bins=THETA_PHI_BINS,
        log_scale=THETA_PHI_LOG_SCALE,
    )
    theta_hist_path = plot_1d_histograms_by_fit_tt(
        datasets,
        selection,
        variable_col=THETA_COL,
        bins=ONE_D_HIST_BINS,
        density=ONE_D_HIST_DENSITY,
        ncols=ONE_D_HIST_NCOLS,
    )
    phi_hist_path = plot_1d_histograms_by_fit_tt(
        datasets,
        selection,
        variable_col=PHI_COL,
        bins=ONE_D_HIST_BINS,
        density=ONE_D_HIST_DENSITY,
        ncols=ONE_D_HIST_NCOLS,
    )
    theta_ratio_path = plot_fit_tt_ratio_histograms(
        datasets,
        selection,
        variable_col=THETA_COL,
        numerator_fit_tt_values=RATIO_NUMERATOR_FIT_TT_VALUES,
        denominator_fit_tt_value=RATIO_DENOMINATOR_FIT_TT,
        bins=RATIO_HIST_BINS,
    )
    phi_ratio_path = plot_fit_tt_ratio_histograms(
        datasets,
        selection,
        variable_col=PHI_COL,
        numerator_fit_tt_values=RATIO_NUMERATOR_FIT_TT_VALUES,
        denominator_fit_tt_value=RATIO_DENOMINATOR_FIT_TT,
        bins=RATIO_HIST_BINS,
    )

    print()
    print(f"Saved theta-vs-phi comparison plot: {theta_phi_path}")
    print(f"Saved theta-by-fit_tt plot: {theta_hist_path}")
    print(f"Saved phi-by-fit_tt plot: {phi_hist_path}")
    print(f"Saved theta fit_tt ratio plot: {theta_ratio_path}")
    print(f"Saved phi fit_tt ratio plot: {phi_ratio_path}")


if __name__ == "__main__":
    main()
