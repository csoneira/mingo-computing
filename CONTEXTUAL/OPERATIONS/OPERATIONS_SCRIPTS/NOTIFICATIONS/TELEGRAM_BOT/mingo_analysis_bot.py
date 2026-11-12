#!/usr/bin/env python3
"""On-demand metadata plotting for the MINGO computing Telegram bot."""

from __future__ import annotations

import logging
import configparser
import math
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import telebot


_REPO_IMPORT_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root
BASE_DIR = get_repo_root()
BOT_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BOT_DIR / "API_TOKEN.txt"
RESTART_SCRIPT = BOT_DIR / "kill_bot_and_restart.sh"
PAGE_SIZE = 18
MAX_DAYS = 3650.0
REQUESTS: dict[int, dict[str, object]] = {}
PLOT_CONFIG_PATH = BOT_DIR / "plot_metadata.ini"
GUN_CHAMBER_DIR = BOT_DIR / "GUN_CHAMBER"


def load_plot_config(path: Path = PLOT_CONFIG_PATH) -> dict[str, float]:
    config = configparser.ConfigParser()
    if not config.read(path, encoding="utf-8"):
        raise FileNotFoundError(f"Metadata plot config not found: {path}")
    quantile_percent = config.getfloat("plot", "clip_quantile_percent")
    if not math.isfinite(quantile_percent) or not 0 <= quantile_percent < 50:
        raise ValueError("clip_quantile_percent must be at least 0 and less than 50")
    return {"clip_quantile_percent": quantile_percent}


PLOT_CONFIG = load_plot_config()


def load_token() -> str:
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("Telegram token file is empty")
    return token


def metadata_files(station: str) -> list[Path]:
    station_root = BASE_DIR / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station
    live_root = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    files = sorted(live_root.glob("TASK_*/METADATA/*.csv"))
    # Older, consolidated products remain useful where no live task CSV exists.
    if not files:
        product_root = station_root / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "METADATA"
        files = sorted(product_root.glob("TASK_*/task_*.csv"))
    return [path for path in files if path.is_file()]


def numeric_columns(path: Path) -> list[str]:
    frame = pd.read_csv(path, nrows=100)
    excluded = {"filename_base", "execution_timestamp", "execution_date", "param_hash"}
    columns: list[str] = []
    for name in frame.columns:
        if name in excluded:
            continue
        converted = pd.to_numeric(frame[name], errors="coerce")
        if converted.notna().any():
            columns.append(str(name))
    return columns


def column_options(columns: list[str]) -> list[dict[str, object]]:
    """Group strip fields into 4x4 and plane fields into 4x1 selections."""
    strip_pattern = re.compile(r"^P([1-4])_s([1-4])_(.+)$")
    plane_pattern = re.compile(r"^P([1-4])_(.+)$")
    entries: list[tuple[tuple[str, str], object]] = []
    strip_groups: dict[str, dict[tuple[int, int], str]] = {}
    plane_groups: dict[str, dict[int, str]] = {}
    positions: dict[tuple[str, str], int] = {}

    for column in columns:
        match = strip_pattern.match(column)
        if match is not None:
            plane, strip, suffix = int(match.group(1)), int(match.group(2)), match.group(3)
            key = ("strip", suffix)
            if suffix not in strip_groups:
                strip_groups[suffix] = {}
                positions[key] = len(entries)
                entries.append((key, None))
            strip_groups[suffix][(plane, strip)] = column
            continue

        match = plane_pattern.match(column)
        if match is not None:
            plane, suffix = int(match.group(1)), match.group(2)
            key = ("plane", suffix)
            if suffix not in plane_groups:
                plane_groups[suffix] = {}
                positions[key] = len(entries)
                entries.append((key, None))
            plane_groups[suffix][plane] = column
            continue

        if match is None:
            entries.append((column, {"label": column, "column": column, "members": {}}))

    for suffix, members in strip_groups.items():
        if len(members) == 1:
            column = next(iter(members.values()))
            entries[positions[("strip", suffix)]] = (
                ("strip", suffix), {"label": column, "column": column, "members": {}}
            )
        else:
            entries[positions[("strip", suffix)]] = (
                ("strip", suffix),
                {
                    "label": f"P*_s*_{suffix} (4x4; {len(members)}/16 present)",
                    "column": suffix,
                    "members": members,
                },
            )
    for suffix, members in plane_groups.items():
        entries[positions[("plane", suffix)]] = (
            ("plane", suffix),
            {
                "label": f"P*_{suffix} (4x1; {len(members)}/4 present)",
                "column": suffix,
                "plane_members": members,
            },
        )
    return [option for _, option in entries if option is not None]


