#!/usr/bin/env python3
"""Recovery orchestration. Bootstrap uses only the system Python standard library.

Never prints credential contents, subprocess authentication diagnostics, or pip config.
Remote probes are read-only; only the explicit enroll-ssh command modifies authorized_keys.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CONTENTS = ROOT / 'CONFIG/CONTENTS'
HOME = Path.home()
STATE = ROOT / 'OPERATIONS/OPERATIONS_RUNTIME/SETUP'
PYTHON = ROOT / '.venv/bin/python3'
UNPACKER = ROOT / 'MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES'
BEGIN = '# BEGIN DATAFLOW MANAGED CRON'
END = '# END DATAFLOW MANAGED CRON'
COMMANDS = 'bash python3 git tmux crontab ssh ssh-keygen ssh-copy-id rsync flock watch pgrep pkill ps nohup find xargs awk sed grep logger swapoff swapon sudo visudo readlink realpath date sort uniq cut head tail wc tr timeout sha256sum stat df du mktemp tar gzip gunzip bzip2 unzip wget curl jq octave tput'.split()


def is_repository_root(root):
    """Check required repository structure without depending on its basename."""
    root = Path(root)
    required = (
        root / 'CONFIG/CONTENTS/environment/dataflow.sh',
        root / 'CONFIG/SETUP/recovery.py',
        root / 'MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS',
        root / 'MINGO_DIGITAL_TWIN',
        root / 'OPERATIONS/OPERATIONS_RUNTIME',
    )
    return root.is_dir() and all(path.exists() for path in required)


def safe_repository_path(root):
    return not re.search(r'[^/a-zA-Z0-9_.-]', str(Path(root)))


def run(args, *, timeout=30, env=None, input=None, cwd=ROOT):
    try:
        return subprocess.run([str(x) for x in args], text=True, input=input,
                              capture_output=True, timeout=timeout, env=env, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 124, '', 'unavailable or timed out')


def lines(path):
    return [l.split('#', 1)[0].strip() for l in path.read_text().splitlines()
            if l.split('#', 1)[0].strip()]


def manifest(name):
    return json.loads((CONTENTS / name).read_text())


def expand(value):
    return value.replace('@REPO_ROOT@', str(ROOT)).replace('@HOME@', str(HOME))


def cron_env():
    # No inherited agent, interactive PATH, PYTHONPATH, or credentials.
    return {'HOME': str(HOME), 'USER': pwd.getpwuid(os.getuid()).pw_name,
            'LOGNAME': pwd.getpwuid(os.getuid()).pw_name, 'SHELL': '/bin/bash',
            'PATH': f'{ROOT}/.venv/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
            'DATAFLOW_ROOT': str(ROOT), 'MASTER_STAGE_ROOT': str(ROOT / 'MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES'),
            'PYTHON_BIN': str(PYTHON), 'MPLBACKEND': 'Agg', 'LANG': 'C.UTF-8'}


def render_cron():
    text = expand((CONTENTS / 'cron/analysis_pc.crontab').read_text())
    out = [BEGIN]
    for line in text.splitlines():
        if line.strip() and not line.startswith('#') and not re.match(r'^\w+=', line):
            n = 1 if line.startswith('@') else 5
            parts = line.split(None, n)
            if len(parts) != n + 1:
                raise ValueError('Malformed cron schedule')
            line = ' '.join(parts[:n]) + f' /bin/bash {ROOT}/CONFIG/SETUP/run-job.sh -- ' + parts[n]
        out.append(line)
    return '\n'.join(out + [END, ''])


def split_cron(text):
    """Preserve unrelated jobs. Recognize old DATAFLOW entries during migration."""
    result = []; inside = False
    for line in text.splitlines():
        if line == BEGIN:
            if inside:
                raise ValueError('Nested managed crontab block')
            inside = True; continue
        if line == END:
            if not inside:
                raise ValueError('Unmatched managed crontab marker')
            inside = False; continue
        if inside:
            continue
        if line.startswith('# RECOVERY PAUSED:'):
            continue
        active = line.strip() and not line.lstrip().startswith('#')
        if active and ('DATAFLOW_v3' in line or '$DATAFLOW_ROOT' in line or '$MASTER_STAGE_ROOT' in line or re.match(r'^(DATAFLOW_ROOT|MASTER_STAGE_ROOT|PYTHON_BIN)=', line)):
            continue
        result.append(line)
    if inside:
        raise ValueError('Unclosed managed crontab block')
    return '\n'.join(result).rstrip() + '\n'


def read_cron():
    r = run(['crontab', '-l'])
    if r.returncode == 0:
        return r.stdout
    if r.returncode == 1 and 'no crontab for' in r.stderr.lower():
        return ''
    raise RuntimeError('Cannot read crontab; refusing to overwrite it')


def cron_paths(text):
    env = cron_env(); paths = set(); commands = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('#') or re.match(r'^\w+=', line):
            continue
        n = 1 if line.startswith('@') else 5
        cmd = line.split(None, n)[n]
        for key in sorted(env, key=len, reverse=True):
            cmd = cmd.replace('${' + key + '}', env[key]).replace('$' + key, env[key])
        commands.append(cmd)
        for token in shlex.split(cmd):
            token = token.split('=', 1)[-1] if '=' in token else token
            if token.startswith('/'):
                paths.add(Path(token))
    return paths, commands


def runtime_dirs():
    result = {ROOT / p for p in manifest('environment/runtime-directories.json')}
    for path in cron_paths(render_cron())[0]:
        if path.suffix in ('.log', '.lock') and path.is_relative_to(ROOT):
            result.add(path.parent)
    result.add(STATE)
    for p in result:
        if not p.resolve().is_relative_to(ROOT):
            raise ValueError(f'Runtime directory escapes repository: {p}')
    return result


class Report:
    def __init__(self): self.entries = []
    def add(self, level, message):
        self.entries.append((level, message))
    def check(self, ok, message, *, warn=False):
        self.add('PASS' if ok else 'WARN' if warn else 'FAIL', message)
    def finish(self):
        passes = [message for level, message in self.entries if level == 'PASS']
        imports = sum(message.startswith('Cron environment import ') for message in passes)
        executables = sum(message.startswith('Executable ') for message in passes)
        print(f'Working: {executables} cron executables; {imports} Python imports')
        highlights = ('APT manifest installed', 'pip dependency consistency',
                      'All structural/runtime/cron-log directories writable',
                      'Cron command references exist', 'Bash syntax for all',
                      'cron daemon active', 'Installed managed crontab matches',
                      'Production gate enabled', 'Fixed DATAFLOW cron schedule:',
                      'Noninteractive sudo swapoff:', 'Noninteractive sudo swapon:')
        for message in passes:
            if message.startswith(highlights) or ('SSH ' in message and 'unattended dedicated-key access' in message):
                print('PASS: ' + message)
        print('\n' + '  '.join(f'{x}: {sum(level == x for level, _ in self.entries)}' for x in ('PASS', 'WARN', 'FAIL')))
        pending = [(l, m) for l, m in self.entries if l != 'PASS']
        if pending:
            print('Remaining actions:')
            for level, msg in pending: print(f'  {level}: {msg}')
        return int(any(l == 'FAIL' for l, _ in self.entries))


def safe_mode(path, max_mode=0o600):
    return path.is_file() and path.stat().st_uid == os.getuid() and not (stat.S_IMODE(path.stat().st_mode) & ~max_mode)


def python_smoke(report):
    report.check(PYTHON.is_file(), f'Repository interpreter {PYTHON}')
    if not PYTHON.is_file(): return
    code = "import importlib,sys; importlib.import_module(sys.argv[1])"
    for name in lines(CONTENTS / 'packages/python-imports.txt'):
        r = run([PYTHON, '-c', code, name], env=cron_env(), timeout=40)
        report.check(r.returncode == 0, f'Cron environment import {name}')
    r = run([PYTHON, '-m', 'pip', 'check'], env=cron_env())
    report.check(r.returncode == 0, 'pip dependency consistency')
    r = run([PYTHON, '-c', 'import sys; assert sys.prefix != sys.base_prefix; import yaml; from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.path_config import get_repo_root; assert str(get_repo_root()) == sys.argv[1]', ROOT], env=cron_env())
    report.check(r.returncode == 0, 'Python path configuration resolves this checkout')
    r = run([ROOT / '.venv/bin/yq', '-r', '.logbook.gid_by_station."1"'], input='logbook:\n  gid_by_station:\n    "1": "123"\n', env=cron_env())
    report.check(r.returncode == 0 and r.stdout.strip() == '123', 'Pinned kislyuk/yq supports production jq-style query')


def ssh_target(host):
    alias = host['alias']; env = cron_env()
    g = run(['ssh', '-G', alias], env=env)
    effective = dict(l.split(' ', 1) for l in g.stdout.splitlines() if ' ' in l)
    canonical = run(['ssh', '-F', CONTENTS / 'ssh/config', '-G', alias], env=env)
    intended = dict(l.split(' ', 1) for l in canonical.stdout.splitlines() if ' ' in l)
    expected = canonical.returncode == 0 and all(effective.get(k) == intended.get(k) for k in ('hostname', 'user', 'port', 'proxyjump'))
    if not expected or g.returncode:
        return [(False, f'SSH {alias}: effective endpoint differs from remote-targets.json; resolve configuration conflict')]
    results = [(True, f'SSH {alias}: endpoint/user/port/jump match manifest')]
    # -F isolates the dedicated key from legacy identities and SSH_AUTH_SOCK.
    opts = ['ssh', '-F', str(HOME / '.ssh/dataflow.conf'), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes']
    r = run(opts + [alias, 'true'], env=env, timeout=25)
    results.append((r.returncode == 0, f'SSH {alias}: unattended dedicated-key access with verified host key'))
    if r.returncode: return results
    tests = ['test "$(id -un)" = ' + shlex.quote(intended['user']), 'command -v rsync >/dev/null']
    tests += ['test -d ' + shlex.quote(p) for p in host['directories']]
    tests += ['test -r ' + shlex.quote(p) for p in host['files']]
    r = run(opts + [alias, ' && '.join(tests)], env=env, timeout=25)
    results.append((r.returncode == 0, f'SSH {alias}: remote user, rsync, expected data/deployment paths'))
    if r.returncode: return results
    if alias.startswith('mingo'):
        rsh = shlex.join(opts)
        cmd = ['rsync', '-avzn', '--delete', '--itemize-changes',
               '--exclude-from=' + str(CONTENTS / 'rsync/station-deploy-excludes.list'), '-e', rsh,
               str(ROOT / 'FOR_MINGO_SYSTEMS/station_automation_scripts') + '/',
               f"{intended['user']}@{alias}:/home/rpcuser/station_automation_scripts/"]
        r = run(cmd, env=env, timeout=45)
        deletes = sum(l.startswith('*deleting') for l in r.stdout.splitlines())
        results.append((r.returncode == 0, f'SSH {alias}: deployment rsync --dry-run (proposed deletions={deletes}; no files transferred)'))
    else:
        r = run(['rsync', '--list-only', '-e', shlex.join(opts), alias + ':' + host['directories'][0] + '/'], env=env, timeout=30)
        results.append((r.returncode == 0, f'SSH {alias}: rsync read-only listing'))
    return results


def inspect_secrets(report, network):
    present = {}
    for item in manifest('secrets/manifest.json'):
        p = Path(expand(item['path']))
        ok = p.is_file() and p.stat().st_size > 0 and safe_mode(p)
        present[p.name] = ok
        report.check(ok, f"{item['component']}: {'credential present and private' if ok else 'restore nonempty mode-0600 file'} {p}", warn=True)
    if not PYTHON.is_file(): return
    bot = ROOT / 'OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/TELEGRAM_BOT/mingo_analysis_bot.py'
    # --check-config never starts polling, runs handlers, or sends messages.
    if present.get('API_TOKEN.txt') and present.get('TERMINAL_PASSWORD.txt'):
        r = run([PYTHON, bot, '--check-config'] + (['--online'] if network else []), env=cron_env(), timeout=25)
        report.check(r.returncode == 0, 'Telegram startup configuration' + (' and read-only getMe authentication' if network else ' (offline)'), warn=True)
    cds = HOME / '.cdsapirc'
    if present.get('.cdsapirc'):
        code = "import cdsapi; c=cdsapi.Client(quiet=True,debug=False,timeout=10,retry_max=0); "
        code += 'c.client.check_authentication()' if network else 'assert c is not None'
        r = run([PYTHON, '-c', code], env=cron_env(), timeout=25)
        report.check(r.returncode == 0, 'Copernicus client ' + ('read-only authentication (no retrieval)' if network else 'configuration'), warn=True)


def doctor(args):
    report = Report()
    report.check(os.getuid() != 0 and HOME == Path(pwd.getpwuid(os.getuid()).pw_dir), 'Run as the pipeline user with its real HOME')
    report.check(is_repository_root(ROOT), f'Repository structure is valid at {ROOT}')
    report.check(safe_repository_path(ROOT), 'Repository path has no shell-unsafe characters')
    report.check(Path('/etc/debian_version').exists(), 'Debian/Ubuntu host')
    for cmd in COMMANDS:
        report.check(shutil.which(cmd, path=cron_env()['PATH']) is not None, f'Executable {cmd} in cron PATH')
    missing_packages = [p for p in lines(CONTENTS / 'packages/apt-packages.txt') if run(['dpkg-query', '-W', '-f=${Status}', p]).stdout != 'install ok installed']
    report.check(not missing_packages, 'APT manifest installed' + (': ' + ', '.join(missing_packages) if missing_packages else ''))
    python_smoke(report)
    if PYTHON.is_file():
        r = run([PYTHON, ROOT / 'CONFIG/SETUP/config_probe.py'] + (['--offline'] if args.offline else []), env=cron_env(), timeout=70)
        try:
            for ok, message in json.loads(r.stdout):
                report.check(ok, message, warn=message.startswith('QA retry is enabled:'))
        except (ValueError, TypeError): report.add('FAIL', 'Configuration/logbook prerequisite probe failed')
    for p in runtime_dirs():
        if not (p.is_dir() and os.access(p, os.W_OK)):
            report.add('FAIL', f'Create writable runtime directory {p}')
    report.check(all(p.is_dir() and os.access(p, os.W_OK) for p in runtime_dirs()), 'All structural/runtime/cron-log directories writable')
    paths, cmds = cron_paths(render_cron())
    bad = []
    for p in sorted(paths):
        if p.suffix in ('.log', '.lock') or p == HOME / '.safe-mingo-computing': continue
        if not p.exists(): bad.append(str(p))
    report.check(not bad, 'Cron command references exist' + (': ' + ', '.join(bad) if bad else ''))
    missing_plotter = ROOT / 'MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/create_metadata_plots.sh'
    report.check(missing_plotter.is_file(), 'Metadata plotter source is unavailable and has no cron entry: ' + str(missing_plotter), warn=True)
    report.check(all(run(['bash', '-n', '-c', c]).returncode == 0 for c in cmds), f'Bash syntax for all {len(cmds)} active cron commands')
    tracked = run(['git', 'ls-files', '-z']).stdout.split('\0')
    shell_errors = [p for p in tracked if p.endswith('.sh') and (ROOT / p).exists() and run(['bash', '-n', ROOT / p]).returncode]
    report.check(not shell_errors, 'Tracked shell syntax' + (': ' + ', '.join(shell_errors) if shell_errors else ''))
    links = [p for p in tracked if p and (ROOT / p).is_symlink() and not (ROOT / p).exists()]
    report.check(not links, 'No dangling tracked symlinks' + (': ' + ', '.join(links) if links else ''))
    report.check(run(['systemctl', 'is-active', '--quiet', 'cron']).returncode == 0, 'cron daemon active')
    current = read_cron()
    matched = render_cron() in current
    report.check(matched, 'Installed managed crontab matches rendered CONTENTS', warn=args.prerequisites)
    report.check((STATE / 'production-enabled').is_file(), 'Production gate enabled', warn=args.prerequisites)
    report.check(not any('crontab ' in l and 'add_to_crontab' in l for l in current.splitlines() if l and not l.startswith('#')), 'No active every-minute crontab self-reinstaller')
    report.check((HOME / '.local/bin/start-dataflow-tmux').is_file(), 'DATAFLOW tmux launcher installed')
    bashrc = HOME / '.bashrc'
    report.check(bashrc.is_file() and '# BEGIN DATAFLOW SHELL' in bashrc.read_text(), 'Managed DATAFLOW shell fragment installed')
    report.check((HOME / '.ssh').is_dir() and stat.S_IMODE((HOME / '.ssh').stat().st_mode) == 0o700, 'SSH directory mode 0700')
    for name in ('config', 'dataflow.conf', 'id_ed25519_dataflow', 'known_hosts'):
        report.check(safe_mode(HOME / '.ssh' / name), f'SSH {name}: user-owned, private permissions')
    conf = HOME / '.ssh/dataflow.conf'
    report.check(conf.is_file() and conf.read_text() == (CONTENTS / 'ssh/config').read_text(), 'Installed SSH fragment matches CONTENTS')
    report.check(run(['ssh', '-G', 'ana'], env=cron_env()).returncode == 0, 'SSH configuration parses')
    if args.offline:
        report.add('WARN', 'Remote SSH, rsync and API checks skipped (--offline); cannot authorize production')
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            hosts = manifest('environment/remote-targets.json')
            for host, results in zip(hosts, pool.map(ssh_target, hosts)):
                for ok, message in results: report.check(ok, message, warn=True)
        report.add('PASS', f'Fixed DATAFLOW cron schedule: {len(cron_paths(render_cron())[1])} jobs, independent of current SSH and secrets')
    report.add('WARN', 'A second distinct backup-PC SSH endpoint is undocumented; backuplip is the only confirmed backup alias')
    inspect_secrets(report, not args.offline)
    calibration = UNPACKER / 'system/lookUpTables/timeCalibrationParametersC001.mat'
    report.check(calibration.is_file() and calibration.stat().st_size > 0, 'Restore original C001 TDC calibration: ' + str(calibration))
    if calibration.is_file() and shutil.which('octave'):
        # Validate content without running the unpacker or fabricating calibration.
        # The reference calibration includes unused channels with zero width;
        # require enough usable channels (32 detector channels plus reference).
        code = "s=load('" + str(calibration) + "'); assert(isfield(s,'tCalPar')); assert(columns(s.tCalPar)>=3); assert(all(isfinite(s.tCalPar(:)))); assert(nnz(s.tCalPar(:,3)!=s.tCalPar(:,2))>=33);"
        report.check(run(['octave', '--no-gui', '--no-history', '--quiet', '--eval', code]).returncode == 0, 'Octave reads valid TDC calibration coefficients')
    tot = ROOT / 'MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/CALIBRATIONS_AND_LUTS/TOT_TO_CHARGE_CAL/tot_to_charge_calibration.csv'
    report.check(tot.is_file() and tot.stat().st_size > 0, 'Restore empirical TOT-to-charge calibration; simulation Step 8 uses checked-in linear fallback until restored: ' + str(tot), warn=True)
    itineraries = ROOT / 'MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/CALIBRATIONS_AND_LUTS/TIME_CALIBRATION_ITINERARIES/itineraries.csv'
    report.check(itineraries.is_file() and itineraries.stat().st_size > 0, 'Time-calibration itinerary table: ' + str(itineraries), warn=True)
    outlier = ROOT / 'MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/CONFIG_FILES/STAGE_1/LOG_DATA/STEP_2/config_step_2.csv'
    outlier_ok = False
    if outlier.is_file():
        try:
            with outlier.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            columns = {key.strip().lower(): key for key in rows[0]} if rows else {}
            outlier_ok = {'column', 'lower', 'upper'} <= columns.keys()
            if outlier_ok:
                outlier_ok = all(row[columns['column']].strip() and float(row[columns['lower']]) < float(row[columns['upper']]) for row in rows)
        except (OSError, ValueError, KeyError, AttributeError): pass
    report.check(outlier_ok, 'Restore valid Stage 1 log-merge outlier limits CSV (column,lower,upper); merges for stations 1–3 fail without it: ' + str(outlier), warn=True)
    for cmd in ('swapoff', 'swapon'):
        path = shutil.which(cmd, path=cron_env()['PATH'])
        ok = path and run(['sudo', '-n', '-l', path, '-a']).returncode == 0
        ok = ok and run(['sudo', '-n', path, '--help']).returncode == 0
        report.check(bool(ok), f'Noninteractive sudo {cmd}: authorization for -a and safe --help execution (no swap changes)')
    free = shutil.disk_usage(ROOT).free / (1024 ** 3)
    report.check(free >= 10, f'Disk free {free:.1f} GiB (minimum bootstrap headroom 10 GiB; size retention separately)')
    return report.finish()


class Installer:
    def __init__(self):
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        self.backups = HOME / '.local/state/dataflow-recovery' / stamp
        self.backups.mkdir(parents=True, mode=0o700)
        self.pending = []
        print(f'Configuration backups: {self.backups}', flush=True)
    def backup(self, p):
        if p.exists() or p.is_symlink():
            target = self.backups / str(p).lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(p, target, follow_symlinks=True)
            target.chmod(0o600)
    def write(self, p, content, mode=0o600):
        if p.is_symlink():
            raise RuntimeError(f'Refusing to replace machine configuration symlink: {p}')
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.read_text() == content:
            p.chmod(mode); return
        self.backup(p)
        fd, temp = tempfile.mkstemp(dir=p.parent, prefix='.' + p.name)
        try:
            with os.fdopen(fd, 'w') as f: f.write(content)
            os.chmod(temp, mode); os.replace(temp, p)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    def stage(self, name): print(f'\n== {name} ==', flush=True)
    def defer(self, text): self.pending.append(text); print('PENDING: ' + text, flush=True)
    def prepare_cron(self):
        current = read_cron()
        (self.backups / 'crontab.before').write_text(current)
        STATE.mkdir(parents=True, exist_ok=True)
        if BEGIN in current and END in current:
            print('Existing managed cron remains running until replacement.')
            return
        (STATE / 'production-enabled').unlink(missing_ok=True)
        paused = split_cron(current)
        if paused != current and run(['crontab', '-'], input=paused).returncode:
            raise RuntimeError('Unable to remove unsafe legacy cron entries')
    def packages(self):
        missing = [p for p in lines(CONTENTS / 'packages/apt-packages.txt') if run(['dpkg-query', '-W', '-f=${Status}', p]).stdout != 'install ok installed']
        if not missing: print('All required OS packages installed.'); return
        print('Missing OS packages: ' + ' '.join(missing))
        if run(['sudo', '-n', 'true']).returncode:
            self.defer('Run setup from a terminal with sudo access to install: ' + ' '.join(missing)); return
        for command in (['sudo', '-n', 'apt-get', 'update'], ['sudo', '-n', 'apt-get', 'install', '-y', '--no-install-recommends', *missing]):
            if subprocess.run(command).returncode:
                self.defer('APT installation failed; rerun setup after fixing package access'); return
    def python(self):
        if not PYTHON.exists():
            if subprocess.run(['/usr/bin/python3', '-m', 'venv', ROOT / '.venv']).returncode:
                self.defer('python3-venv is needed to create .venv'); return
        requirements = CONTENTS / 'packages/python-lock.txt'
        if not requirements.exists(): requirements = CONTENTS / 'packages/python-requirements.txt'
        if subprocess.run([str(PYTHON), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(requirements)]).returncode:
            self.defer('Python dependency installation failed'); return
        self.write(STATE / 'python-installed.freeze', run([PYTHON, '-m', 'pip', 'freeze']).stdout)
    def shell(self):
        p = HOME / '.bashrc'; old = p.read_text() if p.exists() else ''
        old = re.sub(r'(?ms)^# BEGIN DATAFLOW SHELL\n.*?^# END DATAFLOW SHELL\n?', '', old)
        source = shlex.quote(str(CONTENTS / 'shell/dataflow_bashrc.sh'))
        self.write(p, old.rstrip() + f'\n\n# BEGIN DATAFLOW SHELL\nsource {source}\n# END DATAFLOW SHELL\n', 0o644)
        p = HOME / '.local/bin/start-dataflow-tmux'
        launcher = '#!/usr/bin/env bash\nset -euo pipefail\nexec ' + shlex.quote(str(ROOT / 'CONFIG/SETUP/start-dataflow-tmux')) + ' "$@"\n'
        self.write(p, launcher, 0o755)
    def ssh(self):
        d = HOME / '.ssh'; d.mkdir(mode=0o700, exist_ok=True); d.chmod(0o700)
        p = d / 'config'; old = p.read_text() if p.exists() else ''
        old = re.sub(r'(?ms)^# BEGIN DATAFLOW SSH\n.*?^# END DATAFLOW SSH\n?', '', old)
        include = 'Include ~/.ssh/dataflow.conf'
        old = '\n'.join(l for l in old.splitlines() if l != include and l != '# DATAFLOW recovery managed include')
        self.write(d / 'dataflow.conf', (CONTENTS / 'ssh/config').read_text())
        prefix = '# BEGIN DATAFLOW SSH\n' + include + '\n'
        # An explicit IdentityFile suppresses OpenSSH's implicit defaults. Keep
        # surviving default keys available in normal user config during migration;
        # doctor isolates dataflow.conf and tests only the dedicated key.
        legacy = [name for name in ('id_rsa', 'id_ecdsa', 'id_ed25519') if (d / name).is_file()]
        if legacy:
            prefix += 'Host ana backuplip mingo01 mingo02 mingo03 mingo04\n'
            prefix += ''.join('    IdentityFile ~/.ssh/' + name + '\n' for name in legacy)
            prefix += 'Host *\n'
        self.write(p, prefix + '# END DATAFLOW SSH\n' + old.rstrip() + '\n')
        key = d / 'id_ed25519_dataflow'
        if not key.exists():
            if key.with_suffix('.pub').exists():
                self.defer('Public key exists without its private key; refusing key overwrite'); return
            r = run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'DATAFLOW unattended analysis key', '-f', key])
            if r.returncode: self.defer('Dedicated Ed25519 key generation failed'); return
        key.chmod(0o600)
        if key.with_suffix('.pub').exists(): key.with_suffix('.pub').chmod(0o644)
        known = d / 'known_hosts'
        if known.exists(): self.backup(known); known.chmod(0o600)
        print('Existing SSH identities preserved. Dedicated key is unencrypted for cron; see SSH README for enrollment and host-key verification.')
    def secrets(self):
        legacy = ROOT / 'MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/CONFIG_FILES/STAGE_1/COPERNICUS/.cdsapirc'
        target = HOME / '.cdsapirc'
        if legacy.is_file() and not target.exists(): self.write(target, legacy.read_text())
        for item in manifest('secrets/manifest.json'):
            p = Path(expand(item['path']))
            if p.is_file():
                self.backup(p); p.chmod(0o600)
            else: print('OPTIONAL: Restore ' + str(p) + ' (0600) to enable ' + item['component'], flush=True)
    def recover_inputs(self, offline=False):
        for item in manifest('environment/recoverable-inputs.json'):
            target = ROOT / item['path']
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != item['sha256']:
                    print('WARN: Existing calibration differs from audited reference; preserved for scientific review: ' + str(target))
                continue
            if offline:
                print('WARN: Offline: cannot recover ' + str(target)); continue
            for host in item['hosts']:
                # Trusted alias, pinned content digest, no remote writes, no overwrite.
                with tempfile.TemporaryDirectory(prefix='dataflow-recover-') as temp:
                    candidate = Path(temp) / 'input.mat'
                    r = run(['scp', '-q', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10', host + ':' + item['remote_path'], candidate], timeout=40)
                    if r.returncode or not candidate.exists(): continue
                    if hashlib.sha256(candidate.read_bytes()).hexdigest() != item['sha256']: continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as output: output.write(candidate.read_bytes())
                    target.chmod(0o600)
                    self.write(STATE / 'calibration-provenance.json', json.dumps({'source_host': host, **item}, indent=2) + '\n')
                    print('Recovered checksum-verified C001 calibration from ' + host)
                    break
            if not target.exists(): print('WARN: Restore audited calibration ' + str(target))
    def sudoers(self):
        user = pwd.getpwuid(os.getuid()).pw_name
        if not re.fullmatch(r'[a-z_][a-z0-9_-]*', user): raise ValueError('Unsupported sudoers username')
        text = (CONTENTS / 'sudoers/dataflow-swap-clear').read_text().replace('@USER@', user)
        for name in ('swapoff', 'swapon'):
            p = Path(shutil.which(name, path=cron_env()['PATH']) or '/missing').resolve()
            if not p.is_file() or p.stat().st_uid != 0 or p.stat().st_mode & 0o022:
                self.defer('Cannot trust root executable ' + str(p)); return
            text = text.replace('@' + name.upper() + '@', str(p))
        self.write(STATE / 'dataflow-swap-clear', text)
        target = Path('/etc/sudoers.d/dataflow-swap-clear')
        if run(['sudo', '-n', 'true']).returncode:
            if all(run(['sudo', '-n', '-l', shutil.which(cmd, path=cron_env()['PATH']), '-a']).returncode == 0 and run(['sudo', '-n', shutil.which(cmd, path=cron_env()['PATH']), '--help']).returncode == 0 for cmd in ('swapoff', 'swapon')):
                print('Existing sudo policy already permits only-needed swap commands; rendered tighter rule available for administrator review.')
                return
            self.defer('Restricted sudoers is rendered; run setup in an authenticated sudo terminal to install it'); return
        # Stage root-owned candidate outside /etc/sudoers.d, validate, then install.
        candidate = run(['sudo', '-n', 'mktemp', '/etc/dataflow-sudoers.XXXXXX']).stdout.strip()
        if not candidate: self.defer('Cannot stage sudoers'); return
        try:
            if run(['sudo', '-n', 'install', '-o', 'root', '-g', 'root', '-m', '0600', STATE / 'dataflow-swap-clear', candidate]).returncode:
                raise RuntimeError('Cannot stage sudoers')
            if run(['sudo', '-n', 'visudo', '-cf', candidate]).returncode:
                raise RuntimeError('Sudoers validation failed')
            if target.exists():
                if run(['sudo', '-n', 'cp', '-a', target, self.backups / 'sudoers.before']).returncode: raise RuntimeError('Sudoers backup failed')
            if run(['sudo', '-n', 'install', '-o', 'root', '-g', 'root', '-m', '0440', candidate, target]).returncode: raise RuntimeError('Sudoers install failed')
            if run(['sudo', '-n', 'visudo', '-c']).returncode: raise RuntimeError('System sudoers validation failed')
        finally: run(['sudo', '-n', 'rm', '-f', candidate])


def setup(args):
    if args.check: return doctor(argparse.Namespace(offline=args.offline, prerequisites=False))
    if os.getuid() == 0 or HOME != Path(pwd.getpwuid(os.getuid()).pw_dir):
        raise RuntimeError('Run as the pipeline user, not sudo setup.sh')
    if args.apply and (not is_repository_root(ROOT) or not safe_repository_path(ROOT)):
        raise RuntimeError('Setup requires a structurally complete checkout at a shell-safe path')
    if not Path('/etc/debian_version').exists(): raise RuntimeError('Supported bootstrap target: Debian/Ubuntu')
    if args.dry_run or not args.apply:
        print('DRY RUN: no writes, package installs, network probes, cron changes, or key generation.')
        print('Stages: sanity -> backup legacy cron -> apt -> .venv -> directories -> shell/tmux -> SSH -> secrets -> sudoers -> fixed cron -> report')
        print(f'Would create/verify {len(runtime_dirs())} structural directories and render {len(cron_paths(render_cron())[1])} cron jobs.')
        print('Use --apply to install the fixed cron schedule and print one setup report. Missing optional inputs never change the schedule.')
        return 0
    os.umask(0o077)
    # A local interactive run can authenticate sudo once. Noninteractive agents
    # continue user-level stages and report privileged work as pending.
    if sys.stdin.isatty() and run(['sudo', '-n', 'true']).returncode:
        subprocess.run(['sudo', '-v'], check=False)
    inst = Installer()
    inst.stage('Back up cron; remove legacy self-reinstall entries'); inst.prepare_cron()
    inst.stage('System packages'); inst.packages()
    inst.stage('Repository Python environment'); inst.python()
    inst.stage('Structural runtime directories')
    for p in sorted(runtime_dirs()): p.mkdir(parents=True, exist_ok=True)
    inst.stage('Shell and tmux launcher'); inst.shell()
    inst.stage('SSH fragment and unattended Ed25519 key'); inst.ssh()
    inst.stage('Checksum-verified scientific bootstrap inputs'); inst.recover_inputs(args.offline)
    if PYTHON.is_file():
        inst.stage('Restore absent public station logbook configurations')
        r = run([PYTHON, ROOT / 'CONFIG/SETUP/config_probe.py', '--restore-logbooks'] + (['--offline'] if args.offline else []), env=cron_env(), timeout=70)
        try:
            for ok, message in json.loads(r.stdout): print(('PASS: ' if ok else 'PENDING: ') + message)
        except ValueError: print('WARN: Logbook restoration probe failed')
    inst.stage('Secret restoration checks'); inst.secrets()
    inst.stage('Restricted sudoers'); inst.sudoers()
    if run(['systemctl', 'is-active', '--quiet', 'cron']).returncode and run(['sudo', '-n', 'true']).returncode == 0:
        if run(['sudo', '-n', 'systemctl', 'enable', '--now', 'cron']).returncode: inst.defer('Enable cron daemon with systemctl')
    inst.write(STATE / 'analysis_pc.crontab', render_cron())
    inst.stage('Install the fixed DATAFLOW cron schedule')
    before = read_cron()
    combined = split_cron(before) + '\n' + render_cron()
    if before != combined:
        if run(['crontab', '-'], input=combined).returncode: raise RuntimeError('Crontab installation failed')
        if read_cron() != combined: raise RuntimeError('Installed crontab verification failed; production gate remains closed')
        print('Installed fixed cron schedule; unrelated jobs preserved.')
    else: print('Fixed cron schedule already installed; no crontab change.')
    packages_ready = all(run(['dpkg-query', '-W', '-f=${Status}', p]).stdout == 'install ok installed' for p in lines(CONTENTS / 'packages/apt-packages.txt'))
    python_ready = PYTHON.is_file() and run([PYTHON, '-m', 'pip', 'check'], env=cron_env()).returncode == 0
    core_ready = packages_ready and python_ready and all(shutil.which(c, path=cron_env()['PATH']) for c in ('bash', 'crontab', 'ssh', 'rsync', 'flock'))
    if core_ready and not args.offline:
        if not (STATE / 'production-enabled').exists():
            inst.write(STATE / 'production-enabled', dt.datetime.now(dt.timezone.utc).isoformat() + '\n')
        print('Cron gate open. Missing optional inputs are reported below; the schedule remains fixed.')
    elif not (STATE / 'production-enabled').exists():
        print('Cron gate closed: restore core packages/Python or rerun without --offline before jobs can execute.')
    inst.stage('Setup report')
    rc = doctor(argparse.Namespace(offline=args.offline, prerequisites=False))
    if inst.pending:
        print('\nPending installation actions:')
        for item in inst.pending: print('  - ' + item)
    return rc or int(bool(inst.pending))


def tmux_start(args):
    spec = manifest('tmux/pipeline_monitor.json'); session = spec['session']
    if not PYTHON.is_file(): raise RuntimeError('Run setup --apply to create .venv first')
    tmux = ['tmux', '-L', 'dataflow', '-f', str(CONTENTS / 'tmux/preferences.conf')]
    exists = run(tmux + ['has-session', '-t', '=' + session]).returncode == 0
    if not exists:
        # Own socket keeps DATAFLOW preferences separate from personal tmux sessions.
        for index, window in enumerate(spec['windows']):
            command = shlex.join(['/bin/bash', str(ROOT / 'CONFIG/SETUP/monitor-pane.sh'), window['panes'][0]])
            argv = tmux + ['new-session' if index == 0 else 'new-window', '-d']
            argv += ['-s', session] if index == 0 else ['-t', session]
            argv += ['-n', window['name'], '-c', str(ROOT), command]
            if run(argv).returncode: raise RuntimeError('tmux window creation failed')
            for pane in window['panes'][1:]:
                command = shlex.join(['/bin/bash', str(ROOT / 'CONFIG/SETUP/monitor-pane.sh'), pane])
                if run(tmux + ['split-window', '-h', '-t', session + ':' + str(index), '-c', ROOT, command]).returncode:
                    raise RuntimeError('tmux pane creation failed')
    r = run(tmux + ['list-panes', '-s', '-t', session, '-F', '#{pane_dead} #{pane_current_command}'])
    if r.returncode or len(r.stdout.splitlines()) != 3 or any(l.startswith('1 ') for l in r.stdout.splitlines()):
        raise RuntimeError('Existing monitor does not have three live panes; inspect it (never killed automatically)')
    print('pipeline_monitor: three live panes (empty data is shown as waiting).')
    if not args.detach: os.execvp('tmux', tmux + ['attach-session', '-t', session])
    return 0


def enroll(args):
    hosts = {h['alias'] for h in manifest('environment/remote-targets.json')}
    if args.host not in hosts: raise ValueError('Host must be in remote-targets.json')
    pub = HOME / '.ssh/id_ed25519_dataflow.pub'
    if not pub.is_file(): raise RuntimeError('Run setup --apply to generate the key first')
    # Explicit interactive command; strict trust remains enabled. Existing keys can
    # authenticate through normal ~/.ssh/config, otherwise a password is requested.
    if run(['ssh', '-F', HOME / '.ssh/dataflow.conf', args.host, 'true'], env=cron_env(), timeout=25).returncode == 0:
        print('Dedicated key already works; no authorized_keys changes needed.')
        return 0
    # The explicit old IdentityFile would make ssh-copy-id's normal test falsely
    # succeed. We tested the dedicated key separately, so force only this append.
    command = ['ssh-copy-id', '-f', '-i', str(pub), '-o', 'BatchMode=no', '-o', 'StrictHostKeyChecking=yes']
    if args.identity:
        command += ['-o', 'IdentityFile=' + str(Path(args.identity).expanduser())]
    rc = subprocess.call(command + [args.host])
    if rc: return rc
    return run(['ssh', '-F', HOME / '.ssh/dataflow.conf', args.host, 'true'], env=cron_env(), timeout=25).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('setup')
    mode = p.add_mutually_exclusive_group()
    for flag in ('apply', 'dry-run', 'check'): mode.add_argument('--' + flag, action='store_true')
    p.add_argument('--offline', action='store_true')
    p = sub.add_parser('tmux'); p.add_argument('--detach', action='store_true')
    p = sub.add_parser('enroll-ssh'); p.add_argument('host'); p.add_argument('--identity', help='Existing local identity used only for enrollment')
    args = parser.parse_args()
    return {'setup': setup, 'tmux': tmux_start, 'enroll-ssh': enroll}[args.command](args)


if __name__ == '__main__':
    try: sys.exit(main())
    except (RuntimeError, ValueError, OSError) as exc:
        print('FAIL: ' + str(exc), file=sys.stderr); sys.exit(1)
