#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd


STEP15_DIR = (
    Path(__file__).resolve().parents[1]
    / "STEP_1_5_TUNE_DISTANCE_DEFINITION"
)
if str(STEP15_DIR) not in sys.path:
    sys.path.insert(0, str(STEP15_DIR))

from tune_distance_definition import (
    _apply_group_weight_floors,
    _build_feature_group_inputs,
    _exclude_holdout_rows_with_dictionary_parameter_overlap,
    _filter_complete_tuning_rows,
    _load_parameter_space_columns,
    _rerank_distance_candidates_on_holdout,
    _select_holdout_inverse_mapping_configuration,
    _resolve_group_weight_candidates,
)


def test_parameter_columns_resolve_effsim_alias_to_effp_when_needed(tmp_path: Path) -> None:
    payload = {
        "parameter_space_columns_downstream_preferred": [
            "flux_cm2_min",
            "eff_sim_1",
            "eff_sim_2",
            "eff_sim_3",
            "eff_sim_4",
        ],
        "parameter_space_column_aliases": {
            "eff_p1": "eff_sim_1",
            "eff_sim_1": "eff_sim_1",
            "eff_p2": "eff_sim_2",
            "eff_sim_2": "eff_sim_2",
            "eff_p3": "eff_sim_3",
            "eff_sim_3": "eff_sim_3",
            "eff_p4": "eff_sim_4",
            "eff_sim_4": "eff_sim_4",
        },
    }
    p = tmp_path / "parameter_space_columns.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    resolved = _load_parameter_space_columns(
        p,
        available_columns=["flux_cm2_min", "eff_p1", "eff_p2", "eff_p3", "eff_p4"],
    )
    assert resolved == [
        "flux_cm2_min",
        "eff_p1",
        "eff_p2",
        "eff_p3",
        "eff_p4",
    ]


def test_group_weight_candidates_respect_group_min_weight() -> None:
    feature_groups = {
        "rate_histogram": {
            "min_weight": 0.25,
        }
    }

    candidates = _resolve_group_weight_candidates(
        feature_groups=feature_groups,
        group_name="rate_histogram",
        raw_candidates=[0.0, 0.25, 0.5, 1.0],
    )

    assert candidates == [0.25, 0.5, 1.0]


def test_group_weight_floors_keep_mandatory_groups_active() -> None:
    feature_groups = {
        "rate_histogram": {"min_weight": 0.25},
        "efficiency_vectors": {"min_weight": 0.25},
    }

    clamped = _apply_group_weight_floors(
        {"rate_histogram": 0.0, "efficiency_vectors": 1.0},
        feature_groups=feature_groups,
    )

    assert clamped == {
        "rate_histogram": 0.25,
        "efficiency_vectors": 1.0,
    }


def test_build_feature_group_inputs_preserves_group_min_weight() -> None:
    dictionary = pd.DataFrame(
        {
            "events_per_second_0_rate_hz": [0.6, 0.5, 0.4],
            "events_per_second_1_rate_hz": [0.4, 0.5, 0.6],
        }
    )

    _, _, _, feature_groups, group_weights, _ = _build_feature_group_inputs(
        dictionary_df=dictionary,
        feature_cols=[
            "events_per_second_0_rate_hz",
            "events_per_second_1_rate_hz",
        ],
        inverse_cfg={},
        feature_group_defs={
            "rate_histogram": {
                "enabled": True,
                "min_weight": 0.25,
                "feature_columns": [
                    "events_per_second_0_rate_hz",
                    "events_per_second_1_rate_hz",
                ],
            }
        },
    )

    assert group_weights["rate_histogram"] == 1.0
    assert feature_groups["rate_histogram"]["min_weight"] == 0.25


def test_filter_complete_tuning_rows_drops_incomplete_rows_and_requires_columns() -> None:
    dictionary = pd.DataFrame(
        {
            "feature_a": [1.0, 2.0, None],
            "feature_b": [3.0, None, 5.0],
            "flux_cm2_min": [0.1, 0.2, 0.3],
        }
    )

    filtered, info = _filter_complete_tuning_rows(
        dictionary,
        feature_cols=["feature_a", "feature_b"],
        param_cols=["flux_cm2_min"],
        label="dictionary",
    )

    assert filtered.to_dict(orient="list") == {
        "feature_a": [1.0],
        "feature_b": [3.0],
        "flux_cm2_min": [0.1],
    }
    assert int(info["rows_removed"]) == 2
    assert int(info["rows_kept"]) == 1