def filename_datetime(value: object) -> datetime | None:
    token = str(value).strip()
    try:
        if not token.startswith("mi") or len(token) < 15:
            return None
        year, day, hour, minute, second = (
            int(token[4:6]), int(token[6:9]), int(token[9:11]), int(token[11:13]), int(token[13:15])
        )
        if day < 1 or day > 366:
            return None
        return datetime(2000 + year, 1, 1) + timedelta(
            days=day - 1, hours=hour, minutes=minute, seconds=second
        )
    except (TypeError, ValueError):
        return None


def date_values(frame: pd.DataFrame, basis: str) -> pd.Series:
    if basis == "execution":
        for column in ("execution_timestamp", "execution_date"):
            if column in frame.columns:
                dates = pd.to_datetime(frame[column], format="%Y-%m-%d_%H.%M.%S", errors="coerce")
                if not dates.notna().any():
                    dates = pd.to_datetime(frame[column], format="mixed", errors="coerce")
                if dates.notna().any():
                    return dates
        raise ValueError("This CSV has no usable execution_timestamp or execution_date column.")
    if "filename_base" not in frame.columns:
        raise ValueError("This CSV has no filename_base column for acquisition dates.")
    return pd.to_datetime(frame["filename_base"].map(filename_datetime), errors="coerce")


def clip_to_quantiles(
    values: pd.Series, valid: pd.Series, quantile_percent: float
) -> tuple[pd.Series, pd.Series]:
    """Return values clipped at per-series quantiles and the clipped-point mask."""
    quantile = quantile_percent / 100.0
    selected = values[valid]
    lower = float(selected.quantile(quantile))
    upper = float(selected.quantile(1.0 - quantile))
    clipped_mask = valid & ((values < lower) | (values > upper))
    return values.clip(lower=lower, upper=upper), clipped_mask


