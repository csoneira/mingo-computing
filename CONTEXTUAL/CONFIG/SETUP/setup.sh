#!/usr/bin/env bash
# Purpose: Run repository recovery and setup commands.

set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.."
exec /usr/bin/python3 CONTEXTUAL/CONFIG/SETUP/recovery.py setup "$@"