def test_select_holdout_inverse_mapping_configuration_can_change_neighbor_count(
    monkeypatch,
) -> None:
    score_map = {
        ("weighted_mean", 80, 1e6): 4.0,
        ("weighted_median", 80, 1e6): 2.0,
        ("weighted_median", 20, 1e6): 0.8,
        ("local_linear", 80, 1.0): 1.5,
    }

    def _fake_score(
        *,
        aggregation_mode: str,
        neighbor_count: int,
        ridge_lambda: float,
        **_kwargs,
    ) -> float:
        return float(score_map.get((str(aggregation_mode), int(neighbor_count), float(ridge_lambda)), 9.0))

    monkeypatch.setattr(
        "tune_distance_definition._holdout_inverse_mapping_score",
        _fake_score,
    )

    best_agg, best_k, best_lambda, best_score, holdout_scores = _select_holdout_inverse_mapping_configuration(
        dictionary_df=pd.DataFrame({"feature_a": [1.0]}),
        dataset_df=pd.DataFrame({"feature_a": [1.0]}),
        feature_cols=["feature_a"],
        param_cols=["flux_cm2_min"],
        base_distance_definition={"feature_columns": ["feature_a"]},
        aggregation_candidates=["weighted_mean", "weighted_median", "local_linear"],
        k_candidates=[80, 20],
        lambda_grid=[1.0],
        default_k=80,
        default_lambda=1.0,
        use_in_coverage_only=True,
    )

    assert best_agg == "weighted_median"
    assert best_k == 20
    assert best_lambda == 1e6
    assert best_score == 0.8
    assert any(
        row["selected"]
        and row["aggregation"] == "weighted_median"
        and int(row["neighbor_count"]) == 20
        for row in holdout_scores
    )


def test_rerank_distance_candidates_on_holdout_prefers_best_holdout_score() -> None:
    candidates = [
        {"label": "cand_a", "dictionary_score": 0.4},
        {"label": "cand_b", "dictionary_score": 0.2},
        {"label": "cand_c", "dictionary_score": 0.3},
    ]
    holdout_scores = {
        "cand_b": (1.4, "weighted_mean", 20, 1e6),
        "cand_c": (0.8, "weighted_median", 15, 1e6),
    }

    def _score(candidate: dict[str, object]) -> tuple[float, str, int, float]:
        return holdout_scores[str(candidate["label"])]

    selected, diagnostics = _rerank_distance_candidates_on_holdout(
        candidates,
        top_n=2,
        scorer=_score,
    )

    assert selected is not None
    assert selected["label"] == "cand_c"
    assert float(selected["holdout_score"]) == 0.8
    assert str(selected["holdout_selected_aggregation"]) == "weighted_median"
    assert int(selected["holdout_selected_k"]) == 15
    assert len(diagnostics) == 2
    assert [str(row["label"]) for row in diagnostics] == ["cand_b", "cand_c"]
    assert sum(bool(row["selected"]) for row in diagnostics) == 1


def test_exclude_holdout_rows_with_dictionary_parameter_overlap_uses_physical_tuple() -> None:
    dictionary = pd.DataFrame(
        {
            "param_hash_x": ["dict_hash"],
            "flux_cm2_min": [1.2],
            "eff_sim_1": [0.81],
            "eff_sim_2": [0.82],
            "eff_sim_3": [0.83],
            "eff_sim_4": [0.84],
            "z_plane_1": [0.0],
            "z_plane_2": [1.0],
            "z_plane_3": [2.0],
            "z_plane_4": [3.0],
        }
    )
    holdout = pd.DataFrame(
        {
            "param_hash_x": ["different_hash", "holdout_only"],
            "flux_cm2_min": [1.2, 1.5],
            "eff_sim_1": [0.81, 0.71],
            "eff_sim_2": [0.82, 0.72],
            "eff_sim_3": [0.83, 0.73],
            "eff_sim_4": [0.84, 0.74],
            "z_plane_1": [0.0, 0.0],
            "z_plane_2": [1.0, 1.0],
            "z_plane_3": [2.0, 2.0],
            "z_plane_4": [3.0, 3.0],
        }
    )

    filtered, info = _exclude_holdout_rows_with_dictionary_parameter_overlap(
        dictionary,
        holdout,
    )

    assert filtered["param_hash_x"].tolist() == ["holdout_only"]
    assert int(info["rows_removed"]) == 1
    assert int(info["overlap_via_hash_count"]) == 0
    assert int(info["overlap_via_physical_tuple_count"]) == 1
