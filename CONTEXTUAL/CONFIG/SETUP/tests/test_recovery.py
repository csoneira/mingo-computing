"""Safety regressions; no real crontab, SSH, sudo, or scientific processing."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).resolve().parents[1] / 'recovery.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoverySafetyTests(unittest.TestCase):
    def test_repository_validation_is_independent_of_checkout_basename(self):
        with tempfile.TemporaryDirectory(prefix='relocated-checkout-') as temp:
            root = Path(temp) / 'different-name'
            for relative in (
                'CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh',
                'CONTEXTUAL/CONFIG/SETUP/recovery.py',
                'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS',
                'PIPELINE/MINGO_DIGITAL_TWIN',
                'CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME',
            ):
                path = root / relative
                path.mkdir(parents=True, exist_ok=True)
            self.assertTrue(recovery.is_repository_root(root))
            self.assertTrue(recovery.safe_repository_path(root))

    def test_pause_preserves_unrelated_jobs(self):
        unrelated = 'MAILTO=local-user\n15 * * * * /usr/local/bin/personal-backup\n'
        old = '* * * * * crontab $HOME/DATAFLOW_v3/CONTEXTUAL/CONFIG/add_to_crontab.info\n'
        self.assertEqual(recovery.split_cron(unrelated + old), unrelated)

    def test_managed_cron_is_replaceable_without_duplicates(self):
        unrelated = '0 1 * * * /usr/bin/true\n'
        merged = unrelated + recovery.render_cron()
        self.assertEqual(recovery.split_cron(merged), unrelated)
        self.assertEqual(recovery.split_cron(recovery.split_cron(merged)), unrelated)

    def test_unclosed_marker_refuses_destructive_replacement(self):
        with self.assertRaises(ValueError):
            recovery.split_cron(recovery.BEGIN + '\n0 1 * * * important-command\n')

    def test_every_job_has_gate_and_no_system_python(self):
        _, commands = recovery.cron_paths(recovery.render_cron())
        source = recovery.expand(
            (recovery.CONTENTS / 'cron/analysis_pc.crontab').read_text()
        )
        scheduled_lines = [
            line for line in source.splitlines()
            if line.strip() and not line.startswith('#') and not re.match(r'^\w+=', line)
        ]
        self.assertEqual(len(commands), len(scheduled_lines))
        # Jobs commented with STOPPED are deliberately excluded from the
        # rendered schedule. Any enabled production command uses the same gate.
        simulation_commands = [c for c in commands if 'run_main_simulation_cycle.sh' in c]
        self.assertLessEqual(len(simulation_commands), 1)
        for command in simulation_commands:
            self.assertIn('/CONTEXTUAL/CONFIG/SETUP/run-job.sh -- ', command)
        for station in (1, 2, 3, 4):
            command = any(f'guide_raw_to_corrected.sh -s {station}' in c for c in commands)
            configured = any(
                line.strip() and not line.lstrip().startswith('#')
                and f'guide_raw_to_corrected.sh -s {station}' in line
                for line in source.splitlines()
            )
            self.assertEqual(command, configured)
        for command in commands:
            self.assertIn('/CONTEXTUAL/CONFIG/SETUP/run-job.sh -- ', command)
            self.assertNotIn('/usr/bin/python3', command)
            self.assertNotIn('/usr/bin/crontab', command)
            self.assertNotIn('.cdsapirc', command)
            if 'sync_station_scripts.sh' in command:
                self.assertIn('/DATA_MAINTENANCE/REMOTE_SYNC/', command)

    def test_cron_is_independent_of_secrets_and_host_availability(self):
        original = recovery.render_cron()
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(recovery, 'HOME', Path(temp)), \
                patch.object(recovery, 'ssh_target', side_effect=AssertionError('renderer must not probe SSH')):
            self.assertEqual(recovery.render_cron(), original)

    def test_cron_paths_expand_to_current_home(self):
        paths, _ = recovery.cron_paths(recovery.render_cron())
        self.assertTrue(paths)
        self.assertFalse(any('$' in str(p) or '@REPO_ROOT@' in str(p) for p in paths))

    def test_no_runtime_path_escapes_checkout(self):
        with patch.object(recovery, 'manifest', return_value=['../../unsafe']):
            with self.assertRaises(ValueError): recovery.runtime_dirs()

    def test_configured_external_runtime_symlink_is_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            external = Path(temp) / 'external-station-data'
            external_backup = Path(temp) / 'external-log-backup'
            external.mkdir(parents=True)
            external_backup.mkdir()
            station_link = root / 'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS'
            station_link.parent.mkdir(parents=True)
            station_link.symlink_to(external, target_is_directory=True)
            backup_link = root / 'CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/REMOTE_LOG_BACKUP'
            backup_link.parent.mkdir(parents=True)
            backup_link.symlink_to(external_backup, target_is_directory=True)
            with patch.object(recovery, 'ROOT', root), \
                    patch.object(recovery, 'STATE', root / 'CONTEXTUAL/OPERATIONS/SETUP'), \
                    patch.object(recovery, 'manifest', return_value=[
                        'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO01/STAGE_1',
                        'CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/REMOTE_LOG_BACKUP/cron',
                    ]), \
                    patch.object(recovery, 'cron_paths', return_value=(set(), [])):
                paths = recovery.runtime_dirs()
            self.assertIn(station_link / 'MINGO01/STAGE_1', paths)
            self.assertIn(backup_link / 'cron', paths)

    def test_machine_config_symlink_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(recovery, 'HOME', Path(temp)):
            inst = recovery.Installer()
            original = Path(temp) / 'important'; original.write_text('preserve')
            link = Path(temp) / 'config'; link.symlink_to(original)
            with self.assertRaises(RuntimeError): inst.write(link, 'replacement')
            self.assertEqual(original.read_text(), 'preserve')

    def test_machine_config_backup_precedes_replacement(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(recovery, 'HOME', Path(temp)):
            inst = recovery.Installer(); target = Path(temp) / '.bashrc'
            target.write_text('personal aliases\n')
            inst.write(target, 'managed\n')
            backup = inst.backups / str(target).lstrip('/')
            self.assertEqual(backup.read_text(), 'personal aliases\n')
            self.assertEqual(target.read_text(), 'managed\n')
            inst.write(target, 'managed\n')
            self.assertEqual(backup.read_text(), 'personal aliases\n')

    def test_failed_crontab_read_never_means_empty(self):
        result = subprocess.CompletedProcess([], 1, '', 'permission denied')
        with patch.object(recovery, 'run', return_value=result):
            with self.assertRaises(RuntimeError): recovery.read_cron()

    def test_cron_environment_does_not_inherit_agent_or_pythonpath(self):
        env = recovery.cron_env()
        self.assertNotIn('SSH_AUTH_SOCK', env)
        self.assertNotIn('PYTHONPATH', env)
        self.assertTrue(env['PATH'].startswith(str(recovery.ROOT / '.venv/bin')))

    def test_closed_production_gate_does_not_execute_job(self):
        if (recovery.STATE / 'production-enabled').exists():
            self.skipTest('production gate is live; never close it during a running pipeline')
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / 'ran'
            r = subprocess.run(['bash', str(recovery.ROOT / 'CONTEXTUAL/CONFIG/SETUP/run-job.sh'), '--',
                                '/usr/bin/touch', str(marker)], capture_output=True)
            self.assertEqual(r.returncode, 0)
            self.assertFalse(marker.exists())

    def test_station_delete_filter_preserves_remote_only_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'; dest = Path(temp) / 'dest'
            (source / 'bot_scripts').mkdir(parents=True)
            (dest / 'bot_scripts').mkdir(parents=True)
            (source / 'bot_scripts/minitrasgo_bot.py').write_text('new')
            token = dest / 'bot_scripts/API.txt'; token.write_text('local-only-test-value')
            password = dest / 'bot_scripts/TERMINAL_PASSWORD.txt'; password.write_text('local-only-test-value')
            subprocess.run(['rsync', '-a', '--delete',
                            '--exclude-from=' + str(recovery.CONTENTS / 'rsync/station-deploy-excludes.list'),
                            str(source) + '/', str(dest) + '/'], check=True, capture_output=True)
            self.assertTrue(token.exists())
            self.assertTrue(password.exists())
            self.assertEqual((dest / 'bot_scripts/minitrasgo_bot.py').read_text(), 'new')

    def test_operations_wrapper_records_latest_job_status(self):
        script = recovery.ROOT / 'CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/ORCHESTRATION/CRON_RUN_LOGGED/cron_run_logged.sh'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = dict(os.environ, DATAFLOW_ROOT=temp)
            for name, command, expected in (('ok', '/usr/bin/true', '0,ok'), ('failed', '/usr/bin/false', '1,failed')):
                log = root / f'CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/tests/{name}.log'
                result = subprocess.run(['bash', script, log, '--', command], env=env, capture_output=True)
                csv = root / f'CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_STATUS/tests/{name}.csv'
                self.assertEqual(result.returncode, 0 if name == 'ok' else 1)
                self.assertTrue(csv.read_text().strip().endswith(expected))
                self.assertEqual(csv.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__': unittest.main()
