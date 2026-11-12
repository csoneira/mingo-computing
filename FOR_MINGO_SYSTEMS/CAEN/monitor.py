#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monitor CAEN high-voltage channels and report their status."""

import socket
import serial
import time
import sys
from datetime import datetime
import os
import fcntl

LOCKFILE = "/tmp/caen_hv.lock"

# --- GESTÃO DE LOCKS (USB / TCP) ---
def acquire_lock(lockfile=LOCKFILE, timeout=5):
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:

            lock_fd = open(lockfile, "a+")

            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


            lock_fd.seek(0)
            lock_fd.truncate()
            lock_fd.write(str(os.getpid()) + "\n")
            lock_fd.flush()

            return lock_fd

        except BlockingIOError:
            # O ficheiro está a ser usado por outro processo. Fecha o FD e espera.
            if 'lock_fd' in locals():
                lock_fd.close()

            time.sleep(0.05)

    # Se o ciclo terminar, esgotou-se o tempo limite
    print(f"[Error] Failed to access the power supply. Lock occupied for more than {timeout} seconds.")
    sys.exit(1)

def release_lock(lock_fd):
    if lock_fd:
        try:
            # Dá uma margem  (50ms) antes de libertar o lock.
            # dá tempo para o hardware da fonte  limpar o buffer USB antes do próximo processo
            time.sleep(0.05)

            lock_fd.seek(0)
            lock_fd.truncate(0)
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except Exception:
            pass

# --- CONFIGURAÇÃO E LIGAÇÃO ---
def get_config_from_file(filename="variables.txt"):
    config = {}

    # 1. Obtém o caminho absoluto da pasta onde o script (monitor.py) está
    script_dir = os.path.dirname(os.path.abspath(__file__))

    config_path = os.path.join(script_dir, filename)

    try:
        with open(config_path, "r") as f:
            for line in f:
                if ":" in line:
                    key_raw, value = line.strip().split(":", 1)
                    # O split()[0] agarra apenas a primeira palavra antes do espaço ou parêntesis
                    key = key_raw.split()[0].strip()
                    config[key] = value.strip()
    except FileNotFoundError:
        print(f"[Error] File '{config_path}' not found.")
        sys.exit(1)
    return config



def open_connection_tcp(ip, port, timeout=3.0):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, int(port)))
        return sock
    except socket.timeout:
        print(f"[Error] Timeout connecting to IP {ip} on port {port}.")
        sys.exit(1)
    except Exception as e:
        print(f"[Network Error] Unable to connect to {ip}:{port} -> {e}")
        sys.exit(1)

def open_connection_usb(port, baudrate=9600, timeout=1):
    try:
        return serial.Serial(port, baudrate=baudrate, timeout=timeout, exclusive=True)
    except Exception as e:
        print(f"[Serial Error] Unable to open port {port} -> {e}")
        sys.exit(1)

# --- CONSTRUÇÃO E ENVIO DE COMANDOS ---
def build_command(cmd, channel, param, value=None):
    if cmd == "MON":
        command = f"$BD:00,CMD:{cmd},CH:{channel},PAR:{param}"
    elif cmd == "SET":
        if value is not None:
            if isinstance(value, (float, int)):
                val_str = f"{value:.2f}"
            else:
                val_str = str(value)
            command = f"$BD:00,CMD:{cmd},CH:{channel},PAR:{param},VAL:{val_str}"
        else:
            command = f"$BD:00,CMD:{cmd},CH:{channel},PAR:{param}"
    else:
        raise ValueError("Invalid command!")
    return command + "\r\n"

