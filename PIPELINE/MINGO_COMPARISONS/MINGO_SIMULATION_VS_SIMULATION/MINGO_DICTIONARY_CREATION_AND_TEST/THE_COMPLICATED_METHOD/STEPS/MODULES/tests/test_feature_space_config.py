from pathlib import Path
import sys

MODULES_DIR = Path(__file__).resolve().parents[1]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from feature_space_config import (
    extract_ancillary_columns,
    extract_feature_dimensions,
    load_feature_space_config,
    resolve_ancillary_feature_space_columns,
    resolve_feature_group_config_path,
    resolve_feature_space_config_path,
    resolve_feature_space_group_definitions,
    resolve_feature_space_transform_options,
    resolve_materialized_feature_space_columns,
    resolve_selected_feature_space_columns,
)


def test_materialized_columns_use_feature_space_config_patterns():
    cols = [
        "filename_base",
        "events_per_second_global_rate",
        "events_per_second_0_rate_hz",
        "post_tt_123_rate_hz",
        "fit_to_post_tt_123_rate_hz",
    ]
    cfg = {
        "materialized_columns": {
            "include": ["filename_base", "events_per_second_*_rate_hz", "*_tt_*_rate_hz"],
            "exclude": ["events_per_second_global_rate", "*_to_*_tt_*_rate_hz"],
        }
    }
    resolved, info = resolve_materialized_feature_space_columns(
        available_columns=cols,
        feature_space_cfg=cfg,
        fallback_patterns=["filename_base"],
    )
    assert resolved == [
        "filename_base",
        "events_per_second_0_rate_hz",
        "post_tt_123_rate_hz",
    ]
    assert info["used_feature_space_config"] is True


def test_selected_feature_columns_allow_all_minus_excludes():
    cols = [
        "eff_empirical_1",
        "events_per_second_global_rate",
        "events_per_second_0_rate_hz",
        "post_tt_123_rate_hz",
    ]
    cfg = {
        "selected_feature_columns": {
            "exclude": ["events_per_second_global_rate"],
        }
    }
    resolved, info = resolve_selected_feature_space_columns(
        available_columns=cols,
        feature_space_cfg=cfg,
        fallback_columns=[],
    )
    assert resolved == [
        "eff_empirical_1",
        "events_per_second_0_rate_hz",
        "post_tt_123_rate_hz",
    ]
    assert info["include_all_if_omitted"] is True


def test_selected_feature_columns_fall_back_to_explicit_columns():
    resolved, info = resolve_selected_feature_space_columns(
        available_columns=["a", "b", "c"],
        feature_space_cfg={},
        fallback_columns=["b", "a"],
    )
    assert resolved == ["b", "a"]
    assert info["used_feature_space_config"] is False


def test_extract_feature_dimensions_includes_new_dimensions():
    cfg = {
        "step_1_2": "ignored",
        "kept": ["events_per_second_0_rate_hz", "events_per_second_1_rate_hz"],
        "new": {
            "post_tt_two_plane_total_rate_hz": "a + b",
            "post_tt_four_plane_rate_hz": "c",
        },
    }
    assert extract_feature_dimensions(cfg) == [
        "events_per_second_0_rate_hz",
        "events_per_second_1_rate_hz",
        "post_tt_two_plane_total_rate_hz",
        "post_tt_four_plane_rate_hz",
    ]


def test_ancillary_columns_resolve_explicit_columns_and_patterns():
    cols = [
        "events_per_second_global_rate",
        "eff_empirical_1",
        "post_tt_two_plane_total_rate_hz",
        "efficiency_vector_p1_x_bin_000_eff",
    ]
    cfg = {
        "ancillary_columns": {
            "rate": ["events_per_second_global_rate"],
            "efficiency_scalars": ["eff_empirical_*"],
            "post_tt_totals": ["post_tt_two_plane_total_rate_hz"],
        }
    }

    assert extract_ancillary_columns(cfg) == [
        "events_per_second_global_rate",
        "eff_empirical_*",
        "post_tt_two_plane_total_rate_hz",
    ]

    resolved, info = resolve_ancillary_feature_space_columns(
        available_columns=cols,
        feature_space_cfg=cfg,
    )

    assert resolved == [
        "events_per_second_global_rate",
        "eff_empirical_1",
        "post_tt_two_plane_total_rate_hz",
    ]
    assert info["used_feature_space_config"] is True
    assert info["unmatched_include_patterns"] == []


