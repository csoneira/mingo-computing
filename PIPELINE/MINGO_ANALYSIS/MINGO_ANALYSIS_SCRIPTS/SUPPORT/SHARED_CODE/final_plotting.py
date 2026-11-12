"""Load final-plot settings and render configured plots from a task parquet."""

from __future__ import annotations

from pathlib import Path
import re
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Ellipse
import numpy as np
import pandas as pd
import yaml

TASK_TT_COLUMNS = {
    0: ("tt_task0_raw", "tt_task0_acq"),
    1: ("tt_task1_clean", "tt_task0_raw"),
    2: ("tt_task2_cal", "tt_task1_clean"),
    3: ("tt_task3_list", "tt_task2_cal"),
    4: ("tt_task4_fit", "tt_task3_list"),
    5: ("tt_task5_post", "tt_task4_fit"),
}


def _first_existing(df: pd.DataFrame, names) -> str | None:
    return next((str(name) for name in names if str(name) in df.columns), None)


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce")


def _finite_pair(df: pd.DataFrame, x: str, y: str) -> tuple[np.ndarray, np.ndarray]:
    xv = _numeric(df, x).to_numpy(dtype=float)
    yv = _numeric(df, y).to_numpy(dtype=float)
    mask = np.isfinite(xv) & np.isfinite(yv)
    return xv[mask], yv[mask]


def _tt_column(df: pd.DataFrame, task: int) -> str | None:
    return _first_existing(df, TASK_TT_COLUMNS[task])


def _theta_phi(df: pd.DataFrame) -> tuple[str | None, str | None]:
    return (
        _first_existing(df, ("event_theta", "theta", "event_tim_theta", "tim_theta", "event_det_theta", "det_theta")),
        _first_existing(df, ("event_phi", "phi", "event_tim_phi", "tim_phi", "event_det_phi", "det_phi")),
    )


def _event_charge(df: pd.DataFrame) -> pd.Series | None:
    direct = _first_existing(df, ("event_charge", "charge_event", "tim_event_charge"))
    if direct:
        return _numeric(df, direct)
    plane_columns = [f"p{plane}_qsum" for plane in range(1, 5) if f"p{plane}_qsum" in df.columns]
    if plane_columns:
        return df[plane_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)
    strip_columns = [column for column in df.columns if re.fullmatch(r"p[1-4]_s[1-4]_qsum", str(column))]
    if strip_columns:
        return df[strip_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)
    return None


def _preferred_numeric_columns(df: pd.DataFrame, task: int, limit: int = 6) -> list[str]:
    patterns = {
        0: (r"p[1-4]_s[1-4]_e[fb]_[qt]$", r"tt_task0_"),
        1: (r"p[1-4]_s[1-4]_e[fb]_[qt]$", r"filter_task1_", r"tt_task1_"),
        2: (r"p[1-4]_s[1-4]_(qsum|qdif|tsum|tdif)$", r"tt_task2_"),
        3: (r"p[1-4]_(qsum|qdif|tsum|tdif|ypos|xpos)$", r"tt_task3_"),
        4: (r"event_(x|y|theta|phi|s|t0)$", r"event_tim_", r"event_det_", r"p[1-4]_.*res", r"chi"),
        5: (r"event_(x|y|theta|phi|s|t0|charge)$", r"p[1-4]_qsum$", r"tt_task5_"),
    }[task]
    result: list[str] = []
    for pattern in patterns:
        for column in df.columns:
            name = str(column)
            if name in result or re.search(pattern, name) is None:
                continue
            if pd.to_numeric(df[column], errors="coerce").notna().any():
                result.append(name)
                if len(result) >= limit:
                    return result
    for column in df.select_dtypes(include=[np.number]).columns:
        name = str(column)
        if name not in result:
            result.append(name)
        if len(result) >= limit:
            break
    return result


