"""Repository paths shared by the Stage-1 comparison tools."""

from __future__ import annotations

import sys
from pathlib import Path


def _repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (
            (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()
            and (parent / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir()
        ):
            return parent
    raise RuntimeError(f"Could not locate repository root from {__file__}")


REPOSITORY_ROOT = _repository_root()
_ANALYSIS_SHARED_CODE = (
    REPOSITORY_ROOT
    / "PIPELINE"
    / "MINGO_ANALYSIS"
    / "MINGO_ANALYSIS_SCRIPTS"
    / "SUPPORT" / "SHARED_CODE"
)
if str(_ANALYSIS_SHARED_CODE) not in sys.path:
    sys.path.insert(0, str(_ANALYSIS_SHARED_CODE))

# Reuse the canonical repository configuration used by analysis scripts.
from path_config import load_repo_paths  # noqa: E402

_PATHS = load_repo_paths()
ANALYSIS_ROOT = REPOSITORY_ROOT / "PIPELINE" / "MINGO_ANALYSIS"
STATIONS_ROOT = _PATHS.stations_root
DIGITAL_TWIN_ROOT = _PATHS.digital_twin_root