def send_command(conn, mode, command):
    """
    Universal send function - automatically adapts to TCP/IP and USB
    """
    try:
        if mode == 'usb':
            conn.reset_input_buffer()
            conn.reset_output_buffer()

            conn.write(command.encode('utf-8'))
            conn.flush()
        elif mode == 'ethernet':
            conn.sendall(command.encode('utf-8'))

        if "SET" in command:
            time.sleep(0.05)

        # 3. Leitura da Resposta
        if mode == 'usb':
            conn.timeout = 2.0
            linha = conn.readline()
            if linha:
                resposta = linha.decode('utf-8', errors='ignore').strip()
                if resposta.startswith("#"):
                    return resposta
            print(f"[USB Timeout] The high voltage power supply did not respond to: {command.strip()}")
            return None

        elif mode == 'ethernet':
            conn.settimeout(2.0)
            response_bytes = bytearray()
            while True:
                char = conn.recv(1)
                if not char:
                    print("[Error] TCP connection abruptly closed by the high voltage power supply.")
                    return None

                response_bytes += char
                if response_bytes.endswith(b'\n'):
                    resposta = response_bytes.decode('utf-8', errors='ignore').strip()
                    if not resposta or "$BD:" in resposta:
                        response_bytes = bytearray()
                        continue
                    if resposta.startswith("#"):
                        return resposta
                    else:
                        response_bytes = bytearray()

    except socket.timeout:
        print(f"[TCP Timeout] The high voltage power supply did not respond in time to: {command.strip()}")
        return None
    except Exception as e:
        print(f"[Critical Error] Failure in command {command.strip()}: {e}")
        return None

def format_value(val, unit):
    if val == "-" or isinstance(val, str):
        return f"{val} {unit}"
    return f"{val:.2f} {unit}"

# --- FUNÇÕES DE CONTROLO ---
def set_voltage(conn, mode, ch, v): return send_command(conn, mode, build_command("SET", ch, "VSET", v))
def set_current(conn, mode, ch, i): return send_command(conn, mode, build_command("SET", ch, "ISET", i))
def set_power(conn, mode, ch, state): return send_command(conn, mode, build_command("SET", ch, "ON" if state == 'ON' else "OFF"))
def set_maxv(conn, mode, ch, v): return send_command(conn, mode, build_command("SET", ch, "MAXV", v))
def set_ramp_up(conn, mode, ch, v): return send_command(conn, mode, build_command("SET", ch, "RUP", v))
def set_ramp_down(conn, mode, ch, v): return send_command(conn, mode, build_command("SET", ch, "RDW", v))
def set_trip(conn, mode, ch, v): return send_command(conn, mode, build_command("SET", ch, "TRIP", v))
def set_imrange(conn, mode, ch, range_mode): return send_command(conn, mode, build_command("SET", ch, "IMRANGE", range_mode.upper()))
def monitor(conn, mode, ch, param): return send_command(conn, mode, build_command("MON", ch, param))

def parse_value(response):
    if response and "VAL:" in response:
        val = response.split("VAL:")[1].strip()
        try:
            return float(val)
        except ValueError:
            return None
    return None

def parse_command(tokens):
    data = {
        "channels": [], "all_channels": False, "voltage": None, "current": None, "state": None,
        "maxv": None, "ramp_up": None, "ramp_down": None, "trip": None,
        "imrange": None, "monitor_all": False, "print_status": False
    }
    i = 0
    while i < len(tokens):
        token = tokens[i].upper()
        if token == "-CH":
            # Separa os canais por vírgula e converte para inteiros (ex: "0,4" -> [0, 4])
            data["channels"] = [int(x.strip()) for x in tokens[i+1].split(",")]
            i += 2
        elif token == "-ALL":
            # Apenas levanta a flag. O main() decide os números depois.
            data["all_channels"] = True
            i += 1
        elif token == "-V":
            data["voltage"] = float(tokens[i+1])
            i += 2
        elif token == "-I":
            data["current"] = float(tokens[i+1])
            i += 2
        elif token == "-ON":
            data["state"] = "ON"
            i += 1
        elif token == "-OFF":
            data["state"] = "OFF"
            i += 1
        elif token == "-MAXV":
            data["maxv"] = float(tokens[i+1])
            i += 2
        elif token == "-RUP":
            data["ramp_up"] = float(tokens[i+1])
            i += 2
        elif token == "-RDW":
            data["ramp_down"] = float(tokens[i+1])
            i += 2
        elif token == "-TRIP":
            data["trip"] = float(tokens[i+1])
            i += 2
        elif token == "-IMRANGE":
            data["imrange"] = tokens[i+1].upper()
            i += 2
        elif token == "-MON":
            data["monitor_all"] = True
            i += 1
        elif token == "-S":
            data["print_status"] = True
            i += 1
        elif token in ["-H", "--HELP"]:
            print_help()
            sys.exit(0)
        else:
            raise ValueError(f"Unrecognized argument: {token}")
    return data