def plot_metadata(path: Path, selection: dict[str, object], basis: str, days: float) -> Path:
    frame = pd.read_csv(path)
    dates = date_values(frame, basis)
    now = pd.Timestamp.now()
    cutoff = now - timedelta(days=days)
    valid_dates = dates.notna() & (dates >= cutoff) & (dates <= now)
    members = selection.get("members", {})
    label = str(selection["label"])
    quantile_percent = PLOT_CONFIG["clip_quantile_percent"]
    x_label = "Execution date" if basis == "execution" else "Acquisition date"

    plane_members = selection.get("plane_members", {})
    if members or plane_members:
        is_plane_plot = bool(plane_members)
        ncols = 1 if is_plane_plot else 4
        nrows = 4
        fig, axes = plt.subplots(nrows, ncols, figsize=(10 if is_plane_plot else 15, 10),
                                 sharex=True, sharey=True, constrained_layout=True, squeeze=False)
        plotted = False
        if is_plane_plot:
            cells = [(plane, None, plane_members.get(plane)) for plane in range(1, 5)]
        else:
            cells = [(plane, strip, members.get((plane, strip)))
                     for plane in range(1, 5) for strip in range(1, 5)]
        for plane, strip, column in cells:
            ax = axes[plane - 1, 0 if is_plane_plot else strip - 1]
            title = f"Plane {plane}" if is_plane_plot else f"Plane {plane}, strip {strip}"
            ax.set_title(title, fontsize=9)
            if column is None or column not in frame.columns:
                ax.text(0.5, 0.5, "Column missing", ha="center", va="center", transform=ax.transAxes)
            else:
                values = pd.to_numeric(frame[column], errors="coerce")
                valid = valid_dates & values.notna()
                if valid.any():
                    clipped_values, clipped_mask = clip_to_quantiles(values, valid, quantile_percent)
                    normal_mask = valid & ~clipped_mask
                    ax.scatter(dates[normal_mask], clipped_values[normal_mask], s=12, alpha=0.8)
                    if clipped_mask.any():
                        ax.scatter(dates[clipped_mask], clipped_values[clipped_mask],
                                   s=18, color="red", alpha=0.9)
                    plotted = True
                else:
                    ax.text(0.5, 0.5, "No data in window", ha="center", va="center", transform=ax.transAxes)
            ax.grid(True, alpha=0.25)
            ax.set_ylabel(label, fontsize=8)
        if not plotted:
            plt.close(fig)
            raise ValueError(f"No numeric values for `{label}` in the last {days:g} days.")
        fig.supxlabel(x_label)
        fig.suptitle(
            f"{path.parent.parent.name} · {path.name}\n{label} · last {days:g} days\n"
            f"Red points clipped at {quantile_percent:g}% / {100 - quantile_percent:g}% quantiles"
        )
        for ax in axes[-1, :]:
            ax.tick_params(axis="x", labelrotation=25, labelsize=8)
    else:
        column = str(selection["column"])
        if column not in frame.columns:
            raise ValueError("The selected column is no longer present in this CSV.")
        values = pd.to_numeric(frame[column], errors="coerce")
        valid = valid_dates & values.notna()
        if not valid.any():
            raise ValueError(f"No numeric values for `{label}` in the last {days:g} days.")
        clipped_values, clipped_mask = clip_to_quantiles(values, valid, quantile_percent)
        normal_mask = valid & ~clipped_mask
        fig, ax = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
        ax.scatter(dates[normal_mask], clipped_values[normal_mask], s=20, alpha=0.8)
        if clipped_mask.any():
            ax.scatter(dates[clipped_mask], clipped_values[clipped_mask], s=28, color="red", alpha=0.9)
        ax.set_xlabel(x_label)
        ax.set_ylabel(column)
        ax.set_title(
            f"{path.parent.parent.name} · {path.name}\n{label} · last {days:g} days\n"
            f"Red points clipped at {quantile_percent:g}% / {100 - quantile_percent:g}% quantiles"
        )
        ax.grid(True, alpha=0.25)
        fig.autofmt_xdate()
    fd, output_name = tempfile.mkstemp(prefix="mingo_metadata_", suffix=".png")
    os.close(fd)
    output = Path(output_name)
    try:
        fig.savefig(output, dpi=140)
    finally:
        plt.close(fig)
    return output


def page_text(items: list[str], page: int, heading: str) -> str:
    start = page * PAGE_SIZE
    subset = items[start : start + PAGE_SIZE]
    body = "\n".join(f"{start + idx}. {item}" for idx, item in enumerate(subset))
    suffix = "\nReply next for more." if start + PAGE_SIZE < len(items) else ""
    return f"{heading}\n{body}\n\nReply with a number (choices start at 0), or cancel.{suffix}"


def send_page(chat_id: int, state: dict[str, object], kind: str) -> None:
    items = state[f"{kind}_items"]
    page = int(state.get(f"{kind}_page", 0))
    if state.get("mode") == "gui":
        start = page * PAGE_SIZE
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        for index, item in enumerate(items[start : start + PAGE_SIZE], start=start):
            label = str(item)
            if len(label) > 64:
                label = label[:61] + "..."
            markup.add(telebot.types.InlineKeyboardButton(
                label, callback_data=f"pm|select|{kind}|{index}"
            ))
        if start + PAGE_SIZE < len(items):
            markup.add(telebot.types.InlineKeyboardButton(
                "Next page →", callback_data=f"pm|next|{kind}"
            ))
        markup.add(telebot.types.InlineKeyboardButton("Cancel", callback_data="pm|cancel"))
        bot.send_message(chat_id, str(state[f"{kind}_heading"]), reply_markup=markup)
    else:
        bot.send_message(chat_id, page_text(items, page, str(state[f"{kind}_heading"])))


