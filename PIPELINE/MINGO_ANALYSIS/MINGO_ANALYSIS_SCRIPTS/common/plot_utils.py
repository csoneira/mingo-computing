#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/common/plot_utils.py
Purpose: Utilities to ensure matplotlib figures are rasterised before exporting to PDF.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/common/plot_utils.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from datetime import datetime
import os
import matplotlib
import yaml

matplotlib.use("Agg")  # ensure non-interactive backend for batch jobs

from pathlib import Path
from typing import Iterable, Callable  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.artist import Artist  # noqa: E402
from matplotlib.offsetbox import DrawingArea, TextArea, HPacker, VPacker  # noqa: E402
from matplotlib.spines import Spine  # noqa: E402
from .path_config import get_master_config_root
from .file_selection import extract_run_datetime_from_name

__all__ = [
    "collect_saved_plot_paths",
    "ensure_plot_state",
    "rasterize_figure",
    "pdf_save_rasterized_page",
    "save_rasterized_pdf",
    "metadata_output_status_suffix",
    "runtime_plot_directory_name",
]


UNSUPPORTED_RASTER_TYPES = (TextArea, DrawingArea, HPacker, VPacker, Spine)


def runtime_plot_directory_name(data_file_name: str | os.PathLike[str], execution_timestamp: str) -> str:
    """Name runtime plot folders by acquisition date and execution timestamp."""
    data_datetime = extract_run_datetime_from_name(Path(data_file_name).name)
    if data_datetime is None:
        raise ValueError(
            "Cannot derive the acquisition date for runtime plots from "
            f"the task input filename: {Path(data_file_name).name}"
        )
    parsed_execution = None
    for time_format in ("%y-%m-%d_%H.%M.%S", "%Y-%m-%d_%H.%M.%S"):
        try:
            parsed_execution = datetime.strptime(execution_timestamp, time_format)
            break
        except ValueError:
            continue
    if parsed_execution is None:
        raise ValueError(f"Unrecognized runtime plot execution timestamp: {execution_timestamp!r}")
    return f"{data_datetime:%Y_%m_%d}_FIGURES_EXEC_ON_{parsed_execution:%Y_%m_%d_%H.%M.%S}"


def metadata_output_status_suffix(output_type: str) -> str:
    """Return a visible report-title note when a STEP_1 metadata output is disabled."""
    config_path = (
        get_master_config_root()
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "config_step_1.yaml"
    )
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ""
    outputs = config.get("metadata_outputs", {})
    if not isinstance(outputs, dict) or output_type not in outputs:
        return ""
    value = outputs[output_type]
    if value is False or value == 0 or (
        isinstance(value, str) and value.strip().lower() in {"false", "0", "no", "off"}
    ):
        return f" — {output_type} metadata disabled in config; no new rows"
    return ""


def ensure_plot_state(
    namespace: dict[str, object],
    *,
    fig_key: str = "fig_idx",
    plot_list_key: str = "plot_list",
    start_index: int = 1,
) -> tuple[int, list[str]]:
    """
    Ensure plot bookkeeping exists exactly once within a task script namespace.

    This prevents repeated config/setup blocks from accidentally resetting the
    current figure counter or the list of generated plots.
    """

    fig_val = namespace.get(fig_key)
    if not isinstance(fig_val, int) or fig_val < int(start_index):
        fig_val = int(start_index)
        namespace[fig_key] = fig_val

    plot_val = namespace.get(plot_list_key)
    if not isinstance(plot_val, list):
        plot_val = []
        namespace[plot_list_key] = plot_val

    return fig_val, plot_val


def _plot_order_key(path_str: str) -> tuple[int, str]:
    name = Path(path_str).name
    stem = Path(path_str).stem
    prefix = stem.split("_", 1)[0]
    try:
        idx = int(prefix)
    except (TypeError, ValueError):
        idx = 10**12
    return idx, name.lower()


def collect_saved_plot_paths(
    plot_list: Iterable[str] | None,
    figure_directory: str | os.PathLike[str] | None,
    *,
    suffixes: Iterable[str] = (".png",),
) -> list[str]:
    """
    Return saved plot paths in stable order, using both in-memory bookkeeping
    and the on-disk figure directory as a fallback.
    """

    normalized_suffixes = {
        str(s).lower() if str(s).startswith(".") else f".{str(s).lower()}"
        for s in suffixes
    }
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str | os.PathLike[str] | None) -> None:
        if not candidate:
            return
        path_str = str(candidate)
        if path_str in seen or not os.path.exists(path_str):
            return
        if normalized_suffixes and Path(path_str).suffix.lower() not in normalized_suffixes:
            return
        seen.add(path_str)
        ordered.append(path_str)

    for candidate in plot_list or []:
        _add(candidate)

    if figure_directory and os.path.isdir(figure_directory):
        directory_paths = sorted(
            (str(Path(figure_directory) / name) for name in os.listdir(figure_directory)),
            key=_plot_order_key,
        )
        for candidate in directory_paths:
            _add(candidate)

    return ordered


def rasterize_figure(fig: plt.Figure, rasterized_predicate: Callable[[Artist], bool] | None = None) -> None:
    """
    Mark all relevant artists on *fig* as rasterised so exported PDFs embed bitmaps.

    Parameters
    ----------
    fig:
        Matplotlib figure to rasterise.
    rasterized_predicate:
        Optional predicate to decide which artists should be rasterised. When
        omitted, every artist with ``set_rasterized`` is rasterised.
    """

    if rasterized_predicate is None:
        rasterized_predicate = (
            lambda artist: hasattr(artist, "set_rasterized")
            and not isinstance(artist, UNSUPPORTED_RASTER_TYPES)
        )

    for artist in fig.findobj(rasterized_predicate):
        try:
            if isinstance(artist, UNSUPPORTED_RASTER_TYPES):
                continue
            artist.set_rasterized(True)
        except Exception:
            continue


def pdf_save_rasterized_page(pdf: PdfPages, fig: plt.Figure, dpi: int = 150, **savefig_kwargs) -> None:
    """
    Rasterise *fig* and append it to the provided ``PdfPages`` object.
    """

    rasterize_figure(fig)
    pdf.savefig(fig, dpi=dpi, **savefig_kwargs)


def save_rasterized_pdf(fig: plt.Figure, path: str, dpi: int = 150, **savefig_kwargs) -> None:
    """
    Rasterise *fig* and save it directly as a PDF to *path*.
    """

    rasterize_figure(fig)
    fig.savefig(path, dpi=dpi, format="pdf", **savefig_kwargs)
