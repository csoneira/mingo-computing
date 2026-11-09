# Script Header Standard

This page defines the repository-wide standard header/docstring format for scripts.

Canonical source document:
- `DOCUMENTATION/docs/ESSENTIAL/script-header-standard.md`

Automated application tool:
- `CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DEVELOPER_TOOLS/standardize_script_headers.py`

## Required marker

Every standardized script must contain:

- `DATAFLOW_v3 Script Header v1`

## Required fields

1. `Script`
2. `Purpose`
3. `Owner`
4. `Sign-off`
5. `Last Updated`
6. `Runtime`
7. `Usage`
8. `Inputs`
9. `Outputs`
10. `Notes`

## Quick templates

### Python

```python
#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: path/to/script.py
Purpose: One-line purpose.
Owner: DATAFLOW_v3 contributors
Sign-off: <name> <email>
Last Updated: YYYY-MM-DD
Runtime: python3
Usage: python3 path/to/script.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""
```

### Bash

```bash
#!/usr/bin/env bash
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: path/to/script.sh
# Purpose: One-line purpose.
# Owner: DATAFLOW_v3 contributors
# Sign-off: <name> <email>
# Last Updated: YYYY-MM-DD
# Runtime: bash
# Usage: bash path/to/script.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================
```

### Octave/MATLAB

```matlab
% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: path/to/script.m
% Purpose: One-line purpose.
% Owner: DATAFLOW_v3 contributors
% Sign-off: <name> <email>
% Last Updated: YYYY-MM-DD
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================
```

### HTML

```html
<!--
=============================================================================
DATAFLOW_v3 Script Header v1
Script: path/to/page.html
Purpose: One-line purpose.
Owner: DATAFLOW_v3 contributors
Sign-off: <name> <email>
Last Updated: YYYY-MM-DD
Runtime: html
Usage: Open/render in browser or embed in docs/UI workflow.
Inputs: Static assets, linked resources, template variables (if any).
Outputs: Rendered page/view.
Notes: Keep references stable and document external dependencies.
=============================================================================
-->
```

## Apply or refresh headers

```bash
# dry-run
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DEVELOPER_TOOLS/standardize_script_headers.py

# apply headers
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DEVELOPER_TOOLS/standardize_script_headers.py --apply

# refresh existing standardized headers
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DEVELOPER_TOOLS/standardize_script_headers.py --apply --refresh
```

