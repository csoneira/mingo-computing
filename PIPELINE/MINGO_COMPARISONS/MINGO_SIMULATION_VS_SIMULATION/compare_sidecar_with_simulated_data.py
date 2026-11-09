#!/usr/bin/env python3
"""
Compare STEP_FINAL sidecar angular ground truth with Task-5 fitted angles.

The script selects one postprocessed parquet file from the Stage-1 products
parquet lake, finds the matching STEP_FINAL sidecar parquet, joins both tables
on event_id, and writes angular reconstruction diagnostics under PLOTS next to
this script.

Intended installed path:
    PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/compare_sidecar_with_simulated_data.py

Default output path:
    PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/PLOTS
"""

from __future__ import annotations

import argparse
import ast
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

try:
    import yaml
except ImportError:  # pragma: no cover - handled at runtime with a clear message.
    yaml = None

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.collections import PatchCollection
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
DEFAULT_STEP12_DIR = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE"
DEFAULT_SIDECAR_DIR = REPO_ROOT / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/FILES_SIDECARS"
DEFAULT_SIM_PARAMS_CSV = REPO_ROOT / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv"
DEFAULT_STEP2_REGION_CONFIG = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_2/EVENT_DATA/STEP_1_ACCUMULATION/config_step_1_accumulation.yaml"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "PLOTS"

PIPELINE_PREFIXES = (
    "postprocessed_",
    "fitted_",
    "listed_",
    "corrected_",
    "calibrated_",
    "cleaned_",
    "raw_",
    "accumulated_",
    "sidecar_",
)

TT_COLUMN = "tt_task5_post"
EVENT_ID_COLUMN = "event_id"
THETA_TRUTH_CANDIDATES = ("Theta_gen", "theta_gen", "generated_theta", "theta_generated")
PHI_TRUTH_CANDIDATES = ("Phi_gen", "phi_gen", "generated_phi", "phi_generated")
THETA_FIT_CANDIDATES = ("event_theta", "theta", "theta_fit", "Theta_fit", "fit_theta")
PHI_FIT_CANDIDATES = ("event_phi", "phi", "phi_fit", "Phi_fit", "fit_phi")


@dataclass(frozen=True)
class SimulationMetadata:
    file_name: str | None
    param_hash: str | None
    param_set_id: object | None
    efficiencies: tuple[float, float, float, float] | None

    @property
    def efficiency_title(self) -> str:
        if self.efficiencies is None:
            return "efficiencies unavailable"
        e1, e2, e3, e4 = self.efficiencies
        return f"eff: P1={e1:.3f}, P2={e2:.3f}, P3={e3:.3f}, P4={e4:.3f}"

    @property
    def compact_label(self) -> str:
        parts: list[str] = []
        if self.param_set_id is not None and not pd.isna(self.param_set_id):
            parts.append(f"param_set_id={self.param_set_id}")
        if self.param_hash:
            parts.append(f"param_hash={self.param_hash[:10]}…")
        parts.append(self.efficiency_title)
        return " | ".join(parts)


@dataclass(frozen=True)
class AngularRegionConfig:
    theta_boundaries: tuple[float, ...]
    region_layout: tuple[int, ...]
    region_ring_names: tuple[str, ...]

    @property
    def n_regions(self) -> int:
        return int(sum(self.region_layout))

    @property
    def compact_label(self) -> str:
        return (
            f"theta_boundaries={list(self.theta_boundaries)} | "
            f"region_layout={list(self.region_layout)} | "
            f"region_ring_names={list(self.region_ring_names)}"
        )


@dataclass(frozen=True)
class AngleColumns:
    theta_truth: str
    phi_truth: str
    theta_fit: str
    phi_fit: str


@dataclass(frozen=True)
class GridSpec:
    rows: int
    cols: int

    @property
    def capacity(self) -> int:
        return self.rows * self.cols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Join one Stage-1 products parquet with its STEP_FINAL sidecar "
            "and plot generated-vs-fitted angular diagnostics by tt_task5_post."
        )
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help="Specific Stage-1 products parquet file. If omitted, the newest parquet is used.",
    )
    parser.add_argument(
        "--step12-dir",
        type=Path,
        default=DEFAULT_STEP12_DIR,
        help="Directory containing Task-5 postprocessed parquet files.",
    )
    parser.add_argument(
        "--sidecar-dir",
        type=Path,
        default=DEFAULT_SIDECAR_DIR,
        help="Directory containing sidecar_mi00*.parquet files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory. Defaults to PLOTS next to this script.",
    )
    parser.add_argument(
        "--simulation-params-csv",
        type=Path,
        default=DEFAULT_SIM_PARAMS_CSV,
        help=(
            "CSV written by STEP_FINAL with param_hash, file_name, and efficiencies. "
            "Used to annotate figure titles with the four plane efficiencies."
        ),
    )
    parser.add_argument(
        "--angular-region-config",
        type=Path,
        default=DEFAULT_STEP2_REGION_CONFIG,
        help=(
            "STEP_2 YAML configuration containing theta_boundaries, region_layout, "
            "and region_ring_names. Used only for the additional angular-region "
            "migration diagnostic."
        ),
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=200_000,
        help="Maximum points drawn per figure or grid cell. Statistics use all matched rows.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=12345,
        help="Deterministic random state for plotting downsampling.",
    )
    parser.add_argument(
        "--grid-rows",
        type=int,
        default=3,
        help="Rows used for tt_task5_post grid figures.",
    )
    parser.add_argument(
        "--grid-cols",
        type=int,
        default=4,
        help="Columns used for tt_task5_post grid figures.",
    )
    parser.add_argument(
        "--pdf-dpi",
        type=int,
        default=140,
        help="Rasterization resolution for dense artists saved in the diagnostics PDF.",
    )
    parser.add_argument(
        "--scatter-size",
        type=float,
        default=10.0,
        help="Marker area for residual-coloured angular scatter plots.",
    )
    parser.add_argument(
        "--scatter-alpha",
        type=float,
        default=0.45,
        help="Transparency for residual-coloured angular scatter points.",
    )
    parser.add_argument(
        "--theta-hist-bins",
        type=int,
        default=90,
        help="Number of bins for theta generated/fitted step histograms.",
    )
    parser.add_argument(
        "--phi-hist-bins",
        type=int,
        default=72,
        help="Number of bins for phi generated/fitted step histograms.",
    )
    parser.add_argument(
        "--theta-hist-min",
        type=float,
        default=0.0,
        help="Lower theta edge for generated/fitted histograms.",
    )
    parser.add_argument(
        "--theta-hist-max",
        type=float,
        default=90.0,
        help="Upper theta edge for generated/fitted histograms.",
    )
    parser.add_argument(
        "--phi-hist-min",
        type=float,
        default=-180.0,
        help="Lower phi edge for generated/fitted histograms.",
    )
    parser.add_argument(
        "--phi-hist-max",
        type=float,
        default=180.0,
        help="Upper phi edge for generated/fitted histograms.",
    )
    parser.add_argument(
        "--migration-theta-bins",
        type=int,
        default=9,
        help=(
            "Number of theta bins for angular migration matrices. "
            "Default is 9, corresponding to 10-degree bins over 0--90 deg."
        ),
    )
    parser.add_argument(
        "--migration-phi-bins",
        type=int,
        default=18,
        help=(
            "Number of phi bins for angular migration matrices. "
            "Default is 18, corresponding to 20-degree bins over -180--180 deg."
        ),
    )
    parser.add_argument(
        "--migration-theta-min",
        type=float,
        default=0.0,
        help="Lower theta edge in degrees for angular migration matrices.",
    )
    parser.add_argument(
        "--migration-theta-max",
        type=float,
        default=90.0,
        help="Upper theta edge in degrees for angular migration matrices.",
    )
    parser.add_argument(
        "--migration-phi-min",
        type=float,
        default=-180.0,
        help="Lower phi edge in degrees for angular migration matrices.",
    )
    parser.add_argument(
        "--migration-phi-max",
        type=float,
        default=180.0,
        help="Upper phi edge in degrees for angular migration matrices.",
    )
    parser.add_argument(
        "--write-merged",
        action="store_true",
        help="Also save the joined truth/reconstruction table used for plotting.",
    )
    return parser.parse_args()


