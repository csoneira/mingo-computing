from pathlib import Path
import sys

import pandas as pd

MODULES_DIR = Path(__file__).resolve().parents[1]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from feature_space_transform_engine import apply_feature_space_transform


def test_apply_feature_space_transform_applies_keep_and_new_dimensions():
    df = pd.DataFrame(
        {
            "base_a": [1.0, 2.0],
            "base_b": [10.0, 20.0],
        }
    )
    feature_space_cfg = {
        "kept": ["base_a"],
        "new": {"sum_ab": "base_a + base_b"},
        "transformations": {
            "derive_canonical_global_rate": False,
            "derive_empirical_efficiencies": False,
            "derive_physics_helpers": False,
            "derive_post_tt_plane_aggregates": False,
            "keep_only_best_tt_prefix": False,
        },
    }

    out, info = apply_feature_space_transform(
        df,
        cfg_12={},
        feature_space_cfg=feature_space_cfg,
    )

    assert list(out["sum_ab"]) == [11.0, 22.0]
    assert info["column_transform_cfg"]["enabled"] is True
    assert info["column_transform_info"]["final_keep_dimensions"] == ["base_a", "sum_ab"]
    assert info["missing_keep_dimensions"] == []


def test_apply_feature_space_transform_can_backfill_empirical_efficiencies():
    df = pd.DataFrame(
        {
            "post_tt_1234_rate_hz": [80.0, 90.0],
            "post_tt_234_rate_hz": [20.0, 10.0],
            "post_tt_134_rate_hz": [20.0, 10.0],
            "post_tt_124_rate_hz": [20.0, 10.0],
            "post_tt_123_rate_hz": [20.0, 10.0],
            "events_per_second_global_rate": [1.0, 1.2],
        }
    )

    out, info = apply_feature_space_transform(
        df,
        cfg_12={},
        feature_space_cfg={
            "transformations": {
                "derive_canonical_global_rate": True,
                "derive_empirical_efficiencies": True,
                "derive_physics_helpers": True,
                "derive_post_tt_plane_aggregates": False,
                "keep_only_best_tt_prefix": False,
            }
        },
        backfill_efficiency_from_empirical_enabled=True,
    )

    assert "eff_empirical_1" in out.columns
    assert "eff_p1" in out.columns
    assert "eff_sim_1" in out.columns
    assert "efficiency_product_4planes" in out.columns
    assert info["backfilled_efficiency_columns"] >= 2

