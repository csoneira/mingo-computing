from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MODULES_DIR = Path(__file__).resolve().parents[1]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from efficiency_fit_utils import (  # noqa: E402
    append_polynomial_corrected_efficiency_columns,
    load_efficiency_fit_models,
)


def test_load_efficiency_fit_models_reads_step13_summary_block(tmp_path: Path) -> None:
    summary_path = tmp_path / "build_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "efficiency_fit": {
                    "polynomial_order_requested": 4,
                    "models": {
                        "plane_1": {
                            "status": "ok",
                            "coefficients_desc": [1.2, -0.05],
                            "empirical_min": 0.31,
                            "empirical_max": 0.84,
                            "clip_fit_output": True,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    models, status, payload = load_efficiency_fit_models(summary_path)

    assert status == "ok"
    assert payload["efficiency_fit"]["polynomial_order_requested"] == 4
    assert models[1]["coefficients_desc"] == [1.2, -0.05]
    assert models[1]["empirical_min"] == 0.31
    assert models[1]["empirical_max"] == 0.84
    assert models[1]["clip_fit_output"] is True


def test_load_efficiency_fit_models_supports_legacy_keys(tmp_path: Path) -> None:
    summary_path = tmp_path / "legacy_build_summary.json"
    summary_path.write_text(
        json.dumps({"fit_line_eff_2": [0.75, 0.1]}),
        encoding="utf-8",
    )

    models, status, _ = load_efficiency_fit_models(summary_path)

    assert status == "ok"
    assert models[2]["coefficients_desc"] == [0.75, 0.1]
    assert models[2]["order_used"] == 1


def test_append_polynomial_corrected_efficiency_columns_clips_support_and_builds_products() -> None:
    df = pd.DataFrame(
        {
            "eff_empirical_1": [0.10, 0.90],
            "eff_empirical_2": [0.30, 0.40],
            "eff_empirical_3": [0.50, 0.60],
            "eff_empirical_4": [0.70, 0.80],
        }
    )
    fit_models = {
        1: {
            "coefficients_desc": [1.0, 0.0],
            "empirical_min": 0.20,
            "empirical_max": 0.80,
            "clip_fit_output": True,
        },
        2: {
            "coefficients_desc": [1.0, 0.0],
            "clip_fit_output": True,
        },
        3: {
            "coefficients_desc": [1.0, 0.0],
            "clip_fit_output": True,
        },
        4: {
            "coefficients_desc": [2.0, 0.0],
            "clip_fit_output": True,
        },
    }

    info = append_polynomial_corrected_efficiency_columns(df, fit_models)

    assert info["status"] == "ok"
    assert info["planes_applied"] == [1, 2, 3, 4]
    assert np.allclose(df["eff_poly_corrected_1"], [0.20, 0.80])
    assert np.allclose(df["eff_poly_corrected_2"], [0.30, 0.40])
    assert np.allclose(df["eff_poly_corrected_3"], [0.50, 0.60])
    assert np.allclose(df["eff_poly_corrected_4"], [1.00, 1.00])
    assert np.allclose(df["efficiency_product_poly_corrected_4planes"], [0.03, 0.192])
    assert np.allclose(df["efficiency_product_poly_corrected_123"], [0.03, 0.192])
    assert np.allclose(df["efficiency_product_poly_corrected_124"], [0.06, 0.32])
    assert np.allclose(df["efficiency_product_poly_corrected_134"], [0.10, 0.48])
    assert np.allclose(df["efficiency_product_poly_corrected_12"], [0.06, 0.32])
    assert np.allclose(df["efficiency_product_poly_corrected_13"], [0.10, 0.48])
    assert np.allclose(df["efficiency_product_poly_corrected_14"], [0.20, 0.80])
    assert np.allclose(df["efficiency_product_poly_corrected_23"], [0.15, 0.24])
    assert np.allclose(df["efficiency_product_poly_corrected_24"], [0.30, 0.40])
    assert np.allclose(df["efficiency_product_poly_corrected_34"], [0.50, 0.60])
