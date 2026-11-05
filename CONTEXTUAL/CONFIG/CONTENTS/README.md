# Analysis PC contents

`CONTENTS` is the public, declarative machine inventory; `SETUP` applies and
checks it. The primary machine is a Debian/Ubuntu analysis PC owned by the
normal user whose home contains the `mingo-computing` checkout. A station's `rpcuser` crontab,
DAQ, hardware, and system packages are separate and must be recovered on the
station; the analysis PC setup never installs the station crontab.

The cron template is the sole production schedule. It is rendered with the
checkout root, a repository virtual environment, and a job gate. The old
`CONTEXTUAL/CONFIG/add_to_crontab.info` path is a compatibility symlink to this template,
**not** a directly installable crontab. No cron self-reinstaller remains.
`CONTEXTUAL/CONFIG/requirements.list` and `DOCUMENTATION/requirements.txt` are also
compatibility symlinks. The direct Python requirements are in
`packages/python-requirements.txt`; `python-lock.txt` is the tested, pinned
resolution for Python 3.12. Documentation packages are included in the same
virtual environment. `yq` is the kislyuk Python jq wrapper, pinned at 3.4.3;
the query syntax in Stage 0 requires this implementation. `jq` is a separate
APT package. Octave runs the bundled Stage 0 unpacker. Java and Tk are listed
as optional for legacy PDF/GUI tasks, not analysis cron prerequisites.

The APT list is derived from active cron and its child shell scripts: cron,
OpenSSH client, rsync, tmux, util-linux (`flock`, `swapoff`, `swapon`), procps
(`ps`, `pgrep`), GNU text/file tools, `wget` for station logbooks, `jq` for
`yq`, Octave for reprocessing, and Python virtual environment support.
`packages/python-imports.txt` is the smoke-test import list. The complete
tracked-file audit is in `SETUP/AUDIT.md`.

`environment/runtime-directories.json` contains only reproducible structure;
it is never a data manifest. `environment/remote-targets.json` describes
read-only remote path probes, while `ssh/config` is the sole host endpoint
source. `environment/recoverable-inputs.json` pins the shared C001 calibration
digest verified independently on three stations in September 2026.

`rsync/station-deploy-excludes.list` protects station-local API and terminal
password files from the legacy `--delete` deployment. Production activation
requires a dry-run against each station and the exact destination directory.
Dry-run output is information about proposed changes, not permission to push
arbitrary destination paths.