def newest_parquet(directory: Path) -> Path:
    if not directory.exists():
        raise FileNotFoundError(f"Stage-1 products parquet lake does not exist: {directory}")
    candidates = sorted(
        (path for path in directory.glob("*.parquet") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No parquet files found in: {directory}")
    return candidates[0]


def strip_pipeline_prefixes(stem: str) -> str:
    current = stem
    changed = True
    while changed:
        changed = False
        for prefix in PIPELINE_PREFIXES:
            if current.startswith(prefix):
                current = current[len(prefix):]
                changed = True
                break
    return current


def infer_core_basename(path: Path) -> str:
    stem = strip_pipeline_prefixes(path.stem)
    match = re.search(r"(mi\d+)", stem)
    if match:
        return match.group(1)
    return stem


def find_sidecar(input_path: Path, sidecar_dir: Path) -> Path:
    core = infer_core_basename(input_path)
    exact = sidecar_dir / f"sidecar_{core}.parquet"
    if exact.exists():
        return exact

    matches = sorted(sidecar_dir.glob(f"sidecar_*{core}*.parquet"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError(
            "Ambiguous sidecar match for "
            f"{input_path.name}; candidates: {', '.join(str(path) for path in matches)}"
        )
    raise FileNotFoundError(f"No sidecar found for {input_path.name}. Expected {exact}")


def parse_efficiencies(value: object) -> tuple[float, float, float, float] | None:
    """Parse the STEP_FINAL efficiencies column, stored as a stringified Python/JSON list."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, np.ndarray)):
        parsed = list(value)
    else:
        if pd.isna(value):
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            parsed = [part.strip() for part in text.strip("[]").split(",") if part.strip()]

    if not isinstance(parsed, (list, tuple)) or len(parsed) != 4:
        return None
    try:
        return tuple(float(item) for item in parsed)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def sidecar_param_hash(sidecar_df: pd.DataFrame) -> str | None:
    if "param_hash" not in sidecar_df.columns:
        return None
    hashes = sidecar_df["param_hash"].dropna().astype(str).unique()
    if len(hashes) == 0:
        return None
    if len(hashes) > 1:
        print(
            "[WARN] Sidecar contains more than one param_hash; using the first unique value.",
            file=sys.stderr,
        )
    return str(hashes[0])


def load_simulation_metadata(
    *,
    params_csv: Path,
    core: str,
    sidecar_df: pd.DataFrame,
) -> SimulationMetadata:
    """Read STEP_FINAL registry CSV and recover the four plane efficiencies for this file."""
    sidecar_hash = sidecar_param_hash(sidecar_df)
    if not params_csv.exists():
        print(f"[WARN] STEP_FINAL simulation params CSV not found: {params_csv}", file=sys.stderr)
        return SimulationMetadata(
            file_name=f"{core}.dat",
            param_hash=sidecar_hash,
            param_set_id=None,
            efficiencies=None,
        )

    params = pd.read_csv(params_csv)
    if params.empty:
        print(f"[WARN] STEP_FINAL simulation params CSV is empty: {params_csv}", file=sys.stderr)
        return SimulationMetadata(
            file_name=f"{core}.dat",
            param_hash=sidecar_hash,
            param_set_id=None,
            efficiencies=None,
        )

    matches = pd.DataFrame()
    if sidecar_hash and "param_hash" in params.columns:
        matches = params.loc[params["param_hash"].astype(str) == sidecar_hash].copy()

    file_name = f"{core}.dat"
    if matches.empty and "file_name" in params.columns:
        matches = params.loc[params["file_name"].astype(str) == file_name].copy()
    if matches.empty and "sidecar_file_name" in params.columns:
        sidecar_file_name = f"sidecar_{core}.parquet"
        matches = params.loc[params["sidecar_file_name"].astype(str) == sidecar_file_name].copy()

    if matches.empty:
        print(
            "[WARN] No matching row found in STEP_FINAL simulation params CSV for "
            f"file_name={file_name} and param_hash={sidecar_hash}.",
            file=sys.stderr,
        )
        return SimulationMetadata(
            file_name=file_name,
            param_hash=sidecar_hash,
            param_set_id=None,
            efficiencies=None,
        )

    if len(matches) > 1:
        if "file_name" in matches.columns:
            file_matches = matches.loc[matches["file_name"].astype(str) == file_name]
            if not file_matches.empty:
                matches = file_matches
        if len(matches) > 1:
            print(
                "[WARN] Multiple STEP_FINAL simulation params rows match this file; using the first row.",
                file=sys.stderr,
            )

    row = matches.iloc[0]
    row_file_name = str(row["file_name"]) if "file_name" in row.index and not pd.isna(row["file_name"]) else file_name
    row_hash = str(row["param_hash"]) if "param_hash" in row.index and not pd.isna(row["param_hash"]) else sidecar_hash
    param_set_id = row["param_set_id"] if "param_set_id" in row.index else None
    efficiencies = parse_efficiencies(row["efficiencies"]) if "efficiencies" in row.index else None

    if efficiencies is None:
        print(
            f"[WARN] Could not parse four plane efficiencies for {row_file_name} from {params_csv}.",
            file=sys.stderr,
        )
    return SimulationMetadata(
        file_name=row_file_name,
        param_hash=row_hash,
        param_set_id=param_set_id,
        efficiencies=efficiencies,
    )


def title_with_metadata(core: str, description: str, metadata: SimulationMetadata | None) -> str:
    if metadata is None:
        return f"{core} | {description}"
    return f"{core} | {description}\n{metadata.compact_label}"


def first_present(columns: Iterable[str], candidates: Iterable[str], role: str) -> str:
    available = set(map(str, columns))
    for candidate in candidates:
        if candidate in available:
            return candidate
    raise KeyError(f"Missing required {role} column. Tried: {', '.join(candidates)}")


def resolve_angle_columns(step_df: pd.DataFrame, sidecar_df: pd.DataFrame) -> AngleColumns:
    return AngleColumns(
        theta_truth=first_present(sidecar_df.columns, THETA_TRUTH_CANDIDATES, "generated theta"),
        phi_truth=first_present(sidecar_df.columns, PHI_TRUTH_CANDIDATES, "generated phi"),
        theta_fit=first_present(step_df.columns, THETA_FIT_CANDIDATES, "fitted theta"),
        phi_fit=first_present(step_df.columns, PHI_FIT_CANDIDATES, "fitted phi"),
    )


def coerce_event_id(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if EVENT_ID_COLUMN not in df.columns:
        raise KeyError(f"{source_name} does not contain '{EVENT_ID_COLUMN}'.")
    out = df.copy()
    out[EVENT_ID_COLUMN] = pd.to_numeric(out[EVENT_ID_COLUMN], errors="coerce")
    out = out.loc[out[EVENT_ID_COLUMN].notna()].copy()
    out[EVENT_ID_COLUMN] = out[EVENT_ID_COLUMN].astype(np.int64)
    duplicate_count = int(out[EVENT_ID_COLUMN].duplicated().sum())
    if duplicate_count:
        print(
            f"[WARN] {source_name}: dropping {duplicate_count} duplicate event_id row(s), "
            "keeping the last occurrence.",
            file=sys.stderr,
        )
        out = out.drop_duplicates(subset=[EVENT_ID_COLUMN], keep="last")
    return out


def likely_degrees(series: pd.Series, *, kind: str) -> bool:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if values.size == 0:
        return False
    q95 = float(np.nanquantile(np.abs(values), 0.95))
    if kind == "theta":
        return q95 > (math.pi + 0.25)
    if kind == "phi":
        return q95 > (2.0 * math.pi + 0.25)
    raise ValueError(f"Unknown angle kind: {kind}")


def to_degrees(series: pd.Series, *, kind: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").astype(float)
    if likely_degrees(numeric, kind=kind):
        return numeric
    return np.degrees(numeric)


def wrap_phi_deg(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").astype(float)
    return ((numeric + 180.0) % 360.0) - 180.0


def circular_delta_deg(fitted_deg: pd.Series, truth_deg: pd.Series) -> pd.Series:
    """Signed shortest phi residual in degrees, with the -180/180 boundary connected."""
    return ((fitted_deg - truth_deg + 180.0) % 360.0) - 180.0


def spherical_angular_separation_deg(
    theta_a_deg: pd.Series,
    phi_a_deg: pd.Series,
    theta_b_deg: pd.Series,
    phi_b_deg: pd.Series,
) -> pd.Series:
    """Angular separation between two directions parameterized by polar theta and azimuth phi."""
    ta = np.radians(pd.to_numeric(theta_a_deg, errors="coerce").astype(float).to_numpy())
    pa = np.radians(pd.to_numeric(phi_a_deg, errors="coerce").astype(float).to_numpy())
    tb = np.radians(pd.to_numeric(theta_b_deg, errors="coerce").astype(float).to_numpy())
    pb = np.radians(pd.to_numeric(phi_b_deg, errors="coerce").astype(float).to_numpy())

    dot = np.sin(ta) * np.sin(tb) * np.cos(pa - pb) + np.cos(ta) * np.cos(tb)
    dot = np.clip(dot, -1.0, 1.0)
    return pd.Series(np.degrees(np.arccos(dot)), index=theta_a_deg.index)


def normalize_tt_label(value: object) -> str:
    if pd.isna(value):
        return "nan"
    try:
        as_float = float(value)
        if np.isfinite(as_float) and as_float.is_integer():
            return str(int(as_float))
    except Exception:
        pass
    return str(value).strip().replace("/", "_").replace(" ", "_")


def sanitize_for_filename(label: object) -> str:
    text = normalize_tt_label(label)
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("_") or "unknown"


def tt_sort_key(value: object) -> tuple[int, int | str]:
    label = normalize_tt_label(value)
    try:
        return (0, int(label))
    except ValueError:
        return (1, label)


def finite_frame(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    out = df.loc[:, list(columns)].copy()
    for col in columns:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan).dropna()


def sample_for_plot(df: pd.DataFrame, max_points: int, random_state: int) -> pd.DataFrame:
    if max_points > 0 and len(df) > max_points:
        return df.sample(n=max_points, random_state=random_state)
    return df


def robust_limits_from_columns(
    df: pd.DataFrame,
    columns: Sequence[str],
    *,
    quantile_low: float = 0.005,
    quantile_high: float = 0.995,
    symmetric: bool = False,
    minimum_span: float = 1.0,
) -> tuple[float, float]:
    parts = []
    for col in columns:
        if col in df.columns:
            parts.append(pd.to_numeric(df[col], errors="coerce"))
    if not parts:
        return -minimum_span, minimum_span
    values = pd.concat(parts, ignore_index=True).replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return -minimum_span, minimum_span

    if symmetric:
        hi_abs = float(values.abs().quantile(quantile_high))
        if not np.isfinite(hi_abs) or hi_abs <= 0:
            hi_abs = float(values.abs().max())
        hi_abs = max(hi_abs, minimum_span)
        return -1.08 * hi_abs, 1.08 * hi_abs

    lo = float(values.quantile(quantile_low))
    hi = float(values.quantile(quantile_high))
    if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
        lo = float(values.min())
        hi = float(values.max())
    if lo == hi:
        pad = minimum_span if lo == 0 else max(abs(lo) * 0.05, minimum_span)
    else:
        pad = max(0.05 * (hi - lo), 0.05 * minimum_span)
    return lo - pad, hi + pad


def residual_color_limits(merged: pd.DataFrame) -> tuple[float, float]:
    residual = pd.to_numeric(merged["angular_residual_deg"], errors="coerce")
    residual = residual.replace([np.inf, -np.inf], np.nan).dropna()
    if residual.empty:
        return 0.0, 1.0
    vmax = float(residual.quantile(0.99))
    if not np.isfinite(vmax) or vmax <= 0.0:
        vmax = float(residual.max())
    if not np.isfinite(vmax) or vmax <= 0.0:
        vmax = 1.0
    return 0.0, vmax


def set_sparse_axis_labels(ax: plt.Axes, *, row: int, col: int, rows: int, xlabel: str, ylabel: str) -> None:
    if row == rows - 1:
        ax.set_xlabel(xlabel, fontsize=11)
    else:
        ax.set_xlabel("")
    if col == 0:
        ax.set_ylabel(ylabel, fontsize=11)
    else:
        ax.set_ylabel("")


def make_step_histograms_figure(
    merged: pd.DataFrame,
    *,
    core: str,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    theta_bins: int,
    phi_bins: int,
    theta_range: tuple[float, float],
    phi_range: tuple[float, float],
) -> Path | None:
    theta = finite_frame(merged, ["theta_generated_deg", "theta_fitted_deg"])
    phi = finite_frame(merged, ["phi_generated_deg", "phi_fitted_deg"])
    if theta.empty and phi.empty:
        print(f"[WARN] Skipping empty finite generated/fitted histograms for {core}", file=sys.stderr)
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14.0, 5.6))
    fig.suptitle(f"{core} | generated and fitted angular distributions", fontsize=15)

    if not theta.empty:
        axes[0].hist(
            theta["theta_generated_deg"],
            bins=theta_bins,
            range=theta_range,
            histtype="step",
            linewidth=1.6,
            label="Generated",
        )
        axes[0].hist(
            theta["theta_fitted_deg"],
            bins=theta_bins,
            range=theta_range,
            histtype="step",
            linewidth=1.6,
            label="Fitted",
        )
    axes[0].set_title("Theta", fontsize=13)
    axes[0].set_xlabel("Theta [deg]", fontsize=12)
    axes[0].set_ylabel("Events", fontsize=12)
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(fontsize=10)

    if not phi.empty:
        axes[1].hist(
            phi["phi_generated_deg"],
            bins=phi_bins,
            range=phi_range,
            histtype="step",
            linewidth=1.6,
            label="Generated",
        )
        axes[1].hist(
            phi["phi_fitted_deg"],
            bins=phi_bins,
            range=phi_range,
            histtype="step",
            linewidth=1.6,
            label="Fitted",
        )
    axes[1].set_title("Phi", fontsize=13)
    axes[1].set_xlabel("Phi [deg]", fontsize=12)
    axes[1].set_ylabel("Events", fontsize=12)
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(fontsize=10)

    for ax in axes:
        ax.tick_params(axis="both", labelsize=10)

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out_png, dpi=170)
    pdf.savefig(fig, dpi=pdf_dpi)
    plt.close(fig)
    return out_png



def make_step_histogram_grid(
    merged: pd.DataFrame,
    *,
    tt_values: Sequence[object],
    generated_col: str,
    fitted_col: str,
    angle_name: str,
    xlabel: str,
    hist_bins: int,
    hist_range: tuple[float, float],
    suptitle: str,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    grid: GridSpec,
) -> Path | None:
    """Create overlaid generated/fitted step-histogram grids separated by tt_task5_post."""
    finite_all = finite_frame(merged, [generated_col, fitted_col])
    if finite_all.empty:
        print(f"[WARN] Skipping empty finite {angle_name} histogram grid: {suptitle}", file=sys.stderr)
        return None

    pages = [tt_values[i:i + grid.capacity] for i in range(0, len(tt_values), grid.capacity)]
    if not pages:
        print(f"[WARN] Skipping {angle_name} histogram grid: no {TT_COLUMN} values with finite pairs.", file=sys.stderr)
        return None

    last_written: Path | None = None
    for page_idx, page_values in enumerate(pages, start=1):
        page_suffix = "" if len(pages) == 1 else f"_page{page_idx:02d}"
        page_png = out_png.with_name(f"{out_png.stem}{page_suffix}{out_png.suffix}")
        fig, axes = plt.subplots(
            grid.rows,
            grid.cols,
            figsize=(4.2 * grid.cols, 3.35 * grid.rows),
            sharex=True,
            sharey=True,
            squeeze=False,
        )
        fig.suptitle(suptitle if len(pages) == 1 else f"{suptitle} | page {page_idx}", fontsize=15)

        for flat_idx, ax in enumerate(axes.ravel()):
            row = flat_idx // grid.cols
            col = flat_idx % grid.cols
            set_sparse_axis_labels(ax, row=row, col=col, rows=grid.rows, xlabel=xlabel, ylabel="Events")
            ax.tick_params(axis="both", labelsize=9)
            ax.grid(True, alpha=0.25)
            ax.set_xlim(*hist_range)

            if flat_idx >= len(page_values):
                ax.set_visible(False)
                continue

            tt_value = page_values[flat_idx]
            tt_label = normalize_tt_label(tt_value)
            group = merged.loc[merged[TT_COLUMN] == tt_value]
            finite = finite_frame(group, [generated_col, fitted_col])
            if finite.empty:
                ax.set_title(f"tt = {tt_label}\nno finite pairs", fontsize=10)
                continue

            ax.hist(
                finite[generated_col],
                bins=hist_bins,
                range=hist_range,
                histtype="step",
                linewidth=1.25,
                label="Generated",
            )
            ax.hist(
                finite[fitted_col],
                bins=hist_bins,
                range=hist_range,
                histtype="step",
                linewidth=1.25,
                label="Fitted",
            )
            ax.set_title(f"tt = {tt_label} | N = {len(finite):,}", fontsize=10)
            if flat_idx == 0:
                ax.legend(fontsize=8, loc="upper right")

        fig.tight_layout(rect=[0, 0, 1, 0.96])
        fig.savefig(page_png, dpi=170)
        pdf.savefig(fig, dpi=pdf_dpi)
        plt.close(fig)
        last_written = page_png

    return last_written

def make_residual_colored_theta_phi_comparison_figure(
    merged: pd.DataFrame,
    *,
    core: str,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    max_points: int,
    random_state: int,
    scatter_size: float,
    scatter_alpha: float,
) -> Path | None:
    needed = [
        "phi_generated_deg",
        "theta_generated_deg",
        "phi_fitted_deg",
        "theta_fitted_deg",
        "angular_residual_deg",
    ]
    finite = finite_frame(merged, needed)
    if finite.empty:
        print(f"[WARN] Skipping empty finite residual-coloured theta-phi comparison for {core}", file=sys.stderr)
        return None

    plot_df = sample_for_plot(finite, max_points=max_points, random_state=random_state)
    phi_xlim = robust_limits_from_columns(finite, ["phi_generated_deg", "phi_fitted_deg"], minimum_span=10.0)
    theta_ylim = robust_limits_from_columns(finite, ["theta_generated_deg", "theta_fitted_deg"], minimum_span=5.0)
    vmin, vmax = residual_color_limits(finite)

    fig, axes = plt.subplots(1, 2, figsize=(14.0, 6.2), sharex=True, sharey=True)
    fig.suptitle(f"{core} | angular phase space coloured by fit residual", fontsize=15)

    panels = (
        (axes[0], "phi_generated_deg", "theta_generated_deg", "Generated coordinates"),
        (axes[1], "phi_fitted_deg", "theta_fitted_deg", "Fitted coordinates"),
    )
    scatter = None
    for ax, x_col, y_col, title in panels:
        scatter = ax.scatter(
            plot_df[x_col],
            plot_df[y_col],
            c=plot_df["angular_residual_deg"],
            s=scatter_size,
            alpha=scatter_alpha,
            linewidths=0,
            edgecolors="none",
            vmin=vmin,
            vmax=vmax,
            cmap="viridis",
            rasterized=True,
        )
        ax.set_title(f"{title} | plotted N = {len(plot_df):,}", fontsize=13)
        ax.set_xlabel("Phi [deg]", fontsize=12)
        ax.grid(True, alpha=0.25)
        ax.tick_params(axis="both", labelsize=10)
        ax.set_xlim(*phi_xlim)
        ax.set_ylim(*theta_ylim)

    axes[0].set_ylabel("Theta [deg]", fontsize=12)
    if scatter is not None:
        cbar = fig.colorbar(scatter, ax=axes.ravel().tolist(), fraction=0.035, pad=0.03)
        cbar.set_label("Angular residual [deg]", fontsize=11)
        cbar.ax.tick_params(labelsize=9)

    fig.tight_layout(rect=[0, 0, 0.96, 0.94])
    fig.savefig(out_png, dpi=170)
    pdf.savefig(fig, dpi=pdf_dpi)
    plt.close(fig)
    return out_png


def make_residual_colored_phase_space_grid(
    merged: pd.DataFrame,
    *,
    tt_values: Sequence[object],
    x_col: str,
    y_col: str,
    xlabel: str,
    ylabel: str,
    suptitle: str,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    grid: GridSpec,
    max_points: int,
    random_state: int,
    scatter_size: float,
    scatter_alpha: float,
) -> Path | None:
    finite_all = finite_frame(merged, [x_col, y_col, "angular_residual_deg"])
    if finite_all.empty:
        print(f"[WARN] Skipping empty finite residual-coloured phase-space grid: {suptitle}", file=sys.stderr)
        return None

    xlim = robust_limits_from_columns(finite_all, [x_col], minimum_span=10.0)
    ylim = robust_limits_from_columns(finite_all, [y_col], minimum_span=5.0)
    vmin, vmax = residual_color_limits(finite_all)
    pages = [tt_values[i:i + grid.capacity] for i in range(0, len(tt_values), grid.capacity)]
    last_written: Path | None = None

    for page_idx, page_values in enumerate(pages, start=1):
        page_suffix = "" if len(pages) == 1 else f"_page{page_idx:02d}"
        page_png = out_png.with_name(f"{out_png.stem}{page_suffix}{out_png.suffix}")
        fig, axes = plt.subplots(
            grid.rows,
            grid.cols,
            figsize=(4.2 * grid.cols, 3.55 * grid.rows),
            sharex=True,
            sharey=True,
            squeeze=False,
        )
        fig.suptitle(suptitle if len(pages) == 1 else f"{suptitle} | page {page_idx}", fontsize=15)
        scatter = None

        for flat_idx, ax in enumerate(axes.ravel()):
            row = flat_idx // grid.cols
            col = flat_idx % grid.cols
            set_sparse_axis_labels(ax, row=row, col=col, rows=grid.rows, xlabel=xlabel, ylabel=ylabel)
            ax.tick_params(axis="both", labelsize=9)
            ax.grid(True, alpha=0.25)
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)

            if flat_idx >= len(page_values):
                ax.set_visible(False)
                continue

            tt_value = page_values[flat_idx]
            tt_label = normalize_tt_label(tt_value)
            group = merged.loc[merged[TT_COLUMN] == tt_value]
            finite = finite_frame(group, [x_col, y_col, "angular_residual_deg"])
            if finite.empty:
                ax.set_title(f"tt = {tt_label}\nno finite pairs", fontsize=10)
                continue

            plot_df = sample_for_plot(finite, max_points=max_points, random_state=random_state)
            scatter = ax.scatter(
                plot_df[x_col],
                plot_df[y_col],
                c=plot_df["angular_residual_deg"],
                s=scatter_size,
                alpha=scatter_alpha,
                linewidths=0,
                edgecolors="none",
                vmin=vmin,
                vmax=vmax,
                cmap="viridis",
                rasterized=True,
            )
            ax.set_title(f"tt = {tt_label} | N = {len(group):,}", fontsize=10)

        if scatter is not None:
            cbar = fig.colorbar(scatter, ax=axes.ravel().tolist(), fraction=0.026, pad=0.02)
            cbar.set_label("Angular residual [deg]", fontsize=10)
            cbar.ax.tick_params(labelsize=8)

        fig.tight_layout(rect=[0, 0, 0.965, 0.96])
        fig.savefig(page_png, dpi=170)
        pdf.savefig(fig, dpi=pdf_dpi)
        plt.close(fig)
        last_written = page_png

    return last_written



def make_paired_step_histogram_by_tt_figure(
    merged: pd.DataFrame,
    *,
    tt_values: Sequence[object],
    core: str,
    metadata: SimulationMetadata | None,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    theta_bins: int,
    phi_bins: int,
    theta_range: tuple[float, float],
    phi_range: tuple[float, float],
) -> Path | None:
    """Create one two-column figure: theta histograms left, phi histograms right, one row per tt_task5_post."""
    if not tt_values:
        print(f"[WARN] Skipping paired histogram figure for {core}: no finite plane-combination groups.", file=sys.stderr)
        return None

    n_rows = len(tt_values)
    fig_height = max(3.2, 2.35 * n_rows + 1.2)
    fig, axes = plt.subplots(
        n_rows,
        2,
        figsize=(14.0, fig_height),
        sharex="col",
        sharey=False,
        squeeze=False,
    )
    fig.suptitle(
        title_with_metadata(core, f"generated and fitted step histograms by {TT_COLUMN}", metadata),
        fontsize=15,
    )
    axes[0, 0].set_title("Theta", fontsize=13)
    axes[0, 1].set_title("Phi", fontsize=13)

    legend_drawn = False
    for row, tt_value in enumerate(tt_values):
        tt_label = normalize_tt_label(tt_value)
        group = merged.loc[merged[TT_COLUMN] == tt_value]

        theta_ax = axes[row, 0]
        phi_ax = axes[row, 1]
        theta_ax.set_xlim(*theta_range)
        phi_ax.set_xlim(*phi_range)

        for ax in (theta_ax, phi_ax):
            ax.grid(True, alpha=0.25)
            ax.tick_params(axis="both", labelsize=8)

        theta = finite_frame(group, ["theta_generated_deg", "theta_fitted_deg"])
        if not theta.empty:
            theta_ax.hist(
                theta["theta_generated_deg"],
                bins=theta_bins,
                range=theta_range,
                histtype="step",
                linewidth=1.15,
                label="Generated",
            )
            theta_ax.hist(
                theta["theta_fitted_deg"],
                bins=theta_bins,
                range=theta_range,
                histtype="step",
                linewidth=1.15,
                label="Fitted",
            )
        else:
            theta_ax.text(0.5, 0.5, "No finite theta pairs", transform=theta_ax.transAxes, ha="center", va="center", fontsize=9)

        phi = finite_frame(group, ["phi_generated_deg", "phi_fitted_deg"])
        if not phi.empty:
            phi_ax.hist(
                phi["phi_generated_deg"],
                bins=phi_bins,
                range=phi_range,
                histtype="step",
                linewidth=1.15,
                label="Generated",
            )
            phi_ax.hist(
                phi["phi_fitted_deg"],
                bins=phi_bins,
                range=phi_range,
                histtype="step",
                linewidth=1.15,
                label="Fitted",
            )
        else:
            phi_ax.text(0.5, 0.5, "No finite phi pairs", transform=phi_ax.transAxes, ha="center", va="center", fontsize=9)

        theta_ax.set_ylabel(f"tt = {tt_label}\nEvents", fontsize=9)
        if row == n_rows - 1:
            theta_ax.set_xlabel("Theta [deg]", fontsize=11)
            phi_ax.set_xlabel("Phi [deg]", fontsize=11)

        if not legend_drawn and (not theta.empty or not phi.empty):
            theta_ax.legend(fontsize=8, loc="upper right")
            legend_drawn = True

    fig.tight_layout(rect=[0, 0, 1, 0.965])
    fig.savefig(out_png, dpi=170)
    pdf.savefig(fig, dpi=pdf_dpi)
    plt.close(fig)
    return out_png


def make_paired_residual_colored_phase_space_by_tt_figure(
    merged: pd.DataFrame,
    *,
    tt_values: Sequence[object],
    core: str,
    metadata: SimulationMetadata | None,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    max_points: int,
    random_state: int,
    scatter_size: float,
    scatter_alpha: float,
) -> Path | None:
    """Create one two-column figure: generated phase space left, fitted phase space right, one row per tt_task5_post."""
    needed = [
        "phi_generated_deg",
        "theta_generated_deg",
        "phi_fitted_deg",
        "theta_fitted_deg",
        "angular_residual_deg",
    ]
    finite_all = finite_frame(merged, needed)
    if finite_all.empty or not tt_values:
        print(f"[WARN] Skipping paired residual-coloured phase-space figure for {core}: no finite groups.", file=sys.stderr)
        return None

    n_rows = len(tt_values)
    fig_height = max(3.4, 2.85 * n_rows + 1.4)
    fig, axes = plt.subplots(
        n_rows,
        2,
        figsize=(14.2, fig_height),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    fig.suptitle(
        title_with_metadata(core, f"angular phase space coloured by angular residual by {TT_COLUMN}", metadata),
        fontsize=15,
    )
    axes[0, 0].set_title("Generated coordinates", fontsize=13)
    axes[0, 1].set_title("Fitted coordinates", fontsize=13)

    phi_xlim = robust_limits_from_columns(finite_all, ["phi_generated_deg", "phi_fitted_deg"], minimum_span=10.0)
    theta_ylim = robust_limits_from_columns(finite_all, ["theta_generated_deg", "theta_fitted_deg"], minimum_span=5.0)
    vmin, vmax = residual_color_limits(finite_all)
    scatter = None

    for row, tt_value in enumerate(tt_values):
        tt_label = normalize_tt_label(tt_value)
        group = merged.loc[merged[TT_COLUMN] == tt_value]
        finite = finite_frame(group, needed)

        for col in range(2):
            ax = axes[row, col]
            ax.set_xlim(*phi_xlim)
            ax.set_ylim(*theta_ylim)
            ax.grid(True, alpha=0.25)
            ax.tick_params(axis="both", labelsize=8)
            if row == n_rows - 1:
                ax.set_xlabel("Phi [deg]", fontsize=11)
            if col == 0:
                ax.set_ylabel(f"tt = {tt_label}\nTheta [deg]", fontsize=9)

        if finite.empty:
            for col in range(2):
                axes[row, col].text(0.5, 0.5, "No finite pairs", transform=axes[row, col].transAxes, ha="center", va="center", fontsize=9)
            continue

        per_panel_max_points = max(1, max_points // max(n_rows, 1)) if max_points > 0 else max_points
        plot_df = sample_for_plot(finite, max_points=per_panel_max_points, random_state=random_state + row)

        scatter = axes[row, 0].scatter(
            plot_df["phi_generated_deg"],
            plot_df["theta_generated_deg"],
            c=plot_df["angular_residual_deg"],
            s=scatter_size,
            alpha=scatter_alpha,
            linewidths=0,
            edgecolors="none",
            vmin=vmin,
            vmax=vmax,
            cmap="viridis",
            rasterized=True,
        )
        scatter = axes[row, 1].scatter(
            plot_df["phi_fitted_deg"],
            plot_df["theta_fitted_deg"],
            c=plot_df["angular_residual_deg"],
            s=scatter_size,
            alpha=scatter_alpha,
            linewidths=0,
            edgecolors="none",
            vmin=vmin,
            vmax=vmax,
            cmap="viridis",
            rasterized=True,
        )
        axes[row, 0].text(0.02, 0.92, f"N = {len(finite):,}", transform=axes[row, 0].transAxes, fontsize=8, va="top")
        axes[row, 1].text(0.02, 0.92, f"Plotted = {len(plot_df):,}", transform=axes[row, 1].transAxes, fontsize=8, va="top")

    if scatter is not None:
        cbar = fig.colorbar(scatter, ax=axes.ravel().tolist(), fraction=0.018, pad=0.02)
        cbar.set_label("Angular residual [deg]", fontsize=10)
        cbar.ax.tick_params(labelsize=8)

    fig.tight_layout(rect=[0, 0, 0.965, 0.965])
    fig.savefig(out_png, dpi=170)
    pdf.savefig(fig, dpi=pdf_dpi)
    plt.close(fig)
    return out_png


def make_per_tt_migration_matrix_grid_outputs(
    merged: pd.DataFrame,
    *,
    tt_values: Sequence[object],
    core: str,
    metadata: SimulationMetadata | None,
    output_dir: Path,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    theta_bins: int,
    phi_bins: int,
    theta_min: float,
    theta_max: float,
    phi_min: float,
    phi_max: float,
    grid_cols: int,
) -> tuple[Path | None, Path]:
    """Save per-tt migration tables and one grid figure containing all non-empty migration matrices."""
    per_tt_dir = output_dir / f"{core}_angular_migration_by_{TT_COLUMN}"
    per_tt_dir.mkdir(parents=True, exist_ok=True)

    matrix_items: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for tt_value in tt_values:
        tt_label = normalize_tt_label(tt_value)
        tt_file_label = sanitize_for_filename(tt_value)
        group = merged.loc[merged[TT_COLUMN] == tt_value]
        counts, _theta_edges, _phi_edges, labels, frame = build_angular_migration_matrix(
            group,
            theta_bins=theta_bins,
            phi_bins=phi_bins,
            theta_min=theta_min,
            theta_max=theta_max,
            phi_min=phi_min,
            phi_max=phi_max,
        )
        finite_events = int(len(frame))
        in_range_events = int(counts.sum())
        out_of_range_events = finite_events - in_range_events

        stem = f"{core}_{TT_COLUMN}_{tt_file_label}_theta_phi_angular_migration_matrix"
        counts_csv = per_tt_dir / f"{stem}_counts.csv"
        row_norm_csv = per_tt_dir / f"{stem}_row_normalized.csv"
        long_csv = per_tt_dir / f"{stem}_long.csv"
        save_migration_tables(
            counts,
            labels,
            counts_csv=counts_csv,
            row_normalized_csv=row_norm_csv,
            long_csv=long_csv,
        )

        if in_range_events > 0:
            matrix_items.append(
                {
                    "tt_value": tt_value,
                    "tt_label": tt_label,
                    "counts": counts,
                    "row_normalized": row_normalize_counts(counts),
                    "in_range_events": in_range_events,
                    "finite_events": finite_events,
                }
            )
        else:
            print(f"[WARN] {TT_COLUMN} = {tt_label}: no in-range migration events.", file=sys.stderr)

        if out_of_range_events > 0:
            print(
                f"[WARN] {TT_COLUMN} = {tt_label}: angular migration out-of-range events = {out_of_range_events:,}.",
                file=sys.stderr,
            )

        summary_rows.append(
            {
                TT_COLUMN: tt_label,
                "events": int(len(group)),
                "finite_migration_events": finite_events,
                "in_range_migration_events": in_range_events,
                "out_of_range_migration_events": out_of_range_events,
                "migration_counts_csv": str(counts_csv),
                "migration_row_normalized_csv": str(row_norm_csv),
                "migration_long_csv": str(long_csv),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(TT_COLUMN, key=lambda col: col.map(lambda x: tt_sort_key(x)))
    summary_csv = output_dir / f"{core}_theta_phi_angular_migration_by_{TT_COLUMN}_summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    if not matrix_items:
        print(f"[WARN] Skipping per-{TT_COLUMN} migration matrix grid for {core}: no non-empty matrices.", file=sys.stderr)
        return None, summary_csv

    cols = max(1, int(grid_cols))
    rows = int(math.ceil(len(matrix_items) / cols))
    fig_width = 4.0 * cols
    fig_height = 3.75 * rows + 0.8
    fig, axes = plt.subplots(rows, cols, figsize=(fig_width, fig_height), squeeze=False)
    fig.suptitle(
        title_with_metadata(core, f"angular migration matrices by {TT_COLUMN}", metadata),
        fontsize=15,
    )
    image = None

    for flat_idx, ax in enumerate(axes.ravel()):
        if flat_idx >= len(matrix_items):
            ax.set_visible(False)
            continue
        item = matrix_items[flat_idx]
        row_norm = item["row_normalized"]
        image = ax.imshow(
            row_norm,
            origin="upper",
            aspect="auto",
            interpolation="nearest",
            vmin=0.0,
            vmax=1.0,
            rasterized=True,
        )
        ax.set_title(
            f"tt = {item['tt_label']} | N = {int(item['in_range_events']):,}",
            fontsize=9,
        )
        ax.set_xlabel("Fitted bin", fontsize=8)
        ax.set_ylabel("Generated bin", fontsize=8)
        ax.set_xticks([])
        ax.set_yticks([])

    if image is not None:
        cbar = fig.colorbar(image, ax=axes.ravel().tolist(), fraction=0.018, pad=0.015)
        cbar.set_label("Probability within generated bin", fontsize=10)
        cbar.ax.tick_params(labelsize=8)

    fig.tight_layout(rect=[0, 0, 0.965, 0.965])
    fig.savefig(out_png, dpi=170)
    pdf.savefig(fig, dpi=pdf_dpi)
    plt.close(fig)
    return out_png, summary_csv

def bin_indices(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    indices = np.searchsorted(edges, values, side="right") - 1
    upper_edge_mask = values == edges[-1]
    indices[upper_edge_mask] = len(edges) - 2
    valid = np.isfinite(values) & (values >= edges[0]) & (values <= edges[-1])
    indices[~valid] = -1
    indices[(indices < 0) | (indices >= len(edges) - 1)] = -1
    return indices.astype(np.int64)


def angular_bin_labels(theta_edges: np.ndarray, phi_edges: np.ndarray) -> list[str]:
    labels: list[str] = []
    for theta_idx in range(len(theta_edges) - 1):
        theta_lo = theta_edges[theta_idx]
        theta_hi = theta_edges[theta_idx + 1]
        for phi_idx in range(len(phi_edges) - 1):
            phi_lo = phi_edges[phi_idx]
            phi_hi = phi_edges[phi_idx + 1]
            labels.append(f"θ[{theta_lo:.0f},{theta_hi:.0f}) φ[{phi_lo:.0f},{phi_hi:.0f})")
    if labels:
        labels[-1] = labels[-1].replace(")", "]", 1)
    return labels


def build_angular_migration_matrix(
    merged: pd.DataFrame,
    *,
    theta_bins: int,
    phi_bins: int,
    theta_min: float,
    theta_max: float,
    phi_min: float,
    phi_max: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], pd.DataFrame]:
    if theta_bins <= 0 or phi_bins <= 0:
        raise ValueError("Migration theta and phi bin counts must be positive integers.")
    if not theta_min < theta_max:
        raise ValueError("Migration theta range must satisfy theta_min < theta_max.")
    if not phi_min < phi_max:
        raise ValueError("Migration phi range must satisfy phi_min < phi_max.")

    finite = finite_frame(
        merged,
        [
            "theta_generated_deg",
            "phi_generated_deg",
            "theta_fitted_deg",
            "phi_fitted_deg",
        ],
    )
    theta_edges = np.linspace(theta_min, theta_max, theta_bins + 1, dtype=float)
    phi_edges = np.linspace(phi_min, phi_max, phi_bins + 1, dtype=float)
    labels = angular_bin_labels(theta_edges, phi_edges)
    n_angular_bins = theta_bins * phi_bins
    counts = np.zeros((n_angular_bins, n_angular_bins), dtype=np.int64)

    if finite.empty:
        return counts, theta_edges, phi_edges, labels, finite

    # Enforce periodic phi normalization at the migration-matrix construction point too.
    # This makes the migration code robust even if it is called with a frame whose
    # phi columns have not already been wrapped upstream.
    finite = finite.copy()
    finite["phi_generated_deg"] = wrap_phi_deg(finite["phi_generated_deg"])
    finite["phi_fitted_deg"] = wrap_phi_deg(finite["phi_fitted_deg"])

    gen_theta_bin = bin_indices(finite["theta_generated_deg"].to_numpy(dtype=float), theta_edges)
    gen_phi_bin = bin_indices(finite["phi_generated_deg"].to_numpy(dtype=float), phi_edges)
    fit_theta_bin = bin_indices(finite["theta_fitted_deg"].to_numpy(dtype=float), theta_edges)
    fit_phi_bin = bin_indices(finite["phi_fitted_deg"].to_numpy(dtype=float), phi_edges)

    valid = (
        (gen_theta_bin >= 0)
        & (gen_phi_bin >= 0)
        & (fit_theta_bin >= 0)
        & (fit_phi_bin >= 0)
    )
    truth_bin = gen_theta_bin[valid] * phi_bins + gen_phi_bin[valid]
    fitted_bin = fit_theta_bin[valid] * phi_bins + fit_phi_bin[valid]
    np.add.at(counts, (truth_bin, fitted_bin), 1)

    finite = finite.copy()
    finite["migration_in_range"] = valid
    finite["generated_angular_bin"] = -1
    finite["fitted_angular_bin"] = -1
    finite.loc[valid, "generated_angular_bin"] = truth_bin
    finite.loc[valid, "fitted_angular_bin"] = fitted_bin
    return counts, theta_edges, phi_edges, labels, finite


def row_normalize_counts(counts: np.ndarray) -> np.ndarray:
    row_sums = counts.sum(axis=1, keepdims=True)
    return np.divide(
        counts,
        row_sums,
        out=np.zeros_like(counts, dtype=float),
        where=row_sums > 0,
    )


def save_migration_tables(
    counts: np.ndarray,
    labels: Sequence[str],
    *,
    counts_csv: Path,
    row_normalized_csv: Path,
    long_csv: Path,
) -> None:
    safe_labels = [label.replace("\n", " ") for label in labels]
    counts_df = pd.DataFrame(counts, index=safe_labels, columns=safe_labels)
    counts_df.index.name = "generated_angular_bin"
    counts_df.columns.name = "fitted_angular_bin"
    counts_df.to_csv(counts_csv)

    row_normalized = row_normalize_counts(counts)
    row_df = pd.DataFrame(row_normalized, index=safe_labels, columns=safe_labels)
    row_df.index.name = "generated_angular_bin"
    row_df.columns.name = "fitted_angular_bin"
    row_df.to_csv(row_normalized_csv)

    long_rows = []
    for origin_idx, origin_label in enumerate(safe_labels):
        total = int(counts[origin_idx].sum())
        for fitted_idx, fitted_label in enumerate(safe_labels):
            count = int(counts[origin_idx, fitted_idx])
            probability = float(count / total) if total > 0 else np.nan
            long_rows.append(
                {
                    "generated_bin_index": origin_idx,
                    "generated_bin_label": origin_label,
                    "fitted_bin_index": fitted_idx,
                    "fitted_bin_label": fitted_label,
                    "count": count,
                    "row_probability": probability,
                    "generated_bin_total": total,
                }
            )
    pd.DataFrame(long_rows).to_csv(long_csv, index=False)


def sparse_ticks(n_bins: int, max_ticks: int = 18) -> np.ndarray:
    if n_bins <= max_ticks:
        return np.arange(n_bins)
    step = int(math.ceil(n_bins / max_ticks))
    ticks = np.arange(0, n_bins, step)
    if ticks[-1] != n_bins - 1:
        ticks = np.append(ticks, n_bins - 1)
    return ticks


def make_migration_matrix_figure(
    counts: np.ndarray,
    labels: Sequence[str],
    *,
    core: str,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
) -> Path | None:
    if counts.size == 0 or counts.sum() == 0:
        print(f"[WARN] Skipping angular migration matrix for {core}: no in-range events.", file=sys.stderr)
        return None

    row_normalized = row_normalize_counts(counts)
    n_bins = counts.shape[0]
    safe_labels = [label.replace("\n", " ") for label in labels]

    fig_width = min(max(9.5, 0.10 * n_bins + 7.0), 22.0)
    fig_height = min(max(8.0, 0.10 * n_bins + 5.2), 22.0)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    image = ax.imshow(
        row_normalized,
        origin="upper",
        aspect="auto",
        interpolation="nearest",
        vmin=0.0,
        vmax=1.0,
        rasterized=True,
    )
    cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Probability within generated bin", fontsize=11)
    cbar.ax.tick_params(labelsize=9)

    ax.set_title(f"{core} | angular migration matrix, generated bin to fitted bin", fontsize=14)
    ax.set_xlabel("Fitted theta-phi bin", fontsize=12)
    ax.set_ylabel("Generated theta-phi bin", fontsize=12)

    ticks = sparse_ticks(n_bins)
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.set_xticklabels([safe_labels[i] for i in ticks], rotation=90, fontsize=7)
    ax.set_yticklabels([safe_labels[i] for i in ticks], fontsize=7)
    ax.tick_params(axis="both", length=0)

    if n_bins <= 40:
        ax.set_xticks(np.arange(-0.5, n_bins, 1.0), minor=True)
        ax.set_yticks(np.arange(-0.5, n_bins, 1.0), minor=True)
        ax.grid(which="minor", linewidth=0.35, alpha=0.35)
        ax.tick_params(which="minor", bottom=False, left=False)

    if n_bins <= 16:
        for row in range(n_bins):
            for col in range(n_bins):
                count = int(counts[row, col])
                if count == 0:
                    continue
                ax.text(
                    col,
                    row,
                    f"{row_normalized[row, col]:.2f}\n{count}",
                    ha="center",
                    va="center",
                    fontsize=6,
                )

    fig.tight_layout()
    fig.savefig(out_png, dpi=170)
    pdf.savefig(fig, dpi=pdf_dpi)
    plt.close(fig)
    return out_png



def _first_recursive_key(data: Any, key: str) -> Any:
    """Return the first value found for key in a nested mapping/list structure."""
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            found = _first_recursive_key(value, key)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _first_recursive_key(item, key)
            if found is not None:
                return found
    return None


def _parse_sequence(value: Any, *, role: str) -> list[Any]:
    if value is None:
        raise ValueError(f"Missing angular-region configuration field: {role}")
    if isinstance(value, str):
        text = value.strip()
        try:
            value = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            value = [part.strip() for part in text.strip("[]").split(",") if part.strip()]
    if not isinstance(value, (list, tuple, np.ndarray)):
        raise ValueError(f"Angular-region configuration field {role} must be a sequence.")
    return list(value)


def load_angular_region_config(config_path: Path) -> AngularRegionConfig | None:
    """Load STEP_2 angular-region definition from YAML without affecting other plots."""
    if not config_path.exists():
        print(f"[WARN] Angular-region STEP_2 config not found: {config_path}", file=sys.stderr)
        return None
    if yaml is None:
        print(
            "[WARN] PyYAML is not installed; skipping angular-region migration diagnostic.",
            file=sys.stderr,
        )
        return None

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    raw_theta_boundaries = _first_recursive_key(data, "theta_boundaries")
    raw_region_layout = _first_recursive_key(data, "region_layout")
    raw_region_ring_names = _first_recursive_key(data, "region_ring_names")

    theta_boundaries = tuple(
        float(item) for item in _parse_sequence(raw_theta_boundaries, role="theta_boundaries")
    )
    region_layout = tuple(
        int(item) for item in _parse_sequence(raw_region_layout, role="region_layout")
    )
    region_ring_names = tuple(
        str(item) for item in _parse_sequence(raw_region_ring_names, role="region_ring_names")
    )

    if len(theta_boundaries) == 0:
        raise ValueError("theta_boundaries must contain at least one boundary.")
    if any(not np.isfinite(item) for item in theta_boundaries):
        raise ValueError("theta_boundaries must be finite numeric values.")
    if tuple(sorted(theta_boundaries)) != theta_boundaries:
        raise ValueError("theta_boundaries must be strictly increasing.")
    if len(set(theta_boundaries)) != len(theta_boundaries):
        raise ValueError("theta_boundaries must not contain duplicated values.")
    expected_rings = len(theta_boundaries) + 1
    if len(region_layout) != expected_rings:
        raise ValueError(
            "region_layout length must be len(theta_boundaries) + 1. "
            f"Got {len(region_layout)} for {len(theta_boundaries)} theta boundaries."
        )
    if len(region_ring_names) != expected_rings:
        raise ValueError(
            "region_ring_names length must be len(theta_boundaries) + 1. "
            f"Got {len(region_ring_names)} for {len(theta_boundaries)} theta boundaries."
        )
    if any(item <= 0 for item in region_layout):
        raise ValueError("region_layout entries must be positive integers.")

    return AngularRegionConfig(
        theta_boundaries=theta_boundaries,
        region_layout=region_layout,
        region_ring_names=region_ring_names,
    )


def compass_sector_names_for_wrapped_phi(n_phi_regions: int) -> list[str]:
    """
    Return human-readable azimuth-sector names in the same order as the
    script's wrapped-phi bins, which run from -180 to +180 degrees.

    Convention used for naming only:
    - phi = 0 deg is North,
    - positive phi rotates toward East,
    - negative phi rotates toward West.

    Therefore, for 8 equal bins ordered from -180 to +180, the labels are
    S, SW, W, NW, N, NE, E, SE. For 4 equal bins, only cardinal labels are
    used: S, W, N, E. This preserves the actual bin ordering used by the
    region assignment while replacing numeric labels by compass-style names.
    """
    n = int(n_phi_regions)
    if n == 1:
        return [""]
    if n == 4:
        return ["S", "W", "N", "E"]
    if n == 8:
        return ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]

    # Generic fallback for other layouts: assign each bin centre to the nearest
    # named point on the corresponding n-wind compass rose when possible.
    canonical_by_n = {
        16: [
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        ],
    }
    if n in canonical_by_n:
        return canonical_by_n[n]
    return [f"sector{idx + 1:02d}" for idx in range(n)]


def angular_region_labels(config: AngularRegionConfig) -> list[str]:
    labels: list[str] = []
    theta_edges_for_labels = [None, *config.theta_boundaries, None]
    for ring_idx, n_phi_regions in enumerate(config.region_layout):
        ring_name = config.region_ring_names[ring_idx]
        theta_lo = theta_edges_for_labels[ring_idx]
        theta_hi = theta_edges_for_labels[ring_idx + 1]
        if theta_lo is None:
            theta_label = f"θ<{theta_hi:g}"
        elif theta_hi is None:
            theta_label = f"θ≥{theta_lo:g}"
        else:
            theta_label = f"{theta_lo:g}≤θ<{theta_hi:g}"

        if n_phi_regions == 1:
            labels.append(f"{ring_name}\n{theta_label}\nall φ")
            continue

        compass_names = compass_sector_names_for_wrapped_phi(int(n_phi_regions))
        phi_edges = np.linspace(-180.0, 180.0, n_phi_regions + 1, dtype=float)
        for phi_idx in range(n_phi_regions):
            phi_lo = phi_edges[phi_idx]
            phi_hi = phi_edges[phi_idx + 1]
            sector_name = compass_names[phi_idx]
            if sector_name:
                full_region_name = f"{ring_name}.{sector_name}"
            else:
                full_region_name = str(ring_name)
            labels.append(
                f"{full_region_name}\n"
                f"{theta_label}\n"
                f"{phi_lo:.0f}≤φ<{phi_hi:.0f}"
            )
    return labels


def assign_angular_regions(
    theta_deg: pd.Series,
    phi_deg: pd.Series,
    config: AngularRegionConfig,
) -> np.ndarray:
    theta = pd.to_numeric(theta_deg, errors="coerce").to_numpy(dtype=float)
    phi = wrap_phi_deg(phi_deg).to_numpy(dtype=float)
    boundaries = np.asarray(config.theta_boundaries, dtype=float)
    ring_index = np.searchsorted(boundaries, theta, side="right").astype(np.int64)

    valid = np.isfinite(theta) & np.isfinite(phi)
    valid &= ring_index >= 0
    valid &= ring_index < len(config.region_layout)

    offsets = np.cumsum((0, *config.region_layout[:-1])).astype(np.int64)
    region_id = np.full(theta.shape, -1, dtype=np.int64)

    for ring_idx, n_phi_regions in enumerate(config.region_layout):
        mask = valid & (ring_index == ring_idx)
        if not np.any(mask):
            continue
        if n_phi_regions == 1:
            phi_region = np.zeros(int(mask.sum()), dtype=np.int64)
        else:
            phi_edges = np.linspace(-180.0, 180.0, n_phi_regions + 1, dtype=float)
            phi_region = bin_indices(phi[mask], phi_edges)
        local_valid = phi_region >= 0
        target_indices = np.flatnonzero(mask)
        region_id[target_indices[local_valid]] = offsets[ring_idx] + phi_region[local_valid]

    return region_id


def build_angular_region_migration_matrix(
    merged: pd.DataFrame,
    config: AngularRegionConfig,
) -> tuple[np.ndarray, list[str], pd.DataFrame]:
    finite = finite_frame(
        merged,
        [
            "theta_generated_deg",
            "phi_generated_deg",
            "theta_fitted_deg",
            "phi_fitted_deg",
        ],
    )
    labels = angular_region_labels(config)
    n_regions = config.n_regions
    counts = np.zeros((n_regions, n_regions), dtype=np.int64)
    if finite.empty:
        return counts, labels, finite

    finite = finite.copy()
    finite["phi_generated_deg"] = wrap_phi_deg(finite["phi_generated_deg"])
    finite["phi_fitted_deg"] = wrap_phi_deg(finite["phi_fitted_deg"])

    generated_region = assign_angular_regions(
        finite["theta_generated_deg"],
        finite["phi_generated_deg"],
        config,
    )
    fitted_region = assign_angular_regions(
        finite["theta_fitted_deg"],
        finite["phi_fitted_deg"],
        config,
    )
    valid = (generated_region >= 0) & (fitted_region >= 0)
    np.add.at(counts, (generated_region[valid], fitted_region[valid]), 1)

    finite = finite.copy()
    finite["angular_region_migration_in_range"] = valid
    finite["generated_angular_region"] = generated_region
    finite["fitted_angular_region"] = fitted_region
    return counts, labels, finite


def make_region_migration_matrix_figure(
    counts: np.ndarray,
    labels: Sequence[str],
    *,
    core: str,
    metadata: SimulationMetadata | None,
    region_config: AngularRegionConfig,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
) -> Path | None:
    if counts.size == 0 or counts.sum() == 0:
        print(f"[WARN] Skipping angular-region migration matrix for {core}: no in-range events.", file=sys.stderr)
        return None

    row_normalized = row_normalize_counts(counts)
    n_regions = counts.shape[0]
    fig_width = min(max(9.0, 0.65 * n_regions + 4.5), 18.0)
    fig_height = min(max(7.5, 0.55 * n_regions + 3.8), 16.0)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    image = ax.imshow(
        row_normalized,
        origin="upper",
        aspect="auto",
        interpolation="nearest",
        vmin=0.0,
        vmax=1.0,
        rasterized=True,
    )
    cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Probability within generated region", fontsize=11)
    cbar.ax.tick_params(labelsize=9)

    ax.set_title(
        title_with_metadata(
            core,
            "angular-region migration matrix, generated region to fitted region\n"
            f"{region_config.compact_label}",
            metadata,
        ),
        fontsize=13,
    )
    ax.set_xlabel("Fitted angular region", fontsize=12)
    ax.set_ylabel("Generated angular region", fontsize=12)
    ax.set_xticks(np.arange(n_regions))
    ax.set_yticks(np.arange(n_regions))
    ax.set_xticklabels([label.replace("\n", " ") for label in labels], rotation=90, fontsize=7)
    ax.set_yticklabels([label.replace("\n", " ") for label in labels], fontsize=7)
    ax.tick_params(axis="both", length=0)
    ax.set_xticks(np.arange(-0.5, n_regions, 1.0), minor=True)
    ax.set_yticks(np.arange(-0.5, n_regions, 1.0), minor=True)
    ax.grid(which="minor", linewidth=0.35, alpha=0.35)
    ax.tick_params(which="minor", bottom=False, left=False)

    if n_regions <= 20:
        for row in range(n_regions):
            for col in range(n_regions):
                count = int(counts[row, col])
                if count == 0:
                    continue
                ax.text(
                    col,
                    row,
                    f"{row_normalized[row, col]:.2f}\n{count}",
                    ha="center",
                    va="center",
                    fontsize=6,
                )

    fig.tight_layout()
    fig.savefig(out_png, dpi=170)
    pdf.savefig(fig, dpi=pdf_dpi)
    plt.close(fig)
    return out_png


def make_per_tt_region_migration_matrix_grid_outputs(
    merged: pd.DataFrame,
    *,
    tt_values: Sequence[object],
    core: str,
    metadata: SimulationMetadata | None,
    region_config: AngularRegionConfig,
    output_dir: Path,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    grid_cols: int,
) -> tuple[Path | None, Path]:
    """Save per-tt region-migration tables and one grid figure containing all non-empty region matrices."""
    per_tt_dir = output_dir / f"{core}_angular_region_migration_by_{TT_COLUMN}"
    per_tt_dir.mkdir(parents=True, exist_ok=True)

    labels = angular_region_labels(region_config)
    matrix_items: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for tt_value in tt_values:
        tt_label = normalize_tt_label(tt_value)
        tt_file_label = sanitize_for_filename(tt_value)
        group = merged.loc[merged[TT_COLUMN] == tt_value]
        counts, labels, frame = build_angular_region_migration_matrix(group, region_config)
        finite_events = int(len(frame))
        in_range_events = int(counts.sum())
        out_of_range_events = finite_events - in_range_events

        stem = f"{core}_{TT_COLUMN}_{tt_file_label}_angular_region_migration_matrix"
        counts_csv = per_tt_dir / f"{stem}_counts.csv"
        row_norm_csv = per_tt_dir / f"{stem}_row_normalized.csv"
        long_csv = per_tt_dir / f"{stem}_long.csv"
        save_migration_tables(
            counts,
            labels,
            counts_csv=counts_csv,
            row_normalized_csv=row_norm_csv,
            long_csv=long_csv,
        )

        if in_range_events > 0:
            matrix_items.append(
                {
                    "tt_value": tt_value,
                    "tt_label": tt_label,
                    "counts": counts,
                    "row_normalized": row_normalize_counts(counts),
                    "in_range_events": in_range_events,
                    "finite_events": finite_events,
                }
            )
        else:
            print(f"[WARN] {TT_COLUMN} = {tt_label}: no in-range angular-region migration events.", file=sys.stderr)

        if out_of_range_events > 0:
            print(
                f"[WARN] {TT_COLUMN} = {tt_label}: angular-region migration out-of-range events = {out_of_range_events:,}.",
                file=sys.stderr,
            )

        summary_rows.append(
            {
                TT_COLUMN: tt_label,
                "events": int(len(group)),
                "finite_region_migration_events": finite_events,
                "in_range_region_migration_events": in_range_events,
                "out_of_range_region_migration_events": out_of_range_events,
                "region_migration_counts_csv": str(counts_csv),
                "region_migration_row_normalized_csv": str(row_norm_csv),
                "region_migration_long_csv": str(long_csv),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(TT_COLUMN, key=lambda col: col.map(lambda x: tt_sort_key(x)))
    summary_csv = output_dir / f"{core}_angular_region_migration_by_{TT_COLUMN}_summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    if not matrix_items:
        print(f"[WARN] Skipping per-{TT_COLUMN} angular-region migration matrix grid for {core}: no non-empty matrices.", file=sys.stderr)
        return None, summary_csv

    cols = max(1, int(grid_cols))
    rows = int(math.ceil(len(matrix_items) / cols))
    fig_width = 4.0 * cols
    fig_height = 3.75 * rows + 1.0
    fig, axes = plt.subplots(rows, cols, figsize=(fig_width, fig_height), squeeze=False)
    fig.suptitle(
        title_with_metadata(
            core,
            f"angular-region migration matrices by {TT_COLUMN}\n{region_config.compact_label}",
            metadata,
        ),
        fontsize=14,
    )
    image = None

    for flat_idx, ax in enumerate(axes.ravel()):
        if flat_idx >= len(matrix_items):
            ax.set_visible(False)
            continue
        item = matrix_items[flat_idx]
        row_norm = item["row_normalized"]
        image = ax.imshow(
            row_norm,
            origin="upper",
            aspect="auto",
            interpolation="nearest",
            vmin=0.0,
            vmax=1.0,
            rasterized=True,
        )
        ax.set_title(
            f"tt = {item['tt_label']} | N = {int(item['in_range_events']):,}",
            fontsize=9,
        )
        ax.set_xlabel("Fitted region", fontsize=8)
        ax.set_ylabel("Generated region", fontsize=8)
        ax.set_xticks([])
        ax.set_yticks([])

    if image is not None:
        cbar = fig.colorbar(image, ax=axes.ravel().tolist(), fraction=0.018, pad=0.015)
        cbar.set_label("Probability within generated region", fontsize=10)
        cbar.ax.tick_params(labelsize=8)

    fig.tight_layout(rect=[0, 0, 0.965, 0.955])
    fig.savefig(out_png, dpi=170)
    pdf.savefig(fig, dpi=pdf_dpi)
    plt.close(fig)
    return out_png, summary_csv



def angular_region_rectangles(
    config: AngularRegionConfig,
    *,
    theta_min: float = 0.0,
    theta_max: float = 90.0,
) -> tuple[list[Rectangle], list[tuple[float, float]], list[str]]:
    """Return rectangle patches, label positions, and labels for the configured angular regions."""
    if not theta_min < theta_max:
        raise ValueError("Angular-region occupancy plot requires theta_min < theta_max.")

    theta_edges = [theta_min, *[float(item) for item in config.theta_boundaries], theta_max]
    labels = angular_region_labels(config)
    rectangles: list[Rectangle] = []
    centers: list[tuple[float, float]] = []

    for ring_idx, n_phi_regions in enumerate(config.region_layout):
        theta_lo = float(theta_edges[ring_idx])
        theta_hi = float(theta_edges[ring_idx + 1])
        if theta_hi <= theta_lo:
            raise ValueError(
                "Angular-region theta plotting edges are not increasing. "
                f"Check theta boundaries and plot range: edges={theta_edges}"
            )

        phi_edges = np.linspace(-180.0, 180.0, int(n_phi_regions) + 1, dtype=float)
        for phi_idx in range(int(n_phi_regions)):
            phi_lo = float(phi_edges[phi_idx])
            phi_hi = float(phi_edges[phi_idx + 1])
            rectangles.append(Rectangle((phi_lo, theta_lo), phi_hi - phi_lo, theta_hi - theta_lo))
            centers.append(((phi_lo + phi_hi) / 2.0, (theta_lo + theta_hi) / 2.0))

    if len(rectangles) != config.n_regions:
        raise RuntimeError(
            "Internal angular-region rectangle construction mismatch: "
            f"got {len(rectangles)} rectangles for {config.n_regions} regions."
        )
    if len(labels) != config.n_regions:
        raise RuntimeError(
            "Internal angular-region label construction mismatch: "
            f"got {len(labels)} labels for {config.n_regions} regions."
        )
    return rectangles, centers, labels


def angular_region_occupancy_counts(
    frame: pd.DataFrame,
    *,
    theta_col: str,
    phi_col: str,
    region_config: AngularRegionConfig,
) -> tuple[np.ndarray, int, int]:
    """Count events in configured angular regions for one theta-phi coordinate system."""
    finite = finite_frame(frame, [theta_col, phi_col])
    if finite.empty:
        return np.zeros(region_config.n_regions, dtype=np.int64), 0, 0

    region_id = assign_angular_regions(finite[theta_col], finite[phi_col], region_config)
    valid = region_id >= 0
    counts = np.bincount(region_id[valid], minlength=region_config.n_regions).astype(np.int64)
    return counts, int(len(finite)), int(valid.sum())


def make_region_occupancy_grid_figure(
    merged: pd.DataFrame,
    *,
    tt_values: Sequence[object],
    core: str,
    metadata: SimulationMetadata | None,
    region_config: AngularRegionConfig,
    coordinate_label: str,
    theta_col: str,
    phi_col: str,
    out_png: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    grid: GridSpec,
) -> tuple[Path | None, pd.DataFrame]:
    """Plot configured angular regions coloured by occupancy count for each plane combination."""
    labels = angular_region_labels(region_config)
    if not tt_values:
        print(
            f"[WARN] Skipping angular-region occupancy grid for {coordinate_label}: "
            "no finite plane-combination groups.",
            file=sys.stderr,
        )
        return None, pd.DataFrame()

    rectangles_template, centers, labels = angular_region_rectangles(region_config)
    occupancy_items: list[dict[str, object]] = []
    table_rows: list[dict[str, object]] = []

    for tt_value in tt_values:
        tt_label = normalize_tt_label(tt_value)
        group = merged.loc[merged[TT_COLUMN] == tt_value]
        counts, finite_events, in_range_events = angular_region_occupancy_counts(
            group,
            theta_col=theta_col,
            phi_col=phi_col,
            region_config=region_config,
        )
        occupancy_items.append(
            {
                "tt_value": tt_value,
                "tt_label": tt_label,
                "counts": counts,
                "finite_events": finite_events,
                "in_range_events": in_range_events,
            }
        )
        total = int(counts.sum())
        for region_idx, region_label in enumerate(labels):
            count = int(counts[region_idx])
            table_rows.append(
                {
                    "coordinate_space": coordinate_label,
                    TT_COLUMN: tt_label,
                    "region_index": region_idx,
                    "region_label": region_label.replace("\n", " "),
                    "count": count,
                    "fraction_within_coordinate_space": float(count / total) if total > 0 else np.nan,
                    "finite_events": finite_events,
                    "in_range_events": in_range_events,
                    "out_of_range_events": finite_events - in_range_events,
                }
            )

    max_count = max((int(np.max(np.asarray(item["counts"]))) for item in occupancy_items), default=0)
    norm = Normalize(vmin=0.0, vmax=float(max(max_count, 1)))
    pages = [occupancy_items[i:i + grid.capacity] for i in range(0, len(occupancy_items), grid.capacity)]
    last_written: Path | None = None

    for page_idx, page_items in enumerate(pages, start=1):
        page_suffix = "" if len(pages) == 1 else f"_page{page_idx:02d}"
        page_png = out_png.with_name(f"{out_png.stem}{page_suffix}{out_png.suffix}")
        fig, axes = plt.subplots(
            grid.rows,
            grid.cols,
            figsize=(4.1 * grid.cols, 3.45 * grid.rows),
            sharex=True,
            sharey=True,
            squeeze=False,
        )
        description = f"{coordinate_label} angular-region occupancy by {TT_COLUMN}\n{region_config.compact_label}"
        if len(pages) > 1:
            description = f"{description} | page {page_idx}"
        fig.suptitle(title_with_metadata(core, description, metadata), fontsize=14)

        collection_for_colorbar = None
        for flat_idx, ax in enumerate(axes.ravel()):
            row = flat_idx // grid.cols
            col = flat_idx % grid.cols
            ax.set_xlim(-180.0, 180.0)
            ax.set_ylim(0.0, 90.0)
            ax.grid(True, alpha=0.18)
            ax.tick_params(axis="both", labelsize=8)
            set_sparse_axis_labels(ax, row=row, col=col, rows=grid.rows, xlabel="Phi [deg]", ylabel="Theta [deg]")

            if flat_idx >= len(page_items):
                ax.set_visible(False)
                continue

            item = page_items[flat_idx]
            counts = np.asarray(item["counts"], dtype=float)
            patches = [Rectangle(rect.get_xy(), rect.get_width(), rect.get_height()) for rect in rectangles_template]
            collection = PatchCollection(
                patches,
                cmap="viridis",
                norm=norm,
                edgecolor="black",
                linewidth=0.45,
                rasterized=True,
            )
            collection.set_array(counts)
            ax.add_collection(collection)
            collection_for_colorbar = collection

            ax.set_title(f"tt = {item['tt_label']} | N = {int(item['in_range_events']):,}", fontsize=9)

            if region_config.n_regions <= 20:
                for region_idx, (x_center, y_center) in enumerate(centers):
                    label_text = labels[region_idx].split("\n", 1)[0]
                    ax.text(
                        x_center,
                        y_center,
                        f"{label_text}\n{int(counts[region_idx]):,}",
                        ha="center",
                        va="center",
                        fontsize=5.8,
                    )

        if collection_for_colorbar is not None:
            cbar = fig.colorbar(collection_for_colorbar, ax=axes.ravel().tolist(), fraction=0.018, pad=0.016)
            cbar.set_label("Events in angular region", fontsize=10)
            cbar.ax.tick_params(labelsize=8)

        fig.tight_layout(rect=[0, 0, 0.965, 0.945])
        fig.savefig(page_png, dpi=170)
        pdf.savefig(fig, dpi=pdf_dpi)
        plt.close(fig)
        last_written = page_png

    occupancy_df = pd.DataFrame(table_rows)
    if not occupancy_df.empty:
        occupancy_df["_tt_sort"] = occupancy_df[TT_COLUMN].map(tt_sort_key)
        occupancy_df = occupancy_df.sort_values(["coordinate_space", "_tt_sort", "region_index"]).drop(columns="_tt_sort")
    return last_written, occupancy_df

def make_per_tt_migration_outputs(
    merged: pd.DataFrame,
    *,
    core: str,
    output_dir: Path,
    pdf: PdfPages,
    pdf_dpi: int,
    theta_bins: int,
    phi_bins: int,
    theta_min: float,
    theta_max: float,
    phi_min: float,
    phi_max: float,
) -> tuple[list[Path], Path]:
    per_tt_dir = output_dir / f"{core}_angular_migration_by_{TT_COLUMN}"
    per_tt_dir.mkdir(parents=True, exist_ok=True)

    figure_outputs: list[Path] = []
    summary_rows: list[dict[str, object]] = []
    grouped = sorted(list(merged.groupby(TT_COLUMN, dropna=False, sort=False)), key=lambda item: tt_sort_key(item[0]))

    for tt_value, group in grouped:
        tt_label = normalize_tt_label(tt_value)
        tt_file_label = sanitize_for_filename(tt_value)
        counts, _theta_edges, _phi_edges, labels, frame = build_angular_migration_matrix(
            group,
            theta_bins=theta_bins,
            phi_bins=phi_bins,
            theta_min=theta_min,
            theta_max=theta_max,
            phi_min=phi_min,
            phi_max=phi_max,
        )
        finite_events = int(len(frame))
        in_range_events = int(counts.sum())
        out_of_range_events = finite_events - in_range_events

        stem = f"{core}_{TT_COLUMN}_{tt_file_label}_theta_phi_angular_migration_matrix"
        counts_csv = per_tt_dir / f"{stem}_counts.csv"
        row_norm_csv = per_tt_dir / f"{stem}_row_normalized.csv"
        long_csv = per_tt_dir / f"{stem}_long.csv"
        out_png = per_tt_dir / f"{stem}_row_normalized.png"

        save_migration_tables(
            counts,
            labels,
            counts_csv=counts_csv,
            row_normalized_csv=row_norm_csv,
            long_csv=long_csv,
        )
        out = make_migration_matrix_figure(
            counts,
            labels,
            core=f"{core} | {TT_COLUMN} = {tt_label}",
            out_png=out_png,
            pdf=pdf,
            pdf_dpi=pdf_dpi,
        )
        if out is not None:
            figure_outputs.append(out)

        if in_range_events == 0:
            print(f"[WARN] {TT_COLUMN} = {tt_label}: no in-range migration events.", file=sys.stderr)
        elif out_of_range_events > 0:
            print(
                f"[WARN] {TT_COLUMN} = {tt_label}: angular migration out-of-range events = "
                f"{out_of_range_events:,}.",
                file=sys.stderr,
            )

        summary_rows.append(
            {
                TT_COLUMN: tt_label,
                "events": int(len(group)),
                "finite_migration_events": finite_events,
                "in_range_migration_events": in_range_events,
                "out_of_range_migration_events": out_of_range_events,
                "migration_counts_csv": str(counts_csv),
                "migration_row_normalized_csv": str(row_norm_csv),
                "migration_long_csv": str(long_csv),
                "migration_png": str(out_png) if out is not None else "",
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(TT_COLUMN, key=lambda col: col.map(lambda x: tt_sort_key(x)))
    summary_csv = output_dir / f"{core}_theta_phi_angular_migration_by_{TT_COLUMN}_summary.csv"
    summary_df.to_csv(summary_csv, index=False)
    return figure_outputs, summary_csv


def tt_values_with_finite_columns(merged: pd.DataFrame, columns: Sequence[str]) -> list[object]:
    values: list[object] = []
    for tt_value, group in merged.groupby(TT_COLUMN, dropna=False, sort=False):
        finite = finite_frame(group, list(columns))
        if not finite.empty:
            values.append(tt_value)
    return sorted(values, key=tt_sort_key)


def residual_summary(series: pd.Series) -> tuple[float, float]:
    finite = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return np.nan, np.nan
    arr = finite.to_numpy(dtype=float)
    return float(np.mean(arr)), float(np.sqrt(np.mean(arr ** 2)))


def main() -> int:
    args = parse_args()
    if args.grid_rows <= 0 or args.grid_cols <= 0:
        raise ValueError("--grid-rows and --grid-cols must be positive integers.")
    if args.pdf_dpi <= 0:
        raise ValueError("--pdf-dpi must be a positive integer.")
    if args.scatter_size <= 0:
        raise ValueError("--scatter-size must be positive.")
    if not 0.0 < args.scatter_alpha <= 1.0:
        raise ValueError("--scatter-alpha must be in the interval (0, 1].")
    if args.theta_hist_bins <= 0 or args.phi_hist_bins <= 0:
        raise ValueError("Histogram bin counts must be positive integers.")
    if not args.theta_hist_min < args.theta_hist_max:
        raise ValueError("Theta histogram range must satisfy min < max.")
    if not args.phi_hist_min < args.phi_hist_max:
        raise ValueError("Phi histogram range must satisfy min < max.")

    grid = GridSpec(rows=args.grid_rows, cols=args.grid_cols)

    input_path = args.input_file if args.input_file is not None else newest_parquet(args.step12_dir)
    input_path = input_path.expanduser().resolve()
    sidecar_dir = args.sidecar_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input parquet does not exist: {input_path}")

    sidecar_path = find_sidecar(input_path, sidecar_dir)
    core = infer_core_basename(input_path)

    print(f"Input STEP_1_TO_2 file: {input_path}")
    print(f"Matched sidecar file:   {sidecar_path}")
    print(f"Core basename:          {core}")

    step_df = pd.read_parquet(input_path, engine="pyarrow")
    sidecar_df = pd.read_parquet(sidecar_path, engine="pyarrow")

    metadata = load_simulation_metadata(
        params_csv=args.simulation_params_csv.expanduser().resolve(),
        core=core,
        sidecar_df=sidecar_df,
    )
    print(f"Simulation metadata:   {metadata.compact_label}")

    region_config = load_angular_region_config(args.angular_region_config.expanduser().resolve())
    if region_config is not None:
        print(f"Angular region config: {region_config.compact_label}")

    if TT_COLUMN not in step_df.columns:
        raise KeyError(f"Input file does not contain '{TT_COLUMN}'.")

    angle_cols = resolve_angle_columns(step_df, sidecar_df)
    print(f"Using fitted theta column:    {angle_cols.theta_fit}")
    print(f"Using fitted phi column:      {angle_cols.phi_fit}")
    print(f"Using generated theta column: {angle_cols.theta_truth}")
    print(f"Using generated phi column:   {angle_cols.phi_truth}")

    step_keep = [EVENT_ID_COLUMN, TT_COLUMN, angle_cols.theta_fit, angle_cols.phi_fit]
    sidecar_keep = [EVENT_ID_COLUMN, angle_cols.theta_truth, angle_cols.phi_truth]
    optional_sidecar = [
        col
        for col in ("sim_event_id", "T_thick_s", "X_gen", "Y_gen", "Z_gen", "station_datetime")
        if col in sidecar_df.columns
    ]
    sidecar_keep.extend(optional_sidecar)

    step_sel = coerce_event_id(step_df.loc[:, step_keep], "STEP_1_TO_2 file")
    sidecar_sel = coerce_event_id(sidecar_df.loc[:, sidecar_keep], "sidecar file")

    merged = step_sel.merge(
        sidecar_sel,
        on=EVENT_ID_COLUMN,
        how="inner",
        validate="one_to_one",
        suffixes=("_fit", "_truth"),
    )
    if merged.empty:
        raise RuntimeError("Join on event_id produced zero matched rows.")

    print(f"Rows in STEP_1_TO_2 file: {len(step_df):,}")
    print(f"Rows in sidecar file:     {len(sidecar_df):,}")
    print(f"Matched rows:             {len(merged):,}")

    merged["theta_generated_deg"] = to_degrees(merged[angle_cols.theta_truth], kind="theta")
    merged["theta_fitted_deg"] = to_degrees(merged[angle_cols.theta_fit], kind="theta")
    merged["phi_generated_deg"] = wrap_phi_deg(to_degrees(merged[angle_cols.phi_truth], kind="phi"))
    merged["phi_fitted_deg"] = wrap_phi_deg(to_degrees(merged[angle_cols.phi_fit], kind="phi"))
    merged["theta_residual_deg"] = merged["theta_fitted_deg"] - merged["theta_generated_deg"]
    merged["phi_residual_deg"] = circular_delta_deg(merged["phi_fitted_deg"], merged["phi_generated_deg"])
    merged["phi_abs_residual_deg"] = merged["phi_residual_deg"].abs()
    merged["angular_residual_deg"] = spherical_angular_separation_deg(
        merged["theta_generated_deg"],
        merged["phi_generated_deg"],
        merged["theta_fitted_deg"],
        merged["phi_fitted_deg"],
    )

    if args.write_merged:
        merged_path = output_dir / f"{core}_sidecar_truth_vs_fit_merged.parquet"
        merged.to_parquet(merged_path, engine="pyarrow", compression="zstd", index=False)
        print(f"Saved merged table: {merged_path}")

    histogram_tt_values = tt_values_with_finite_columns(
        merged,
        [
            "theta_generated_deg",
            "theta_fitted_deg",
            "phi_generated_deg",
            "phi_fitted_deg",
        ],
    )
    phase_space_tt_values = tt_values_with_finite_columns(
        merged,
        [
            "phi_generated_deg",
            "theta_generated_deg",
            "phi_fitted_deg",
            "theta_fitted_deg",
            "angular_residual_deg",
        ],
    )
    migration_tt_values = tt_values_with_finite_columns(
        merged,
        [
            "theta_generated_deg",
            "phi_generated_deg",
            "theta_fitted_deg",
            "phi_fitted_deg",
        ],
    )

    pdf_path = output_dir / f"{core}_sidecar_truth_vs_fit_diagnostics.pdf"
    paired_histograms_png = output_dir / (
        f"{core}_theta_phi_generated_vs_fitted_step_histograms_by_{TT_COLUMN}.png"
    )
    paired_phase_space_png = output_dir / (
        f"{core}_theta_phi_generated_left_fitted_right_colored_by_angular_residual_by_{TT_COLUMN}.png"
    )
    migration_matrix_grid_png = output_dir / (
        f"{core}_theta_phi_angular_migration_matrix_grid_by_{TT_COLUMN}.png"
    )
    migration_counts_csv = output_dir / f"{core}_theta_phi_angular_migration_matrix_counts.csv"
    migration_row_normalized_csv = output_dir / f"{core}_theta_phi_angular_migration_matrix_row_normalized.csv"
    migration_long_csv = output_dir / f"{core}_theta_phi_angular_migration_matrix_long.csv"
    region_migration_matrix_png = output_dir / f"{core}_angular_region_migration_matrix_row_normalized.png"
    region_migration_matrix_grid_png = output_dir / f"{core}_angular_region_migration_matrix_grid_by_{TT_COLUMN}.png"
    region_migration_counts_csv = output_dir / f"{core}_angular_region_migration_matrix_counts.csv"
    region_migration_row_normalized_csv = output_dir / f"{core}_angular_region_migration_matrix_row_normalized.csv"
    region_migration_long_csv = output_dir / f"{core}_angular_region_migration_matrix_long.csv"
    region_generated_occupancy_grid_png = output_dir / (
        f"{core}_angular_region_generated_occupancy_grid_by_{TT_COLUMN}.png"
    )
    region_fitted_occupancy_grid_png = output_dir / (
        f"{core}_angular_region_fitted_occupancy_grid_by_{TT_COLUMN}.png"
    )
    region_occupancy_csv = output_dir / f"{core}_angular_region_occupancy_by_{TT_COLUMN}.csv"
    per_tt_region_migration_summary_csv: Path | None = None

    migration_counts, _theta_edges, _phi_edges, migration_labels, migration_frame = build_angular_migration_matrix(
        merged,
        theta_bins=args.migration_theta_bins,
        phi_bins=args.migration_phi_bins,
        theta_min=args.migration_theta_min,
        theta_max=args.migration_theta_max,
        phi_min=args.migration_phi_min,
        phi_max=args.migration_phi_max,
    )
    save_migration_tables(
        migration_counts,
        migration_labels,
        counts_csv=migration_counts_csv,
        row_normalized_csv=migration_row_normalized_csv,
        long_csv=migration_long_csv,
    )
    finite_migration_events = int(len(migration_frame))
    in_range_migration_events = int(migration_counts.sum())
    if finite_migration_events != in_range_migration_events:
        print(
            "[WARN] Global angular migration out-of-range events = "
            f"{finite_migration_events - in_range_migration_events:,}.",
            file=sys.stderr,
        )

    region_migration_counts: np.ndarray | None = None
    region_migration_labels: list[str] | None = None
    if region_config is not None:
        region_migration_counts, region_migration_labels, region_migration_frame = build_angular_region_migration_matrix(
            merged,
            region_config,
        )
        save_migration_tables(
            region_migration_counts,
            region_migration_labels,
            counts_csv=region_migration_counts_csv,
            row_normalized_csv=region_migration_row_normalized_csv,
            long_csv=region_migration_long_csv,
        )
        finite_region_migration_events = int(len(region_migration_frame))
        in_range_region_migration_events = int(region_migration_counts.sum())
        if finite_region_migration_events != in_range_region_migration_events:
            print(
                "[WARN] Global angular-region migration out-of-range events = "
                f"{finite_region_migration_events - in_range_region_migration_events:,}.",
                file=sys.stderr,
            )

    figure_outputs: list[Path] = []
    with PdfPages(pdf_path) as pdf:
        out = make_paired_step_histogram_by_tt_figure(
            merged,
            tt_values=histogram_tt_values,
            core=core,
            metadata=metadata,
            out_png=paired_histograms_png,
            pdf=pdf,
            pdf_dpi=args.pdf_dpi,
            theta_bins=args.theta_hist_bins,
            phi_bins=args.phi_hist_bins,
            theta_range=(args.theta_hist_min, args.theta_hist_max),
            phi_range=(args.phi_hist_min, args.phi_hist_max),
        )
        if out is not None:
            figure_outputs.append(out)

        out = make_paired_residual_colored_phase_space_by_tt_figure(
            merged,
            tt_values=phase_space_tt_values,
            core=core,
            metadata=metadata,
            out_png=paired_phase_space_png,
            pdf=pdf,
            pdf_dpi=args.pdf_dpi,
            max_points=args.max_points,
            random_state=args.random_state,
            scatter_size=args.scatter_size,
            scatter_alpha=args.scatter_alpha,
        )
        if out is not None:
            figure_outputs.append(out)

        out, per_tt_migration_summary_csv = make_per_tt_migration_matrix_grid_outputs(
            merged,
            tt_values=migration_tt_values,
            core=core,
            metadata=metadata,
            output_dir=output_dir,
            out_png=migration_matrix_grid_png,
            pdf=pdf,
            pdf_dpi=args.pdf_dpi,
            theta_bins=args.migration_theta_bins,
            phi_bins=args.migration_phi_bins,
            theta_min=args.migration_theta_min,
            theta_max=args.migration_theta_max,
            phi_min=args.migration_phi_min,
            phi_max=args.migration_phi_max,
            grid_cols=args.grid_cols,
        )
        if out is not None:
            figure_outputs.append(out)

        if region_config is not None and region_migration_counts is not None and region_migration_labels is not None:
            out = make_region_migration_matrix_figure(
                region_migration_counts,
                region_migration_labels,
                core=core,
                metadata=metadata,
                region_config=region_config,
                out_png=region_migration_matrix_png,
                pdf=pdf,
                pdf_dpi=args.pdf_dpi,
            )
            if out is not None:
                figure_outputs.append(out)

            out, per_tt_region_migration_summary_csv = make_per_tt_region_migration_matrix_grid_outputs(
                merged,
                tt_values=migration_tt_values,
                core=core,
                metadata=metadata,
                region_config=region_config,
                output_dir=output_dir,
                out_png=region_migration_matrix_grid_png,
                pdf=pdf,
                pdf_dpi=args.pdf_dpi,
                grid_cols=args.grid_cols,
            )
            if out is not None:
                figure_outputs.append(out)

            out, generated_region_occupancy_df = make_region_occupancy_grid_figure(
                merged,
                tt_values=migration_tt_values,
                core=core,
                metadata=metadata,
                region_config=region_config,
                coordinate_label="Generated",
                theta_col="theta_generated_deg",
                phi_col="phi_generated_deg",
                out_png=region_generated_occupancy_grid_png,
                pdf=pdf,
                pdf_dpi=args.pdf_dpi,
                grid=grid,
            )
            if out is not None:
                figure_outputs.append(out)

            out, fitted_region_occupancy_df = make_region_occupancy_grid_figure(
                merged,
                tt_values=migration_tt_values,
                core=core,
                metadata=metadata,
                region_config=region_config,
                coordinate_label="Fitted",
                theta_col="theta_fitted_deg",
                phi_col="phi_fitted_deg",
                out_png=region_fitted_occupancy_grid_png,
                pdf=pdf,
                pdf_dpi=args.pdf_dpi,
                grid=grid,
            )
            if out is not None:
                figure_outputs.append(out)

            region_occupancy_parts = [
                part for part in (generated_region_occupancy_df, fitted_region_occupancy_df) if not part.empty
            ]
            if region_occupancy_parts:
                pd.concat(region_occupancy_parts, ignore_index=True).to_csv(region_occupancy_csv, index=False)

    summary_rows: list[dict[str, object]] = []
    for tt_value, group in merged.groupby(TT_COLUMN, dropna=False, sort=False):
        tt_label = normalize_tt_label(tt_value)
        theta_mean, theta_rms = residual_summary(group["theta_residual_deg"])
        phi_mean, phi_rms = residual_summary(group["phi_residual_deg"])
        angular_mean, angular_rms = residual_summary(group["angular_residual_deg"])
        summary_rows.append(
            {
                TT_COLUMN: tt_label,
                "events": int(len(group)),
                "theta_finite_pairs": int(len(finite_frame(group, ["theta_generated_deg", "theta_fitted_deg"]))),
                "phi_finite_pairs": int(len(finite_frame(group, ["phi_generated_deg", "phi_fitted_deg"]))),
                "theta_mean_residual_deg": theta_mean,
                "theta_rms_residual_deg": theta_rms,
                "phi_mean_residual_deg_wrapped": phi_mean,
                "phi_rms_residual_deg_wrapped": phi_rms,
                "angular_mean_residual_deg": angular_mean,
                "angular_rms_residual_deg": angular_rms,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(TT_COLUMN, key=lambda col: col.map(lambda x: tt_sort_key(x)))
    summary_csv = output_dir / f"{core}_truth_vs_fit_by_{TT_COLUMN}_summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    print(f"Saved diagnostics PDF: {pdf_path}")
    print(f"Saved summary CSV:     {summary_csv}")
    print(f"Saved migration counts CSV:         {migration_counts_csv}")
    print(f"Saved migration row-normalized CSV: {migration_row_normalized_csv}")
    print(f"Saved migration long CSV:           {migration_long_csv}")
    print(f"Saved per-tt migration summary CSV: {per_tt_migration_summary_csv}")
    if region_config is not None:
        print(f"Saved region migration counts CSV:         {region_migration_counts_csv}")
        print(f"Saved region migration row-normalized CSV: {region_migration_row_normalized_csv}")
        print(f"Saved region migration long CSV:           {region_migration_long_csv}")
        if per_tt_region_migration_summary_csv is not None:
            print(f"Saved per-tt region migration summary CSV: {per_tt_region_migration_summary_csv}")
        if region_occupancy_csv.exists():
            print(f"Saved angular-region occupancy CSV:      {region_occupancy_csv}")
    print(f"Saved PNG directory:   {output_dir}")
    if figure_outputs:
        print("Saved consolidated PNG figures:")
        for path in figure_outputs:
            print(f"  - {path}")

    if not summary_df.empty:
        print("\nSummary:")
        with pd.option_context("display.max_columns", None, "display.width", 180):
            print(summary_df.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
