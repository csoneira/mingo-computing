#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/MODULES/uncertainty_lut.py
Purpose: Uncertainty LUT loader and interpolation module (pure empirical).
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/MODULES/uncertainty_lut.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd


# ── module-level helpers ────────────────────────────────────────────────────

def _interp3d(
    x: float, y: float, z: float,
    xm: np.ndarray, ym: np.ndarray, zm: np.ndarray,
    grid: np.ndarray,
) -> float | None:
    """Trilinear interpolation on a 3-D rectilinear grid with clamp-to-edge.

    Parameters
    ----------
    x, y, z : float
        Query point (flux, eff, events).
    xm, ym, zm : 1-D sorted arrays
        Midpoints along each axis.
    grid : 3-D array  (len(xm), len(ym), len(zm))
        Values to interpolate (should be NaN-free).
    """
    if len(xm) < 2 or len(ym) < 2 or len(zm) < 2:
        # Grid too small for interpolation — return single value if available
        if grid.size == 1:
            v = grid.flat[0]
            return float(v) if np.isfinite(v) else None
        return None

    # Clamp to boundary
    x = float(np.clip(x, xm[0], xm[-1]))
    y = float(np.clip(y, ym[0], ym[-1]))
    z = float(np.clip(z, zm[0], zm[-1]))

    # Index helpers
    def _bracket(val, mids):
        i = int(np.searchsorted(mids, val, side="right")) - 1
        i = max(0, min(i, len(mids) - 2))
        lo, hi = mids[i], mids[i + 1]
        t = (val - lo) / (hi - lo) if hi != lo else 0.0
        return i, t

    ix, tx = _bracket(x, xm)
    iy, ty = _bracket(y, ym)
    iz, tz = _bracket(z, zm)

    # 8 corner values
    c000 = grid[ix,     iy,     iz]
    c100 = grid[ix + 1, iy,     iz]
    c010 = grid[ix,     iy + 1, iz]
    c110 = grid[ix + 1, iy + 1, iz]
    c001 = grid[ix,     iy,     iz + 1]
    c101 = grid[ix + 1, iy,     iz + 1]
    c011 = grid[ix,     iy + 1, iz + 1]
    c111 = grid[ix + 1, iy + 1, iz + 1]

    corners = np.array([c000, c100, c010, c110, c001, c101, c011, c111])
    if np.any(~np.isfinite(corners)):
        valid = corners[np.isfinite(corners)]
        return float(np.mean(valid)) if len(valid) else None

    # Trilinear
    c00 = c000 * (1 - tx) + c100 * tx
    c01 = c001 * (1 - tx) + c101 * tx
    c10 = c010 * (1 - tx) + c110 * tx
    c11 = c011 * (1 - tx) + c111 * tx

    c0 = c00 * (1 - ty) + c10 * ty
    c1 = c01 * (1 - ty) + c11 * ty

    val = c0 * (1 - tz) + c1 * tz
    return float(val)


