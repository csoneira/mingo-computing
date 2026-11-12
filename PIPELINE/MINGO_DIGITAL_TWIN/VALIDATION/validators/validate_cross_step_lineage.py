#!/usr/bin/env python3

"""Cross-step lineage and integrity validator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common_io import (
    STEP_TO_INTERSTEP,
    StepArtifact,
    compute_exact_manifest_count,
    find_registry_entry,
    get_metadata_for_data_path,
    load_frame,
    resolve_source_dataset_path,
)
from .common_report import RESULT_COLUMNS, ResultBuilder


def _upstream_fingerprint(upstream_meta: dict | None) -> str | None:
    if not isinstance(upstream_meta, dict):
        return None
    payload = {
        "step": upstream_meta.get("step"),
        "config_hash": upstream_meta.get("config_hash"),
        "upstream_hash": upstream_meta.get("upstream_hash"),
    }
    payload_json = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _plot_row_counts(row_counts: dict[str, int | None], plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)

    keys = [k for k in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"] if k in row_counts]
    vals = [row_counts[k] if row_counts[k] is not None else 0 for k in keys]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(keys, vals, color="steelblue", alpha=0.8)
    ax.set_title("Row counts by step")
    ax.set_xlabel("Step")
    ax.set_ylabel("Rows")
    fig.tight_layout()
    fig.savefig(plot_dir / "cross_step_row_counts.png", dpi=140)
    plt.close(fig)


def _load_event_id_set(art: StepArtifact | None) -> set[int] | None:
    if art is None or art.data_path is None or not art.data_path.exists():
        return None
    try:
        df = load_frame(art.data_path, columns=["event_id"])
    except Exception:
        return None
    if "event_id" not in df.columns:
        return None
    return set(df["event_id"].astype(int).tolist())


def _parse_sim_run_ids(sim_run: str | None) -> tuple[str, ...]:
    if not sim_run or not sim_run.startswith("SIM_RUN_"):
        return tuple()
    parts = [token for token in sim_run[len("SIM_RUN_") :].split("_") if token]
    return tuple(parts)


def _lineage_prefix_match(art_a: StepArtifact | None, art_b: StepArtifact | None, prefix_len: int) -> bool:
    ids_a = _parse_sim_run_ids(art_a.sim_run if art_a else None)
    ids_b = _parse_sim_run_ids(art_b.sim_run if art_b else None)
    if prefix_len <= 0:
        return True
    if len(ids_a) < prefix_len or len(ids_b) < prefix_len:
        return False
    return ids_a[:prefix_len] == ids_b[:prefix_len]


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
) -> pd.DataFrame:
    art10 = artifacts.get("10")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_cross_step_lineage",
        step="cross",
        sim_run=art10.sim_run if art10 else None,
        config_hash=art10.config_hash if art10 else None,
        upstream_hash=art10.upstream_hash if art10 else None,
        n_rows_in=None,
        n_rows_out=None,
    )

    # Per-step registry and metadata integrity.
    row_counts: dict[str, int | None] = {}
    for step_key in [str(i) for i in range(1, 11)]:
        art = artifacts.get(step_key)
        if art is None:
            rb.add(
                test_id=f"cross_step{step_key}_artifact",
                test_name=f"STEP {step_key} artifact discovered",
                metric_name="exists",
                metric_value=0,
                status="SKIP",
            )
            continue

        exists = int(art.exists)
        rb.add(
            test_id=f"cross_step{step_key}_exists",
            test_name=f"STEP {step_key} data exists",
            metric_name="exists",
            metric_value=exists,
            expected_value=1,
            threshold_low=1,
            threshold_high=1,
            status="PASS" if exists else "SKIP",
        )

        if not art.exists:
            row_counts[step_key] = None
            continue

        row_counts[step_key] = art.row_count

        cfg_hash_ok = int(bool(art.config_hash))
        up_hash_ok = int(bool(art.upstream_hash)) if step_key != "1" else 1
        rb.add(
            test_id=f"cross_step{step_key}_hashes",
            test_name=f"STEP {step_key} config/upstream hashes available",
            metric_name="hash_fields_present",
            metric_value=cfg_hash_ok + up_hash_ok,
            expected_value=2,
            threshold_low=2,
            threshold_high=2,
            status="PASS" if cfg_hash_ok + up_hash_ok == 2 else "WARN",
        )

        entry = find_registry_entry(art.interstep_dir, art.sim_run)
        registry_ok = 1 if entry is not None else 0
        rb.add(
            test_id=f"cross_step{step_key}_registry_entry",
            test_name=f"STEP {step_key} SIM_RUN in registry",
            metric_name="entry_exists",
            metric_value=registry_ok,
            expected_value=1,
            threshold_low=1,
            threshold_high=1,
            status="PASS" if registry_ok else "WARN",
            notes=f"sim_run={art.sim_run}",
        )

        # Check manifest row_count by exact concatenation when feasible.
        exact_count, note = compute_exact_manifest_count(art.manifest_path, max_rows_to_scan=2_000_000)
        if note == "exact_count" and exact_count is not None and art.row_count is not None:
            status = "PASS" if int(exact_count) == int(art.row_count) else "FAIL"
            rb.add(
                test_id=f"cross_step{step_key}_manifest_rowcount",
                test_name=f"STEP {step_key} manifest row_count exact check",
                metric_name="difference",
                metric_value=int(exact_count) - int(art.row_count),
                expected_value=0,
                threshold_low=0,
                threshold_high=0,
                status=status,
            )
        elif note == "skipped_large_manifest":
            rb.add(
                test_id=f"cross_step{step_key}_manifest_rowcount",
                test_name=f"STEP {step_key} manifest row_count exact check",
                metric_name="status",
                metric_value=np.nan,
                status="WARN",
                notes="Skipped exact count for large manifest",
            )
        elif note.startswith("missing_chunk"):
            rb.add(
                test_id=f"cross_step{step_key}_manifest_rowcount",
                test_name=f"STEP {step_key} manifest row_count exact check",
                metric_name="status",
                metric_value=np.nan,
                status="FAIL",
                notes=note,
            )

        # Upstream consistency check via metadata hash recomputation.
        meta = art.metadata
        upstream_meta = meta.get("upstream") if isinstance(meta, dict) else None
        recomputed = _upstream_fingerprint(upstream_meta)
        if step_key != "1":
            if recomputed is None or not art.upstream_hash:
                rb.add(
                    test_id=f"cross_step{step_key}_upstream_hash",
                    test_name=f"STEP {step_key} upstream hash recomputation",
                    metric_name="status",
                    metric_value=np.nan,
                    status="WARN",
                    notes="Missing nested upstream metadata",
                )
            else:
                match = int(recomputed == art.upstream_hash)
                rb.add(
                    test_id=f"cross_step{step_key}_upstream_hash",
                    test_name=f"STEP {step_key} upstream hash recomputation",
                    metric_name="match",
                    metric_value=match,
                    expected_value=1,
                    threshold_low=1,
                    threshold_high=1,
                    status="PASS" if match == 1 else "FAIL",
                )

        # source_dataset path is expected from STEP 3 onward when the upstream
        # dataset is still present. Cascade cleanup may remove consumed
        # upstream folders, in which case source path existence is non-fatal.
        if int(step_key) >= 2:
            src_path = resolve_source_dataset_path(meta, art.run_dir)
            src_exists = int(src_path is not None and src_path.exists())
            upstream_key = str(int(step_key) - 1)
            upstream_art = artifacts.get(upstream_key)
            upstream_exists = bool(upstream_art and upstream_art.exists)
            upstream_matches = _lineage_prefix_match(upstream_art, art, int(step_key) - 1)
            source_required = int(step_key) >= 3 and upstream_exists and upstream_matches
            if src_exists:
                source_status = "PASS"
            elif int(step_key) < 3:
                source_status = "WARN"
            elif not upstream_exists:
                source_status = "WARN"
            elif not upstream_matches:
                source_status = "WARN"
            else:
                source_status = "FAIL"

            source_notes = str(src_path) if src_path is not None else "source_dataset missing"
            if not src_exists and int(step_key) >= 3 and not upstream_exists:
                source_notes = f"{source_notes}; upstream step {upstream_key} dataset unavailable"
            elif not src_exists and int(step_key) >= 3 and not upstream_matches:
                source_notes = (
                    f"{source_notes}; upstream step {upstream_key} sim_run does not match "
                    f"STEP {step_key} lineage"
                )
            rb.add(
                test_id=f"cross_step{step_key}_source_dataset",
                test_name=f"STEP {step_key} source_dataset exists",
                metric_name="path_exists",
                metric_value=src_exists,
                expected_value=1 if source_required else None,
                threshold_low=1 if source_required else None,
                threshold_high=1 if source_required else None,
                status=source_status,
                notes=source_notes,
            )

            # If source metadata is readable, compare hash hints.
            if src_path is not None and src_path.exists() and isinstance(upstream_meta, dict):
                src_meta = get_metadata_for_data_path(src_path)
                src_cfg_hash = src_meta.get("config_hash")
                up_cfg_hash = upstream_meta.get("config_hash")
                if src_cfg_hash is not None and up_cfg_hash is not None:
                    match = int(str(src_cfg_hash) == str(up_cfg_hash))
                    rb.add(
                        test_id=f"cross_step{step_key}_source_hash_match",
                        test_name=f"STEP {step_key} source metadata hash matches nested upstream",
                        metric_name="match",
                        metric_value=match,
                        expected_value=1,
                        threshold_low=1,
                        threshold_high=1,
                        status="PASS" if match == 1 else "WARN",
                    )

    # Row delta expectations across steps.
    pairs = [("1", "2"), ("2", "3"), ("3", "4"), ("4", "5"), ("5", "6"), ("6", "7"), ("7", "8"), ("8", "9"), ("9", "10")]
    same_expected = {("2", "3"), ("3", "4"), ("4", "5"), ("5", "6"), ("6", "7"), ("7", "8"), ("9", "10")}
    selection_expected = {("8", "9")}

    for a, b in pairs:
        art_a = artifacts.get(a)
        art_b = artifacts.get(b)
        if not _lineage_prefix_match(art_a, art_b, int(a)):
            rb.add(
                test_id=f"cross_rows_{a}_{b}",
                test_name=f"Row delta STEP {a}->{b}",
                metric_name="delta",
                metric_value=np.nan,
                status="SKIP",
                notes=f"Incompatible SIM_RUN lineage: {art_a.sim_run if art_a else None} vs {art_b.sim_run if art_b else None}",
            )
            continue

        na = row_counts.get(a)
        nb = row_counts.get(b)
        if na is None or nb is None:
            rb.add(
                test_id=f"cross_rows_{a}_{b}",
                test_name=f"Row delta STEP {a}->{b}",
                metric_name="delta",
                metric_value=np.nan,
                status="SKIP",
                notes="Missing row_count",
            )
            continue

        delta = int(nb) - int(na)
        ratio = (float(nb) / float(na)) if na else np.nan
        if (a, b) in same_expected:
            status = "PASS" if delta == 0 else "FAIL"
        elif (a, b) in selection_expected:
            status = "PASS" if nb <= na else "FAIL"
        else:
            # STEP 1->2 can naturally reduce strongly due acceptance.
            status = "PASS" if (0 < nb <= na) else "WARN"

        rb.add(
            test_id=f"cross_rows_{a}_{b}",
            test_name=f"Row delta STEP {a}->{b}",
            metric_name="delta",
            metric_value=delta,
            expected_value=0 if (a, b) in same_expected else None,
            status=status,
            notes=f"ratio={ratio:.6f}" if np.isfinite(ratio) else "",
        )

    # Event-id conservation checks.
    id_sets: dict[str, set[int] | None] = {}
    for step_key in [str(i) for i in range(2, 11)]:
        id_sets[step_key] = _load_event_id_set(artifacts.get(step_key))

    # STEP 1 is huge; range check against row_count.
    ids2 = id_sets.get("2")
    n1 = row_counts.get("1")
    if ids2 is not None and n1 is not None:
        out_of_range = int(sum((eid < 0 or eid >= n1) for eid in ids2))
        rb.add(
            test_id="cross_ids_1_2_range",
            test_name="STEP 2 event_id values are within STEP 1 row range",
            metric_name="out_of_range_ids",
            metric_value=out_of_range,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if out_of_range == 0 else "FAIL",
        )

    # Exact set equality where expected.
    exact_pairs = [("2", "3"), ("3", "4"), ("4", "5"), ("5", "6"), ("6", "7"), ("7", "8"), ("9", "10")]
    for a, b in exact_pairs:
        art_a = artifacts.get(a)
        art_b = artifacts.get(b)
        if not _lineage_prefix_match(art_a, art_b, int(a)):
            rb.add(
                test_id=f"cross_ids_{a}_{b}",
                test_name=f"event_id conservation STEP {a}->{b}",
                metric_name="set_diff",
                metric_value=np.nan,
                status="SKIP",
                notes=f"Incompatible SIM_RUN lineage: {art_a.sim_run if art_a else None} vs {art_b.sim_run if art_b else None}",
            )
            continue

        sa = id_sets.get(a)
        sb = id_sets.get(b)
        if sa is None or sb is None:
            rb.add(
                test_id=f"cross_ids_{a}_{b}",
                test_name=f"event_id conservation STEP {a}->{b}",
                metric_name="set_diff",
                metric_value=np.nan,
                status="SKIP",
                notes="Missing event_id set",
            )
            continue
        diff = len(sa.symmetric_difference(sb))
        rb.add(
            test_id=f"cross_ids_{a}_{b}",
            test_name=f"event_id conservation STEP {a}->{b}",
            metric_name="set_diff",
            metric_value=diff,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if diff == 0 else "FAIL",
        )

    # STEP 8->9 should be subset after trigger.
    s8 = id_sets.get("8")
    s9 = id_sets.get("9")
    if s8 is not None and s9 is not None:
        missing = len(s9 - s8)
        rb.add(
            test_id="cross_ids_8_9_subset",
            test_name="STEP 9 event_id subset of STEP 8",
            metric_name="unexpected_ids",
            metric_value=missing,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if missing == 0 else "FAIL",
        )

    # STEP 0 mesh -> STEP 1 metadata consistency for cos_n.
    art0 = artifacts.get("0")
    art1 = artifacts.get("1")
    if (
        art0 is None
        or art0.data_path is None
        or not art0.data_path.exists()
        or art1 is None
        or art1.data_path is None
        or not art1.data_path.exists()
    ):
        rb.add(
            test_id="cross_step1_cosn_mesh_match",
            test_name="STEP 1 config.cos_n matches STEP 0 mesh row",
            metric_name="status",
            metric_value=np.nan,
            status="SKIP",
            notes="STEP 0 or STEP 1 artifact missing",
        )
    else:
        meta1 = art1.metadata if isinstance(art1.metadata, dict) else {}
        cfg1 = meta1.get("config") if isinstance(meta1.get("config"), dict) else {}
        cos_raw = cfg1.get("cos_n")
        step1_id_raw = meta1.get("step_1_id", cfg1.get("step_1_id"))
        try:
            cos_meta = float(cos_raw)
            step1_id = int(float(step1_id_raw))
        except (TypeError, ValueError):
            rb.add(
                test_id="cross_step1_cosn_mesh_match",
                test_name="STEP 1 config.cos_n matches STEP 0 mesh row",
                metric_name="status",
                metric_value=np.nan,
                status="SKIP",
                notes="Missing or invalid STEP 1 config.cos_n / step_1_id in metadata",
            )
        else:
            try:
                mesh_df = pd.read_csv(art0.data_path, usecols=["step_1_id", "cos_n"])
            except Exception as exc:
                rb.add_exception(
                    test_id="cross_step1_cosn_mesh_match_read",
                    test_name="Read STEP 0 mesh for cos_n cross-check",
                    exc=exc,
                )
            else:
                mesh_step1 = pd.to_numeric(mesh_df["step_1_id"], errors="coerce")
                mesh_rows = mesh_df.loc[mesh_step1 == step1_id]
                if mesh_rows.empty:
                    rb.add(
                        test_id="cross_step1_cosn_mesh_match",
                        test_name="STEP 1 config.cos_n matches STEP 0 mesh row",
                        metric_name="status",
                        metric_value=np.nan,
                        status="FAIL",
                        notes=f"No param_mesh row with step_1_id={step1_id:03d}",
                    )
                else:
                    mesh_cos_vals = pd.to_numeric(mesh_rows["cos_n"], errors="coerce").dropna().unique()
                    if mesh_cos_vals.size == 0:
                        rb.add(
                            test_id="cross_step1_cosn_mesh_match",
                            test_name="STEP 1 config.cos_n matches STEP 0 mesh row",
                            metric_name="status",
                            metric_value=np.nan,
                            status="FAIL",
                            notes=f"param_mesh rows for step_1_id={step1_id:03d} have invalid cos_n",
                        )
                    elif mesh_cos_vals.size > 1:
                        rb.add(
                            test_id="cross_step1_cosn_mesh_match",
                            test_name="STEP 1 config.cos_n matches STEP 0 mesh row",
                            metric_name="status",
                            metric_value=np.nan,
                            status="FAIL",
                            notes=(
                                f"param_mesh has multiple cos_n values for step_1_id={step1_id:03d}: "
                                f"{mesh_cos_vals.tolist()}"
                            ),
                        )
                    else:
                        mesh_cos = float(mesh_cos_vals[0])
                        diff = abs(cos_meta - mesh_cos)
                        rb.add(
                            test_id="cross_step1_cosn_mesh_match",
                            test_name="STEP 1 config.cos_n matches STEP 0 mesh row",
                            metric_name="abs_difference",
                            metric_value=diff,
                            expected_value=0.0,
                            threshold_low=0.0,
                            threshold_high=1e-12,
                            status="PASS" if diff <= 1e-12 else "FAIL",
                            notes=(
                                f"step_1_id={step1_id:03d}, meta={cos_meta:.12g}, mesh={mesh_cos:.12g}"
                            ),
                        )

    if make_plots:
        _plot_row_counts(row_counts, output_dir / "plots" / "validate_cross_step_lineage")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