def detect_num_channels(conn, mode):
    """
    Automatically detects how many channels the high voltage power supply has
    """
    cmd_bdnch = "$BD:00,CMD:MON,PAR:BDNCH\r\n"
    resp = send_command(conn, mode, cmd_bdnch)
    val = parse_value(resp)

    if val is not None:
        return int(val)

    # Se a resposta for inválida ou None, enviar erro
    raise RuntimeError("Unable to automatically detect the number of channels for the high voltage power supply. Check the communication.")


def monitor_all_channels(conn, mode, num_channels):
    params = ["VSET", "VMON", "VMIN", "MAXV", "ISET", "IMON", "IMIN", "IMAX"]
    values = []
    for ch in range(num_channels): #percorre o loop para o num canais que a fonte tiver
        for param in params:
            response = monitor(conn, mode, ch, param)
            val = parse_value(response)
            values.append(val if val is not None else -1)
    return values



def get_channel_status(conn, mode, ch):
    params = ["VSET", "VMON", "VMIN", "MAXV", "ISET", "IMON", "IMIN", "IMAX","IMRANGE", "STAT"]
    status = {}
    for param in params:
        cmd = build_command("MON", ch, param)
        resp = send_command(conn, mode, cmd)

        if param == "STAT":
            val = parse_value(resp)
            if val is not None:
                is_on = int(val) & 1 == 1
                status["ON"] = "ON" if is_on else "OFF"
            else:
                status["ON"] = "-"
        elif param == "IMRANGE":
            if resp and "VAL:" in resp:
                status["IMRANGE"] = resp.split("VAL:")[1].strip()
            else:
                status["IMRANGE"] = "-"
        else:
            val = parse_value(resp)
            status[param] = val if val is not None else "-"
    return status

