#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/EFFICIENCY_PROXY_AUDIT/reproduce_suspicious_efficiency_cases.py
Purpose: Reproduce suspicious efficiency cases with the current STEP 1-9 code path, without modifying the simulator.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-27
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/EFFICIENCY_PROXY_AUDIT/reproduce_suspicious_efficiency_cases.py [options]
Inputs: Current digital-twin physics configs plus the step_final_simulation_params catalog and dictionary outputs.
Outputs: CSV, JSON, and PDF diagnostic files in this directory.
Notes: Read-only reproduction using imported step functions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
import yaml

ROOT_DIR = Path(__file__).resolve().parents[5]
sys.path.append(str(ROOT_DIR / "PIPELINE" / "MINGO_DIGITAL_TWIN"))
sys.path.append(str(ROOT_DIR / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "MASTER_STEPS"))

from STEP_SHARED.sim_utils import DetectorBounds
from STEP_1.step_1_blank_to_generated import generate_muon_sample
from STEP_2.step_2_generated_to_crossing import calculate_intersections
from STEP_3.step_3_crossing_to_hit import build_avalanche
from STEP_4.step_4_hit_to_measured import induce_signal
from STEP_5.step_5_measured_to_triggered import compute_tdiff_qdiff
from STEP_6.step_6_triggered_to_timing import compute_front_back
from STEP_7.step_7_timing_to_uncalibrated import apply_calibration
from STEP_8.step_8_uncalibrated_to_threshold import apply_fee, apply_threshold
from STEP_9.step_9_threshold_to_trigger import apply_trigger
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.tot_charge_calibration import (
    TotChargeCalibration,
    default_tot_charge_calibration_path,
)


PLANE_MISSING_TAG = {1: "234", 2: "134", 3: "124", 4: "123"}
DEFAULT_CASES = [1049, 1083, 1887]


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _normalize_tt(values: pd.Series | np.ndarray | list[object]) -> np.ndarray:
    series = pd.Series(values, copy=False).astype("string").fillna("")
    series = series.str.strip().str.replace(r"\.0$", "", regex=True)
    series = series.replace({"0": "", "0.0": "", "nan": "", "<NA>": ""})
    return series.to_numpy(dtype=str)


def _tt_counter(values: np.ndarray) -> dict[str, int]:
    counts = pd.Series(values).value_counts()
    return {str(k): int(v) for k, v in counts.items() if str(k) != ""}


def _proxy_from_counts(counts: dict[str, int], plane: int) -> float:
    num = counts.get("1234", 0)
    den = num + counts.get(PLANE_MISSING_TAG[plane], 0)
    if den <= 0:
        return float("nan")
    return float(num) / float(den)


def _active_tt_from_threshold(df: pd.DataFrame) -> np.ndarray:
    n = len(df)
    labels = np.full(n, "", dtype=object)
    for plane_idx in range(1, 5):
        plane_active = np.zeros(n, dtype=bool)
        for strip_idx in range(1, 5):
            qf = pd.to_numeric(df.get(f"Q_front_{plane_idx}_s{strip_idx}"), errors="coerce").fillna(0.0).to_numpy()
            qb = pd.to_numeric(df.get(f"Q_back_{plane_idx}_s{strip_idx}"), errors="coerce").fillna(0.0).to_numpy()
            plane_active |= (qf > 0.0) | (qb > 0.0)
        labels = np.where(plane_active, labels + str(plane_idx), labels)
    return labels


def _load_observed_case_table() -> pd.DataFrame:
    transformed = pd.read_csv(
        ROOT_DIR
        / "MINGO_DICTIONARY_CREATION_AND_TEST"
        / "STEPS/STEP_1_SETUP/STEP_1_2_TRANSFORM_FEATURE_SPACE/OUTPUTS/FILES/transformed_feature_space.csv",
        usecols=["filename_base", "param_set_id", "flux_cm2_min", "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4"],
    )
    ancillary = pd.read_csv(
        ROOT_DIR
        / "MINGO_DICTIONARY_CREATION_AND_TEST"
        / "STEPS/STEP_1_SETUP/STEP_1_2_TRANSFORM_FEATURE_SPACE/OUTPUTS/FILES/transformed_feature_space_ancillary.csv",
        usecols=["filename_base", "eff_empirical_1", "eff_empirical_2", "eff_empirical_3", "eff_empirical_4"],
    )
    merged = transformed.merge(ancillary, on="filename_base", how="inner")
    grouped = (
        merged.groupby("param_set_id", as_index=False)
        .agg(
            {
                "flux_cm2_min": "median",
                "eff_sim_1": "median",
                "eff_sim_2": "median",
                "eff_sim_3": "median",
                "eff_sim_4": "median",
                "eff_empirical_1": "median",
                "eff_empirical_2": "median",
                "eff_empirical_3": "median",
                "eff_empirical_4": "median",
            }
        )
        .copy()
    )
    return grouped


