from pathlib import Path

from comparison_paths import (
    ANALYSIS_ROOT,
    DIGITAL_TWIN_ROOT,
    REPOSITORY_ROOT,
    STATIONS_ROOT,
)


def test_shared_stage1_tools_resolve_current_repository_layout() -> None:
    assert REPOSITORY_ROOT.is_dir()
    assert ANALYSIS_ROOT == REPOSITORY_ROOT / "PIPELINE" / "MINGO_ANALYSIS"
    assert STATIONS_ROOT == ANALYSIS_ROOT / "MINGO_ANALYSIS_STATIONS"
    assert DIGITAL_TWIN_ROOT == REPOSITORY_ROOT / "PIPELINE" / "MINGO_DIGITAL_TWIN"
    assert (STATIONS_ROOT / "MINGO01").is_dir()
    assert DIGITAL_TWIN_ROOT.is_dir()


def test_stage1_tools_are_outside_the_production_analysis_tree() -> None:
    tools_root = Path(__file__).resolve().parents[1]
    assert tools_root.is_relative_to(REPOSITORY_ROOT / "PIPELINE" / "MINGO_COMPARISONS")
