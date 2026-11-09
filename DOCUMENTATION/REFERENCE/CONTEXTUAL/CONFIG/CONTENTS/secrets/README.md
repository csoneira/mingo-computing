# Machine-local secrets

See `manifest.json` for exact paths and modes. Setup verifies nonempty files,
changes their mode to `0600` when they are present, and never prints values.
The Telegram bot needs both its `API_TOKEN.txt` and `TERMINAL_PASSWORD.txt`
at the tracked bot script directory. Restore them from a trusted personal
backup or create new credentials out of band. The terminal password enables
remote terminal mode: review whether that feature should remain enabled.

Copernicus uses `~/.cdsapirc` directly. Restore it at mode `0600` from a
trusted secret store or create a fresh CDS API key. The former cron copy from
an ignored `.cdsapirc` inside the clone has been retired. Never copy the file
into this public repository. `setup.sh --check` performs local CDS client
initialization; the optional online check attempts read-only authentication,
without submitting a data request.

An old Octave configuration also had a database password literal in tracked
source. The working tree now disables this unused publishing path and clears the
password field. The historical DB endpoint is outside current analysis cron.
Rotate the old database password if still valid: Git history still contains
it. A future DB integration needs a separate security review; do not put a
replacement in a shell fragment, tracked file, or cron line.

Station-local `bot_scripts/API.txt` and `TERMINAL_PASSWORD.txt` belong on
each station and are excluded from deployment deletion. They are not cloned
or stored by analysis setup. Simulation notification environment overrides
are optional; the bot token file is the fallback. Secret files, SSH private
keys, cookies, and `.env*` files are ignored by Git. Run `git status --short`
before committing to check for surprises.

A second tracked Octave helper contained an SMTP password. It is now disabled
and its literal removed from the working tree. Rotate that credential too;
the old value remains in Git history.
