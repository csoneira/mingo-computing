"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/__init__.py
Purpose: Validation package for MINGO digital twin outputs.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/__init__.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from .common_io import StepArtifact
from .common_report import RESULT_COLUMNS, SUMMARY_COLUMNS

__all__ = [
    "StepArtifact",
    "RESULT_COLUMNS",
    "SUMMARY_COLUMNS",
]