def _rate_plot(df: pd.DataFrame, task: int, alias: str):
    time_column = _first_existing(df, ("datetime", "Time", "timestamp"))
    if time_column is None:
        return _tt_plot(df, task, alias)
    times = pd.to_datetime(df[time_column], errors="coerce")
    valid = times.notna()
    if not valid.any():
        return _tt_plot(df, task, alias)
    frame = pd.DataFrame({"time": times.loc[valid]})
    tt_column = _tt_column(df, task)
    if tt_column:
        frame["tt"] = df.loc[valid, tt_column].astype(str).to_numpy()
    span = frame["time"].max() - frame["time"].min()
    frequency = "1min" if span <= pd.Timedelta(hours=6) else "10min"
    frame["bin"] = frame["time"].dt.floor(frequency)
    fig, ax = plt.subplots(figsize=(11, 5))
    if "tt" in frame:
        for label in frame["tt"].value_counts().head(8).index:
            counts = frame.loc[frame["tt"] == label].groupby("bin").size()
            ax.plot(counts.index, counts.values, marker=".", linewidth=1, label=str(label))
        ax.legend(title=tt_column, fontsize=8, ncol=2)
    else:
        counts = frame.groupby("bin").size()
        ax.plot(counts.index, counts.values, marker=".")
    ax.set_xlabel("Time")
    ax.set_ylabel(f"Events / {frequency}")
    ax.set_title(alias.replace("_", " "))
    ax.grid(alpha=0.25)
    return fig


def _tt_plot(df: pd.DataFrame, task: int, alias: str):
    column = _tt_column(df, task)
    if column is None:
        return None
    counts = df[column].astype(str).value_counts().head(30)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(counts.index, counts.values)
    ax.set_xlabel(column)
    ax.set_ylabel("Events")
    ax.tick_params(axis="x", rotation=60)
    ax.set_title(alias.replace("_", " "))
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    return fig


def _hist_grid(df: pd.DataFrame, task: int, alias: str, columns: list[str] | None = None):
    columns = columns or _preferred_numeric_columns(df, task, 6)
    columns = [column for column in columns if column in df.columns]
    if not columns:
        return None
    rows = int(np.ceil(len(columns) / 2))
    fig, axes = plt.subplots(rows, 2, figsize=(12, 3.4 * rows), squeeze=False)
    for ax, column in zip(axes.ravel(), columns):
        values = _numeric(df, column).to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if values.size:
            ax.hist(values, bins=80, alpha=0.8)
        ax.set_title(column)
        ax.grid(alpha=0.2)
    for ax in axes.ravel()[len(columns):]:
        ax.set_visible(False)
    fig.suptitle(alias.replace("_", " "))
    fig.tight_layout()
    return fig


def _charge_plot(df: pd.DataFrame, task: int, alias: str):
    columns = [column for column in ("event_charge", "p1_qsum", "p2_qsum", "p3_qsum", "p4_qsum") if column in df.columns]
    charge = _event_charge(df)
    if charge is not None and "event_charge" not in columns:
        temporary = df.copy()
        temporary["__derived_event_charge"] = charge
        return _hist_grid(temporary, task, alias, ["__derived_event_charge", *columns[:5]])
    if columns:
        return _hist_grid(df, task, alias, columns[:6])
    return _hist_grid(df, task, alias)


