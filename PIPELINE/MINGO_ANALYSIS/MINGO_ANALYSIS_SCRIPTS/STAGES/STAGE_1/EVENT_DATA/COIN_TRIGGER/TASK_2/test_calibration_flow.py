"""Test Task 2 calibration-sample flow and filtering behavior."""

import ast
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yaml


SCRIPT_PATH = Path(__file__).with_name("script_2_clean_to_cal.py")
CALIBRATION_CONFIG_PATH = (
    Path(__file__).parents[5]
    / "SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_2/config_calibration_subsample_task_2.yaml"
)


def _source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def _config() -> dict[str, object]:
    return yaml.safe_load(CALIBRATION_CONFIG_PATH.read_text(encoding="utf-8"))


def test_river_yaml_has_ordered_main_filters_and_calibration_stages() -> None:
    config = _config()
    assert config["version"] == 3
    assert list(config["main_subsample"]["preprocessing"]["charge_zeroing"]) == [
        "enabled", "channel", "strip", "plane", "detector",
    ]
    assert list(config["main_subsample"]["row_filters"]) == [
        "topology",
        "raw_tsum",
    ]
    assert list(config["calibration_flow"]) == [
        "charge_pedestal",
        "t_dif",
        "qfb",
        "q_tdif",
        "t_sum",
        "slewing",
    ]
    for stage in config["calibration_flow"].values():
        assert "enabled" in stage
        assert "fit_mask" in stage
        assert stage["application_mask"] == {"active_strip": True}
        assert "post_application_filter" in stage


def test_requested_branch_topologies_are_explicit() -> None:
    flow = _config()["calibration_flow"]
    assert flow["charge_pedestal"]["fit_mask"]["strip_topology"] == [
        "1000", "0100", "0010", "0001", "1100", "0110", "0011",
    ]
    assert flow["t_dif"]["fit_mask"]["strip_topology"][:4] == [
        "1000", "0100", "0010", "0001",
    ]
    assert flow["qfb"]["fit_mask"]["strip_topology"] == [
        "1000", "0100", "0010", "0001", "1110", "0111", "1111",
    ]
    assert flow["q_tdif"]["fit_mask"]["strip_topology"] == flow["qfb"]["fit_mask"]["strip_topology"]
    assert flow["t_sum"]["fit_mask"]["plane_combination"] == [1234, 123, 234]
    assert flow["t_sum"]["fit_mask"]["use_high_common_charge_cut"] is False
    cdf_diagnostic = flow["t_dif"]["cdf_top_hat_diagnostic"]
    assert cdf_diagnostic["enabled"] is True
    assert cdf_diagnostic["plane_combination"] == [1234, 124, 134]
    assert flow["t_dif"]["fit_mask"]["plane_combination"] == [1234, 123, 234, 124, 134]


def test_obsolete_qfb_and_one_strip_controls_are_removed() -> None:
    source = _source()
    config_text = CALIBRATION_CONFIG_PATH.read_text(encoding="utf-8")
    for removed_name in (
        "_task2_validate_qfb_coefficients",
        "_task2_validate_qfb_for_working_channel",
        "qfb_full_sample_validation",
        "fit_requires_exactly_one_strip_per_plane",
        "task2_charge_component_backup_df",
    ):
        assert removed_name not in source
        assert removed_name not in config_text


def test_qfb_and_qtdif_share_broad_application_functions() -> None:
    source = _source()
    assert source.count("apply_task2_qfb_correction(") == 3  # definition + calibration + working
    assert source.count("apply_task2_qtdif_correction(") == 3
    assert 'qfb_river_config["application_mask"]' in source
    assert 'qtdif_river_config["application_mask"]' in source
    assert "calibration_df.loc[cond, qdif_col]" not in source


def test_calibrated_tsum_histogram_uses_river_filter_window_by_default() -> None:
    source = _source()
    assert '_task2_tsum_plot_filter_config = calibration_flow_config["t_sum"]["post_application_filter"]' in source
    assert 'config.get("task2_qt_histogram_tsum_xlim_left", _task2_tsum_plot_default_left)' in source
    assert 'config.get("task2_qt_histogram_tsum_xlim_right", _task2_tsum_plot_default_right)' in source
    assert "return values.clip(" not in source
    assert "def _task2_qt_histogram_plot_values(" in source
    assert "limits = task2_qt_histogram_plot_limits.get(kind)" in source
    assert "visible_values = values[(values >= left) & (values <= right)]" in source


