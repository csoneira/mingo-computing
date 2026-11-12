#!/usr/bin/env python3

"""Validator for STEP 9 trigger selection logic."""

from __future__ import annotations

import itertools
from pathlib import Path
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common_io import StepArtifact, load_frame
from .common_report import RESULT_COLUMNS, ResultBuilder, normalize_tt_series


def _build_plane_activity(df: pd.DataFrame, suffix: str = "") -> tuple[dict[int, np.ndarray], list[str]]:
    n = len(df)
    plane_active: dict[int, np.ndarray] = {}
    tt_rows = np.full(n, "", dtype=object)

    for i in range(1, 5):
        act = np.zeros(n, dtype=bool)
        for j in range(1, 5):
            qf = f"Q_front_{i}_s{j}{suffix}"
            qb = f"Q_back_{i}_s{j}{suffix}"
            if qf in df.columns:
                act |= df[qf].to_numpy(dtype=float) > 0
            if qb in df.columns:
                act |= df[qb].to_numpy(dtype=float) > 0
        plane_active[i] = act

    for i in range(1, 5):
        act = plane_active[i]
        tt_rows = np.where(act, tt_rows + str(i), tt_rows)

    return plane_active, tt_rows.tolist()


def _passes_triggers(tt: str, triggers: list[str]) -> bool:
    for trig in triggers:
        if all(ch in tt for ch in trig):
            return True
    return False


def _build_trigger_regex(triggers: list[str]) -> str:
    branches: list[str] = []
    for trig in triggers:
        token = str(trig)
        if token == "":
            branches.append("^.*$")
            continue
        lookaheads = "".join(f"(?=.*{re.escape(ch)})" for ch in token)
        branches.append(f"^{lookaheads}.*$")
    return "|".join(branches) if branches else r"^$"


def _independence_expected_acceptance(p: dict[int, float], triggers: list[str]) -> float:
    expected = 0.0
    for bits in itertools.product([0, 1], repeat=4):
        active = "".join(str(idx + 1) for idx, bit in enumerate(bits) if bit)
        prob = 1.0
        for idx, bit in enumerate(bits, start=1):
            pi = p[idx]
            prob *= pi if bit else (1.0 - pi)
        if _passes_triggers(active, triggers):
            expected += prob
    return float(expected)