def _task5_gate_charge_spectra(df: pd.DataFrame, gate_name: str, alias: str):
    """Plot per-plane charge spectra for passing/failing Task-5 gate events."""
    if "gate" not in df.columns:
        return None
    tt_column = _tt_column(df, 5)
    charge_columns = [f"p{plane}_qsum" for plane in range(1, 5)]
    if tt_column is None or not all(column in df.columns for column in charge_columns):
        return None

    labels = df["gate"].fillna("").astype(str).str.split("|")
    passed = labels.map(lambda event_gates: gate_name in event_gates).to_numpy(dtype=bool)
    tt_values = pd.to_numeric(df[tt_column], errors="coerce").fillna(0).astype(int)
    trigger_types = sorted(int(value) for value in tt_values.unique() if int(value) != 0)
    if not trigger_types:
        return None

    all_charge = np.concatenate(
        [
            _numeric(df, column).to_numpy(dtype=float)
            for column in charge_columns
        ]
    )
    all_charge = all_charge[np.isfinite(all_charge) & (all_charge != 0)]
    if not all_charge.size:
        return None
    low, high = np.quantile(all_charge, [0.005, 0.995])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low, high = float(np.min(all_charge)), float(np.max(all_charge))
    if high <= low:
        low, high = low - 0.5, high + 0.5
    bins = np.linspace(low, high, 81)

    fig, axes = plt.subplots(
        4,
        len(trigger_types),
        figsize=(max(8, 2.6 * len(trigger_types)), 10),
        sharex=True,
        squeeze=False,
    )
    for plane_index, column in enumerate(charge_columns):
        values = _numeric(df, column).to_numpy(dtype=float)
        for tt_index, tt in enumerate(trigger_types):
            ax = axes[plane_index, tt_index]
            tt_mask = tt_values.to_numpy() == tt
            pass_mask = tt_mask & passed
            fail_mask = tt_mask & ~passed
            pass_charge = values[pass_mask & np.isfinite(values) & (values != 0)]
            fail_charge = values[fail_mask & np.isfinite(values) & (values != 0)]
            pass_counts = np.histogram(pass_charge, bins=bins)[0]
            fail_counts = np.histogram(fail_charge, bins=bins)[0]
            if np.any(pass_counts):
                ax.stairs(pass_counts, bins, color="tab:blue", label="Pass")
            if np.any(fail_counts):
                ax.stairs(fail_counts, bins, color="tab:red", linestyle="--", label="Fail")
            ax.set_yscale("log")
            positive = np.concatenate((pass_counts[pass_counts > 0], fail_counts[fail_counts > 0]))
            if positive.size:
                ax.set_ylim(bottom=max(float(positive.min()) * 0.5, 0.1))
            else:
                ax.set_ylim(0.1, 1)
                ax.text(0.5, 0.5, "No entries", transform=ax.transAxes, ha="center", fontsize=7)
            ax.set_title(f"P{plane_index + 1} · TT{tt}\npass {pass_mask.sum()} / fail {fail_mask.sum()}", fontsize=8)
            ax.grid(alpha=0.2)
            if tt_index == 0:
                ax.set_ylabel("Events / bin")
            if plane_index == 3:
                ax.set_xlabel("Plane charge Q_sum")
            if plane_index == 0 and tt_index == 0 and (np.any(pass_counts) or np.any(fail_counts)):
                ax.legend(fontsize=7)
    fig.suptitle(f"{alias.replace('_', ' ')} · solid = pass, dashed = fail", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig


def _pair_matrix(df: pd.DataFrame, task: int, alias: str, mode: str):
    columns = _preferred_numeric_columns(df, task, 5 if task == 4 else 4)
    if len(columns) < 2:
        return None
    n_columns = len(columns)
    fig, axes = plt.subplots(n_columns, n_columns, figsize=(3.0 * n_columns, 3.0 * n_columns), squeeze=False)
    for row, y_column in enumerate(columns):
        for col, x_column in enumerate(columns):
            ax = axes[row, col]
            xv, yv = _finite_pair(df, x_column, y_column)
            if row == col:
                if xv.size:
                    ax.hist(xv, bins=50, alpha=0.8)
            elif xv.size:
                if mode == "hexbin":
                    ax.hexbin(xv, yv, gridsize=45, mincnt=1, bins="log")
                else:
                    sample_count = min(12000, xv.size)
                    indices = np.linspace(0, xv.size - 1, sample_count, dtype=int)
                    ax.scatter(xv[indices], yv[indices], s=2, alpha=0.25)
            if row == n_columns - 1:
                ax.set_xlabel(x_column, fontsize=7)
            if col == 0:
                ax.set_ylabel(y_column, fontsize=7)
            ax.tick_params(labelsize=6)
    fig.suptitle(alias.replace("_", " "))
    fig.tight_layout()
    return fig


def _theta_phi_plot(df: pd.DataFrame, alias: str):
    theta, phi = _theta_phi(df)
    if theta is None or phi is None:
        return None
    phi_values, theta_values = _finite_pair(df, phi, theta)
    if not phi_values.size:
        return None
    if "polar" in alias:
        fig = plt.figure(figsize=(7, 7))
        ax = fig.add_subplot(111, projection="polar")
        ax.scatter(phi_values, theta_values, s=3, alpha=0.25)
    else:
        fig, ax = plt.subplots(figsize=(8, 6))
        image = ax.hexbin(phi_values, theta_values, gridsize=60, mincnt=1, bins="log")
        fig.colorbar(image, ax=ax, label="log count")
        ax.set_xlabel(phi)
        ax.set_ylabel(theta)
    ax.set_title(alias.replace("_", " "))
    return fig


def _matrix_plot(df: pd.DataFrame, task: int, alias: str):
    columns = [str(column) for column in df.columns if re.search(r"(qsum|_q$)", str(column))][:16]
    if len(columns) < 2:
        columns = _preferred_numeric_columns(df, task, 10)
    if len(columns) < 2:
        return None
    values = pd.DataFrame(index=df.index)
    for column in columns:
        numeric = _numeric(df, column)
        values[column] = (numeric.fillna(0) != 0).astype(float) if re.search(r"qsum|_q$", column) else numeric
    matrix = values.corr().to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(9, 8))
    image = ax.imshow(matrix, vmin=-1, vmax=1, aspect="auto")
    fig.colorbar(image, ax=ax)
    ax.set_xticks(range(len(values.columns)), values.columns, rotation=90, fontsize=7)
    ax.set_yticks(range(len(values.columns)), values.columns, fontsize=7)
    ax.set_title(alias.replace("_", " "))
    fig.tight_layout()
    return fig


