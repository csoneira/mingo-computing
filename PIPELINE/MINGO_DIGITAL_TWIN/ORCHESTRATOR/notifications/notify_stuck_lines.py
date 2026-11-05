#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/notifications/notify_stuck_lines.py
Purpose: Rate-limited alerting for persistent STEP_1 stuck-line and broken-run conditions.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/notifications/notify_stuck_lines.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib import error, parse, request


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    root = _root_dir()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-csv", required=True, type=Path)
    parser.add_argument("--stuck-csv", type=Path, default=None)
    parser.add_argument("--alert-state-file", required=True, type=Path)
    parser.add_argument("--min-cycles", type=int, default=3)
    parser.add_argument("--repeat-cycles", type=int, default=60)
    parser.add_argument("--min-observation-interval-s", type=int, default=45)
    parser.add_argument(
        "--token-file",
        type=Path,
        default=root / "CONTEXTUAL" / "OPERATIONS" / "OPERATIONS_SCRIPTS" / "NOTIFICATIONS" / "TELEGRAM_BOT" / "API_TOKEN.txt",
    )
    parser.add_argument(
        "--chat-ids-file",
        type=Path,
        default=root / "CONTEXTUAL" / "OPERATIONS" / "OPERATIONS_SCRIPTS" / "NOTIFICATIONS" / "TELEGRAM_BOT" / "ALERT_CHAT_IDS.txt",
    )
    parser.add_argument("--chat-ids", default="")
    parser.add_argument("--source", default="run_step")
    parser.add_argument("--enabled", choices=["0", "1"], default="1")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_state_csv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = str(row.get("key", "")).strip()
            value = str(row.get("value", "")).strip()
            if key:
                values[key] = value
    return values


def read_stuck_preview(path: Path | None, limit: int = 5) -> list[str]:
    if path is None or not path.exists():
        return []
    preview: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            status = str(row.get("status", "")).strip().lower()
            if status not in {"stuck", "no_activity"}:
                continue
            step_1_id = str(row.get("step_1_id", "")).strip() or "?"
            age_s = str(row.get("age_s", "")).strip() or "?"
            pending_rows = str(row.get("pending_rows", "")).strip() or "?"
            preview.append(f"line={step_1_id} age_s={age_s} pending_rows={pending_rows}")
            if len(preview) >= limit:
                break
    return preview


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_chat_ids(raw: str) -> list[str]:
    values: list[str] = []
    for token in raw.replace("\n", ",").replace(" ", ",").split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        values.append(cleaned)
    return values


def load_chat_ids(args: argparse.Namespace) -> list[str]:
    env_chat_ids = os.environ.get("SIM_ALERT_TELEGRAM_CHAT_IDS", "")
    merged = [args.chat_ids, env_chat_ids]
    for item in merged:
        parsed = parse_chat_ids(item)
        if parsed:
            return parsed

    if args.chat_ids_file.exists():
        collected: list[str] = []
        for line in args.chat_ids_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            collected.extend(parse_chat_ids(line))
        if collected:
            return collected
    return []


