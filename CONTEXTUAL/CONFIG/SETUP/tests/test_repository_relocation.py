from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
LEGACY_BASENAME = "DATAFLOW" + "_v3"
SCANNED_SUFFIXES = {
    ".py", ".sh", ".m", ".yaml", ".yml", ".json", ".conf", ".toml", ".ini", ".info",
}


class RepositoryRelocationTests(unittest.TestCase):
    def test_executable_and_configuration_files_do_not_pin_checkout_name(self) -> None:
        forbidden = [
            re.compile(rf"\$HOME/{LEGACY_BASENAME}(?:/|\b)"),
            re.compile(rf"\$\{{HOME\}}/{LEGACY_BASENAME}(?:/|\b)"),
            re.compile(rf"~/{LEGACY_BASENAME}(?:/|\b)"),
            re.compile(rf"/home/[^/\s\"']+/{LEGACY_BASENAME}(?:/|\b)"),
            re.compile(rf"Path\.home\(\)\s*/\s*['\"]{LEGACY_BASENAME}['\"]"),
            re.compile(rf"expanduser\([^)]*{LEGACY_BASENAME}(?:/|['\"])") ,
            re.compile(rf"DATAFLOW_ROOT:-[^}}]*{LEGACY_BASENAME}"),
        ]
        intentionally_legacy = {
            Path("CONTEXTUAL/CONFIG/SETUP/tests/test_recovery.py"),
        }
        tracked = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=REPO_ROOT
        ).decode().split("\0")
        failures: list[str] = []
        for relative in filter(None, tracked):
            path = Path(relative)
            if path.suffix.lower() not in SCANNED_SUFFIXES:
                continue
            if "OPERATIONS_RUNTIME/OBSERVABILITY/SEARCH_FOR_ERRORS/ERROR_SUMMARIES" in relative:
                continue
            if relative == "REPOSITORY_RENAME_MIGRATION_PLAN.md" or path in intentionally_legacy:
                continue
            try:
                content = (REPO_ROOT / path).read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                marker = "%" if path.suffix.lower() == ".m" else "#"
                code = line.split(marker, 1)[0] if path.suffix.lower() in {".py", ".sh", ".m", ".conf", ".ini"} else line
                if any(pattern.search(code) for pattern in forbidden):
                    failures.append(f"{path}:{line_number}: {line.strip()}")
        self.assertEqual([], failures, "Checkout-name-dependent runtime/config paths found:\n" + "\n".join(failures))

    def test_path_config_resolves_this_checkout(self) -> None:
        import sys

        sys.path.insert(0, str(REPO_ROOT))
        from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root

        self.assertEqual(REPO_ROOT.resolve(), get_repo_root().resolve())


if __name__ == "__main__":
    unittest.main()