def test_crosstalk_center_diagnostic_uses_three_and_four_strip_minima_only() -> None:
    charge_pedestal = _config()["calibration_flow"]["charge_pedestal"]
    flow = charge_pedestal["crosstalk_center_diagnostic"]
    assert charge_pedestal["production_offset_method"] == "three_strip_crosstalk_sigmoid"
    assert flow["enabled"] is True
    assert flow["strip_counts"] == [3, 4]
    assert flow["offset_candidate_strip_count"] == 3
    assert flow["charge_range_adc"] == [80.0, 100.0]
    source = _source()
    assert '"three_strip": _fit_logistic_cdf_to_crosstalk_sample(three_values)' in source
    assert '"four_strip": _fit_logistic_cdf_to_crosstalk_sample(four_values)' in source
    assert "(qsum == minimum[:, np.newaxis])" in source
    pedestal_start = source.index("def calibrate_strip_Q_pedestal(")
    pedestal_end = source.index("def _save_charge_pedestal_derivation_figures(", pedestal_start)
    pedestal_body = source[pedestal_start:pedestal_end]
    assert "_select_charge_pedestal_offset(" in pedestal_body
    assert '"three_strip"' in pedestal_body


def test_three_strip_sigmoid_is_selected_and_failed_fit_uses_legacy_fallback() -> None:
    module = ast.parse(_source())
    function = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_select_charge_pedestal_offset"
    )
    namespace = {"np": np}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SCRIPT_PATH), "exec"), namespace)
    choose = namespace["_select_charge_pedestal_offset"]

    applied, method = choose(
        94.0,
        "derivative of smoothed CDF",
        {"status": "fit_succeeded", "center": 91.5},
        "three_strip_crosstalk_sigmoid",
    )
    assert applied == 91.5
    assert method == "three-strip minimum-charge crosstalk sigmoid"

    applied, method = choose(
        94.0,
        "derivative of smoothed CDF",
        {"status": "fit_failed"},
        "three_strip_crosstalk_sigmoid",
    )
    assert applied == 94.0
    assert method == "legacy fallback: derivative of smoothed CDF"


def test_crosstalk_logistic_cdf_recovers_synthetic_center_and_width() -> None:
    tree = ast.parse(_source())
    fit_node = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_fit_logistic_cdf_to_crosstalk_sample"
    )
    namespace: dict[str, object] = {"np": np}
    exec(compile(ast.Module(body=[fit_node], type_ignores=[]), str(SCRIPT_PATH), "exec"), namespace)
    rng = np.random.default_rng(3204)
    sample = rng.logistic(loc=92.0, scale=4.5, size=20000)
    fit = namespace["_fit_logistic_cdf_to_crosstalk_sample"](sample)
    assert fit["status"] == "fit_succeeded"
    assert abs(float(fit["center"]) - 92.0) < 0.25
    assert abs(float(fit["logistic_scale"]) - 4.5) < 0.35
    assert abs(float(fit["width_10_90"]) - 2 * np.log(9) * 4.5) < 1.0


def test_unbinned_top_hat_cdf_recovers_uniform_interval() -> None:
    tree = ast.parse(_source())
    fit_node = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_fit_tdif_top_hat_cdf"
    )
    namespace: dict[str, object] = {"np": np}
    exec(compile(ast.Module(body=[fit_node], type_ignores=[]), str(SCRIPT_PATH), "exec"), namespace)
    rng = np.random.default_rng(117)
    values = rng.uniform(-3.2, 5.7, size=12000)
    result = namespace["_fit_tdif_top_hat_cdf"](values)
    assert result["status"] == "fit_succeeded"
    assert abs(float(result["a"]) - (-3.2)) < 0.12
    assert abs(float(result["b"]) - 5.7) < 0.12
    assert abs(float(result["center"]) - 1.25) < 0.1
    assert float(result["rmse"]) < 0.01


