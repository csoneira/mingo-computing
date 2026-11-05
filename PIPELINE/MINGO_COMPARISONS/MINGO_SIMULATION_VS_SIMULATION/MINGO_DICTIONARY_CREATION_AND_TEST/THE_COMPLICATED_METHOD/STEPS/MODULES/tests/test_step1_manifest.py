from pathlib import Path
import sys

MODULES_DIR = Path(__file__).resolve().parents[1]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from step1_manifest import (  # noqa: E402
    build_step1_feature_manifest,
    load_step1_feature_manifest,
    manifest_primary_feature_columns,
    manifest_target_columns,
    write_step1_feature_manifest,
)


def test_manifest_build_and_roundtrip(tmp_path: Path) -> None:
    manifest = build_step1_feature_manifest(
        input_csv="in.csv",
        output_csv="out.csv",
        ancillary_csv="anc.csv",
        feature_space_config_path="cfg.json",
        feature_space_config_loaded=True,
        input_columns=["a", "b", "meta", "param"],
        output_columns=["a", "anc", "meta", "param"],
        primary_feature_columns=["a"],
        ancillary_columns=["anc"],
        general_passthrough_columns=["meta"],
        parameter_passthrough_columns=["param"],
        legacy_passthrough_columns=[],
        declared_feature_dimensions=["a", "new_col"],
        declared_new_dimensions=["new_col"],
    )
    path = tmp_path / "feature_space_manifest.json"
    write_step1_feature_manifest(path, manifest)
    loaded = load_step1_feature_manifest(path)

    assert loaded["columns"]["primary_feature_columns"] == ["a"]
    assert loaded["columns"]["ancillary_columns"] == ["anc"]
    assert loaded["columns"]["general_passthrough_columns"] == ["meta"]
    assert loaded["columns"]["parameter_passthrough_columns"] == ["param"]
    assert loaded["columns"]["dropped_from_input_columns"] == ["b"]


def test_manifest_target_columns_support_real_data_view() -> None:
    manifest = build_step1_feature_manifest(
        input_csv="in.csv",
        output_csv="out.csv",
        ancillary_csv=None,
        feature_space_config_path="cfg.json",
        feature_space_config_loaded=True,
        input_columns=["feat1", "feat2", "anc1", "meta1", "param1"],
        output_columns=["feat1", "feat2", "anc1", "meta1", "param1"],
        primary_feature_columns=["feat1", "feat2"],
        ancillary_columns=["anc1"],
        general_passthrough_columns=["meta1"],
        parameter_passthrough_columns=["param1"],
        legacy_passthrough_columns=[],
        declared_feature_dimensions=["feat1", "feat2"],
        declared_new_dimensions=[],
    )

    assert manifest_primary_feature_columns(manifest) == ["feat1", "feat2"]
    assert manifest_target_columns(
        manifest,
        include_primary_features=True,
        include_ancillary=True,
        include_general_passthrough=True,
        include_parameter_passthrough=False,
    ) == ["feat1", "feat2", "anc1", "meta1"]