def _load_case_catalog() -> pd.DataFrame:
    catalog = pd.read_csv(
        ROOT_DIR / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "SIMULATION_OUTPUTS" / "SIMULATED_DATA" / "step_final_simulation_params.csv",
        usecols=["param_set_id", "cos_n", "flux_cm2_min", "efficiencies"],
    ).drop_duplicates("param_set_id")
    effs = catalog["efficiencies"].apply(json.loads)
    for plane in range(1, 5):
        catalog[f"catalog_eff_{plane}"] = effs.apply(lambda row, idx=plane - 1: float(row[idx]))
    return catalog


def _simulate_case(row: pd.Series, cfg: dict, n_tracks: int, seed: int) -> dict:
    rng_step3 = np.random.default_rng(seed + 10)
    rng_step4 = np.random.default_rng(seed + 20)
    rng_step5 = np.random.default_rng(seed + 30)
    rng_step8 = np.random.default_rng(seed + 40)

    step1_cfg = cfg["step1"]
    step2_cfg = cfg["step2"]
    step3_cfg = cfg["step3"]
    step4_cfg = cfg["step4"]
    step5_cfg = cfg["step5"]
    step7_cfg = cfg["step7"]
    step8_cfg = cfg["step8"]
    step9_cfg = cfg["step9"]

    df1 = generate_muon_sample(
        n_tracks=n_tracks,
        xlim=float(step1_cfg["xlim_mm"]),
        ylim=float(step1_cfg["ylim_mm"]),
        z_plane=float(step1_cfg["z_plane_mm"]),
        cos_n=float(row["cos_n"]),
        seed=seed,
        thick_rate_hz=None,
        drop_last_second=False,
        batch_size=min(n_tracks, 200_000),
    )

    z_positions = [float(value) for value in step2_cfg["z_positions"]]
    bounds_cfg = step2_cfg["bounds_mm"]
    bounds = DetectorBounds(
        x_min=float(bounds_cfg["x_min"]),
        x_max=float(bounds_cfg["x_max"]),
        y_min=float(bounds_cfg["y_min"]),
        y_max=float(bounds_cfg["y_max"]),
    )
    df2 = calculate_intersections(
        df1,
        z_positions=z_positions,
        bounds=bounds,
        c_mm_per_ns=float(step1_cfg["c_mm_per_ns"]),
    )

    efficiencies = [float(row[f"catalog_eff_{plane}"]) for plane in range(1, 5)]
    df3 = build_avalanche(
        df2,
        efficiencies=efficiencies,
        townsend_alpha=float(step3_cfg["townsend_alpha_per_mm"]),
        gap_mm=float(step3_cfg["avalanche_gap_mm"]),
        electron_sigma=float(step3_cfg["avalanche_electron_sigma"]),
        rng=rng_step3,
    )

    df4 = induce_signal(
        df3,
        x_noise=float(step4_cfg["x_noise_mm"]),
        time_sigma_ns=float(step4_cfg["time_sigma_ns"]),
        lorentzian_gamma_mm=float(
            step4_cfg.get("lorentzian_gamma_mm", 0.5 * float(step4_cfg.get("avalanche_width_mm", 40.0)))
        ),
        induced_charge_fraction=float(step4_cfg.get("induced_charge_fraction", 1.0)),
        rng=rng_step4,
        debug_event_index=None,
        debug_points=None,
    )
    df5 = compute_tdiff_qdiff(
        df4,
        c_mm_per_ns=float(step1_cfg["c_mm_per_ns"]),
        qdiff_width=float(step5_cfg["qdiff_width"]),
        rng=rng_step5,
    )
    df6 = compute_front_back(df5)
    df7 = apply_calibration(df6, step7_cfg)
    charge_conversion_model = str(
        step8_cfg.get("charge_conversion_model", "linear_q_to_time_factor")
    ).strip().lower()
    charge_calibration = None
    if charge_conversion_model == "tot_curve_inverse":
        calibration_path = step8_cfg.get("tot_to_charge_calibration_path")
        if calibration_path is None:
            calibration_path = default_tot_charge_calibration_path(ROOT_DIR)
        else:
            calibration_path = Path(calibration_path)
            if not calibration_path.is_absolute():
                calibration_path = ROOT_DIR / calibration_path
        charge_calibration = TotChargeCalibration.from_csv(calibration_path)
    df8 = apply_fee(
        df7,
        t_fee_sigma_ns=float(step8_cfg["t_fee_sigma_ns"]),
        charge_conversion_model=charge_conversion_model,
        q_to_time_factor=float(step8_cfg["q_to_time_factor"]),
        charge_calibration=charge_calibration,
        qfront_offsets=step8_cfg["qfront_offsets"],
        qback_offsets=step8_cfg["qback_offsets"],
        rng=rng_step8,
    )
    df8 = apply_threshold(df8, threshold=float(step8_cfg["charge_threshold"]))
    df9 = apply_trigger(df8, triggers=list(step9_cfg["trigger_combinations"]))

    tt2 = _tt_counter(_normalize_tt(df2["tt_crossing"]))
    tt3 = _tt_counter(_normalize_tt(df3["tt_avalanche"]))
    tt8 = _tt_counter(_active_tt_from_threshold(df8))
    tt9 = _tt_counter(_normalize_tt(df9["tt_trigger"]))

    cross1234_mask = _normalize_tt(df2["tt_crossing"]) == "1234"
    cross1234_count = int(cross1234_mask.sum())

    result: dict[str, object] = {
        "param_set_id": int(row["param_set_id"]),
        "seed": int(seed),
        "n_tracks": int(n_tracks),
        "cos_n": float(row["cos_n"]),
        "flux_cm2_min": float(row["flux_cm2_min"]),
    }
    for plane in range(1, 5):
        result[f"configured_eff_{plane}"] = float(row[f"catalog_eff_{plane}"])
        result[f"observed_empirical_{plane}"] = float(row[f"eff_empirical_{plane}"])
        result[f"step2_geometry_proxy_{plane}"] = _proxy_from_counts(tt2, plane)
        result[f"step3_proxy_{plane}"] = _proxy_from_counts(tt3, plane)
        result[f"step8_active_proxy_{plane}"] = _proxy_from_counts(tt8, plane)
        result[f"step9_trigger_proxy_{plane}"] = _proxy_from_counts(tt9, plane)
        if cross1234_count > 0:
            avalanche_exists = pd.to_numeric(df3.loc[cross1234_mask, f"avalanche_exists_{plane}"], errors="coerce").fillna(0)
            result[f"step3_cond_avalanche_on_cross1234_{plane}"] = float(avalanche_exists.astype(int).mean())
        else:
            result[f"step3_cond_avalanche_on_cross1234_{plane}"] = float("nan")
    return result