def _success_mask(df: pd.DataFrame, task: int) -> pd.Series | None:
    passes = f"passes_task_{task}"
    if passes in df.columns:
        return pd.to_numeric(df[passes], errors="coerce").fillna(0) > 0
    tt_column = _tt_column(df, task)
    if tt_column is None:
        return None
    labels = df[tt_column].astype(str).str.replace(".0", "", regex=False)
    return labels.str.len() >= 4


def _efficiency_plot(df: pd.DataFrame, task: int, alias: str):
    success = _success_mask(df, task)
    if success is None:
        return None
    theta, _phi = _theta_phi(df)
    fig, ax = plt.subplots(figsize=(8, 5))
    if theta:
        values = _numeric(df, theta)
        valid = values.notna()
        if valid.sum() > 10:
            low, high = values[valid].quantile([0.01, 0.99])
            if np.isfinite(low) and np.isfinite(high) and high > low:
                bins = np.linspace(low, high, 16)
                categories = pd.cut(values[valid], bins=bins, include_lowest=True)
                efficiency = success[valid].groupby(categories, observed=True).mean()
                centers = np.array([interval.mid for interval in efficiency.index])
                ax.plot(centers, efficiency.to_numpy(), marker="o")
                ax.set_xlabel(theta)
                ax.set_ylabel("Efficiency / pass fraction")
                ax.set_ylim(0, 1.05)
            else:
                ax.bar(["pass", "fail"], [int(success.sum()), int((~success).sum())])
        else:
            ax.bar(["pass", "fail"], [int(success.sum()), int((~success).sum())])
    else:
        ax.bar(["pass", "fail"], [int(success.sum()), int((~success).sum())])
    ax.set_title(alias.replace("_", " "))
    ax.grid(alpha=0.25)
    return fig


def _occupancy_plot(df: pd.DataFrame, alias: str):
    columns = [str(column) for column in df.columns if re.fullmatch(r"p[1-4](_s[1-4])?_qsum", str(column))]
    if not columns:
        return None
    fractions = [float((_numeric(df, column).fillna(0) > 0).mean()) for column in columns]
    fig, ax = plt.subplots(figsize=(max(9, len(columns) * 0.45), 5))
    ax.bar(columns, fractions)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Non-zero fraction")
    ax.tick_params(axis="x", rotation=75)
    ax.set_title(alias.replace("_", " "))
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    return fig


