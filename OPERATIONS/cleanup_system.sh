#!/usr/bin/env bash

set -u

# ============================================================
# Ubuntu cleanup script
#
# Usage:
#   ~/mingo-computing/OPERATIONS/cleanup_system.sh
#       Full cleanup, including privileged operations.
#
#   ~/mingo-computing/OPERATIONS/cleanup_system.sh --no-sudo
#       User-only cleanup. Never invokes sudo.
#
# Reports:
#   - disk space before
#   - disk space after
#   - total recovered space in GB and GiB
# ============================================================

NO_SUDO=0

usage() {
    cat <<USAGE
Usage: $(basename "$0") [--no-sudo]

Options:
  --no-sudo, -n   Never use sudo. Skip operations requiring root.
  --help, -h      Show this help.
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --no-sudo|-n)
            NO_SUDO=1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done


# ------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------

HOME_FS="$HOME"

bytes_free() {
    df -B1 --output=avail "$HOME_FS" | tail -1 | tr -d ' '
}

gb_decimal() {
    awk -v bytes="$1" 'BEGIN { printf "%.3f", bytes / 1000000000 }'
}

gib_binary() {
    awk -v bytes="$1" 'BEGIN { printf "%.3f", bytes / 1073741824 }'
}

show_disk() {
    df -h "$HOME_FS"
}

remove_contents() {
    local dir="$1"

    if [ -d "$dir" ]; then
        echo "Cleaning: $dir"
        find "$dir" -mindepth 1 -maxdepth 1 \
            -exec rm -rf -- {} + 2>/dev/null || true
    fi
}

section() {
    echo
    echo "------------------------------------------------------------"
    echo "$1"
    echo "------------------------------------------------------------"
}


# ------------------------------------------------------------
# Initial report
# ------------------------------------------------------------

echo
echo "============================================================"
echo " SYSTEM CLEANUP"
echo "============================================================"
echo "Host : $(hostname)"
echo "User : $(whoami)"
echo "Date : $(date)"

if [ "$NO_SUDO" -eq 1 ]; then
    echo "Mode : NO-SUDO"
else
    echo "Mode : FULL"
fi

echo

FREE_BEFORE=$(bytes_free)

echo "Disk space BEFORE cleanup:"
show_disk

echo
echo "Available before: $(gb_decimal "$FREE_BEFORE") GB ($(gib_binary "$FREE_BEFORE") GiB)"


# ------------------------------------------------------------
# Acquire sudo once, only in full mode
# ------------------------------------------------------------

if [ "$NO_SUDO" -eq 0 ]; then
    section "Preparing privileged cleanup"

    echo "Some cleanup operations require sudo."

    if ! sudo -v; then
        echo "Could not obtain sudo privileges." >&2
        exit 1
    fi
fi


# ------------------------------------------------------------
# 1. Disabled Snap revisions
# ------------------------------------------------------------

section "1. Removing disabled Snap revisions"

if [ "$NO_SUDO" -eq 1 ]; then
    echo "Skipped: requires sudo."
else
    if command -v snap >/dev/null 2>&1; then

        snap list --all 2>/dev/null |
        awk '$NF == "disabled" {print $1, $3}' |
        while read -r snapname revision; do

            [ -z "$snapname" ] && continue

            echo "Removing old Snap: $snapname revision $revision"

            sudo snap remove \
                "$snapname" \
                --revision="$revision" || true
        done

    else
        echo "Snap is not installed."
    fi
fi


# ------------------------------------------------------------
# 2. APT cache
# ------------------------------------------------------------

section "2. Cleaning APT package cache"

if [ "$NO_SUDO" -eq 1 ]; then
    echo "Skipped: requires sudo."
else
    sudo apt-get clean
fi


# ------------------------------------------------------------
# 3. Unused APT packages
# ------------------------------------------------------------

section "3. Removing unused APT packages"

if [ "$NO_SUDO" -eq 1 ]; then
    echo "Skipped: requires sudo."
else
    sudo apt-get autoremove --purge -y
fi


# ------------------------------------------------------------
# 4. User Trash
# ------------------------------------------------------------

section "4. Emptying user Trash"

remove_contents "$HOME/.local/share/Trash/files"
remove_contents "$HOME/.local/share/Trash/info"

echo "Trash cleaned."


# ------------------------------------------------------------
# 5. Thumbnail cache
# ------------------------------------------------------------

section "5. Cleaning thumbnail cache"

remove_contents "$HOME/.cache/thumbnails"


# ------------------------------------------------------------
# 6. Common disposable user caches
# ------------------------------------------------------------

section "6. Cleaning common disposable user caches"

remove_contents "$HOME/.cache/fontconfig"
remove_contents "$HOME/.cache/mesa_shader_cache"
remove_contents "$HOME/.cache/mesa_shader_cache_db"