def load_token(args: argparse.Namespace) -> str:
    token = os.environ.get("SIM_ALERT_TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token
    if args.token_file.exists():
        token = args.token_file.read_text(encoding="utf-8").strip()
    return token


def send_telegram_message(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    body = parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = request.Request(endpoint, data=body, method="POST")
    try:
        with request.urlopen(req, timeout=15) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        return False, f"http_error:{exc.code}"
    except Exception as exc:  # pragma: no cover - runtime/network failures
        return False, f"network_error:{exc}"

    try:
        parsed_payload = json.loads(payload)
    except json.JSONDecodeError:
        return False, "invalid_json_response"

    if parsed_payload.get("ok"):
        return True, "ok"
    return False, str(parsed_payload.get("description", "telegram_error"))


def build_alert_message(
    source: str,
    stuck_lines: int,
    broken_runs: int,
    oldest_age_s: int,
    consecutive_cycles: int,
    preview: list[str],
) -> str:
    lines = [
        f"[MINGO_DIGITAL_TWIN] {source} persistent scheduler issue",
        f"stuck_step1_lines={stuck_lines} broken_runs={broken_runs}",
        f"oldest_active_step1_age_s={oldest_age_s} consecutive_cycles={consecutive_cycles}",
    ]
    if preview:
        lines.append("preview:")
        lines.extend(preview)
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    min_cycles = max(1, int(args.min_cycles))
    repeat_cycles = max(1, int(args.repeat_cycles))
    min_observation_interval_s = max(0, int(args.min_observation_interval_s))

    values = read_state_csv(args.state_csv)
    stuck_lines = parse_int(values.get("stuck_step1_lines"), default=0)
    broken_runs = parse_int(values.get("broken_runs"), default=0)
    oldest_age_s = parse_int(values.get("oldest_active_step1_age_s"), default=0)

    now = int(time.time())
    alert_state = load_json(args.alert_state_file)
    last_observed_epoch = parse_int(alert_state.get("last_observed_epoch"), default=0)
    if min_observation_interval_s > 0 and (now - last_observed_epoch) < min_observation_interval_s:
        remaining = min_observation_interval_s - (now - last_observed_epoch)
        print(f"status=observation_throttled remaining_s={remaining}")
        return 0

    condition_active = stuck_lines > 0 or broken_runs > 0
    alert_state["last_observed_epoch"] = now

    if condition_active:
        if bool(alert_state.get("condition_active", False)):
            consecutive_cycles = parse_int(alert_state.get("consecutive_cycles"), default=0) + 1
        else:
            consecutive_cycles = 1
            alert_state["first_detected_epoch"] = now
        alert_state["condition_active"] = True
        alert_state["consecutive_cycles"] = consecutive_cycles
    else:
        alert_state.update(
            {
                "condition_active": False,
                "consecutive_cycles": 0,
                "last_alert_cycle": 0,
                "last_alert_epoch": 0,
            }
        )
        save_json(args.alert_state_file, alert_state)
        print("status=clear")
        return 0

    if consecutive_cycles < min_cycles:
        save_json(args.alert_state_file, alert_state)
        print(
            f"status=pending consecutive_cycles={consecutive_cycles} min_cycles={min_cycles} "
            f"stuck_step1_lines={stuck_lines} broken_runs={broken_runs}"
        )
        return 0

    last_alert_cycle = parse_int(alert_state.get("last_alert_cycle"), default=0)
    alerts_sent = parse_int(alert_state.get("alerts_sent"), default=0)
    if alerts_sent > 0 and (consecutive_cycles - last_alert_cycle) < repeat_cycles:
        save_json(args.alert_state_file, alert_state)
        remaining = repeat_cycles - (consecutive_cycles - last_alert_cycle)
        print(
            f"status=cooldown remaining_cycles={remaining} consecutive_cycles={consecutive_cycles} "
            f"stuck_step1_lines={stuck_lines} broken_runs={broken_runs}"
        )
        return 0

    preview = read_stuck_preview(args.stuck_csv)
    message = build_alert_message(
        source=args.source,
        stuck_lines=stuck_lines,
        broken_runs=broken_runs,
        oldest_age_s=oldest_age_s,
        consecutive_cycles=consecutive_cycles,
        preview=preview,
    )

    token = load_token(args)
    chat_ids = load_chat_ids(args)
    enabled = args.enabled == "1"
    sent_count = 0
    failures: list[str] = []

    if not enabled:
        status = "disabled"
    elif not token:
        status = "missing_token"
    elif not chat_ids:
        status = "missing_chat_ids"
    elif args.dry_run:
        status = "dry_run"
    else:
        status = "sent"
        for chat_id in chat_ids:
            ok, detail = send_telegram_message(token, chat_id, message)
            if ok:
                sent_count += 1
            else:
                failures.append(f"{chat_id}:{detail}")
        if sent_count == 0:
            status = "send_failed"

    alert_state["last_alert_cycle"] = consecutive_cycles
    alert_state["last_alert_epoch"] = now
    alert_state["alerts_sent"] = alerts_sent + 1
    save_json(args.alert_state_file, alert_state)

    if failures:
        print(
            f"status={status} recipients={sent_count}/{len(chat_ids)} failures={'|'.join(failures)} "
            f"stuck_step1_lines={stuck_lines} broken_runs={broken_runs}"
        )
    else:
        print(
            f"status={status} recipients={sent_count}/{len(chat_ids)} "
            f"stuck_step1_lines={stuck_lines} broken_runs={broken_runs}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
