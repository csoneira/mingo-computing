"""TOTAL_SUMMARY builder for QUALITY_ASSURANCE_NEW."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd

from .common import apply_date_filter, get_station_date_range, normalize_station_name, parse_filename_timestamp_series, read_csv_if_exists
from .status_plots import plot_column_status_grid, plot_step_score_grid, plot_top_failing_parameters
from .status_reports import build_parameter_status_summary

OVERWRITTEN_METADATA_RE = "*_overwritten_metadata_rows.csv"


def _atomic_to_csv(frame: pd.DataFrame, path: Path) -> None:
    """Publish a CSV with one filesystem replace, never a partial generation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_handle:
            temporary_path = Path(temporary_handle.name)
            frame.to_csv(temporary_handle, index=False)
            temporary_handle.flush()
            os.fsync(temporary_handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _output_files_dir(base_dir: Path) -> Path:
    path = base_dir / "OUTPUTS" / "FILES"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _output_plots_dir(base_dir: Path) -> Path:
    path = base_dir / "OUTPUTS" / "PLOTS"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_total_plots_dir(base_dir: Path) -> None:
    plots_dir = _output_plots_dir(base_dir)
    for path in plots_dir.iterdir():
        if path.is_file():
            path.unlink()


def _station_root(total_root: Path, station_name: str) -> Path:
    return total_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station_name


def _filter_total_frame(frame: pd.DataFrame, *, station_name: str, root_config: dict[str, Any]) -> pd.DataFrame:
    if frame.empty or "plot_timestamp" not in frame.columns:
        return frame

    filtered = frame.copy()
    filtered["plot_timestamp"] = pd.to_datetime(filtered["plot_timestamp"], errors="coerce")
    date_range = get_station_date_range(root_config, station_name)
    if date_range is None:
        return filtered

    filtered["__timestamp__"] = filtered["plot_timestamp"]
    filtered = filtered.loc[filtered["__timestamp__"].notna()].copy()
    if filtered.empty:
        return filtered.drop(columns="__timestamp__", errors="ignore")
    filtered = apply_date_filter(filtered, date_range)
    return filtered.drop(columns="__timestamp__", errors="ignore").reset_index(drop=True)


def _read_step_outputs(
    step_dir: Path,
    display_name: str,
    station_name: str,
    root_config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    files_dir = step_dir / "OUTPUTS" / station_name / "FILES"
    summary_df = read_csv_if_exists(files_dir / f"{station_name}_{display_name}_step_summary.csv")
    eval_df = read_csv_if_exists(files_dir / f"{station_name}_{display_name}_column_status.csv")
    summary_df = _filter_total_frame(summary_df, station_name=station_name, root_config=root_config)
    eval_df = _filter_total_frame(eval_df, station_name=station_name, root_config=root_config)
    return summary_df, eval_df


def _quality_key(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["step_name"].astype(str)
        + "::TASK_"
        + frame["task_id"].astype(int).astype(str)
        + "::"
        + frame["evaluation_column"].astype(str)
    )


def _long_to_wide_status(long_df: pd.DataFrame, *, index_columns: list[str], value_column: str) -> pd.DataFrame:
    if long_df.empty:
        return pd.DataFrame(columns=index_columns)
    wide_df = (
        long_df.pivot_table(
            index=index_columns,
            columns="qa_key",
            values=value_column,
            aggfunc="first",
        )
        .reset_index()
    )
    wide_df.columns.name = None
    return wide_df


def _build_reprocessing_quality_table(wide_df: pd.DataFrame) -> pd.DataFrame:
    index_columns = [column for column in ("station_name", "filename_base", "plot_timestamp") if column in wide_df.columns]
    quality_columns = [column for column in wide_df.columns if column not in set(index_columns)]
    if not {"station_name", "filename_base"} <= set(wide_df.columns):
        return pd.DataFrame(
            columns=[
                "station_name",
                "filename_base",
                "quality_status",
                "failed_quality_columns",
                "failed_quality_versions",
            ]
        )

    if not quality_columns:
        out = wide_df[[column for column in ("station_name", "filename_base") if column in wide_df.columns]].copy()
        if "plot_timestamp" in wide_df.columns:
            out["plot_timestamp"] = wide_df["plot_timestamp"]
        out["quality_status"] = "pass"
        out["failed_quality_columns"] = ""
        out["failed_quality_versions"] = ""
        return out

    working = wide_df.copy()
    quality_frame = working[quality_columns]

    def _failed_columns(row: pd.Series) -> str:
        failed = [column for column in quality_columns if str(row[column]).strip().lower() == "fail"]
        return ";".join(failed)

    out = working[[column for column in ("station_name", "filename_base") if column in working.columns]].copy()
    if "plot_timestamp" in working.columns:
        out["plot_timestamp"] = working["plot_timestamp"]
    out["failed_quality_columns"] = quality_frame.apply(_failed_columns, axis=1)
    out["failed_quality_versions"] = ""
    out["quality_status"] = out["failed_quality_columns"].map(lambda value: "pass" if not value else "fail")

    ordered_columns = [
        column
        for column in (
            "station_name",
            "filename_base",
            "plot_timestamp",
            "quality_status",
            "failed_quality_columns",
            "failed_quality_versions",
        )
        if column in out.columns
    ]
    return out[ordered_columns].copy()


def _version_marker(frame: pd.DataFrame) -> pd.Series:
    for column in ("execution_timestamp", "execution_date", "qa_timestamp", "plot_timestamp"):
        if column not in frame.columns:
            continue
        values = frame[column].astype("string").fillna("").str.strip()
        if values.ne("").any():
            return values
    return pd.Series("", index=frame.index, dtype="string")


def _apply_failed_quality_versions(reprocessing_df: pd.DataFrame, long_df: pd.DataFrame) -> pd.DataFrame:
    if reprocessing_df.empty or long_df.empty:
        return reprocessing_df
    required = {"station_name", "filename_base", "qa_key", "status"}
    if not required <= set(long_df.columns):
        return reprocessing_df

    working = long_df.copy()
    working["status"] = working["status"].astype("string").fillna("").str.strip().str.lower()
    working = working[working["status"] == "fail"].copy()
    if working.empty:
        out = reprocessing_df.copy()
        if "failed_quality_versions" not in out.columns:
            out["failed_quality_versions"] = ""
        else:
            out["failed_quality_versions"] = ""
        return out

    working["version_marker"] = _version_marker(working)
    working["failed_quality_version"] = working["qa_key"].astype(str) + "@" + working["version_marker"].astype(str)
    version_df = (
        working.groupby(["station_name", "filename_base"], dropna=False)["failed_quality_version"]
        .agg(lambda values: ";".join(sorted({str(value).strip() for value in values if str(value).strip()})))
        .reset_index()
        .rename(columns={"failed_quality_version": "failed_quality_versions"})
    )
    out = reprocessing_df.merge(version_df, on=["station_name", "filename_base"], how="left", suffixes=("", "_agg"))
    if "failed_quality_versions_agg" in out.columns:
        out["failed_quality_versions"] = out["failed_quality_versions_agg"].fillna(out.get("failed_quality_versions", ""))
        out = out.drop(columns=["failed_quality_versions_agg"])
    out["failed_quality_versions"] = out["failed_quality_versions"].astype("string").fillna("").astype(str)
    out.loc[out["quality_status"].astype(str).str.lower() == "pass", "failed_quality_versions"] = ""
    return out


def _collect_overwritten_metadata_reports(
    qa_root: Path,
    *,
    enabled_steps: list[dict[str, Any]],
    stations: list[str],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    station_set = set(stations)
    for step in enabled_steps:
        step_name = str(step["step_name"])
        step_dir = qa_root / "STEPS" / step_name
        for report_path in sorted(step_dir.glob(f"TASK_*/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/*/OUTPUTS/FILES/{OVERWRITTEN_METADATA_RE}")):
            task_part = next((part for part in report_path.parts if part.startswith("TASK_")), "")
            station_name = next((part for part in report_path.parts if part.startswith("MINGO")), "")
            if station_name not in station_set:
                continue
            report_df = read_csv_if_exists(report_path)
            if report_df.empty:
                continue
            try:
                task_id = int(task_part.removeprefix("TASK_"))
            except ValueError:
                task_id = pd.NA
            report_df = report_df.copy()
            report_df.insert(0, "step_name", step_name)
            report_df.insert(1, "step_display_name", str(step.get("display_name", step_name)))
            report_df.insert(2, "task_id", task_id)
            report_df.insert(3, "station_name", station_name)
            report_df.insert(4, "report_path", str(report_path))
            frames.append(report_df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_total_summary(
    qa_root: Path,
    *,
    root_config: dict[str, Any],
    pipeline_steps: list[dict[str, Any]],
    stations_override: list[str] | None = None,
    generate_plots: bool = True,
) -> int:
    """Build TOTAL_SUMMARY outputs from already-generated step/task outputs."""
    total_root = qa_root / "TOTAL_SUMMARY"
    total_root.mkdir(parents=True, exist_ok=True)

    stations = stations_override or [normalize_station_name(value) for value in root_config.get("stations", [])]
    enabled_steps = [step for step in pipeline_steps if bool(step.get("enabled", True))]
    step_order = [str(step["display_name"]) for step in enabled_steps]

    all_station_step_frames: list[pd.DataFrame] = []
    all_station_long_frames: list[pd.DataFrame] = []
    all_station_parameter_frames: list[pd.DataFrame] = []

    for station_name in stations:
        step_frames: list[pd.DataFrame] = []
        eval_frames: list[pd.DataFrame] = []
        for step in enabled_steps:
            step_dir = qa_root / "STEPS" / str(step["step_name"])
            summary_df, eval_df = _read_step_outputs(step_dir, str(step["display_name"]), station_name, root_config)
            if not summary_df.empty:
                step_frames.append(summary_df)
            if not eval_df.empty:
                eval_frames.append(eval_df)

        station_files_dir = _output_files_dir(_station_root(total_root, station_name))
        station_plots_dir = _output_plots_dir(_station_root(total_root, station_name)) if generate_plots else None
        _cleanup_total_plots_dir(_station_root(total_root, station_name))

        if step_frames:
            step_df = pd.concat(step_frames, ignore_index=True)
            step_df.insert(0, "station_name", station_name)
            step_df.to_csv(station_files_dir / f"{station_name}_total_step_summary.csv", index=False)
            all_station_step_frames.append(step_df)
        else:
            step_df = pd.DataFrame()

        if eval_frames:
            long_df = pd.concat(eval_frames, ignore_index=True)
            long_df.insert(0, "station_name", station_name)
            long_df["plot_timestamp"] = pd.to_datetime(long_df["plot_timestamp"], errors="coerce")
            long_df["qa_key"] = _quality_key(long_df)
            long_df.to_csv(station_files_dir / f"{station_name}_total_quality_long.csv", index=False)

            file_index = long_df[["station_name", "filename_base", "plot_timestamp"]].drop_duplicates(
                subset=["station_name", "filename_base"]
            )
            wide_df = _long_to_wide_status(
                long_df[["station_name", "filename_base", "qa_key", "status"]],
                index_columns=["station_name", "filename_base"],
                value_column="status",
            )
            wide_df = file_index.merge(wide_df, on=["station_name", "filename_base"], how="left")
            wide_df = wide_df.sort_values("plot_timestamp", na_position="last").reset_index(drop=True)
            wide_df.to_csv(station_files_dir / f"{station_name}_total_quality_wide.csv", index=False)

            parameter_summary_df = build_parameter_status_summary(
                long_df,
                group_by=["step_name", "task_id", "source_column"],
                timestamp_column="plot_timestamp",
            )
            if not parameter_summary_df.empty:
                parameter_summary_df.insert(0, "station_name", station_name)
                parameter_summary_df["parameter_label"] = (
                    parameter_summary_df["step_name"].astype(str)
                    + "::TASK_"
                    + parameter_summary_df["task_id"].astype(int).astype(str)
                    + "::"
                    + parameter_summary_df["source_column"].astype(str)
                )
                parameter_summary_df.to_csv(station_files_dir / f"{station_name}_total_parameter_summary.csv", index=False)
                all_station_parameter_frames.append(parameter_summary_df)

            if generate_plots and station_plots_dir is not None:
                plot_column_status_grid(
                    df=long_df,
                    x_column="plot_timestamp",
                    y_column="qa_key",
                    status_column="status",
                    out_path=station_plots_dir / f"{station_name}_total_quality_by_column.png",
                    title=f"{station_name} total quality by column",
                    max_rows_per_plot=120,
                )
            if generate_plots and station_plots_dir is not None and not parameter_summary_df.empty:
                plot_top_failing_parameters(
                    df=parameter_summary_df,
                    label_column="parameter_label",
                    fail_count_column="failed_file_count",
                    warn_count_column="warning_file_count",
                    out_path=station_plots_dir / f"{station_name}_total_top_quality_failures.png",
                    title=f"{station_name} top quality failures",
                    top_n=30,
                )
            all_station_long_frames.append(long_df)
        else:
            long_df = pd.DataFrame()

        if generate_plots and station_plots_dir is not None and not step_df.empty:
            used_step_order = [name for name in step_order if name in set(step_df["step_display_name"].astype(str))]
            plot_step_score_grid(
                df=step_df,
                x_column="plot_timestamp",
                y_column="step_display_name",
                score_column="qa_pass_fraction",
                y_order=used_step_order,
                out_path=station_plots_dir / f"{station_name}_total_step_scores.png",
                title=f"{station_name} total step scores",
            )

    global_files_dir = _output_files_dir(total_root)
    if all_station_step_frames:
        pd.concat(all_station_step_frames, ignore_index=True).to_csv(
            global_files_dir / "qa_all_stations_step_summary.csv",
            index=False,
        )
    if all_station_long_frames:
        global_long_df = pd.concat(all_station_long_frames, ignore_index=True)
        global_long_df.to_csv(global_files_dir / "qa_all_stations_quality_long.csv", index=False)
        global_wide_df = _long_to_wide_status(
            global_long_df[["station_name", "filename_base", "qa_key", "status"]],
            index_columns=["station_name", "filename_base"],
            value_column="status",
        )
        global_wide_df["plot_timestamp"] = parse_filename_timestamp_series(global_wide_df["filename_base"])
        global_wide_df = global_wide_df.sort_values(
            ["station_name", "plot_timestamp", "filename_base"],
            na_position="last",
        ).reset_index(drop=True)
        global_wide_df.to_csv(global_files_dir / "qa_all_stations_quality_wide.csv", index=False)
        reprocessing_df = _build_reprocessing_quality_table(global_wide_df)
        reprocessing_df = _apply_failed_quality_versions(reprocessing_df, global_long_df)
        _atomic_to_csv(
            reprocessing_df,
            global_files_dir / "qa_all_stations_reprocessing_quality.csv",
        )
    if all_station_parameter_frames:
        pd.concat(all_station_parameter_frames, ignore_index=True).to_csv(
            global_files_dir / "qa_all_stations_parameter_summary.csv",
            index=False,
        )
    overwritten_df = _collect_overwritten_metadata_reports(
        qa_root,
        enabled_steps=enabled_steps,
        stations=stations,
    )
    overwritten_path = global_files_dir / "qa_all_stations_overwritten_metadata_rows.csv"
    if overwritten_df.empty:
        if overwritten_path.exists():
            overwritten_path.unlink()
    else:
        overwritten_df.to_csv(overwritten_path, index=False)

    print(f"TOTAL_SUMMARY complete: stations={len(stations)}")
    return 0