# ------------------------------------------------------------
# 7. Python package caches
# ------------------------------------------------------------

section "7. Cleaning Python package caches"

if command -v pip >/dev/null 2>&1; then
    echo "Cleaning pip cache..."
    pip cache purge 2>/dev/null || true
fi

if command -v pip3 >/dev/null 2>&1; then
    echo "Cleaning pip3 cache..."
    pip3 cache purge 2>/dev/null || true
fi

if command -v uv >/dev/null 2>&1; then
    echo "Cleaning uv cache..."
    uv cache clean 2>/dev/null || true
fi

remove_contents "$HOME/.cache/pip"


# ------------------------------------------------------------
# 8. JavaScript package-manager caches
# ------------------------------------------------------------

section "8. Cleaning JavaScript package-manager caches"

if command -v npm >/dev/null 2>&1; then
    echo "Cleaning npm cache..."
    npm cache clean --force >/dev/null 2>&1 || true
fi

if command -v yarn >/dev/null 2>&1; then
    echo "Cleaning yarn cache..."
    yarn cache clean >/dev/null 2>&1 || true
fi

if command -v pnpm >/dev/null 2>&1; then
    echo "Pruning pnpm store..."
    pnpm store prune >/dev/null 2>&1 || true
fi


# ------------------------------------------------------------
# 9. Unused user Flatpak runtimes
# ------------------------------------------------------------

section "9. Removing unused user Flatpak runtimes"

if command -v flatpak >/dev/null 2>&1; then
    flatpak uninstall --user --unused -y 2>/dev/null || true
else
    echo "Flatpak is not installed."
fi


# ------------------------------------------------------------
# 10. User systemd temporary files
# ------------------------------------------------------------

section "10. Cleaning user temporary files"

if command -v systemd-tmpfiles >/dev/null 2>&1; then
    systemd-tmpfiles --user --clean 2>/dev/null || true
fi


# ------------------------------------------------------------
# 11. Old user cache files
# ------------------------------------------------------------

section "11. Removing stale user cache files older than 60 days"

if [ -d "$HOME/.cache" ]; then

    find "$HOME/.cache" \
        -type f \
        -atime +60 \
        -delete 2>/dev/null || true

    find "$HOME/.cache" \
        -depth \
        -type d \
        -empty \
        -delete 2>/dev/null || true

fi


# ------------------------------------------------------------
# 12. System journal
# ------------------------------------------------------------

section "12. Cleaning old system journal logs"

if [ "$NO_SUDO" -eq 1 ]; then
    echo "Skipped: requires sudo."
else
    if command -v journalctl >/dev/null 2>&1; then
        echo "Keeping the last 14 days of journal logs."
        sudo journalctl --vacuum-time=14d
    else
        echo "systemd journal not available."
    fi
fi


# ------------------------------------------------------------
# 13. /tmp
# ------------------------------------------------------------

section "13. Cleaning stale /tmp files"

if [ "$NO_SUDO" -eq 1 ]; then
    echo "Skipped: system /tmp cleanup requires sudo."
else
    echo "Deleting entries in /tmp older than 7 days."

    sudo find /tmp \
        -mindepth 1 \
        -mtime +7 \
        -delete 2>/dev/null || true
fi


# ------------------------------------------------------------
# 14. APT partial downloads
# ------------------------------------------------------------

section "14. Cleaning obsolete APT download fragments"

if [ "$NO_SUDO" -eq 1 ]; then
    echo "Skipped: requires sudo."
else
    sudo find /var/cache/apt/archives/partial \
        -mindepth 1 \
        -maxdepth 1 \
        -delete 2>/dev/null || true
fi


# ------------------------------------------------------------
# Final report
# ------------------------------------------------------------

sync

FREE_AFTER=$(bytes_free)
GAIN=$((FREE_AFTER - FREE_BEFORE))

echo
echo "============================================================"
echo " CLEANUP COMPLETE"
echo "============================================================"
echo

echo "Disk space AFTER cleanup:"
show_disk

echo
printf "%-15s %10s GB  (%s GiB)\n" \
    "Free before:" \
    "$(gb_decimal "$FREE_BEFORE")" \
    "$(gib_binary "$FREE_BEFORE")"

printf "%-15s %10s GB  (%s GiB)\n" \
    "Free after:" \
    "$(gb_decimal "$FREE_AFTER")" \
    "$(gib_binary "$FREE_AFTER")"

printf "%-15s %10s GB  (%s GiB)\n" \
    "RECOVERED:" \
    "$(gb_decimal "$GAIN")" \
    "$(gib_binary "$GAIN")"

echo
echo "Completed: $(date)"
echo "============================================================"