def test_transform_options_override_defaults():
    opts = resolve_feature_space_transform_options(
        feature_space_cfg={
            "transformations": {
                "derive_canonical_global_rate": False,
                "derive_empirical_efficiencies": False,
                "derive_physics_helpers": True,
                "derive_post_tt_plane_aggregates": True,
                "keep_only_best_tt_prefix": False,
                "tt_prefix_priority": ["fit_tt", "post_tt"],
            }
        },
        default_tt_prefix_priority=("post_tt", "fit_tt"),
    )
    assert opts == {
        "derive_canonical_global_rate": False,
        "derive_empirical_efficiencies": False,
        "derive_physics_helpers": True,
        "derive_post_tt_plane_aggregates": True,
        "keep_only_best_tt_prefix": False,
        "tt_prefix_priority": ("fit_tt", "post_tt"),
    }


def test_resolve_feature_space_config_path_prefers_override(tmp_path: Path):
    path = resolve_feature_space_config_path(
        tmp_path,
        config={"feature_space_config_json": "custom.json"},
        step_cfg={},
    )
    assert path == (tmp_path / "custom.json").resolve()


def test_resolve_feature_space_config_path_prefers_primary_default_name(tmp_path: Path):
    primary = tmp_path / "config_step_1.2_feature_space.json"
    primary.write_text("{}", encoding="utf-8")
    path = resolve_feature_space_config_path(tmp_path, config={}, step_cfg={})
    assert path == primary


def test_resolve_feature_space_config_path_falls_back_to_legacy_default_name(tmp_path: Path):
    legacy = tmp_path / "config_feature_space.json"
    legacy.write_text("{}", encoding="utf-8")
    path = resolve_feature_space_config_path(tmp_path, config={}, step_cfg={})
    assert path == legacy


def test_resolve_feature_group_config_path_prefers_primary_default_name(tmp_path: Path):
    primary = tmp_path / "config_step_1.5_feature_groups.json"
    primary.write_text("{}", encoding="utf-8")
    path = resolve_feature_group_config_path(tmp_path, config={}, step_cfg={})
    assert path == primary


def test_resolve_feature_group_config_path_falls_back_to_feature_space(tmp_path: Path):
    primary_space = tmp_path / "config_step_1.2_feature_space.json"
    primary_space.write_text("{}", encoding="utf-8")
    path = resolve_feature_group_config_path(tmp_path, config={}, step_cfg={})
    assert path == primary_space


def test_load_feature_space_config_returns_empty_on_invalid_json(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("{ bad", encoding="utf-8")
    assert load_feature_space_config(p) == {}


def test_resolve_feature_space_group_definitions_uses_explicit_patterns():
    cols = [
        "eff_empirical_2",
        "events_per_second_0_rate_hz",
        "events_per_second_1_rate_hz",
        "efficiency_vector_p1_x_bin_000_eff",
        "efficiency_vector_p1_x_bin_001_eff",
        "noise_col",
    ]
    cfg = {
        "feature_groups": {
            "rate_histogram": {
                "enabled": True,
                "blend_mode": "normalized",
                "feature_columns": {
                    "include": ["events_per_second_*_rate_hz"],
                },
            },
            "efficiency_vectors": {
                "enabled": True,
                "feature_columns": {
                    "include": ["efficiency_vector_p*_x_bin_*_eff"],
                },
            },
        }
    }

    resolved, info = resolve_feature_space_group_definitions(
        available_columns=cols,
        feature_space_cfg=cfg,
    )

    assert resolved["rate_histogram"]["feature_columns"] == [
        "events_per_second_0_rate_hz",
        "events_per_second_1_rate_hz",
    ]
    assert resolved["efficiency_vectors"]["feature_columns"] == [
        "efficiency_vector_p1_x_bin_000_eff",
        "efficiency_vector_p1_x_bin_001_eff",
    ]
    assert info["used_feature_space_config"] is True
