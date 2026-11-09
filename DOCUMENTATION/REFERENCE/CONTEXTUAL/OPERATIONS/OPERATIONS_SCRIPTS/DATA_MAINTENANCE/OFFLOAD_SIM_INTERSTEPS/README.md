# External simulation INTERSTEPS

The external root is configured in `CONTEXTUAL/CONFIG/CONTENTS/storage/external_storage.conf`.
The simulation keeps using its existing logical path
`PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS`; after a verified cutover
that path is a symlink to the external directory. No simulation skip, queue,
or step-output rules change.

Default invocation is a read-only inventory:

```bash
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_SIM_INTERSTEPS/offload_sim_intersteps.py
```

To copy, hash-verify, atomically redirect, and release the original local copy:

```bash
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_SIM_INTERSTEPS/offload_sim_intersteps.py --activate
```

Activation refuses while simulation phase locks are held, or simulation
controller/step processes are running. It requires a separate writable
filesystem, refuses pre-existing destination data, verifies source and copy
before cutover, and removes the local original only after the symlink points to
the verified copy. If interrupted, preserve and inspect any
`.INTERSTEPS.external-link-*` directory beside `INTERSTEPS` before recovery.
Keep the external disk mounted before restarting simulation; a missing target
is treated as an error, not silently replaced with local storage.