def test_tdif_cdf_diagnostic_renders_candidate_and_reference_curves(tmp_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tree = ast.parse(_source())
    plot_node = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_save_tdif_cdf_top_hat_diagnostic"
    )
    output_path = tmp_path / "1_tdif_cdf_top_hat_diagnostic_4x4.png"

    def _save_plot(path, *, fig, **_kwargs):
        fig.savefig(path)

    namespace: dict[str, object] = {
        "np": np,
        "plt": plt,
        "os": __import__("os"),
        "task2_plot_requested": lambda *_args, **_kwargs: True,
        "save_plot_figure": _save_plot,
        "base_directories": {"figure_directory": str(tmp_path)},
        "index_of_cal_plot": 1,
    }
    exec(compile(ast.Module(body=[plot_node], type_ignores=[]), str(SCRIPT_PATH), "exec"), namespace)
    rng = np.random.default_rng(991)
    values = rng.uniform(-2.0, 3.0, size=1000)
    fit_tree = ast.parse(_source())
    fit_node = next(
        node for node in fit_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_fit_tdif_top_hat_cdf"
    )
    fit_namespace: dict[str, object] = {"np": np}
    exec(compile(ast.Module(body=[fit_node], type_ignores=[]), str(SCRIPT_PATH), "exec"), fit_namespace)
    fit = fit_namespace["_fit_tdif_top_hat_cdf"](values)
    diagnostic = {
        (plane, strip): {
            "fit": fit,
            "reference_values": values + 0.2,
            "current_offset": 0.5,
            "same_sample_offset": 0.4,
        }
        for plane in range(1, 5)
        for strip in range(1, 5)
    }
    namespace["_save_tdif_cdf_top_hat_diagnostic"](
        diagnostic,
        plane_combinations=[1234, 124, 134],
    )
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_top_hat_tdif_plot_is_enabled_without_changing_production_mask() -> None:
    plot_config = yaml.safe_load(
        (CALIBRATION_CONFIG_PATH.parents[0] / "config_plots_task_2.yaml").read_text(encoding="utf-8")
    )
    assert "tdif_cdf_top_hat_diagnostic_4x4" in plot_config["-plot"]
    source = _source()
    assert 'tdif_cdf_config.get(' in source
    assert 'plane_combination", [1234, 124, 134]' in source
    assert 'tdif_river_config["fit_mask"]' in source
    assert "Production offsets are unchanged." in source


def test_charge_gate_histogram_plots_the_quantities_actually_gated() -> None:
    source = _source()
    assert "plt.subplots(4, 2" in source
    assert 'enumerate(_axes[0])' in source and 'enumerate(_axes[3])' in source
    assert '"Raw Q-side charge"' in source
    assert '"Strip Q_sum charge"' in source


def test_only_initial_main_filters_replace_calibration_rows() -> None:
    source = _source()
    assert source.count("calibration_df = calibration_df.loc[") == 1
    assert "calibration_df = calibration_df.loc[_main_row_mask].copy()" in source
    assert "filter_task2_calibration_rows_by_strip_t_sum_window(" in source


def _selection_function_namespace() -> dict[str, object]:
    selected_names = {
        "_task2_active_strip_matrix_from_raw",
        "_coerce_config_bool",
        "_task2_plane_topology_labels_from_active",
        "_task2_active_plane_combination_labels",
        "_task2_exact_topology_mask_from_active",
        "_task2_plane_strip_qsum_from_raw",
        "apply_task2_sequential_charge_zeroing",
        "apply_task2_final_calibrated_strip_gate",
        "build_task2_exact_topology_mask",
    }
    tree = ast.parse(_source())
    selected_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in selected_names
    ]
    namespace: dict[str, object] = {"np": np, "pd": pd, "Iterable": Iterable}
    exec(compile(ast.Module(body=selected_nodes, type_ignores=[]), str(SCRIPT_PATH), "exec"), namespace)
    return namespace


def _raw_frame(patterns_by_plane: dict[int, list[list[float]]]) -> pd.DataFrame:
    rows = len(next(iter(patterns_by_plane.values())))
    data: dict[str, np.ndarray] = {}
    for plane in range(1, 5):
        patterns = patterns_by_plane.get(plane, [[0.0] * 4 for _ in range(rows)])
        for strip in range(1, 5):
            q_values = np.asarray([patterns[row][strip - 1] for row in range(rows)], dtype=float)
            data[f"p{plane}_s{strip}_ef_q"] = q_values
            data[f"p{plane}_s{strip}_eb_q"] = q_values
            data[f"p{plane}_s{strip}_ef_t"] = np.ones(rows)
            data[f"p{plane}_s{strip}_eb_t"] = np.ones(rows)
    return pd.DataFrame(data)