@dataclass
class UncertaintyLUT:
    """Look-Up Table for inference uncertainty estimates (pure empirical).

    This LUT is trained on *validation data* (simulated data matched
    against the dictionary) but is applied to *any* data — simulated or
    real.  The query inputs are always data-side quantities.

    Attributes
    ----------
    lut : pd.DataFrame
        Dense 3-D empirical LUT with σ per (flux, eff, events) cell.
    meta : dict
        Full metadata including ranges, edges, global fallback.
    global_sigma_flux : float
        Global fallback σ_flux [%].
    global_sigma_eff : float
        Global fallback σ_eff [%].
    """

    lut: pd.DataFrame
    meta: dict
    global_sigma_flux: float
    global_sigma_eff: float

    # Column mapping (supports legacy and current LUT schemas)
    flux_dim_col: str = "flux_mid"
    eff_dim_col: str = "eff_mid"
    events_dim_col: str = "events_mid"
    sigma_flux_col: str = "sigma_flux_pct"
    sigma_eff_col: str = "sigma_eff_pct"

    # Derived 3-D grids (built at load time)
    _flux_mids: np.ndarray  = field(default_factory=lambda: np.array([]))
    _eff_mids: np.ndarray   = field(default_factory=lambda: np.array([]))
    _events_mids: np.ndarray = field(default_factory=lambda: np.array([]))
    _sigma_flux_grid: np.ndarray = field(
        default_factory=lambda: np.array([]))
    _sigma_eff_grid: np.ndarray  = field(
        default_factory=lambda: np.array([]))

    # ── construction ────────────────────────────────────────────────────

    @classmethod
    def load(cls, lut_dir: str | Path) -> "UncertaintyLUT":
        """Load a previously built LUT from disk.

        Parameters
        ----------
        lut_dir : path-like
            Directory containing ``uncertainty_lut_meta.json`` and
            ``uncertainty_lut.csv``.
        """
        lut_dir = Path(lut_dir)
        meta_path = lut_dir / "uncertainty_lut_meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"LUT metadata not found: {meta_path}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        lut_path = lut_dir / "uncertainty_lut.csv"
        if not lut_path.exists():
            raise FileNotFoundError(f"LUT CSV not found: {lut_path}")
        # Current STEP 2.3 writes a metadata header with comment lines.
        lut_df = pd.read_csv(lut_path, comment="#", low_memory=False)
        if lut_df.empty:
            raise ValueError(f"LUT CSV is empty after parsing comments: {lut_path}")

        def _strip_est_prefix(name: str) -> str:
            return name[4:] if name.startswith("est_") else name

        def _pick_first(options: list[str], available: set[str]) -> str | None:
            for opt in options:
                if opt in available:
                    return opt
            return None

        def _pick_sigma_column(df: pd.DataFrame, param_name: str, q_target: int) -> str | None:
            exact = f"sigma_{param_name}_p{q_target}"
            if exact in df.columns:
                return exact
            std_col = f"sigma_{param_name}_std"
            if std_col in df.columns:
                return std_col

            patt = re.compile(rf"^sigma_{re.escape(param_name)}_p(\d+)$")
            ranked: list[tuple[int, str]] = []
            for col in df.columns:
                m = patt.match(str(col))
                if m is None:
                    continue
                try:
                    q_col = int(m.group(1))
                except (TypeError, ValueError):
                    continue
                ranked.append((abs(q_col - q_target), col))
            if not ranked:
                return None
            ranked.sort(key=lambda item: (item[0], item[1]))
            return ranked[0][1]

        legacy_schema = {"flux_mid", "eff_mid", "events_mid"}.issubset(set(lut_df.columns))
        if legacy_schema:
            flux_dim_col = "flux_mid"
            eff_dim_col = "eff_mid"
            events_dim_col = "events_mid"
            sigma_flux_col = "sigma_flux_pct"
            sigma_eff_col = "sigma_eff_pct"
            missing_legacy = {
                "flux_mid",
                "eff_mid",
                "events_mid",
                "sigma_flux_pct",
                "sigma_eff_pct",
            } - set(lut_df.columns)
            if missing_legacy:
                raise ValueError(
                    "Legacy LUT schema is incomplete. Missing columns: "
                    f"{sorted(missing_legacy)}"
                )
        else:
            centre_cols = [c for c in lut_df.columns if str(c).endswith("_centre")]
            if not centre_cols:
                raise ValueError(
                    "LUT CSV schema is unsupported: expected legacy *_mid columns "
                    "or modern *_centre columns."
                )

            dims_available = {str(c)[:-len("_centre")] for c in centre_cols}
            flux_dim = _pick_first(
                ["est_flux_cm2_min", "flux_cm2_min", "est_flux", "flux"],
                dims_available,
            )
            eff_dim = _pick_first(
                [
                    "est_eff_sim_2",
                    "est_eff_sim_1",
                    "est_eff_sim_3",
                    "est_eff_sim_4",
                    "eff_sim_2",
                    "eff_sim_1",
                    "eff_sim_3",
                    "eff_sim_4",
                    "est_eff",
                    "eff",
                ],
                dims_available,
            )
            events_dim = _pick_first(
                ["n_events", "true_n_events", "events", "sample_events_count"],
                dims_available,
            )
            if events_dim is None:
                # Last-resort fallback for event-like dimensions.
                event_like = sorted([d for d in dims_available if "event" in d.lower()])
                events_dim = event_like[0] if event_like else None

            if flux_dim is None or eff_dim is None or events_dim is None:
                raise ValueError(
                    "Could not map modern LUT dimensions to (flux, eff, n_events). "
                    f"Available dimensions: {sorted(dims_available)}"
                )

            quantiles_raw = meta.get("quantiles", [])
            q_labels: list[int] = []
            if isinstance(quantiles_raw, list):
                for q in quantiles_raw:
                    try:
                        qf = float(q)
                    except (TypeError, ValueError):
                        continue
                    if np.isfinite(qf):
                        q_labels.append(int(round(qf * 100.0)))
            q_target = 68
            if q_labels:
                q_target = 68 if 68 in q_labels else min(q_labels, key=lambda v: abs(v - 68))

            flux_param = _strip_est_prefix(flux_dim)
            eff_param = _strip_est_prefix(eff_dim)
            sigma_flux_col = _pick_sigma_column(lut_df, flux_param, q_target)
            sigma_eff_col = _pick_sigma_column(lut_df, eff_param, q_target)
            if sigma_flux_col is None:
                sigma_candidates = sorted([c for c in lut_df.columns if str(c).startswith("sigma_")])
                raise ValueError(
                    f"Could not find sigma column for flux parameter '{flux_param}'. "
                    f"Available sigma columns: {sigma_candidates}"
                )
            if sigma_eff_col is None:
                sigma_candidates = sorted([c for c in lut_df.columns if str(c).startswith("sigma_")])
                raise ValueError(
                    f"Could not find sigma column for efficiency parameter '{eff_param}'. "
                    f"Available sigma columns: {sigma_candidates}"
                )

            flux_dim_col = f"{flux_dim}_centre"
            eff_dim_col = f"{eff_dim}_centre"
            events_dim_col = f"{events_dim}_centre"

        required_cols = [
            flux_dim_col,
            eff_dim_col,
            events_dim_col,
            sigma_flux_col,
            sigma_eff_col,
        ]
        missing_required = [c for c in required_cols if c not in lut_df.columns]
        if missing_required:
            raise ValueError(
                "LUT schema check failed: missing required mapped columns "
                f"{missing_required}"
            )

        lut_df = lut_df.copy()
        for col in required_cols:
            lut_df[col] = pd.to_numeric(lut_df[col], errors="coerce")

        valid_dims = (
            np.isfinite(lut_df[flux_dim_col])
            & np.isfinite(lut_df[eff_dim_col])
            & np.isfinite(lut_df[events_dim_col])
        )
        if not bool(valid_dims.any()):
            raise ValueError(
                "LUT schema check failed: no rows have finite (flux, eff, n_events) mapped dimensions."
            )

        dup_mask = lut_df.duplicated(
            subset=[flux_dim_col, eff_dim_col, events_dim_col],
            keep=False,
        )
        if bool(dup_mask.any()):
            # Keep loader deterministic when multiple calibration rows map to the
            # same LUT cell: collapse to median uncertainty per cell.
            lut_df = (
                lut_df.loc[valid_dims, required_cols]
                .groupby(
                    [flux_dim_col, eff_dim_col, events_dim_col],
                    as_index=False,
                    sort=True,
                )
                .median(numeric_only=True)
            )

        valid_dims = (
            np.isfinite(lut_df[flux_dim_col])
            & np.isfinite(lut_df[eff_dim_col])
            & np.isfinite(lut_df[events_dim_col])
        )
        if not bool(np.isfinite(lut_df.loc[valid_dims, sigma_flux_col]).any()):
            raise ValueError(
                f"LUT schema check failed: '{sigma_flux_col}' has no finite values on valid dimension rows."
            )
        if not bool(np.isfinite(lut_df.loc[valid_dims, sigma_eff_col]).any()):
            raise ValueError(
                f"LUT schema check failed: '{sigma_eff_col}' has no finite values on valid dimension rows."
            )

        lut_meta = meta.get("lut", {})
        if isinstance(lut_meta, dict) and (
            "global_sigma_flux_pct" in lut_meta or "global_sigma_eff_pct" in lut_meta
        ):
            global_sf = float(lut_meta.get("global_sigma_flux_pct", 5.0))
            global_se = float(lut_meta.get("global_sigma_eff_pct", 4.0))
        else:
            # Current metadata no longer stores explicit global fallbacks.
            sigma_flux_vals = pd.to_numeric(lut_df.get(sigma_flux_col), errors="coerce")
            sigma_eff_vals = pd.to_numeric(lut_df.get(sigma_eff_col), errors="coerce")
            sigma_flux_vals = sigma_flux_vals[np.isfinite(sigma_flux_vals)]
            sigma_eff_vals = sigma_eff_vals[np.isfinite(sigma_eff_vals)]
            global_sf = float(np.nanmedian(np.abs(sigma_flux_vals))) if len(sigma_flux_vals) else 5.0
            global_se = float(np.nanmedian(np.abs(sigma_eff_vals))) if len(sigma_eff_vals) else 4.0

        obj = cls(
            lut=lut_df,
            meta=meta,
            global_sigma_flux=global_sf,
            global_sigma_eff=global_se,
            flux_dim_col=flux_dim_col,
            eff_dim_col=eff_dim_col,
            events_dim_col=events_dim_col,
            sigma_flux_col=sigma_flux_col,
            sigma_eff_col=sigma_eff_col,
        )
        obj._build_grids()
        return obj

    def _build_grids(self) -> None:
        """Pre-compute dense 3-D grids for trilinear interpolation."""
        df = self.lut
        if df.empty:
            return

        required_cols = [
            self.flux_dim_col,
            self.eff_dim_col,
            self.events_dim_col,
        ]
        for col in required_cols:
            if col not in df.columns:
                raise KeyError(f"Required LUT column missing: {col}")

        work = df.copy()
        for col in [*required_cols, self.sigma_flux_col, self.sigma_eff_col]:
            if col in work.columns:
                work[col] = pd.to_numeric(work[col], errors="coerce")
        work = work.dropna(subset=required_cols)
        if work.empty:
            return

        flux_mids = np.sort(work[self.flux_dim_col].unique())
        eff_mids  = np.sort(work[self.eff_dim_col].unique())
        evts_mids = np.sort(work[self.events_dim_col].unique())

        self._flux_mids   = flux_mids
        self._eff_mids    = eff_mids
        self._events_mids = evts_mids

        nf = len(flux_mids)
        ne = len(eff_mids)
        nn = len(evts_mids)

        sf_grid = np.full((nf, ne, nn), np.nan)
        se_grid = np.full((nf, ne, nn), np.nan)

        flux_idx  = {v: i for i, v in enumerate(flux_mids)}
        eff_idx   = {v: i for i, v in enumerate(eff_mids)}
        events_idx = {v: i for i, v in enumerate(evts_mids)}

        for _, row in work.iterrows():
            fi = flux_idx.get(row[self.flux_dim_col])
            ei = eff_idx.get(row[self.eff_dim_col])
            ni = events_idx.get(row[self.events_dim_col])
            if fi is None or ei is None or ni is None:
                continue
            sf = row.get(self.sigma_flux_col)
            se = row.get(self.sigma_eff_col)
            if sf is not None and np.isfinite(sf):
                sf_grid[fi, ei, ni] = sf
            if se is not None and np.isfinite(se):
                se_grid[fi, ei, ni] = se

        # Fill remaining NaN via nearest-neighbour in 3-D grid space
        _fill_nan_nearest_3d(sf_grid)
        _fill_nan_nearest_3d(se_grid)

        self._sigma_flux_grid = sf_grid
        self._sigma_eff_grid  = se_grid

    # ── query interface ─────────────────────────────────────────────────

    def query(
        self,
        est_flux: float,
        est_eff: float,
        n_events: float,
    ) -> tuple[float, float]:
        """Return (σ_flux_pct, σ_eff_pct) for the given data measurement.

        Parameters
        ----------
        est_flux : float
            Estimated flux from the dictionary match for this data sample.
        est_eff : float
            Estimated efficiency from the dictionary match.
        n_events : float
            Number of events in the data sample being analysed.

        Returns
        -------
        (sigma_flux_pct, sigma_eff_pct) : tuple[float, float]
            Uncertainty in percent relative error.  These represent the
            expected error between the dictionary-matched estimate and
            the true value, as calibrated from the validation dataset.
        """
        sf = _interp3d(
            est_flux, est_eff, n_events,
            self._flux_mids, self._eff_mids, self._events_mids,
            self._sigma_flux_grid,
        )
        se = _interp3d(
            est_flux, est_eff, n_events,
            self._flux_mids, self._eff_mids, self._events_mids,
            self._sigma_eff_grid,
        )
        if sf is None or se is None or not np.isfinite(sf) or not np.isfinite(se):
            return (self.global_sigma_flux, self.global_sigma_eff)
        return (max(sf, 0.0), max(se, 0.0))

    def query_batch(
        self,
        est_flux: np.ndarray,
        est_eff: np.ndarray,
        n_events: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Vectorised version of :meth:`query`.

        Returns arrays (sigma_flux_pct, sigma_eff_pct).
        """
        est_flux = np.asarray(est_flux, dtype=float)
        est_eff  = np.asarray(est_eff,  dtype=float)
        n_events = np.asarray(n_events, dtype=float)
        n = len(est_flux)
        sf = np.empty(n, dtype=float)
        se = np.empty(n, dtype=float)
        for i in range(n):
            sf[i], se[i] = self.query(est_flux[i], est_eff[i], n_events[i])
        return sf, se

    # ── utilities ───────────────────────────────────────────────────────

    def summary(self) -> str:
        """Human-readable summary of the loaded LUT."""
        m = self.meta
        lm = m.get("lut", {})
        lines = [
            "Uncertainty LUT Summary (empirical)",
            "=" * 44,
            f"Source:        {m.get('source_csv', '?')}",
            f"Valid rows:    {m.get('n_valid_rows', '?')}",
            f"Flux range:    {m.get('estimated_flux_range', '?')}",
            f"Eff range:     {m.get('estimated_eff_range', '?')}",
            f"Events range:  {m.get('events_range', '?')}",
            "",
            f"Grid shape:    {len(self._flux_mids)} × "
            f"{len(self._eff_mids)} × {len(self._events_mids)}",
            f"Total cells:   {lm.get('n_cells_total', '?')}",
            f"Direct cells:  {lm.get('n_cells_filled', '?')}",
            f"Infilled:      {lm.get('n_cells_infilled', '?')}",
            f"Outliers removed: {lm.get('n_outliers_removed', '?')}",
            f"Quantile:      p{int(lm.get('quantile', 0.68) * 100)}",
            f"IQR factor:    {lm.get('iqr_factor', '?')}",
            "",
            f"Global fallback: σ_flux={self.global_sigma_flux:.3f}%  "
            f"σ_eff={self.global_sigma_eff:.3f}%",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        shape = (len(self._flux_mids), len(self._eff_mids),
                 len(self._events_mids))
        return f"UncertaintyLUT(grid={shape[0]}×{shape[1]}×{shape[2]})"


# ── 3-D NaN infilling ──────────────────────────────────────────────────────

def _fill_nan_nearest_3d(grid: np.ndarray) -> None:
    """In-place fill NaN cells with nearest valid neighbour in 3-D."""
    nan_mask = ~np.isfinite(grid)
    if not nan_mask.any():
        return
    if not (~nan_mask).any():
        return

    try:
        from scipy.ndimage import distance_transform_edt
        _, nearest_idx = distance_transform_edt(
            nan_mask, return_distances=True, return_indices=True)
        grid[nan_mask] = grid[tuple(nearest_idx[:, nan_mask])]
    except ImportError:
        valid_ijk = np.argwhere(~nan_mask)
        nan_ijk   = np.argwhere(nan_mask)
        for ni, nj, nk in nan_ijk:
            dists = ((valid_ijk[:, 0] - ni) ** 2
                     + (valid_ijk[:, 1] - nj) ** 2
                     + (valid_ijk[:, 2] - nk) ** 2)
            best = valid_ijk[dists.argmin()]
            grid[ni, nj, nk] = grid[best[0], best[1], best[2]]


def load_uncertainty_lut_table(lut_csv_path: str | Path) -> pd.DataFrame:
    """Load the STEP 2.3 LUT CSV, allowing comment-prefixed metadata headers."""
    return pd.read_csv(Path(lut_csv_path), comment="#", low_memory=False)


def detect_uncertainty_lut_param_names(
    lut_df: pd.DataFrame,
    lut_meta_path: str | Path | None = None,
) -> list[str]:
    """Resolve parameter names represented in the uncertainty LUT."""
    meta_path = Path(lut_meta_path) if lut_meta_path is not None else None
    if meta_path is not None and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            params = meta.get("param_names", [])
            if isinstance(params, list):
                cleaned = [str(p) for p in params if str(p)]
                if cleaned:
                    return cleaned
        except Exception:
            pass

    params: list[str] = []
    for c in lut_df.columns:
        if not str(c).startswith("sigma_"):
            continue
        if "_p" in str(c):
            pname = str(c)[len("sigma_") :].split("_p", 1)[0]
        elif str(c).endswith("_std"):
            pname = str(c)[len("sigma_") : -len("_std")]
        else:
            continue
        if pname and pname not in params:
            params.append(pname)
    return params


def interpolate_uncertainty_columns(
    query_df: pd.DataFrame,
    lut_df: pd.DataFrame,
    *,
    param_names: Sequence[str],
    quantile: float,
    neighbor_count: int | None = None,
    distance_power: float = 2.0,
    min_neighbors: int = 4,
) -> pd.DataFrame:
    """Smoothly interpolate LUT uncertainty columns onto query rows.

    This is a generic multidimensional LUT interpolator used by STEP 3.3 and
    STEP 4.2. Unlike the old nearest-row lookup, it uses inverse-distance
    weighting over the closest valid LUT rows, which avoids staircase-like
    uncertainty outputs when the LUT grid is coarse.
    """
    if lut_df.empty or query_df.empty:
        return pd.DataFrame(index=query_df.index)

    q_label = str(int(round(float(quantile) * 100.0)))
    centre_cols = [str(c) for c in lut_df.columns if str(c).endswith("_centre")]
    if not centre_cols:
        return pd.DataFrame(index=query_df.index)

    lut_centres_df = lut_df[centre_cols].apply(pd.to_numeric, errors="coerce")
    lut_centres = lut_centres_df.to_numpy(dtype=float)
    valid_centres = np.all(np.isfinite(lut_centres), axis=1)
    if not np.any(valid_centres):
        return pd.DataFrame(index=query_df.index)

    centre_valid = lut_centres[valid_centres]
    dim_center = np.nanmedian(centre_valid, axis=0)
    dim_scale = np.nanpercentile(centre_valid, 90, axis=0) - np.nanpercentile(centre_valid, 10, axis=0)
    dim_scale = np.where(np.isfinite(dim_scale) & (dim_scale > 0.0), dim_scale, np.nanmax(centre_valid, axis=0) - np.nanmin(centre_valid, axis=0))
    dim_scale = np.where(np.isfinite(dim_scale) & (dim_scale > 0.0), dim_scale, 1.0)

    n_rows = len(query_df)
    n_dims = len(centre_cols)
    query_vals = np.zeros((n_rows, n_dims), dtype=float)
    for j, cc in enumerate(centre_cols):
        dim = cc[: -len("_centre")]
        if dim in query_df.columns:
            qv = pd.to_numeric(query_df[dim], errors="coerce").to_numpy(dtype=float)
        elif dim == "n_events":
            qv = pd.to_numeric(query_df.get("n_events"), errors="coerce").to_numpy(dtype=float)
        else:
            qv = np.full(n_rows, np.nan, dtype=float)
        qv = np.where(np.isfinite(qv), qv, dim_center[j])
        query_vals[:, j] = qv

    normalized_lut = centre_valid / dim_scale[np.newaxis, :]
    normalized_query = query_vals / dim_scale[np.newaxis, :]
    diff = normalized_query[:, np.newaxis, :] - normalized_lut[np.newaxis, :, :]
    distances = np.sqrt(np.sum(diff * diff, axis=2))

    out = pd.DataFrame(index=query_df.index)
    for pname in param_names:
        pref_col = f"sigma_{pname}_p{q_label}"
        sigma_col = pref_col if pref_col in lut_df.columns else None
        if sigma_col is None:
            alt = f"sigma_{pname}_std"
            sigma_col = alt if alt in lut_df.columns else None
        if sigma_col is None:
            out[f"unc_{pname}_pct_raw"] = np.nan
            out[f"unc_{pname}_pct"] = np.nan
            continue

        sigma_vals = pd.to_numeric(lut_df[sigma_col], errors="coerce").to_numpy(dtype=float)[valid_centres]
        valid_sigma = np.isfinite(sigma_vals)
        if not np.any(valid_sigma):
            out[f"unc_{pname}_pct_raw"] = np.nan
            out[f"unc_{pname}_pct"] = np.nan
            continue

        sigma_valid = sigma_vals[valid_sigma]
        distances_valid = distances[:, valid_sigma]
        if sigma_valid.size == 0 or distances_valid.shape[1] == 0:
            out[f"unc_{pname}_pct_raw"] = np.nan
            out[f"unc_{pname}_pct"] = np.nan
            continue

        k = int(neighbor_count) if neighbor_count is not None else min(max(int(min_neighbors), 2 * n_dims), int(sigma_valid.size))
        k = max(1, min(k, int(sigma_valid.size)))
        order = np.argpartition(distances_valid, kth=k - 1, axis=1)[:, :k]
        local_dist = np.take_along_axis(distances_valid, order, axis=1)
        local_sigma = sigma_valid[order]

        exact_mask = np.any(local_dist <= 1e-12, axis=1)
        raw = np.full(n_rows, np.nan, dtype=float)
        if np.any(exact_mask):
            exact_pos = np.argmin(local_dist[exact_mask], axis=1)
            raw[exact_mask] = local_sigma[exact_mask, exact_pos]

        non_exact_mask = ~exact_mask
        if np.any(non_exact_mask):
            local_dist_ne = local_dist[non_exact_mask]
            local_sigma_ne = local_sigma[non_exact_mask]
            weights = 1.0 / np.power(np.maximum(local_dist_ne, 1e-12), max(float(distance_power), 0.0))
            weights = np.where(np.isfinite(weights), weights, 0.0)
            weight_sum = np.sum(weights, axis=1)
            weighted = np.sum(weights * local_sigma_ne, axis=1)
            sigma_median = float(np.nanmedian(sigma_valid))
            interp = np.where(weight_sum > 0.0, weighted / weight_sum, sigma_median)
            raw[non_exact_mask] = interp

        sigma_median = float(np.nanmedian(sigma_valid))
        raw = np.where(np.isfinite(raw), raw, sigma_median)
        out[f"unc_{pname}_pct_raw"] = raw
        out[f"unc_{pname}_pct"] = np.abs(raw)

    return out


# ── convenience for scripts ─────────────────────────────────────────────────

def load_lut(lut_dir: str | Path) -> UncertaintyLUT:
    """Shortcut for ``UncertaintyLUT.load(lut_dir)``."""
    return UncertaintyLUT.load(lut_dir)