def _load_current_configs() -> dict[str, dict]:
    base = ROOT_DIR / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "MASTER_STEPS"
    return {
        "step1": _load_yaml(base / "STEP_1" / "config_step_1_physics.yaml"),
        "step2": _load_yaml(base / "STEP_2" / "config_step_2_physics.yaml"),
        "step3": _load_yaml(base / "STEP_3" / "config_step_3_physics.yaml"),
        "step4": _load_yaml(base / "STEP_4" / "config_step_4_physics.yaml"),
        "step5": _load_yaml(base / "STEP_5" / "config_step_5_physics.yaml"),
        "step7": _load_yaml(base / "STEP_7" / "config_step_7_physics.yaml"),
        "step8": _load_yaml(base / "STEP_8" / "config_step_8_physics.yaml"),
        "step9": _load_yaml(base / "STEP_9" / "config_step_9_physics.yaml"),
    }


def _plot_case_bars(df: pd.DataFrame, pdf: PdfPages) -> None:
    stages = [
        ("configured_eff", "Configured"),
        ("observed_empirical", "Observed dictionary empirical"),
        ("step3_cond_avalanche_on_cross1234", "STEP 3 conditional avalanche"),
        ("step3_proxy", "STEP 3 proxy"),
        ("step8_active_proxy", "STEP 8 active proxy"),
        ("step9_trigger_proxy", "STEP 9 trigger proxy"),
    ]
    for _, row in df.iterrows():
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharey=True)
        axes = axes.flatten()
        for plane, ax in zip(range(1, 5), axes):
            values = [row[f"{key}_{plane}"] for key, _ in stages]
            labels = [label for _, label in stages]
            colors = ["black", "tab:blue", "tab:green", "tab:orange", "tab:purple", "tab:red"]
            ax.bar(range(len(values)), values, color=colors, alpha=0.85)
            ax.set_xticks(range(len(values)))
            ax.set_xticklabels(labels, rotation=40, ha="right")
            ax.set_ylim(0.5, 1.02)
            ax.set_title(f"Plane {plane}")
            ax.grid(axis="y", alpha=0.20)
        fig.suptitle(
            f"param_set_id={int(row['param_set_id'])}  flux={row['flux_cm2_min']:.6f}  "
            f"n_tracks={int(row['n_tracks'])}  seed={int(row['seed'])}"
        )
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
        pdf.savefig(fig, dpi=150)
        plt.close(fig)