def print_table(status_list, mode):
    modo_str = "Rede TCP/IP" if mode == "ethernet" else "Serie USB"
    print(f"\nHV channels status ({modo_str}) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    num_channels = len(status_list)

    # 1. Construir e imprimir o cabeçalho
    header = f"{'Parameter':<10}"
    for i in range(num_channels):
        header += f" | {'CH ' + str(i):<12}"

    print("-" * len(header))
    print(header)
    print("-" * len(header))

    # 2. Definir a ordem das linhas a mostrar
    parametros = [
        ("Status", "ON", ""),
        ("Vset", "VSET", "V"),
        ("Vmon", "VMON", "V"),
        ("Vmin", "VMIN", "V"),
        ("Vmax", "MAXV", "V"),
        ("Iset", "ISET", "uA"),
        ("Imon", "IMON", "uA"),
        ("Imin", "IMIN", "uA"),
        ("Imax", "IMAX", "uA"),
        ("ImRange", "IMRANGE", "")
    ]

    # 3. Construir cada linha iterando sobre todos os canais
    for label, key, unit in parametros:
        linha = f"{label:<10}"

        for s in status_list:
            val = s.get(key, '-')

            # Para estados de texto não aplicamos a unidade
            if key in ["ON", "IMRANGE"]:
                val_str = str(val)
            else:
                val_str = format_value(val, unit)

            # Adiciona o valor à linha com espaçamento fixo de 12 caracteres (para alinhar as colunas)
            linha += f" | {val_str:<12}"

        print(linha)

    print("-" * len(header))
    print()



def print_help():
    help_text = """
Usage:
  ./monitor.py [OPTIONS]

OPTIONS:
  -CH (num)             HV channel (e.g., 0). For multiple channels use commas (e.g., 0,4)
  -ALL                  Apply commands to all available channels
  -V (val)              Set voltage (VSET)
  -I (val)              Set current (ISET)
  -MAXV (val)           Set maximum voltage
  -RUP (val)            Set ramp-up speed (V/s)
  -RDW (val)            Set ramp-down speed (V/s)
  -TRIP (val)           Set trip time (s)
  -ON                   Turn high voltage ON
  -OFF                  Turn high voltage OFF
  -IMRANGE (HIGH/LOW)   Set IMON range (low / high mode)
  -MON                  Monitor and log all channel parameters
  -S                    Show channel status on screen
  -h, --help            Show this help message

Examples:
  ./monitor.py -CH 0 -V 500 -ON        Turn on channel 0 at 500V
  ./monitor.py -CH 0,4 -V 1000 -ON     Turn on channels 0 and 4 at 1000V
  ./monitor.py -ALL -OFF               Turn off all channels
"""
    print(help_text)


def main():
    args = sys.argv[1:]
    if not args:
        print("No arguments provided.")
        sys.exit(0)


    try:
        parsed = parse_command(args)
    except ValueError as e:
        print(f"\n[Command Error] {e}")
        print("Run './monitor.py -h' to see the list of valid commands.\n")
        sys.exit(1)
    except IndexError:
        print("\n[Command Error] Missing a value for one of your arguments.")
        print("Run './monitor.py -h' for help.\n")
        sys.exit(1)



    lock_fd = acquire_lock()
    conn = None

    try:
        config = get_config_from_file("variables.txt")
        mode = config.get("mode", "ethernet").lower() # Por omissão assume ethernet
        logpath = config.get("logpath", ".")

        # INICIAR LIGAÇÃO BASEADA NO MODO
        if mode == "ethernet":
            ip = config.get("ip")
            port = config.get("tcp_port")
            if not ip or not port:
                raise ValueError("Ethernet mode requires 'ip' and 'tcp_port' in variables.txt")
            conn = open_connection_tcp(ip, port)

        elif mode == "usb":
            serial_port = config.get("serial_port")
            if not serial_port:
                raise ValueError("USB mode requires 'serial_port' in variables.txt")
            conn = open_connection_usb(serial_port)

        else:
            raise ValueError("The 'mode' parameter in variables.txt must be 'ethernet' or 'usb'.")

        # Descobre automaticamente o número de canais da placa ligada
        num_channels = detect_num_channels(conn, mode)

        # --- DEFINIR QUAIS CANAIS PROCESSAR ---
        if parsed.get("all_channels"):
            # Se for -ALL, cria uma lista com todos os canais disponíveis
            canais_a_processar = list(range(num_channels))
        else:
            # Caso contrário, usa os canais definidos no -CH (ex: [0, 4])
            canais_a_processar = parsed.get("channels", [])

        # --- APLICAR COMANDOS ---
        for ch in canais_a_processar:
            # impede o envio de ordens para canais inexistentes
            if ch >= num_channels:
                print(f"[Warning] Channel {ch} does not exist on the high voltage power supply (this unit has {num_channels} channels). Ignored.")
                continue

            if parsed["voltage"] is not None: set_voltage(conn, mode, ch, parsed["voltage"])
            if parsed["current"] is not None: set_current(conn, mode, ch, parsed["current"])
            if parsed["state"] is not None: set_power(conn, mode, ch, parsed["state"])
            if parsed["maxv"] is not None: set_maxv(conn, mode, ch, parsed["maxv"])
            if parsed["ramp_up"] is not None: set_ramp_up(conn, mode, ch, parsed["ramp_up"])
            if parsed["ramp_down"] is not None: set_ramp_down(conn, mode, ch, parsed["ramp_down"])
            if parsed["trip"] is not None: set_trip(conn, mode, ch, parsed["trip"])
            if parsed["imrange"] is not None: set_imrange(conn, mode, ch, parsed["imrange"])



        if parsed["monitor_all"]:
            # O datalogger adapta-se dinamicamente ao tamanho da linha (16 ou 64 colunas de dados - consoante fte de 2 ou 8 canais)
            values = monitor_all_channels(conn, mode, num_channels)
            timestamp = datetime.now().isoformat(sep='T', timespec='seconds')
            line = f"{timestamp} " + " ".join(f"{v:.2f}" if isinstance(v, (float, int)) else str(v) for v in values) + "\n"

            # logpath absoluto ou relativo
            if not os.path.isabs(logpath):
                script_dir = os.path.dirname(os.path.abspath(__file__))
                absolute_logpath = os.path.join(script_dir, logpath)
            else:
                absolute_logpath = logpath

            os.makedirs(absolute_logpath, exist_ok=True)
            log_filename = os.path.join(absolute_logpath, f"hv_{datetime.now().date()}.log")

            with open(log_filename, "a") as f:
                f.write(line)


        if parsed["print_status"]:
            status = [get_channel_status(conn, mode, ch) for ch in range(num_channels)]
            print_table(status, mode)

    except Exception as e:
        print(f"General error: {e}")
        sys.exit(1)

    finally:
        if conn:
            try: conn.close()
            except: pass
        release_lock(lock_fd)

if __name__ == "__main__":
    main()