def clear_request(chat_id: int) -> None:
    REQUESTS.pop(chat_id, None)


try:
    TOKEN = load_token()
except Exception:
    if "--check-config" in sys.argv:
        print("Telegram configuration check failed; inspect the token file privately.")
        raise SystemExit(1)
    raise

bot = telebot.TeleBot(TOKEN)

if "--check-config" in sys.argv:
    try:
        if "--online" in sys.argv:
            telebot.apihelper.CONNECT_TIMEOUT = 10
            telebot.apihelper.READ_TIMEOUT = 10
            bot.get_me()
    except Exception:
        print("Telegram configuration/authentication check failed; inspect credentials privately.")
        raise SystemExit(1)
    print("Telegram configuration check passed; polling was not started.")
    raise SystemExit(0)


@bot.message_handler(commands=["start", "help"])
def welcome(message):
    bot.send_message(
        message.chat.id,
        "Metadata plots are generated only when requested.\n\n"
        "/plot_metadata_gui - choose options with buttons.\n"
        "/plot_metadata_cli - choose options by replying with numbers.\n"
        "/round_in_the_chamber - send the newest file from GUN_CHAMBER.\n"
        "/restart_bot - restart the Telegram bot.\n"
        "Use `cancel` at any prompt to stop.",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["restart_bot"])
