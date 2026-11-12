#!/usr/bin/env python3

"""Test deterministic generation of Stage-1 simulation outputs."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


def _load_step1_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "STEP_1" / "step_1_blank_to_generated.py"
    spec = importlib.util.spec_from_file_location("step1_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generate_muon_sample_is_reproducible_with_seed():
    step1 = _load_step1_module()
    params = dict(
        n_tracks=2000,
        xlim=100.0,
        ylim=100.0,
        z_plane=120.0,
        cos_n=2.0,
        seed=12345,
        thick_rate_hz=80.0,
        drop_last_second=False,
        batch_size=500,
    )
    df_a = step1.generate_muon_sample(**params)
    df_b = step1.generate_muon_sample(**params)
    assert len(df_a) == len(df_b) == 2000
    assert np.array_equal(df_a["event_id"].to_numpy(), df_b["event_id"].to_numpy())
    assert np.allclose(df_a["X_gen"].to_numpy(), df_b["X_gen"].to_numpy())
    assert np.allclose(df_a["Y_gen"].to_numpy(), df_b["Y_gen"].to_numpy())
    assert np.allclose(df_a["Theta_gen"].to_numpy(), df_b["Theta_gen"].to_numpy())
    assert np.allclose(df_a["Phi_gen"].to_numpy(), df_b["Phi_gen"].to_numpy())
    # Regression guard for the dedicated time RNG path.
    assert np.allclose(df_a["T_thick_s"].to_numpy(), df_b["T_thick_s"].to_numpy())


def test_generate_muon_sample_changes_when_seed_changes():
    step1 = _load_step1_module()
    common = dict(
        n_tracks=1000,
        xlim=100.0,
        ylim=100.0,
        z_plane=120.0,
        cos_n=2.0,
        thick_rate_hz=50.0,
        drop_last_second=False,
        batch_size=500,
    )
    df_a = step1.generate_muon_sample(seed=1, **common)
    df_b = step1.generate_muon_sample(seed=2, **common)
    assert not np.allclose(df_a["T_thick_s"].to_numpy(), df_b["T_thick_s"].to_numpy())