def _threshold_plot(df: pd.DataFrame, alias: str):
    charge = _event_charge(df)
    if charge is None:
        return None
    values = charge.to_numpy(dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size < 2:
        return None
    thresholds = np.quantile(values, np.linspace(0.0, 0.95, 40))
    retention = np.array([(values >= threshold).mean() for threshold in thresholds])
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(thresholds, retention, marker=".")
    ax.set_xlabel("Charge threshold")
    ax.set_ylabel("Retained fraction")
    ax.set_ylim(0, 1.05)
    ax.set_title(alias.replace("_", " "))
    ax.grid(alpha=0.25)
    return fig


def _topology_plot(df: pd.DataFrame, alias: str):
    column = _first_existing(df, ("topology_task2_strip", "topology_task3_plane", "transferred_task3_cal_to_list"))
    if column is None:
        return None
    counts = df[column].astype(str).value_counts().head(25)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(counts.index, counts.values)
    ax.tick_params(axis="x", rotation=80)
    ax.set_ylabel("Events")
    ax.set_title(alias.replace("_", " "))
    fig.tight_layout()
    return fig


def _event_display(df: pd.DataFrame, alias: str):
    y_columns = [f"p{plane}_ypos" for plane in range(1, 5)]
    x_columns = [f"p{plane}_xpos" for plane in range(1, 5)]
    if not all(column in df.columns for column in y_columns):
        return None
    z_values = []
    for plane in range(1, 5):
        z_column = f"z_p{plane}"
        if z_column in df.columns:
            finite = _numeric(df, z_column).dropna()
            z_values.append(float(finite.iloc[0]) if not finite.empty else float(plane - 1))
        else:
            z_values.append(float(plane - 1))
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for sample_index, (_index, row) in enumerate(df.head(8).iterrows()):
        y = [pd.to_numeric(row[column], errors="coerce") for column in y_columns]
        axes[1].plot(y, z_values, marker="o", alpha=0.55, label=str(sample_index))
        if all(column in df.columns for column in x_columns):
            x = [pd.to_numeric(row[column], errors="coerce") for column in x_columns]
            axes[0].plot(x, z_values, marker="o", alpha=0.55)
    axes[0].set_xlabel("x")
    axes[1].set_xlabel("y")
    for ax in axes:
        ax.set_ylabel("z")
        ax.grid(alpha=0.25)
    axes[1].legend(title="sample", fontsize=7)
    fig.suptitle(alias.replace("_", " "))
    fig.tight_layout()
    return fig


def _projection_plot(df: pd.DataFrame, alias: str):
    x_column = _first_existing(df, ("event_x", "x", "event_tim_x", "tim_x", "event_det_x", "det_x"))
    y_column = _first_existing(df, ("event_y", "y", "event_tim_y", "tim_y", "event_det_y", "det_y"))
    if x_column is None or y_column is None:
        return None
    xv, yv = _finite_pair(df, x_column, y_column)
    if xv.size < 3:
        return None
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.hexbin(xv, yv, gridsize=60, mincnt=1, bins="log")
    covariance = np.cov(np.vstack([xv, yv]))
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = eigenvalues.argsort()[::-1]
    eigenvalues, eigenvectors = eigenvalues[order], eigenvectors[:, order]
    angle = np.degrees(np.arctan2(*eigenvectors[:, 0][::-1]))
    center = (float(np.nanmean(xv)), float(np.nanmean(yv)))
    for scale in (1, 2):
        width, height = 2 * scale * np.sqrt(np.maximum(eigenvalues, 0))
        ax.add_patch(Ellipse(center, width, height, angle=angle, fill=False, linewidth=1.5))
    ax.set_xlabel(x_column)
    ax.set_ylabel(y_column)
    ax.set_title(alias.replace("_", " "))
    ax.grid(alpha=0.2)
    return fig


def render_final_alias(df: pd.DataFrame, task: int, alias: str):
    key = alias.lower()
    if task == 5 and key.startswith("gate_charge_spectra_"):
        return _task5_gate_charge_spectra(df, key.removeprefix("gate_charge_spectra_"), alias)
    if "rate_vs_time" in key or "events_per_second" in key:
        return _rate_plot(df, task, alias)
    if "theta_phi" in key or "polar_theta_phi" in key:
        return _theta_phi_plot(df, alias)
    if "event_display" in key:
        return _event_display(df, alias)
    if "projection" in key and ("ellipse" in key or "angle" in key):
        return _projection_plot(df, alias)
    if "efficiency" in key:
        return _efficiency_plot(df, task, alias)
    if "occupancy" in key or "multiplicity" in key:
        return _occupancy_plot(df, alias)
    if any(word in key for word in ("retention", "threshold", "weakest")):
        return _threshold_plot(df, alias)
    if "topology" in key:
        return _topology_plot(df, alias)
    if "hexbin" in key or "pairgrid" in key:
        return _pair_matrix(df, task, alias, "hexbin")
    if "scatter" in key:
        return _pair_matrix(df, task, alias, "scatter")
    if any(word in key for word in ("matrix", "contagion", "activation", "transition")):
        return _matrix_plot(df, task, alias)
    if any(word in key for word in ("charge", "streamer")):
        return _charge_plot(df, task, alias)
    if any(word in key for word in ("residual", "gaussian", "histogram", "distribution", "chi2", "offender", "zigzag", "kinematics")):
        residual_columns = [str(column) for column in df.columns if "res" in str(column).lower()]
        if "residual" in key and residual_columns:
            return _hist_grid(df, task, alias, residual_columns[:6])
        return _hist_grid(df, task, alias)
    if "tt" in key or "trigger_types" in key:
        return _tt_plot(df, task, alias)
    return _hist_grid(df, task, alias)


def _enabled_aliases(config: dict) -> list[str]:
    if "-plot" in config or "-not_plot" in config:
        plotted = config.get("-plot", []) or []
        not_plotted = config.get("-not_plot", []) or []
        if not isinstance(plotted, list) or not isinstance(not_plotted, list):
            raise ValueError("'-plot' and '-not_plot' must each contain a YAML list of aliases.")
        plotted = [str(alias) for alias in plotted]
        not_plotted = [str(alias) for alias in not_plotted]
        overlap = sorted(set(plotted) & set(not_plotted))
        if overlap:
            raise ValueError(f"FINAL plot aliases cannot be in both '-plot' and '-not_plot': {overlap}")
        return list(dict.fromkeys(plotted))
    mode = str(config.get("plot_mode", "all")).strip().lower()
    statuses = config.get("plots", {}) or {}
    enabled: list[str] = []
    for alias, raw_status in statuses.items():
        status = str(raw_status).strip().lower()
        if status in {"none", "off", "false", "0"}:
            continue
        if mode == "all":
            enabled.append(str(alias))
        elif mode == "usual" and status in {"usual", "essential"}:
            enabled.append(str(alias))
        elif mode == "essential" and status == "essential":
            enabled.append(str(alias))
        elif mode == "debug" and status == "debug":
            enabled.append(str(alias))
    return enabled


def run_final_plotter(
    *,
    task: int,
    expected_prefixes: tuple[str, ...],
    parquet_path: str | Path,
    config_path: str | Path,
) -> None:
    parquet = Path(parquet_path).expanduser().resolve()
    if not any(parquet.name.startswith(prefix) for prefix in expected_prefixes):
        expected = " or ".join(f"{prefix}*.parquet" for prefix in expected_prefixes)
        raise SystemExit(f"Task {task} final plotter expects {expected}; got {parquet.name!r}.")

    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    aliases = _enabled_aliases(config)
    dataframe = pd.read_parquet(parquet)

    output_directory = parquet.parent / "FINAL_PLOTS" / f"TASK_{task}" / parquet.stem
    output_directory.mkdir(parents=True, exist_ok=True)
    save_png = bool(config.get("save_png", True))
    save_pdf = bool(config.get("save_pdf", True))
    pdf_path = output_directory / f"{parquet.stem}_task_{task}_final_plots.pdf"
    pdf = PdfPages(pdf_path) if save_pdf else None
    generated = 0

    try:
        for index, alias in enumerate(aliases, start=1):
            try:
                figure = render_final_alias(dataframe, task, alias)
            except Exception as exc:
                warnings.warn(f"FINAL plot {alias!r} failed and was skipped: {exc}")
                continue
            if figure is None:
                warnings.warn(f"FINAL plot {alias!r} skipped: the derived parquet does not expose the quantities it needs.")
                continue
            figure.suptitle(f"{parquet.name}\n{alias.replace('_', ' ')}", fontsize=11)
            if save_png:
                figure.savefig(output_directory / f"{index:03d}_{alias}.png", dpi=150, bbox_inches="tight")
            if pdf is not None:
                pdf.savefig(figure, dpi=150, bbox_inches="tight")
            plt.close(figure)
            generated += 1
    finally:
        if pdf is not None:
            pdf.close()
            if generated == 0 and pdf_path.exists():
                pdf_path.unlink()

    print(f"Task {task} FINAL plotting complete: {generated}/{len(aliases)} configured plots generated.")
    print(f"Output directory: {output_directory}")
