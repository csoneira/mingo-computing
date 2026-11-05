# Recovered SSH topology

The host entries in `config` were recovered from this analysis PC's
`~/.ssh/config` on 2026-09-22. `ana` is `rpcuser@ocean.lipc:40022`;
`mingo01..04` are `rpcuser@localhost:20001..20004` **as seen through `ana`**.
`backuplip` is `rpcuser@10.0.1.20:22`. The distinct `mingo` login found in
the old local config was `mingo@ocean.lipc:8022` with an unusable identity
path referring to a different user's home. Its safe endpoint is preserved in
`legacy-optional.conf`. No active analysis job uses it; its role and key must
be confirmed before adding it to production checks.
No second backup PC endpoint was found. Do not infer one from `backuplip`.

Setup merges an Include into `~/.ssh/config`, first backing it up. It also
backs up `known_hosts` before permission changes and creates a dedicated
unencrypted Ed25519 private key at `~/.ssh/id_ed25519_dataflow` only if absent.
The empty passphrase lets cron use it with no agent. Anyone who can read this
key can authenticate as its authorized remote user; keep the private key at
mode `0600`, the SSH directory at `0700`, and restrict remote authorized-key
privileges where possible. A passphrase-protected key needs an agent available
to cron, which this recovery profile does not rely on.

Before trusting any new host key, compare its fingerprint with the operator's
independent station inventory. `StrictHostKeyChecking yes` remains in effect;
setup does not auto-accept unknown or changed keys. Existing entries are
preserved. For each host whose dedicated key fails, install its public key:

```bash
python3 CONTEXTUAL/CONFIG/SETUP/recovery.py enroll-ssh ana
python3 CONTEXTUAL/CONFIG/SETUP/recovery.py enroll-ssh backuplip --identity ~/.ssh/id_rsa
python3 CONTEXTUAL/CONFIG/SETUP/recovery.py enroll-ssh mingo01
python3 CONTEXTUAL/CONFIG/SETUP/recovery.py enroll-ssh mingo02
python3 CONTEXTUAL/CONFIG/SETUP/recovery.py enroll-ssh mingo03
python3 CONTEXTUAL/CONFIG/SETUP/recovery.py enroll-ssh mingo04
```

The optional `--identity` uses an existing local identity only to enroll the
new public key. Password authentication is possible interactively. The
command tests the dedicated key before and after enrolling; it never copies
the private key. A failed `ProxyJump` port cannot be fixed by `ssh-copy-id`.
Check `ssh -G HOST` for endpoint resolution, then
`ssh -F ~/.ssh/dataflow.conf -o BatchMode=yes HOST true` for cron access.
