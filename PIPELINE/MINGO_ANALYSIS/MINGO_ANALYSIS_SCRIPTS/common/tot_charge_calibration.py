from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline, PchipInterpolator


def default_tot_charge_calibration_path(repo_root: str | Path) -> Path:
    root = Path(repo_root)
    return (
        root
        / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"
        / "ANCILLARY"
        / "CALIBRATIONS_AND_LUTS"
        / "TOT_TO_CHARGE_CAL"
        / "tot_to_charge_calibration.csv"
    )


@dataclass(frozen=True)
class TotChargeCalibration:
    path: Path
    widths_ns: np.ndarray
    charges_fc: np.ndarray
    _width_to_charge: CubicSpline
    _charge_to_width: PchipInterpolator

    @classmethod
    def from_csv(cls, calibration_path: str | Path) -> "TotChargeCalibration":
        path = Path(calibration_path)
        table = pd.read_csv(path)
        widths_ns = pd.to_numeric(table["Width"], errors="coerce").to_numpy(dtype=float)
        charges_fc = pd.to_numeric(table["Fast_Charge"], errors="coerce").to_numpy(dtype=float)

        valid = np.isfinite(widths_ns) & np.isfinite(charges_fc)
        widths_ns = widths_ns[valid]
        charges_fc = charges_fc[valid]
        if widths_ns.size < 2:
            raise ValueError(f"Invalid TOT calibration table: {path}")

        width_to_charge = CubicSpline(widths_ns, charges_fc, bc_type="natural")

        widths_ext = np.concatenate(([0.0], widths_ns))
        charges_ext = np.concatenate(([0.0], charges_fc))
        order = np.argsort(charges_ext)
        charge_to_width = PchipInterpolator(
            charges_ext[order],
            widths_ext[order],
            extrapolate=True,
        )

        return cls(
            path=path,
            widths_ns=widths_ns,
            charges_fc=charges_fc,
            _width_to_charge=width_to_charge,
            _charge_to_width=charge_to_width,
        )

    def width_ns_to_charge_fc(self, width_ns: np.ndarray | float) -> np.ndarray:
        values = np.asarray(width_ns, dtype=float)
        result = np.zeros_like(values, dtype=float)
        mask = np.isfinite(values) & (values != 0)
        if np.any(mask):
            result[mask] = self._width_to_charge(values[mask])
        return result

    def charge_fc_to_width_ns(self, charge_fc: np.ndarray | float) -> np.ndarray:
        values = np.asarray(charge_fc, dtype=float)
        result = np.zeros_like(values, dtype=float)
        mask = np.isfinite(values) & (values > 0)
        if np.any(mask):
            converted = self._charge_to_width(values[mask])
            result[mask] = np.maximum(converted, 0.0)
        return result