def handle_restart_bot(message):
    """Restart the polling process via the same watchdog used by cron."""
    chat_id = message.chat.id
    bot.send_message(chat_id, "Restart requested. The bot will reconnect shortly.")
    if not RESTART_SCRIPT.is_file():
        logging.error("Telegram restart script is missing: %s", RESTART_SCRIPT)
        bot.send_message(chat_id, "Restart failed: restart helper is unavailable.")
        return
    try:
        subprocess.Popen(
            ["/bin/bash", str(RESTART_SCRIPT)],
            cwd=str(BOT_DIR),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        logging.exception("Could not launch Telegram bot restart helper")
        bot.send_message(chat_id, "Restart failed: could not launch the restart helper.")


@bot.message_handler(commands=["round_in_the_chamber"])
def send_latest_chamber_file(message):
    """Send the newest regular file staged in the bot-local GUN_CHAMBER folder."""
    if not GUN_CHAMBER_DIR.is_dir():
        bot.send_message(message.chat.id, "The GUN_CHAMBER report folder is not available yet.")
        return

    candidates = [
        path for path in GUN_CHAMBER_DIR.iterdir()
        if path.is_file() and not path.name.startswith(".")
    ]
    if not candidates:
        bot.send_message(message.chat.id, "There is no report in GUN_CHAMBER yet.")
        return

    latest = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    if latest.stat().st_size > 49 * 1024 * 1024:
        bot.send_message(message.chat.id, f"The newest report is too large to send: {latest.name}")
        return

    try:
        with latest.open("rb") as report:
            bot.send_document(message.chat.id, report, caption=f"Latest GUN_CHAMBER file: {latest.name}")
    except Exception:
        logging.exception("Could not send GUN_CHAMBER file %s", latest.name)
        bot.send_message(message.chat.id, "Could not send the newest GUN_CHAMBER file.")


def begin_plot(message, mode: str = "cli"):
    chat_id = message.chat.id
    stations = [f"MINGO{idx:02d}" for idx in range(5)]
    REQUESTS[chat_id] = {
        "step": "station", "station_items": stations, "station_page": 0,
        "station_heading": "Choose a station:", "mode": mode,
    }
    send_page(chat_id, REQUESTS[chat_id], "station")


@bot.message_handler(commands=["plot_metadata", "plot_metadata_cli"])
def begin_plot_cli(message):
    begin_plot(message, "cli")


@bot.message_handler(commands=["plot_metadata_gui"])
def begin_plot_gui(message):
    begin_plot(message, "gui")


def ask_days(chat_id: int) -> None:
    REQUESTS[chat_id]["step"] = "days"
    bot.send_message(
        chat_id,
        f"How many days back? Enter a number greater than 0 and at most {MAX_DAYS:g}; decimals are allowed.",
    )


def choose_basis(chat_id: int, state: dict[str, object], basis: str) -> None:
    state["basis"] = basis
    ask_days(chat_id)


def select_option(chat_id: int, state: dict[str, object], step: str, index: int) -> None:
    selected = state[f"{step}_items"][index]
    if step == "station":
        state["station"] = selected
        files = metadata_files(str(selected))
        if not files:
            clear_request(chat_id)
            bot.send_message(chat_id, f"No metadata CSV files found for {selected}.")
            return
        tasks = sorted({path.parent.parent.name for path in files})
        state.update({"step": "task", "task_items": tasks, "task_page": 0,
                      "task_heading": f"{selected}: choose a task:"})
        send_page(chat_id, state, "task")
        return

    if step == "task":
        task = str(selected)
        files = [path for path in metadata_files(str(state["station"]))
                 if path.parent.parent.name == task]
        if not files:
            clear_request(chat_id)
            bot.send_message(chat_id, f"No metadata CSV files found for {state['station']} {task}.")
            return
        state.update({"task": task, "step": "file", "file_paths": files,
                      "file_items": [path.name for path in files], "file_page": 0,
                      "file_heading": f"{state['station']} {task}: choose a metadata CSV:"})
        send_page(chat_id, state, "file")
        return

    if step == "file":
        selected_path = state["file_paths"][index]
        try:
            columns = numeric_columns(selected_path)
        except Exception as exc:
            clear_request(chat_id)
            bot.send_message(chat_id, f"Could not read metadata CSV: {exc}")
            return
        if not columns:
            clear_request(chat_id)
            bot.send_message(chat_id, "This CSV has no numeric columns to plot.")
            return
        options = column_options(columns)
        state.update({"path": selected_path, "step": "column",
                      "column_items": [option["label"] for option in options],
                      "column_options": options, "column_page": 0,
                      "column_heading": "Choose a numeric column:"})
        send_page(chat_id, state, "column")
        return

    state["column_option"] = state["column_options"][index]
    state["step"] = "basis"
    if state.get("mode") == "gui":
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            telebot.types.InlineKeyboardButton("Execution / processing date", callback_data="pm|basis|execution"),
            telebot.types.InlineKeyboardButton("Acquisition / data date", callback_data="pm|basis|acquisition"),
            telebot.types.InlineKeyboardButton("Cancel", callback_data="pm|cancel"),
        )
        bot.send_message(chat_id, "Choose date basis:", reply_markup=markup)
    else:
        bot.send_message(chat_id, "Choose date basis:\n1. Execution / processing date\n2. Acquisition / data date\nReply `1` or `2`.")


@bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("pm|")))
def plot_callback(call):
    chat_id = call.message.chat.id if call.message else call.from_user.id
    state = REQUESTS.get(chat_id)
    parts = (call.data or "").split("|")
    bot.answer_callback_query(call.id)
    if len(parts) >= 2 and parts[1] == "cancel":
        clear_request(chat_id)
        bot.send_message(chat_id, "Metadata plot request cancelled.")
        return
    if state is None or state.get("mode") != "gui":
        bot.send_message(chat_id, "Plot request expired. Start again with /plot_metadata_gui.")
        return
    if len(parts) == 3 and parts[1] == "next":
        kind = parts[2]
        if kind != state.get("step") or kind not in {"station", "task", "file", "column"}:
            return
        if (int(state[f"{kind}_page"]) + 1) * PAGE_SIZE < len(state[f"{kind}_items"]):
            state[f"{kind}_page"] = int(state[f"{kind}_page"]) + 1
            send_page(chat_id, state, kind)
        return
    if len(parts) == 3 and parts[1] == "basis" and state.get("step") == "basis":
        if parts[2] in {"execution", "acquisition"}:
            choose_basis(chat_id, state, parts[2])
        return
    if len(parts) == 4 and parts[1] == "select":
        kind = parts[2]
        if kind != state.get("step") or kind not in {"station", "task", "file", "column"}:
            return
        try:
            index = int(parts[3])
        except ValueError:
            return
        if index < 0 or index >= len(state[f"{kind}_items"]):
            return
        select_option(chat_id, state, kind, index)


