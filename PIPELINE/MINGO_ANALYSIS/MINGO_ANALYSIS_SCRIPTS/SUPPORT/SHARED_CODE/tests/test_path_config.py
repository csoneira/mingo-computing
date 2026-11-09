from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE import path_config


class RepositoryPathTests(unittest.TestCase):
    def test_root_discovery_uses_repository_markers_not_checkout_name(self) -> None:
        with tempfile.TemporaryDirectory(prefix="relocated-checkout-") as temp:
            root = Path(temp) / "arbitrary-directory-name"
            utility = (
                root
                / "PIPELINE" / "MINGO_ANALYSIS"
                / "MINGO_ANALYSIS_SCRIPTS"
                / "SUPPORT" / "SHARED_CODE"
                / "path_config.py"
            )
            utility.parent.mkdir(parents=True)
            utility.touch()
            (root / "CONTEXTUAL" / "CONFIG").mkdir(parents=True)
            (root / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").touch()

            self.assertEqual(path_config.discover_repo_root(utility), root)

    def test_configured_repo_name_cannot_override_discovered_checkout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="relocated-checkout-") as temp:
            root = Path(temp) / "different-name"
            config = Path(temp) / "paths.yaml"
            config.write_text('home_path: "~"\nrepo_name: stale-name\n', encoding="utf-8")
            with patch.object(path_config, "_discover_repo_root", return_value=root):
                path_config.load_repo_paths.cache_clear()
                try:
                    paths = path_config.load_repo_paths(config)
                finally:
                    path_config.load_repo_paths.cache_clear()

            self.assertEqual(paths.repo_root, root)
            self.assertEqual(paths.repo_name, "different-name")


if __name__ == "__main__":
    unittest.main()
