#!/usr/bin/env bash
# Purpose: update_plots.sh - synchronize selected plot images into the documentation.

# update_plots.sh - synchronize selected plot images into the documentation
# assets folder.
#
# The list of files to refresh is kept in "plot_list.txt" (one entry per
# line, relative to the workspace root). A source can optionally be followed
# by "|" and its destination below the assets directory. Lines beginning with
# "#" or blank are ignored. Each source may contain shell globs.
# Missing generated sources leave the published assets unchanged.

set -euo pipefail

# Determine directories relative to this script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"    # workspace root
ASSETS_DIR="$SCRIPT_DIR"
CONFIG_FILE="$ASSETS_DIR/plot_list.txt"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Configuration file not found: $CONFIG_FILE" >&2
  exit 1
fi

while IFS= read -r entry; do
  # strip whitespace
  entry="${entry%%#*}"      # remove comments after #
  entry="${entry#"${entry%%[![:space:]]*}"}"
  entry="${entry%"${entry##*[![:space:]]}"}"
  [[ -z "$entry" ]] && continue

  source_entry="${entry%%|*}"
  source_entry="${source_entry%"${source_entry##*[![:space:]]}"}"
  if [[ "$entry" == *"|"* ]]; then
    destination="${entry#*|}"
    destination="${destination#"${destination%%[![:space:]]*}"}"
    destination="${destination%"${destination##*[![:space:]]}"}"
  else
    destination="."
  fi
  if [[ -z "$source_entry" || -z "$destination" ]]; then
    echo "[update_plots] invalid entry: '$entry'" >&2
    exit 1
  fi

  # expand glob(s)
  shopt -s nullglob
  files=("$ROOT_DIR"/$source_entry)
  shopt -u nullglob

  if [[ ${#files[@]} -eq 0 ]]; then
    echo "[update_plots] no matches for '$source_entry'; keeping existing asset" >&2
    continue
  fi

  destination_path="$ASSETS_DIR/$destination"
  if [[ ${#files[@]} -gt 1 || "$destination" == */ || "$destination" == "." ]]; then
    mkdir -p "$destination_path"
    destination_is_directory=true
  else
    mkdir -p "$(dirname "$destination_path")"
    destination_is_directory=false
  fi

  for file in "${files[@]}"; do
    if [[ ! -e "$file" ]]; then
      echo "[update_plots] source not generated: '$source_entry'; keeping existing asset" >&2
      continue
    fi
    if [[ "$destination_is_directory" == true ]]; then
      cp -u "$file" "$destination_path/"
    else
      cp -u "$file" "$destination_path"
    fi
  done

done < "$CONFIG_FILE"

exit 0
