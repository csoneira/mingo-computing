# Molière scattering studies

These standalone RPC-material scattering simulations are physical studies, not MINGO production-pipeline components. The scripts and historical figure outputs are preserved here by variant; they have not been run as part of this relocation.

## Contents

- [`moliere.py`](moliere.py): the previously recovered compact study.
- [`HISTORICAL_VARIANTS/MOLIERE_CALCULATION/`](HISTORICAL_VARIANTS/MOLIERE_CALCULATION/): a distinct, configurable simulation with its `rpc_layout.csv`, source figures, and original launcher.
- [`HISTORICAL_VARIANTS/MOLIÉRE/`](HISTORICAL_VARIANTS/MOLIÉRE/): another distinct parameterization, with its own layout and historical figures.

Keep these versions separate until their assumptions, layout inputs, and generated results have been compared. The layout CSV files are not byte-identical.

## Running caution

Do not run `HISTORICAL_VARIANTS/MOLIERE_CALCULATION/run_moliere.sh` casually: it launches the simulation 1,000 times. The scripts also save figures relative to the current working directory and may overwrite existing output names. Review the runtime and output paths before running either variant.