def _plot_focus_planes(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, plane in zip(axes, [2, 3]):
        x = np.arange(len(df))
        width = 0.15
        series = [
            ("configured_eff", "Configured", "black"),
            ("observed_empirical", "Observed", "tab:blue"),
            ("step3_cond_avalanche_on_cross1234", "STEP 3 cond", "tab:green"),
            ("step8_active_proxy", "STEP 8", "tab:purple"),
            ("step9_trigger_proxy", "STEP 9", "tab:red"),
        ]
        for idx, (key, label, color) in enumerate(series):
            vals = df[f"{key}_{plane}"].to_numpy(dtype=float)
            ax.bar(x + (idx - 2) * width, vals, width=width, label=label, color=color, alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels([str(int(v)) for v in df["param_set_id"]], rotation=0)
        ax.set_title(f"Plane {plane}")
        ax.set_xlabel("param_set_id")
        ax.grid(axis="y", alpha=0.20)
    axes[0].set_ylabel("Efficiency / proxy")
    axes[0].set_ylim(0.5, 1.02)
    axes[1].legend(loc="lower right", fontsize=8)
    fig.suptitle("Current-code reproduction for suspicious central-plane cases")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reproduce suspicious efficiency cases with the current STEP 1-9 code.")
    parser.add_argument("--param-set-ids", nargs="*", type=int, default=DEFAULT_CASES)
    parser.add_argument("--n-tracks", type=int, default=100000)
    parser.add_argument("--base-seed", type=int, default=123456)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    observed = _load_observed_case_table()
    catalog = _load_case_catalog()
    current = observed.merge(catalog, on=["param_set_id", "flux_cm2_min"], how="inner")
    cases = current[current["param_set_id"].isin(args.param_set_ids)].copy()
    if cases.empty:
        raise SystemExit("No requested param_set_id values were found in the merged catalog.")

    cfg = _load_current_configs()
    rows: list[dict] = []
    for _, case_row in cases.sort_values("param_set_id").iterrows():
        seed = int(args.base_seed + int(case_row["param_set_id"]))
        rows.append(_simulate_case(case_row, cfg=cfg, n_tracks=int(args.n_tracks), seed=seed))

    result_df = pd.DataFrame(rows).sort_values("param_set_id")

    csv_path = args.output_dir / "reproduced_suspicious_efficiency_cases.csv"
    json_path = args.output_dir / "reproduced_suspicious_efficiency_cases.json"
    pdf_path = args.output_dir / "reproduced_suspicious_efficiency_cases.pdf"

    result_df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(result_df.to_dict(orient="records"), indent=2))
    with PdfPages(pdf_path) as pdf:
        _plot_focus_planes(result_df, pdf)
        _plot_case_bars(result_df, pdf)

    print(f"[OK] wrote {csv_path}")
    print(f"[OK] wrote {json_path}")
    print(f"[OK] wrote {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