@bot.message_handler(func=lambda message: message.chat.id in REQUESTS, content_types=["text"])
def plot_prompt(message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    state = REQUESTS.get(chat_id)
    if state is None:
        return
    if text.lower() in {"cancel", "/cancel"}:
        clear_request(chat_id)
        bot.send_message(chat_id, "Metadata plot request cancelled.")
        return

    step = state["step"]
    if text.lower() in {"next", "/next"} and step in {"station", "task", "file", "column"}:
        if state.get("mode") == "gui":
            bot.send_message(chat_id, "Choose an option using the buttons, or cancel.")
            return
        item_key = f"{step}_items"
        page_key = f"{step}_page"
        if (int(state[page_key]) + 1) * PAGE_SIZE < len(state[item_key]):
            state[page_key] = int(state[page_key]) + 1
            send_page(chat_id, state, str(step))
        else:
            bot.send_message(chat_id, "There are no more choices on this page.")
        return

    if step in {"station", "task", "file", "column"}:
        if state.get("mode") == "gui":
            bot.send_message(chat_id, "Choose an option using the buttons, or cancel.")
            return
        items = state[f"{step}_items"]
        current_page = int(state[f"{step}_page"])
        start = current_page * PAGE_SIZE
        page_end = min(start + PAGE_SIZE, len(items))
        try:
            choice = int(text)
            index = choice
            if choice < start or choice >= page_end:
                raise ValueError
        except ValueError:
            bot.send_message(chat_id, f"Reply with a listed number, `next`, or `cancel`.", parse_mode="Markdown")
            return
        select_option(chat_id, state, str(step), index)
        return

    if step == "basis":
        if text not in {"1", "2"}:
            bot.send_message(chat_id, "Reply `1` for execution date or `2` for acquisition date.")
            return
        choose_basis(chat_id, state, "execution" if text == "1" else "acquisition")
        return

    if step == "days":
        try:
            days = float(text)
            if not math.isfinite(days) or not 0 < days <= MAX_DAYS:
                raise ValueError
            selection = state["column_option"]
            plot_path = plot_metadata(Path(state["path"]), selection, str(state["basis"]), days)
            try:
                with plot_path.open("rb") as photo:
                    bot.send_photo(chat_id, photo, caption=f"{Path(state['path']).name}\n{selection['label']} · {days:g} days")
            finally:
                plot_path.unlink(missing_ok=True)
            clear_request(chat_id)
        except ValueError as exc:
            bot.send_message(chat_id, f"{exc}\nEnter a number greater than 0 and at most {MAX_DAYS:g}; decimals are allowed.")
        except Exception:
            logging.exception("Metadata plot request failed")
            clear_request(chat_id)
            bot.send_message(chat_id, "Could not create this metadata plot. Check that the selected file has valid dates and values.")
        return

    clear_request(chat_id)
    bot.send_message(chat_id, "Plot request expired. Start again with /plot_metadata_gui or /plot_metadata_cli.")


def files_for_station(station: str) -> list[Path]:
    return metadata_files(station)


@bot.message_handler(func=lambda message: True, content_types=["text"])
def unknown(message):
    bot.send_message(
        message.chat.id,
        "Available commands: /plot_metadata_gui, /plot_metadata_cli, /round_in_the_chamber, and /restart_bot. Use /help for instructions.",
    )


if __name__ == "__main__":
    logging.info("Starting metadata plotting Telegram bot")
    bot.infinity_polling()
