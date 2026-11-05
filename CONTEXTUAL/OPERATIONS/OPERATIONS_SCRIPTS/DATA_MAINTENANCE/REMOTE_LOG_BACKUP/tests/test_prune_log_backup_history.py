#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "prune_log_backup_history.py"
SPEC = importlib.util.spec_from_file_location("prune_log_backup_history", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
retention = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = retention
SPEC.loader.exec_module(retention)


class HistoryRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config = self.root / "config_selection.yaml"
        self.config.write_text(
            """
selection:
  stations: [1, 2]
  date_ranges:
    - start: 2026-01-31
      end: 2026-02-01
      stations: [1]
""".lstrip(),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_history_file(
        self, host: str, relative_path: str, *, mtime: datetime | None = None
    ) -> Path:
        path = (
            self.root
            / "hosts"
            / host
            / "history"
            / "20260701T000000Z"
            / relative_path
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative_path, encoding="utf-8")
        if mtime is not None:
            timestamp = mtime.timestamp()
            os.utime(path, (timestamp, timestamp))
        return path

    def test_calendar_month_context_and_station_scope(self) -> None:
        windows = retention.load_station_windows(self.config, context_months=1)

        self.assertEqual(
            windows[1][0].start,
            datetime(2025, 12, 31),
        )
        self.assertEqual(
            windows[1][0].end.date(),
            datetime(2026, 3, 1).date(),
        )
        self.assertEqual(windows[2], [])

    def test_dated_names_precede_mtime_and_apply_removes_only_outside(self) -> None:
        windows = retention.load_station_windows(self.config, context_months=1)
        keep_dated = self.make_history_file("mingo01", "rates_2026-01-15.log")
        remove_dated = self.make_history_file("mingo01", "rates_2026-04-01.log")
        keep_undated = self.make_history_file(
            "mingo01", "clean_rates.txt", mtime=datetime(2026, 2, 15)
        )
        remove_undated = self.make_history_file(
            "mingo01", "done/merged_rates.txt", mtime=datetime(2026, 4, 15)
        )

        dry_stats = retention.prune_host_history(
            self.root / "hosts/mingo01/history", windows[1], apply=False
        )
        self.assertEqual(dry_stats.kept_files, 2)
        self.assertEqual(dry_stats.removed_files, 2)
        self.assertTrue(remove_dated.exists())

        stats = retention.prune_host_history(
            self.root / "hosts/mingo01/history", windows[1], apply=True
        )
        self.assertEqual(stats.kept_files, 2)
        self.assertEqual(stats.removed_files, 2)
        self.assertTrue(keep_dated.exists())
        self.assertTrue(keep_undated.exists())
        self.assertFalse(remove_dated.exists())
        self.assertFalse(remove_undated.exists())

    def test_station_without_selected_range_keeps_no_history(self) -> None:
        windows = retention.load_station_windows(self.config, context_months=1)
        file_path = self.make_history_file("mingo02", "rates_2026-01-31.log")

        stats = retention.prune_host_history(
            self.root / "hosts/mingo02/history", windows[2], apply=True
        )
        self.assertEqual(stats.removed_files, 1)
        self.assertFalse(file_path.exists())

    def test_invalid_config_fails_before_deleting(self) -> None:
        protected = self.make_history_file("mingo01", "rates_2026-04-01.log")
        self.config.write_text("selection: {}\n", encoding="utf-8")

        with self.assertRaises(ValueError):
            retention.load_station_windows(self.config, context_months=1)
        self.assertTrue(protected.exists())


if __name__ == "__main__":
    unittest.main()
