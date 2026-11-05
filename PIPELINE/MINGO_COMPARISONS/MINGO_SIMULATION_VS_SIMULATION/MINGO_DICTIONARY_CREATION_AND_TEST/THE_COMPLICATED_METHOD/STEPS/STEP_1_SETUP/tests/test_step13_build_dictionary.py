#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

_STEP13_DIR = (
    Path(__file__).resolve().parent.parent / "STEP_1_3_BUILD_DICTIONARY"
)
sys.path.insert(0, str(_STEP13_DIR))

from build_dictionary import _plot_relerr_report  # noqa: E402


def test_plot_relerr_report_uses_simulated_efficiency_on_middle_x_axis(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def _fake_save_figure(fig, path, **_kwargs):
        captured["fig"] = fig
        captured["path"] = path

    monkeypatch.setattr("build_dictionary._save_figure", _fake_save_figure)
    monkeypatch.setattr("build_dictionary.plt.close", lambda _fig: None)

    df = pd.DataFrame(
        {
            "eff_empirical_1": [0.55, 0.60, 0.65],
            "eff_empirical_2": [0.70, 0.75, 0.80],
            "eff_empirical_3": [0.72, 0.77, 0.82],
            "eff_empirical_4": [0.56, 0.61, 0.66],
            "eff_sim_1": [0.62, 0.67, 0.71],
            "eff_sim_2": [0.74, 0.79, 0.84],
            "eff_sim_3": [0.76, 0.81, 0.86],
            "eff_sim_4": [0.63, 0.68, 0.72],
            "relerr_eff_1_fit_pct": [2.0, 3.0, 4.0],
            "relerr_eff_2_fit_pct": [1.0, 2.0, 3.0],
            "relerr_eff_3_fit_pct": [1.5, 2.5, 3.5],
            "relerr_eff_4_fit_pct": [2.2, 3.2, 4.2],
        }
    )

    _plot_relerr_report(
        df,
        dictionary_index={0},
        fit_models={},
        cfg_13={},
        cfg_12={},
    )

    fig = captured["fig"]
    middle_axes = [fig.axes[idx] for idx in (1, 4, 7, 10)]
    assert all(ax.get_xlabel() == "Simulated efficiency" for ax in middle_axes)
    assert all("relerr vs simulated" in ax.get_title() for ax in middle_axes)

    plt.close(fig)