def _plot(tt8: list[str], tt9: list[str], plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    s8 = pd.Series(tt8, dtype="string").fillna("")
    s9 = pd.Series(tt9, dtype="string").fillna("")

    c8 = s8.value_counts().sort_index()
    c9 = s9.value_counts().sort_index()

    axes[0].bar(c8.index.astype(str), c8.values, color="slateblue", alpha=0.8)
    axes[0].set_title("STEP 8 active-plane tags")

    axes[1].bar(c9.index.astype(str), c9.values, color="seagreen", alpha=0.8)
    axes[1].set_title("STEP 9 tt_trigger")

    fig.tight_layout()
    fig.savefig(plot_dir / "step9_trigger_patterns.png", dpi=140)
    plt.close(fig)


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
) -> pd.DataFrame:
    art9 = artifacts.get("9")
    art8 = artifacts.get("8")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_step9_trigger",
        step="9",
        sim_run=art9.sim_run if art9 else None,
        config_hash=art9.config_hash if art9 else None,
        upstream_hash=art9.upstream_hash if art9 else None,
        n_rows_in=art8.row_count if art8 else None,
        n_rows_out=art9.row_count if art9 else None,
    )

    if art9 is None or art9.data_path is None or not art9.data_path.exists():
        rb.add(
            test_id="step9_exists",
            test_name="STEP 9 output exists",
            metric_name="step9_exists",
            metric_value=0,
            status="SKIP",
            notes="No STEP 9 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if art8 is None or art8.data_path is None or not art8.data_path.exists():
        rb.add(
            test_id="step9_inputs",
            test_name="STEP 8 inputs available",
            metric_name="step8_available",
            metric_value=0,
            status="SKIP",
            notes="No STEP 8 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cols = ["event_id", "tt_trigger"]
    for i in range(1, 5):
        for j in range(1, 5):
            cols.extend([f"Q_front_{i}_s{j}", f"Q_back_{i}_s{j}"])

    try:
        df9 = load_frame(art9.data_path, columns=cols)
        df8 = load_frame(art8.data_path, columns=cols)
    except Exception as exc:
        rb.add_exception(test_id="step9_read", test_name="Read STEP 8/9", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if df9.empty or df8.empty:
        rb.add(
            test_id="step9_non_empty",
            test_name="STEP 8 and STEP 9 are non-empty",
            metric_name="rows",
            metric_value=int(len(df8) + len(df9)),
            status="FAIL",
            notes="Empty STEP 8 or STEP 9 dataframe",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cfg = art9.metadata.get("config") or {}
    triggers = [str(t) for t in cfg.get("trigger_combinations", [])]
    if not triggers:
        rb.add(
            test_id="step9_trigger_config",
            test_name="Trigger combinations configured",
            metric_name="n_triggers",
            metric_value=0,
            status="SKIP",
            notes="No trigger combinations found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    _, tt8 = _build_plane_activity(df8)
    _, tt9_recomputed = _build_plane_activity(df9)
    tt8_series = pd.Series(tt8, dtype="string").fillna("")
    trigger_pattern = _build_trigger_regex(triggers)
    expected_pass_mask = tt8_series.str.contains(trigger_pattern, regex=True, na=False).to_numpy(dtype=bool)
    expected_event_ids = set(df8.loc[expected_pass_mask, "event_id"].astype(int).tolist())
    observed_event_ids = set(df9["event_id"].astype(int).tolist())

    id_missing = len(expected_event_ids - observed_event_ids)
    id_extra = len(observed_event_ids - expected_event_ids)
    rb.add(
        test_id="step9_event_selection_exact",
        test_name="STEP 9 selected event_id set matches trigger logic",
        metric_name="id_set_diff",
        metric_value=id_missing + id_extra,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if (id_missing == 0 and id_extra == 0) else "FAIL",
        notes=f"missing={id_missing}, extra={id_extra}",
    )

    # Stored tt_trigger consistency.
    if "tt_trigger" in df9.columns:
        stored = normalize_tt_series(df9["tt_trigger"]).tolist()
        mismatch = int(sum(a != b for a, b in zip(stored, tt9_recomputed)))
        rb.add(
            test_id="step9_tt_trigger_consistency",
            test_name="Stored tt_trigger matches observed active planes",
            metric_name="mismatch_rows",
            metric_value=mismatch,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if mismatch == 0 else "FAIL",
        )

    # Acceptance sanity against a simple independence model.
    p = {}
    for i in range(1, 5):
        plane_active = np.zeros(len(df8), dtype=bool)
        for j in range(1, 5):
            qf = f"Q_front_{i}_s{j}"
            qb = f"Q_back_{i}_s{j}"
            if qf in df8.columns:
                plane_active |= df8[qf].to_numpy(dtype=float) > 0
            if qb in df8.columns:
                plane_active |= df8[qb].to_numpy(dtype=float) > 0
        p[i] = float(np.mean(plane_active))

    obs_acc = float(len(df9) / len(df8)) if len(df8) else np.nan
    exp_acc = _independence_expected_acceptance(p, triggers)
    abs_diff = abs(obs_acc - exp_acc)

    # This is a rough model. Keep FAIL only for gross mismatch.
    if abs_diff <= 0.15:
        status = "PASS"
    elif abs_diff <= 0.30:
        status = "WARN"
    else:
        status = "FAIL"

    rb.add(
        test_id="step9_acceptance_sanity",
        test_name="Observed acceptance vs independence estimate",
        metric_name="abs_difference",
        metric_value=abs_diff,
        expected_value=0.0,
        threshold_low=0.0,
        threshold_high=0.15,
        status=status,
        notes=f"obs={obs_acc:.4f}, exp={exp_acc:.4f}, p={p}",
    )

    rb.add(
        test_id="step9_row_drop_info",
        test_name="Trigger selection row reduction",
        metric_name="retained_fraction",
        metric_value=obs_acc,
        expected_value=None,
        status="PASS",
        notes=f"STEP8={len(df8)}, STEP9={len(df9)}",
    )

    if make_plots:
        _plot(tt8, tt9_recomputed, output_dir / "plots" / "validate_step9_trigger")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
