"""
DATAFLOW_v3 Script Header v1
Script: FOR_MINGO_SYSTEMS/station_automation_scripts/bot_scripts/minitrasgo_bot.py
Purpose: Run with.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 FOR_MINGO_SYSTEMS/station_automation_scripts/bot_scripts/minitrasgo_bot.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations
import json

# Run with
# python3 minitrasgo_bot.py

import os
import hmac
import math
import shlex
import socket
import subprocess
import sys
from pathlib import Path

import io
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd

SCRIPT_PATH = Path(__file__).resolve()
BOT_DIRECTORY = SCRIPT_PATH.parent
TERMINAL_PASSWORD_PATH = BOT_DIRECTORY / "TERMINAL_PASSWORD.txt"
TERMINAL_BASE_DIRECTORY = Path.home()
MAX_MESSAGE_CHARS = 3500
TERMINAL_COMMAND_TIMEOUT_SEC = 300
NOISE_CONTROL_PLANE_COMBINATION_REPORT_CANDIDATES = (
    *(
        [
            next(
                parent for parent in SCRIPT_PATH.parents
                if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()
            ) / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/NOISE_CONTROL/PLOTS/noise_control_plane_combination_rate_report.pdf"
        ]
        if any((parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file() for parent in SCRIPT_PATH.parents)
        else []
    ),
    *(Path(os.environ["MINGO_NOISE_CONTROL_REPORT"]) for _ in [0] if os.environ.get("MINGO_NOISE_CONTROL_REPORT")),
)

# Check if a station number is provided
if len(sys.argv) < 2:
    print("Error: No station number provided.")
    print("Usage: python3 script.py <station_number>")
    sys.exit(1)

# Get the station number
station = sys.argv[1]

# Load the API keys from API.txt
api_keys = {}
try:
    with open("/home/rpcuser/station_automation_scripts/bot_scripts/API.txt", "r") as file:
        for line in file:
            key_parts = line.strip().split()
            if len(key_parts) == 2:  # Ensure valid format: <station> <api_key>
                station_id, key = key_parts
                api_keys[station_id] = key
except FileNotFoundError:
    print("Error: API.txt not found.")
    sys.exit(1)

# Get the API key for the specified station
if station in api_keys:
    api_key = api_keys[station]
    print(f"Using configured API key for station {station}.")
else:
    print(f"Error: No API key found for station {station}.")
    sys.exit(1)


# Initialize the bot with the API key
import telebot
from telebot import types as telebot_types
bot = telebot.TeleBot(api_key)
#bot = telebot.TeleBot("8012230734:AAFN1MH_9zbQ3RRoXnKBqalhkJSiEB3V3DE")

BOT_COMMAND_SPECS = [
    ("start", "Welcome message"),
    ("get_username", "Show your Telegram username and ID"),
    ("get_chat_id", "Show the current chat ID"),
    ("get_ip", "Show this station's IP addresses"),
    ("terminal", "Enable authenticated terminal mode"),
    ("exit", "Disable terminal mode"),
    ("send_voltage", "Send LIP power-supply voltage (legacy alias)"),
    ("send_voltage_lip", "Send LIP power-supply voltage"),
    ("send_voltage_caen", "Send voltage status for all CAEN channels"),
    ("send_gas_flow", "Send latest gas flow values"),
    ("send_internal_environment", "Send internal environment readings"),
    ("send_external_environment", "Send external environment readings"),
    ("send_trb_rates", "Send latest TRB rates"),
    ("send_original_report", "Send the original PDF report"),
    ("send_daq_report", "Send the latest DAQ report"),
    ("send_results_vs_time_report", "Send the results-vs-time report"),
    ("send_weekly_results_report", "Send the weekly results report"),
    ("send_monitoring_report", "Send the monitoring report"),
    ("noise_plane_report", "Send the noise-control plane-combination PDF"),
    ("plot_temperature", "Plot internal and external temperature"),
    ("plot_pressure", "Plot internal and external pressure"),
    ("plot_rh", "Plot internal and external humidity"),
    ("plot_asserted_edge_accepted", "Plot TRB asserted, edge, accepted"),
    ("plot_multiplexers", "Plot multiplexer rates"),
    ("plot_coincidence_planes", "Plot coincidence-plane rates"),
    ("plot_all_trb_rates", "Plot all TRB rates"),
    ("plot_hv_lip", "Plot LIP high voltage"),
    ("plot_hv_caen", "Plot CAEN channel voltages"),
    ("restart_tunnel", "Restart the tunnel"),
    ("gas_weight_measurement", "Log a gas-bottle weight measurement"),
]

try:
    bot.set_my_commands(
        [telebot_types.BotCommand(command, description) for command, description in BOT_COMMAND_SPECS]
    )
except Exception as exc:
    print(f"Warning: failed to publish Telegram command menu: {exc}")

def load_user_passwords() -> dict[str, str]:
    """Load per-user bot passwords from local configuration, never from Git."""
    env_value = os.environ.get("MINITRASGO_USER_PASSWORDS_JSON", "").strip()

    try:
        if env_value:
            data = json.loads(env_value)
        else:
            password_path = BOT_DIRECTORY / "USER_PASSWORDS.json"
            data = json.loads(password_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            "Password-protected bot commands disabled: "
            f"{BOT_DIRECTORY / 'USER_PASSWORDS.json'} not found"
        )
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Password-protected bot commands disabled: {exc}")
        return {}

    if not isinstance(data, dict):
        print("Password-protected bot commands disabled: invalid password map")
        return {}

    return {
        str(user_id): password
        for user_id, password in data.items()
        if str(user_id).strip() and isinstance(password, str) and password
    }


passwords = load_user_passwords()

TERMINAL_ACTIVE_CHATS: set[int] = set()
TERMINAL_CHAT_CWDS: dict[int, Path] = {}
PENDING_PLOT_REQUESTS: dict[tuple[int, int], tuple[object, object]] = {}


@bot.message_handler(commands=['get_username'])
def start(message):
    user_id = message.from_user.id  # Get the user's unique ID
    user_username = message.from_user.username  # Get the user's username (if available)
    user_first_name = message.from_user.first_name  # Get the user's first name
    user_last_name = message.from_user.last_name  # Get the user's last name (if available)

    # You can now use this user information as needed
    print(f"User ID: {user_id}")
    print(f"Username: {user_username}")
    print(f"First Name: {user_first_name}")
    print(f"Last Name: {user_last_name}")

    # Respond to the user
    bot.reply_to(message, f"Hello, {user_first_name}! Your ID is {user_id}. Your username is {user_username}.")

@bot.message_handler(commands=['get_chat_id'])
def send_chat_id(message):
    # Get the Chat ID
    chat_id = message.chat.id
    bot.reply_to(message, f"Your Chat ID is: {chat_id}")
    print(f"Chat ID: {chat_id}")  # Print Chat ID to console for debugging

def require_password(func):
    def wrapper(message):
        chat_id = message.chat.id
        user_id = message.from_user.id

        # Check if the user is in the passwords dictionary
        if str(user_id) in passwords:
            password = passwords[str(user_id)]
            bot.send_message(chat_id, "Please enter your password:")
            bot.register_next_step_handler(message, lambda m: check_password(m, password, func))
        else:
            bot.send_message(chat_id, "You are not authorized to perform this action.")

    return wrapper

def check_password(message, expected_password, func):
    user_id = message.from_user.id
    user_password = message.text

    if hmac.compare_digest(user_password, expected_password):
        func(message)
    else:
        bot.send_message(user_id, "Incorrect password. Action canceled.")


def truncate_message(text: str) -> str:
    if len(text) <= MAX_MESSAGE_CHARS:
        return text
    return text[: MAX_MESSAGE_CHARS - 3] + "..."


def load_terminal_password() -> str | None:
    environment_password = os.environ.get("MINITRASGO_TERMINAL_PASSWORD", "").strip()
    if environment_password:
        return environment_password
    try:
        password = TERMINAL_PASSWORD_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        print(
            "Terminal mode disabled: password file not found at "
            f"{TERMINAL_PASSWORD_PATH}"
        )
        return None
    if not password:
        print(f"Terminal mode disabled: password file is empty: {TERMINAL_PASSWORD_PATH}")
        return None
    return password


def get_chat_cwd(chat_id: int) -> Path:
    cwd = TERMINAL_CHAT_CWDS.get(chat_id, TERMINAL_BASE_DIRECTORY)
    if not cwd.exists() or not cwd.is_dir():
        cwd = TERMINAL_BASE_DIRECTORY
        TERMINAL_CHAT_CWDS[chat_id] = cwd
    return cwd


def maybe_handle_cd_command(chat_id: int, command_text: str) -> str | None:
    try:
        tokens = shlex.split(command_text)
    except ValueError as exc:
        return truncate_message(f"$ {command_text}\nInvalid command syntax: {exc}")
    if not tokens or tokens[0] != "cd":
        return None
    if len(tokens) > 2:
        return truncate_message(f"$ {command_text}\nUsage: cd <path>")

    current_cwd = get_chat_cwd(chat_id)
    target_raw = tokens[1] if len(tokens) == 2 else "~"
    target = Path(os.path.expandvars(os.path.expanduser(target_raw)))
    target = (current_cwd / target).resolve() if not target.is_absolute() else target.resolve()
    if not target.exists():
        return truncate_message(
            f"$ {command_text}\nExit code: 1\n"
            f"/bin/bash: cd: {target}: No such file or directory"
        )
    if not target.is_dir():
        return truncate_message(
            f"$ {command_text}\nExit code: 1\n/bin/bash: cd: {target}: Not a directory"
        )
    TERMINAL_CHAT_CWDS[chat_id] = target
    return truncate_message(f"$ {command_text}\nExit code: 0\nCurrent directory: {target}")


def run_terminal_command(command_text: str, cwd: Path) -> str:
    try:
        result = subprocess.run(
            command_text,
            cwd=str(cwd),
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            check=False,
            timeout=TERMINAL_COMMAND_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as exc:
        partial = "".join(
            part
            for part in (
                exc.stdout or "",
                "\n" if exc.stdout and exc.stderr else "",
                exc.stderr or "",
            )
        ).strip() or "<no output>"
        return truncate_message(
            f"$ {command_text}\nTimed out after {TERMINAL_COMMAND_TIMEOUT_SEC}s.\n{partial}"
        )
    except Exception as exc:
        return truncate_message(f"$ {command_text}\nExecution failed: {exc}")

    output = "".join(
        part
        for part in (
            result.stdout or "",
            "\n" if result.stdout and result.stderr else "",
            result.stderr or "",
        )
    ).strip() or "<no output>"
    return truncate_message(
        f"$ {command_text}\nExit code: {result.returncode}\n{output}"
    )


def maybe_handle_terminal_message(message) -> bool:
    chat_id = message.chat.id
    if chat_id not in TERMINAL_ACTIVE_CHATS:
        return False
    text = (message.text or "").strip()
    if not text:
        bot.send_message(chat_id, "Terminal mode is active. Send a command or use /exit.")
        return True
    if text == "/exit":
        TERMINAL_ACTIVE_CHATS.discard(chat_id)
        TERMINAL_CHAT_CWDS.pop(chat_id, None)
        bot.send_message(chat_id, "Terminal mode disabled.")
        return True
    cd_response = maybe_handle_cd_command(chat_id, text)
    if cd_response is not None:
        bot.send_message(chat_id, cd_response)
        return True
    bot.send_message(chat_id, run_terminal_command(text, get_chat_cwd(chat_id)))
    return True


def station_ip_report() -> str:
    hostname = socket.gethostname()
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        addresses = list(dict.fromkeys(result.stdout.split()))
    except (OSError, subprocess.SubprocessError):
        addresses = []
    if not addresses:
        try:
            addresses = sorted({
                item[4][0]
                for item in socket.getaddrinfo(hostname, None)
                if item[4] and item[4][0]
            })
        except socket.gaierror:
            addresses = []
    address_lines = "\n".join(f"- {address}" for address in addresses) or "- unavailable"
    return f"Station {station}\nHostname: {hostname}\nIP addresses:\n{address_lines}"


@bot.message_handler(commands=['terminal', 'term'])
def handle_terminal(message):
    chat_id = message.chat.id
    terminal_password = load_terminal_password()
    if terminal_password is None:
        bot.send_message(chat_id, "Terminal mode is disabled because no password is configured.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        bot.send_message(chat_id, "Usage: /term <password> (or /terminal <password>)")
        return
    if not hmac.compare_digest(parts[1].strip(), terminal_password):
        bot.send_message(chat_id, "Wrong password.")
        return
    TERMINAL_ACTIVE_CHATS.add(chat_id)
    TERMINAL_CHAT_CWDS[chat_id] = TERMINAL_BASE_DIRECTORY
    bot.send_message(
        chat_id,
        f"Terminal mode enabled. Current directory: {TERMINAL_BASE_DIRECTORY}\n"
        "Any text will run as a shell command. Use /exit to leave.",
    )


@bot.message_handler(commands=['exit'])
def handle_terminal_exit(message):
    chat_id = message.chat.id
    if chat_id in TERMINAL_ACTIVE_CHATS:
        TERMINAL_ACTIVE_CHATS.discard(chat_id)
        TERMINAL_CHAT_CWDS.pop(chat_id, None)
        bot.send_message(chat_id, "Terminal mode disabled.")
        return
    bot.send_message(chat_id, "Terminal mode is not active.")


@bot.message_handler(commands=['get_ip', 'ip'])
def send_station_ip(message):
    if maybe_handle_terminal_message(message):
        return
    bot.send_message(message.chat.id, station_ip_report())


def _first_existing_file(candidates):
    for candidate in candidates:
        path = Path(candidate)
        if path.exists() and path.is_file():
            return path
    return None


def _send_document_from_candidates(message, candidates, *, missing_label: str, caption: str | None = None):
    document_path = _first_existing_file(candidates)
    if document_path is None:
        bot.send_message(message.chat.id, f"{missing_label} is not available right now.")
        return

    try:
        with document_path.open('rb') as document:
            bot.send_document(message.chat.id, document, caption=caption)
    except Exception as exc:
        bot.send_message(message.chat.id, f"Error sending {missing_label}: {exc}")


# Monitoring --------------------------------------------------------------------

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    bot.reply_to(message, "Howdy, how are you doing? Type anything to see what you can do with the miniTRASGO bot.")

def _send_lip_voltage(message):
    binary_path = '/home/rpcuser/bin/HV/hv -b 0'
    print(binary_path)

    try:
        # Use subprocess to execute the binary file
        result = subprocess.run(binary_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

        # Check if the execution was successful
        if result.returncode == 0:
            print("Execution successful")
            # Output from the binary is available in result.stdout
        else:
            print("Execution failed")
            # Error message is available in result.stderr
            print("Error:", result.stderr)
    except Exception as e:
        print("An error occurred:", e)
        result = None  # Handle cases where the result variable might not exist

    # Send the response back to the user
    response = f'{result.stdout}' if result else "No response due to error."
    print(response)
    bot.send_message(message.chat.id, response)


@bot.message_handler(commands=['send_voltage', 'send_voltage_lip'])
def send_voltage_lip(message):
    _send_lip_voltage(message)


@bot.message_handler(commands=['send_voltage_caen'])
def send_voltage_caen(message):
    controller = Path('/home/rpcuser/CAEN/monitor.py')
    if not controller.is_file():
        bot.send_message(message.chat.id, "The CAEN power supply is not installed at this station.")
        return
    command = [str(controller), '-S']
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        response = result.stdout.strip() or result.stderr.strip() or "CAEN monitor returned no status."
        if result.returncode != 0:
            response = f"CAEN status failed (exit {result.returncode}):\n{response}"
        bot.send_message(message.chat.id, response[:MAX_MESSAGE_CHARS])
    except Exception as exc:
        bot.send_message(message.chat.id, f"Error reading CAEN voltage status: {exc}")


@bot.message_handler(commands=['send_gas_flow'])
def send_gas_flow(message):
	# /home/rpcuser/bin/flowmeter/bin

	# bash_command = "tail /home/rpcuser/logs/Flow0*"
	# output = os.popen(bash_command).read()
	# bot.send_message(message.chat.id, output)

        binary_path='/home/rpcuser/bin/flowmeter/bin/GetData 0 4'
        print(binary_path)

        # Use subprocess to execute the binary file
        result = subprocess.run(binary_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

        try:
            # Use subprocess to execute the binary file
            result = subprocess.run(binary_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

            # Check if the execution was successful
            if result.returncode == 0:
                print("Execution successful")
                # Output from the binary is available in result.stdout
            else:
                print("Execution failed")
                # Error message is available in result.stderr
                print("Error:", result.stderr)
        except Exception as e:
            print("An error occurred:", e)

        response = f'{result.stdout}'
        print(response)
        bot.send_message(message.chat.id, response)


@bot.message_handler(commands=['send_internal_environment'])
def send_internal_environment(message):
        bash_command = "tail /home/rpcuser/logs/clean_sensors_bus1*"
        output = os.popen(bash_command).read()
        bot.send_message(message.chat.id, "Date --- T (ºC) --- RH (%) --- P (mbar)")
        bot.send_message(message.chat.id, output)


@bot.message_handler(commands=['send_external_environment'])
def send_external_environment(message):
        bash_command = "tail /home/rpcuser/logs/clean_sensors_bus0*"
        output = os.popen(bash_command).read()
        bot.send_message(message.chat.id, "Date --- T (ºC) --- RH (%) --- P (mbar)")
        bot.send_message(message.chat.id, output)


@bot.message_handler(commands=['send_TRB_rates', 'send_trb_rates'])
def send_TRB_rates(message):
        bash_command = "tail /home/rpcuser/logs/clean_rates*"
        output = os.popen(bash_command).read()
        bot.send_message(message.chat.id, "Date --- Asserted - Edge - Accepted --- Multiplexer 1 - M2 - M3 - M4 --- Coincidence Plane 1 - CM2 - CM3 - CM4")
        bot.send_message(message.chat.id, output)

# Operation of miniTRASGO ----------------------------------------------------------------

#@bot.message_handler(commands=['set_data_control_system'])
#@require_password
#def set_data_control_system(message):
#        bash_command = "sh /media/externalDisk/gate/bin/dcs_om.sh"
#        bot.send_message(message.chat.id, 'Started...')
#        os.system(bash_command)
#        bot.send_message(message.chat.id, 'Executed.')


@bot.message_handler(commands=['start_daq'])
@require_password
def start_daq(message):
        bash_command = "/bin/bash /home/rpcuser/trbsoft/userscripts/trb399sc/startup_TRB399.sh"
        bot.send_message(message.chat.id, 'Started...')
        os.system(bash_command)
        bot.send_message(message.chat.id, 'Executed.')


@bot.message_handler(commands=['turn_on_hv'])
@require_password
def turn_on_HV(message):
        binary_path='/home/rpcuser/bin/HV/hv -b 0 -I 1 -V 5.52 -on'
        print(binary_path)

        # Use subprocess to execute the binary file
        result = subprocess.run(binary_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

        try:
            # Use subprocess to execute the binary file
            result = subprocess.run(binary_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

            # Check if the execution was successful
            if result.returncode == 0:
                print("Execution successful")
                # Output from the binary is available in result.stdout
            else:
                print("Execution failed")
                # Error message is available in result.stderr
                print("Error:", result.stderr)
        except Exception as e:
            print("An error occurred:", e)

        response = f'{result.stdout}'
        print(response)
        bot.send_message(message.chat.id, response)


@bot.message_handler(commands=['turn_off_hv'])
@require_password
def turn_off_HV(message):
        binary_path='/home/rpcuser/bin/HV/hv -b 0 -off'
        print(binary_path)

        # Use subprocess to execute the binary file
        result = subprocess.run(binary_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

        try:
            # Use subprocess to execute the binary file
            result = subprocess.run(binary_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

            # Check if the execution was successful
            if result.returncode == 0:
                print("Execution successful")
                # Output from the binary is available in result.stdout
            else:
                print("Execution failed")
                # Error message is available in result.stderr
                print("Error:", result.stderr)
        except Exception as e:
            print("An error occurred:", e)

        response = f'{result.stdout}'
        print(response)
        bot.send_message(message.chat.id, response)


@bot.message_handler(commands=['start_run'])
@require_password
def start_run(message):
        bash_command = "/bin/bash /home/rpcuser/trbsoft/userscripts/trb399sc/caye_startRun.sh"
        bot.send_message(message.chat.id, 'Started...')
        os.system(bash_command)
        bot.send_message(message.chat.id, 'Finished the run.')


@bot.message_handler(commands=['stop_run'])
@require_password
def stop_run(message):
        bash_command = "kill $(ps -ef | grep '[d]abc' | awk '{print $2}')"
        os.system(bash_command)

@bot.message_handler(commands=['any_reboot'])
@require_password
def any_reboot(message):
        bash_command = "reboot"
        bot.send_message(message.chat.id, 'Rebooting the system.')
        os.system(bash_command)

@bot.message_handler(commands=['safe_reboot'])
@require_password
def safe_reboot(message):
        binary_path='/home/rpcuser/bin/HV/hv -b 0 -off'
        print(binary_path)

        # Use subprocess to execute the binary file
        result = subprocess.run(binary_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

        try:
            # Use subprocess to execute the binary file
            result = subprocess.run(binary_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

            # Check if the execution was successful
            if result.returncode == 0:
                print("Execution successful")
                # Output from the binary is available in result.stdout
            else:
                print("Execution failed")
                # Error message is available in result.stderr
                print("Error:", result.stderr)
        except Exception as e:
            print("An error occurred:", e)

        response = f'{result.stdout}'
        print(response)
        bot.send_message(message.chat.id, response)

        bash_command = "sleep 300"
        bot.send_message(message.chat.id, 'Turning of the High Voltage... (waiting five minutes)')
        os.system(bash_command)

        bash_command = "reboot"
        bot.send_message(message.chat.id, 'Rebooting the system.')
        os.system(bash_command)

# Report and plots ------------------------------------------------------------------------

from datetime import datetime, timedelta

@bot.message_handler(commands=['send_original_report'])
def send_original_report(message):
        with open(f'/media/usb0/gate/system/devices/mingo01/reporting/report_mingo01.pdf', 'rb') as document:
                bot.send_document(message.chat.id, document)

@bot.message_handler(commands=['create_report'])
@require_password
def create_report(message):
        bash_command = "export RPCSYSTEM=sRPC;/home/rpcuser/gate/bin/createReport.sh"
        os.system(bash_command)

@bot.message_handler(commands=['send_daq_report'])
def send_daq_report(message):
	current_date = datetime.now()
	one_day_ago = current_date - timedelta(days=1)
	report_day = one_day_ago.strftime('20%y-%m-%d')

	with open(f'/home/rpcuser/caye_software/reports/report_daq_data_from_{report_day}.pdf', 'rb') as document:
		bot.send_document(message.chat.id, document)

@bot.message_handler(commands=['send_results_vs_time_report'])
def send_results_vs_time_report(message):
	current_date = datetime.now()
	one_day_ago = current_date - timedelta(days=1)
	report_day = one_day_ago.strftime('20%y-%m-%d')

	with open(f'/home/rpcuser/caye_software/reports/report_results_vs_time_from_{report_day}.pdf', 'rb') as document:
		bot.send_document(message.chat.id, document)

@bot.message_handler(commands=['send_weekly_results_report'])
def send_weekly_results_report(message):
	current_date = datetime.now()
	one_day_ago = current_date - timedelta(days=1)
	report_day = one_day_ago.strftime('20%y-%m-%d')

	with open(f'/home/rpcuser/caye_software/reports/weekly_report_results_vs_time_from_{report_day}.pdf', 'rb') as document:
		bot.send_document(message.chat.id, document)

@bot.message_handler(commands=['send_monitoring_report'])
def send_monitoring_report(message):
		current_date = datetime.now()
		one_day_ago = current_date - timedelta(days=1)
		report_day = one_day_ago.strftime('20%y-%m-%d')

		with open(f'/home/rpcuser/caye_software/reports/final_diagnosis_report_at_{report_day}.pdf', 'rb') as document:
			bot.send_document(message.chat.id, document)


@bot.message_handler(commands=['noise_plane_report', 'send_noise_control_plane_combination_report'])
def send_noise_control_plane_combination_report(message):
	_send_document_from_candidates(
		message,
		NOISE_CONTROL_PLANE_COMBINATION_REPORT_CANDIDATES,
		missing_label="Noise-control plane-combination report",
		caption="Noise-control plane-combination rate report",
	)


# Emergency and assistance --------------------------------------------------------------------------------------
@bot.message_handler(commands=['restart_tunnel'])
def restart_tunnel(message):
    # Command to find the PID of the 'lipana' process and kill it
    find_pid_command = "pgrep -f 'autossh.*lipana'"
    try:
        import subprocess
        pid = subprocess.check_output(find_pid_command, shell=True).decode().strip()
        if pid:
            os.system(f"kill {pid}")
            bot.send_message(message.chat.id, f'Closing the tunnel... It automatically will be open in less than a minute.')
        else:
            bot.send_message(message.chat.id, 'No process found.')
    except Exception as e:
        bot.send_message(message.chat.id, f'Error killing process: {e}')

@bot.message_handler(commands=['gas_weight_measurement'])
@require_password
def gas_weight_measurement(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "Enter the gas weight in **kilograms** (kg). The number must include **at least one decimal digit** (e.g., 2.5, 0.8).")

    def process_input(msg):
        user_input = msg.text.strip()

        try:
            # Try converting to float and ensure it contains a decimal point
            if '.' not in user_input or user_input.count('.') != 1:
                raise ValueError("Invalid format: No decimal point found.")

            value = float(user_input)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"{now} {value:.3f}\n"

            log_dir = "/home/rpcuser/logs"
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "clean_gas_weight_measurements.log")

            with open(log_file, "a") as f:
                f.write(log_entry)

            bot.send_message(chat_id, f"Logged: {log_entry.strip()}")
            
            bot.send_message(chat_id, f"Creating the log file division")
            SCRIPT_DIR = os.path.expanduser("~/station_automation_scripts/bot_scripts")
            script_path = os.path.join(SCRIPT_DIR, "split_gas_logs.sh")
            subprocess.run([script_path], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


        except ValueError:
            bot.send_message(chat_id, "Invalid input. Please enter a numeric value in kg with at least one decimal digit (e.g., 1.2).")

    bot.register_next_step_handler(message, process_input)



import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import io
import os

def parse_sensor_data(output):
    """Parse sensor rows from one or more raw dated log files."""
    lines = output.strip().split('\n')
    
    timestamps = []
    temperatures = []
    humidities = []
    pressures = []
    
    for line in lines:
        if line.strip():
            normalized = line.replace("T", " ").replace(";", "").replace("nan nan nan nan ", "")
            parts = normalized.split()
            if len(parts) >= 4:
                try:
                    # Parse timestamp
                    timestamp_str = f"{parts[0]} {parts[1]}"
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    timestamps.append(timestamp)
                    
                    # Parse sensor values
                    temperatures.append(float(parts[2]))
                    humidities.append(float(parts[3]))
                    pressures.append(float(parts[4]))
                except (ValueError, IndexError):
                    continue
    
    return timestamps, temperatures, humidities, pressures

number_of_plot_lines = 10000


def _request_plot_days(message, renderer):
    bot.send_message(message.chat.id, "How many days back should I plot? Floating admitted.")
    PENDING_PLOT_REQUESTS[(message.chat.id, message.from_user.id)] = (message, renderer)


def _format_plot_days(days):
    return f"{days:g}"


def _filter_plot_series(timestamps, days, *series):
    end = datetime.now()
    start = end - timedelta(days=days)
    indices = [index for index, timestamp in enumerate(timestamps) if start <= timestamp <= end]
    return ([timestamps[index] for index in indices],) + tuple(
        [[values[index] for index in indices] for values in series]
    )


def _parse_log_timestamp(value):
    return datetime.fromisoformat(value.replace("T", " "))


def _read_recent_logs(pattern, days):
    log_root = Path("/home/rpcuser/logs")
    cutoff_date = (datetime.now() - timedelta(days=days)).date()
    paths = sorted(log_root.glob(pattern)) + sorted((log_root / "done").glob(pattern))
    lines = []
    for path in paths:
        try:
            file_date = datetime.strptime(path.stem.rsplit("_", 1)[-1], "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff_date:
            continue
        try:
            lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    return "\n".join(lines)


def _read_voltage_log(supply, days):
    log_root = Path("/home/rpcuser/logs")
    patterns = {"lip": "hv0_????-??-??.log", "caen": "hv_????-??-??.log"}
    if supply not in patterns:
        raise ValueError(f"Unknown HV supply: {supply}")

    paths = sorted(log_root.glob(patterns[supply])) + sorted((log_root / "done").glob(patterns[supply]))
    timestamps = []
    values = [[] for _ in range(8 if supply == "caen" else 1)]
    cutoff = datetime.now() - timedelta(days=days)
    for path in paths:
        try:
            with path.open(encoding="utf-8", errors="replace") as log_file:
                for line in log_file:
                    parts = line.split()
                    if not parts:
                        continue
                    try:
                        timestamp = _parse_log_timestamp(parts[0])
                        if timestamp < cutoff or timestamp > datetime.now():
                            continue
                        if supply == "caen":
                            if len(parts) < 65:
                                continue
                            channel_values = [float(parts[2 + channel * 8]) for channel in range(8)]
                        else:
                            if len(parts) <= 13:
                                continue
                            channel_values = [float(parts[13])]
                    except (ValueError, IndexError):
                        continue
                    timestamps.append(timestamp)
                    for channel, value in enumerate(channel_values):
                        values[channel].append(value)
        except OSError:
            continue

    timestamps, *values = _filter_plot_series(timestamps, days, *values)
    return timestamps, values


def _plot_voltage(message, days, supply):
    try:
        timestamps, values = _read_voltage_log(supply, days)
        if not timestamps:
            bot.send_message(message.chat.id, f"No {supply.upper()} HV log data found in the last {_format_plot_days(days)} day(s).")
            return
        fig, ax = plt.subplots(figsize=(12, 6))
        if supply == "caen":
            for channel, channel_values in enumerate(values):
                ax.plot(timestamps, channel_values, label=f"Channel {channel}", marker="o", linestyle="None", markersize=3)
            ax.set_ylabel("Voltage (V)")
            title, caption = "CAEN HV by channel", f"CAEN high voltage, last {_format_plot_days(days)} day(s)"
        else:
            ax.plot(timestamps, values[0], "bo", linestyle="None", label="LIP Vset", markersize=3)
            ax.set_ylabel("Voltage (kV)")
            title, caption = "LIP global high voltage", f"LIP high voltage, last {_format_plot_days(days)} day(s)"
        ax.set_title(title)
        ax.set_xlabel("Time")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=250, bbox_inches="tight")
        buf.seek(0)
        plt.close(fig)
        bot.send_photo(message.chat.id, buf, caption=caption)
    except Exception as exc:
        bot.send_message(message.chat.id, f"Error generating {supply.upper()} HV plot: {exc}")


@bot.message_handler(commands=['plot_hv_lip'])
def plot_hv_lip(message):
    _request_plot_days(message, lambda original, days: _plot_voltage(original, days, "lip"))


@bot.message_handler(commands=['plot_hv_caen'])
def plot_hv_caen(message):
    _request_plot_days(message, lambda original, days: _plot_voltage(original, days, "caen"))

@bot.message_handler(commands=['plot_temperature'])
def plot_temperature(message):
    _request_plot_days(message, _plot_temperature)


def _plot_temperature(message, days):
    try:
        # Get internal data (bus1)
        int_times, int_temps, _, _ = parse_sensor_data(_read_recent_logs("sensors_bus1_*.log", days))
        
        # Get external data (bus0)
        ext_times, ext_temps, _, _ = parse_sensor_data(_read_recent_logs("sensors_bus0_*.log", days))
        int_times, int_temps = _filter_plot_series(int_times, days, int_temps)
        ext_times, ext_temps = _filter_plot_series(ext_times, days, ext_temps)
        
        # Create plot
        plt.figure(figsize=(12, 6))
        plt.plot(int_times, int_temps, 'ro', label='Internal Temperature', markersize=4)
        plt.plot(ext_times, ext_temps, 'bo', label='External Temperature', markersize=4)
        
        plt.title('Temperature Comparison - Internal vs External', fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Temperature (°C)', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Format x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Send plot to telegram
        bot.send_photo(message.chat.id, buf, caption="Temperature Time Series")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Error generating temperature plot: {str(e)}")

@bot.message_handler(commands=['plot_pressure'])
def plot_pressure(message):
    _request_plot_days(message, _plot_pressure)


def _plot_pressure(message, days):
    try:
        # Get internal data (bus1)
        int_times, _, _, int_pressures = parse_sensor_data(_read_recent_logs("sensors_bus1_*.log", days))
        
        # Get external data (bus0)
        ext_times, _, _, ext_pressures = parse_sensor_data(_read_recent_logs("sensors_bus0_*.log", days))
        int_times, int_pressures = _filter_plot_series(int_times, days, int_pressures)
        ext_times, ext_pressures = _filter_plot_series(ext_times, days, ext_pressures)
        
        # Create plot
        plt.figure(figsize=(12, 6))
        plt.plot(int_times, int_pressures, 'ro', label='Internal Pressure', markersize=4)
        plt.plot(ext_times, ext_pressures, 'bo', label='External Pressure', markersize=4)
        
        plt.title('Pressure Comparison - Internal vs External', fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Pressure (mbar)', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Format x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Send plot to telegram
        bot.send_photo(message.chat.id, buf, caption="Pressure Time Series")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Error generating pressure plot: {str(e)}")

@bot.message_handler(commands=['plot_RH', 'plot_rh'])
def plot_RH(message):
    _request_plot_days(message, _plot_RH)


def _plot_RH(message, days):
    try:
        # Get internal data (bus1)
        int_times, _, int_humidity, _ = parse_sensor_data(_read_recent_logs("sensors_bus1_*.log", days))
        
        # Get external data (bus0)
        ext_times, _, ext_humidity, _ = parse_sensor_data(_read_recent_logs("sensors_bus0_*.log", days))
        int_times, int_humidity = _filter_plot_series(int_times, days, int_humidity)
        ext_times, ext_humidity = _filter_plot_series(ext_times, days, ext_humidity)
        
        # Create plot
        plt.figure(figsize=(12, 6))
        plt.plot(int_times, int_humidity, 'ro', label='Internal Relative Humidity', markersize=4)
        plt.plot(ext_times, ext_humidity, 'bo', label='External Relative Humidity', markersize=4)
        
        plt.title('Relative Humidity Comparison - Internal vs External', fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Relative Humidity (%)', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Format x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Send plot to telegram
        bot.send_photo(message.chat.id, buf, caption="Relative Humidity Time Series")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Error generating humidity plot: {str(e)}")


def parse_trb_rates_data(output):
    """Parse TRB rate rows from one or more raw dated log files."""
    lines = output.strip().split('\n')
    
    timestamps = []
    asserted = []
    edge = []
    accepted = []
    m1 = []
    m2 = []
    m3 = []
    m4 = []
    cm1 = []
    cm2 = []
    cm3 = []
    cm4 = []
    
    for line in lines:
        if line.strip():
            parts = line.replace("T", " ").replace(";", "").split()
            if len(parts) >= 13:  # Expecting 13 columns based on your header
                try:
                    # Parse timestamp
                    timestamp_str = f"{parts[0]} {parts[1]}"
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    timestamps.append(timestamp)
                    
                    # Parse TRB rates values
                    asserted.append(float(parts[2]))
                    edge.append(float(parts[3]))
                    accepted.append(float(parts[4]))
                    m1.append(float(parts[5]))
                    m2.append(float(parts[6]))
                    m3.append(float(parts[7]))
                    m4.append(float(parts[8]))
                    cm1.append(float(parts[9]))
                    cm2.append(float(parts[10]))
                    cm3.append(float(parts[11]))
                    cm4.append(float(parts[12]))
                except (ValueError, IndexError):
                    continue
    
    return (timestamps, asserted, edge, accepted, m1, m2, m3, m4, cm1, cm2, cm3, cm4)

@bot.message_handler(commands=['plot_asserted_edge_accepted'])
def plot_asserted_edge_accepted(message):
    _request_plot_days(message, _plot_asserted_edge_accepted)


def _plot_asserted_edge_accepted(message, days):
    try:
        # Get TRB rates data
        timestamps, asserted, edge, accepted, _, _, _, _, _, _, _, _ = parse_trb_rates_data(
            _read_recent_logs("rates_*.log", days)
        )
        timestamps, asserted, edge, accepted = _filter_plot_series(timestamps, days, asserted, edge, accepted)
        
        # Create plot
        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, asserted, 'ro', label='Asserted', markersize=4)
        plt.plot(timestamps, edge, 'go', label='Edge', markersize=4)
        plt.plot(timestamps, accepted, 'bo', label='Accepted', markersize=4)
        
        plt.title('TRB Rates - Asserted, Edge, Accepted', fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Rate', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Format x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Send plot to telegram
        bot.send_photo(message.chat.id, buf, caption="TRB Rates - Asserted, Edge, Accepted")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Error generating TRB rates plot: {str(e)}")

@bot.message_handler(commands=['plot_multiplexers'])
def plot_multiplexers(message):
    _request_plot_days(message, _plot_multiplexers)


def _plot_multiplexers(message, days):
    try:
        # Get TRB rates data
        timestamps, _, _, _, m1, m2, m3, m4, _, _, _, _ = parse_trb_rates_data(
            _read_recent_logs("rates_*.log", days)
        )
        timestamps, m1, m2, m3, m4 = _filter_plot_series(timestamps, days, m1, m2, m3, m4)
        
        # Create plot
        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, m1, 'ro', label='Multiplexer 1', markersize=4)
        plt.plot(timestamps, m2, 'go', label='Multiplexer 2', markersize=4)
        plt.plot(timestamps, m3, 'bo', label='Multiplexer 3', markersize=4)
        plt.plot(timestamps, m4, 'mo', label='Multiplexer 4', markersize=4)
        
        plt.title('TRB Rates - Multiplexers 1-4', fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Rate', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Format x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Send plot to telegram
        bot.send_photo(message.chat.id, buf, caption="TRB Rates - Multiplexers 1-4")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Error generating multiplexers plot: {str(e)}")

@bot.message_handler(commands=['plot_coincidence_planes'])
def plot_coincidence_planes(message):
    _request_plot_days(message, _plot_coincidence_planes)


def _plot_coincidence_planes(message, days):
    try:
        # Get TRB rates data
        timestamps, _, _, _, _, _, _, _, cm1, cm2, cm3, cm4 = parse_trb_rates_data(
            _read_recent_logs("rates_*.log", days)
        )
        timestamps, cm1, cm2, cm3, cm4 = _filter_plot_series(timestamps, days, cm1, cm2, cm3, cm4)
        
        # Create plot
        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, cm1, 'ro', label='Coincidence Plane 1', markersize=4)
        plt.plot(timestamps, cm2, 'go', label='Coincidence Plane 2', markersize=4)
        plt.plot(timestamps, cm3, 'bo', label='Coincidence Plane 3', markersize=4)
        plt.plot(timestamps, cm4, 'mo', label='Coincidence Plane 4', markersize=4)
        
        plt.title('TRB Rates - Coincidence Planes 1-4', fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Rate', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Format x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Send plot to telegram
        bot.send_photo(message.chat.id, buf, caption="TRB Rates - Coincidence Planes 1-4")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Error generating coincidence planes plot: {str(e)}")

@bot.message_handler(commands=['plot_all_trb_rates'])
def plot_all_trb_rates(message):
    _request_plot_days(message, _plot_all_trb_rates)


def _plot_all_trb_rates(message, days):
    try:
        # Get TRB rates data
        timestamps, asserted, edge, accepted, m1, m2, m3, m4, cm1, cm2, cm3, cm4 = parse_trb_rates_data(
            _read_recent_logs("rates_*.log", days)
        )
        timestamps, asserted, edge, accepted, m1, m2, m3, m4, cm1, cm2, cm3, cm4 = _filter_plot_series(
            timestamps, days, asserted, edge, accepted, m1, m2, m3, m4, cm1, cm2, cm3, cm4
        )
        
        # Create subplots
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12))
        
        # Plot 1: Asserted, Edge, Accepted
        ax1.plot(timestamps, asserted, 'ro', label='Asserted', markersize=3)
        ax1.plot(timestamps, edge, 'go', label='Edge', markersize=3)
        ax1.plot(timestamps, accepted, 'bo', label='Accepted', markersize=3)
        ax1.set_title('TRB Rates - Asserted, Edge, Accepted', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Rate', fontsize=10)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax1.tick_params(axis='x', rotation=45)
        
        # Plot 2: Multiplexers
        ax2.plot(timestamps, m1, 'ro', label='Multiplexer 1', markersize=3)
        ax2.plot(timestamps, m2, 'go', label='Multiplexer 2', markersize=3)
        ax2.plot(timestamps, m3, 'bo', label='Multiplexer 3', markersize=3)
        ax2.plot(timestamps, m4, 'mo', label='Multiplexer 4', markersize=3)
        ax2.set_title('TRB Rates - Multiplexers 1-4', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Rate', fontsize=10)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax2.tick_params(axis='x', rotation=45)
        
        # Plot 3: Coincidence Planes
        ax3.plot(timestamps, cm1, 'ro', label='Coincidence Plane 1', markersize=3)
        ax3.plot(timestamps, cm2, 'go', label='Coincidence Plane 2', markersize=3)
        ax3.plot(timestamps, cm3, 'bo', label='Coincidence Plane 3', markersize=3)
        ax3.plot(timestamps, cm4, 'mo', label='Coincidence Plane 4', markersize=3)
        ax3.set_title('TRB Rates - Coincidence Planes 1-4', fontsize=12, fontweight='bold')
        ax3.set_xlabel('Time', fontsize=10)
        ax3.set_ylabel('Rate', fontsize=10)
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax3.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Send plot to telegram
        bot.send_photo(message.chat.id, buf, caption="Complete TRB Rates Overview")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Error generating complete TRB rates plot: {str(e)}")


# -----------------------------------------------------------------------------------------


@bot.message_handler(func=lambda message: True)
def echo_all(message):
    request_key = (message.chat.id, message.from_user.id)
    pending_plot = PENDING_PLOT_REQUESTS.get(request_key)
    if pending_plot and message.text:
        raw_days = message.text.strip()
        try:
            days = float(raw_days)
        except ValueError:
            days = None
        if days is not None and math.isfinite(days) and 0 < days <= 3650:
            original_message, renderer = PENDING_PLOT_REQUESTS.pop(request_key)
            renderer(original_message, days)
            return
        if not raw_days.startswith("/"):
            bot.send_message(message.chat.id, "Please reply with a number greater than 0 and at most 3650 days (for example, 0.5).")
            return
        PENDING_PLOT_REQUESTS.pop(request_key, None)

    if maybe_handle_terminal_message(message):
        return
    string = '''
===========================================
            miniTRASGO Bot - Command Guide
===========================================

    General Commands:
    ---------------------
    - /start: Greet the bot and receive a welcome message.
    - /get_username: Show your username, ID, and other details (share this info with csoneira@ucm.es).
    - /get_chat_id: Retrieve your unique Chat ID.
    - /get_ip: Show the station hostname and IP addresses.
    - /term <password>: Enable terminal mode (also available as /terminal).
    - /exit: Leave terminal mode.

    -------------------------------------------

    Monitoring Commands (Text Reports):
    -------------------------------------
    - /send_voltage or /send_voltage_lip: Get the LIP global high voltage status.
    - /send_voltage_caen: Get the status of all CAEN HV channels.
    - /send_gas_flow: Receive the latest gas flow values for each RPC.
    - /send_internal_environment: Get data from the internal environment sensors.
    - /send_external_environment: Get data from the external environment sensors.
    - /send_TRB_rates: Receive the latest triggered TRB rates (Asserted, Edge, Accepted).

    -------------------------------------------

    Monitoring Commands (Plots):
    -------------------------------------
    - /plot_temperature: Plot temperature (°C) data from both internal and external sensors.
    - /plot_pressure: Plot pressure (mbar) data from both internal and external sensors.
    - /plot_RH: Plot relative humidity (%) data from both internal and external sensors.
    - /plot_asserted_edge_accepted: Plot TRB rates (Asserted, Edge, Accepted).
    - /plot_multiplexers: Plot the rates of all 4 multiplexers.
    - /plot_coincidence_planes: Plot the rates of all 4 coincidence planes.
    - /plot_all_trb_rates: View a comprehensive plot with all TRB rates in 3 subplots.
    - /plot_hv_lip: Plot the LIP global HV log.
    - /plot_hv_caen: Plot CAEN HV logs for all eight channels.
    Each plot command asks for the number of days to include.

    -------------------------------------------

    Operation Commands:
    ---------------------
    - /set_data_control_system: (Currently Disabled) Connect via I2C from the mingo PC to the hub with environment, HV, and gas flow sensors.
    - /start_daq: Prepare the Data Acquisition System (DAQ) for measurements (data is not stored).
    - /turn_on_hv: Turn on the high voltage.
    - /turn_off_hv: Turn off the high voltage.
    - /start_run: Start recording data from the DAQ.
    - /stop_run: Stop the current data recording.
    - /any_reboot: Reboot the mingo PC (no impact on HV).

    -------------------------------------------

    Emergency & Assistance:
    ---------------------------
    - /restart_tunnel: Close the tunnel, it will automatically reopen.

    -------------------------------------------

    Logging Tools:
    -----------------
    - /gas_weight_measurement: Manually log the weight of the gas bottle in kilograms (ensure it includes at least one decimal place).
    - /send_noise_control_plane_combination_report: Send the PDF with clean trigger-type rates by plane combination, coloured by offender rate.

    ===========================================
    '''

    bot.send_message(message.chat.id, string)

bot.infinity_polling()