def test_charge_zeroing_is_sequential_and_does_not_remove_rows() -> None:
    frame = _raw_frame({
        1: [[100, 0, 0, 0], [50, 0, 0, 0], [70, 0, 0, 0], [80, 0, 0, 0], [100, 0, 0, 0]],
        2: [[100, 0, 0, 0], [150, 0, 0, 0], [150, 0, 0, 0], [150, 0, 0, 0], [100, 0, 0, 0]],
        3: [[100, 0, 0, 0], [150, 0, 0, 0], [150, 0, 0, 0], [150, 0, 0, 0], [0, 0, 0, 0]],
    })
    namespace = _selection_function_namespace()
    charge_config = {
        "channel": {"min": 60, "max": 1000},
        "strip": {"min": 75, "max": 1000},
        "plane": {"min": 90, "max": 1000},
        "detector": {"min": 250, "max": 1000},
    }
    diagnostics = namespace["apply_task2_sequential_charge_zeroing"](
        frame,
        charge_config=charge_config,
    )
    assert len(frame) == 5
    active = namespace["_task2_active_strip_matrix_from_raw"](frame)
    plane_active = {plane: np.any(active[plane], axis=1) for plane in range(1, 5)}
    labels = ["".join(str(plane) for plane in range(1, 5) if plane_active[plane][row]) for row in range(len(frame))]
    assert labels == ["123", "23", "23", "23", ""]
    for level, (_, post_values) in diagnostics.items():
        lower, upper = charge_config[level]["min"], charge_config[level]["max"]
        nonzero = post_values[np.isfinite(post_values) & (post_values != 0)]
        assert np.all(nonzero >= lower)
        assert np.all(nonzero <= upper)


def test_exact_topology_requires_exact_active_planes_and_strip_patterns() -> None:
    frame = _raw_frame({
        1: [[100, 0, 0, 0], [100, 0, 100, 0], [100, 0, 0, 0]],
        2: [[0, 100, 0, 0], [0, 100, 0, 0], [0, 100, 0, 0]],
        3: [[0, 0, 100, 0], [0, 0, 100, 0], [0, 0, 100, 0]],
        4: [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 100]],
    })
    namespace = _selection_function_namespace()
    mask = namespace["build_task2_exact_topology_mask"](
        frame,
        plane_combinations=((1, 2, 3),),
        strip_topologies=("1000", "0100", "0010", "0001"),
        component_source="raw",
    )
    assert mask.tolist() == [True, False, False]


def test_final_calibrated_strip_gate_preserves_inputs_and_creates_accepted_copies() -> None:
    data: dict[str, object] = {"metadata": ["keep", "keep", "keep"]}
    calibrated_suffixes = ("qsum_cal", "qdif_cal", "tsum_cal", "tdif_cal")
    valid_values = (100.0, 0.5, -110.0, 0.2)
    for plane in range(1, 5):
        for strip in range(1, 5):
            for suffix, value in zip(calibrated_suffixes, valid_values):
                data[f"p{plane}_s{strip}_{suffix}"] = [value, value, 0.0]
            data[f"p{plane}_s{strip}_qsum"] = [91.0, 92.0, 93.0]
    frame = pd.DataFrame(data)
    frame.loc[1, "p2_s3_qdif_cal"] = 3.0
    calibrated_before = frame[[column for column in frame if column.endswith("_cal")]].copy(deep=True)
    untouched_before = frame[["metadata"] + [column for column in frame if column.endswith("_qsum")]].copy(deep=True)

    summary = _selection_function_namespace()["apply_task2_final_calibrated_strip_gate"](
        frame,
        {
            "enabled": True,
            "limits": {
                "qsum": {"min": -10, "max": 300},
                "qdif": {"min": -2, "max": 2},
                "tsum": {"min": -130, "max": -100},
                "tdif": {"min": -0.79, "max": 0.79},
            },
        },
    )

    failing_columns = [f"p2_s3_{suffix.replace('_cal', '_task2')}" for suffix in calibrated_suffixes]
    assert frame.loc[1, failing_columns].tolist() == [0.0, 0.0, 0.0, 0.0]
    assert frame.loc[0, failing_columns].tolist() == list(valid_values)
    assert frame.loc[2, failing_columns].tolist() == [0.0, 0.0, 0.0, 0.0]
    pd.testing.assert_frame_equal(frame[calibrated_before.columns], calibrated_before)
    pd.testing.assert_frame_equal(frame[untouched_before.columns], untouched_before)
    assert frame.loc[1, "filter_task2_calibrated_strip_P2_s3_pass"] == False
    assert frame.loc[0, "filter_task2_calibrated_strip_P2_s3_pass"] == True
    assert summary["strip_blocks_zeroed"] == 1
    assert summary["rows_affected"] == 1
    assert summary["values_zeroed"] == 4
