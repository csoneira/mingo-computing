from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

STEP21_DIR = (
    Path(__file__).resolve().parents[1] / "STEP_2_1_ESTIMATE_PARAMS"
)
if str(STEP21_DIR) not in sys.path:
    sys.path.insert(0, str(STEP21_DIR))

import estimate_and_plot as step21  # noqa: E402


def test_grouped_case_payload_keeps_histogram_for_plot_when_weight_is_zero() -> None:
    dict_df = pd.DataFrame(
        {
            "scalar_feature": [0.0, 1.0],
            "events_per_second_0_rate_hz": [5.0, 6.0],
            "events_per_second_1_rate_hz": [7.0, 8.0],
        }
    )
    data_df = pd.DataFrame(
        {
            "scalar_feature": [0.2],
            "events_per_second_0_rate_hz": [5.5],
            "events_per_second_1_rate_hz": [7.5],
        }
    )
    distance_definition = {
        "available": True,
        "center": [0.0],
        "scale": [1.0],
        "weights": [1.0],
        "p_norm": 2.0,
        "scalar_feature_columns": ["scalar_feature"],
        "feature_groups": {
            "rate_histogram": {
                "feature_columns": [
                    "events_per_second_0_rate_hz",
                    "events_per_second_1_rate_hz",
                ]
            }
        },
        "group_weights": {
            "rate_histogram": 0.0,
        },
    }

    payload = step21._build_grouped_case_payload(
        dict_df=dict_df,
        data_df=data_df,
        feature_cols=["scalar_feature"],
        distance_definition=distance_definition,
        row_idx=0,
        top_k=1,
    )

    assert payload is not None
    assert "histogram" in payload
    assert payload["histogram"]["columns"] == [
        "events_per_second_0_rate_hz",
        "events_per_second_1_rate_hz",
    ]
    assert payload["histogram"]["active"] is False
    assert float(payload["histogram"]["weight"]) == 0.0


def test_require_selected_feature_columns_present_rejects_feature_drift() -> None:
    dict_df = pd.DataFrame({"feature_a": [1.0], "feature_b": [2.0]})
    data_df = pd.DataFrame({"feature_a": [1.5]})

    try:
        step21._require_selected_feature_columns_present(
            ["feature_a", "feature_b"],
            dict_df=dict_df,
            data_df=data_df,
        )
    except ValueError as exc:
        assert "missing in dataset" in str(exc)
        assert "feature_b" in str(exc)
    else:
        raise AssertionError("Expected ValueError for selected-feature drift")
