# Research studies recovered from the legacy TRASGO archive

This index records selected material recovered from `legacy/TRASGO_TESTS_AND_TOOLS` into the current scientific organization. The active copies remain byte-for-byte snapshots of the original scripts; they have not been modernized, validated against current data, or made part of production processing. Exact duplicate files were removed from legacy working trees after verification. Their original repository paths and blob identifiers remain in the [archive manifest](../../legacy/TRASGO_TESTS_AND_TOOLS/ARCHIVE_MANIFEST.md).

For the larger local archive, duplicate-removal details, and additional rescue candidates, see the [ALL_MINITRASGO review](ALL_MINITRASGO_ARCHIVE_REVIEW.md).

Several original input files were intentionally not included in the archive. A script being present in its new location therefore does not imply that it is currently runnable. Do not run an old study until its inputs, assumptions, output paths, and dependencies have been checked.

## Simulation versus data

The user-specified scientific purpose of PSD and PID is to compare measured detector responses with particle labels or ground truth from simulation. They belong in this category even though the old scripts do not contain the simulated truth files themselves.

| Study | Current copy | Original source | Status and caveats |
|---|---|---|---|
| Particle identification using absorber/sample charge differences | [`naive_deltas.py`](../../PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_DATA/PARTICLE_IDENTIFICATION/PID/naive_deltas.py) | `PID/naive_deltas.py` in the source manifest (blob `df0de4f…`) | Historical script expects `naive_deltas.txt` and `naive_deltas_lead.txt`; neither is included. Re-establish sample labels and simulated-muon truth provenance before interpreting separation as PID performance. |
| Pulse-shape analysis (PSD) | [`pseudoPSA.py`](../../PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_DATA/PARTICLE_IDENTIFICATION/PSD/pseudoPSA.py) | `PSD/pseudoPSA.py` in the source manifest (blob `1674a67…`) | Historical script expects `charge_per_event_only_muons.dat`, absent from the curated source archive. The full `ALL_MINITRASGO` dump also did not preserve this named input. The intended simulation-truth comparison follows the study classification. |

These are candidate studies, not integrated MINGO reconstruction or production particle-identification methods.

## Simulation versus simulation

These scripts generate toy or Monte Carlo samples and compare reconstructed/estimated quantities with known inputs. They are useful prototypes for acceptance, efficiency closure, and position-resolution studies.

| Study | Current copy | Legacy source | Status and caveats |
|---|---|---|---|
| Toy four-plane efficiency and trigger-pattern closure | [`eff_simple_toy_model.py`](../../PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/EFFICIENCY_AND_ACCEPTANCE/eff_simple_toy_model.py) | `legacy/TRASGO_TESTS_AND_TOOLS/Efficiency and acceptance studies/eff_simple_toy_model.py` | Uses a simplified geometry and configured plane efficiencies as truth. A lightweight conceptual prototype, not a detector-faithful simulation. |
| Geometric acceptance and plane efficiency scan | [`geometric_acceptance.py`](../../PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/EFFICIENCY_AND_ACCEPTANCE/geometric_acceptance.py) | Original source path and blob `11032f0…` in the [archive manifest](../../legacy/TRASGO_TESTS_AND_TOOLS/ARCHIVE_MANIFEST.md) | Monte Carlo geometry study. The curated archive omits generated result CSVs; inspect its output behavior and parameters before use. |
| Strip-width and position-resolution study | [`strip_width_simulation.py`](../../PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/POSITION_RESOLUTION/strip_width_simulation.py) | Original source path and blob `abf0f7f…` in the [archive manifest](../../legacy/TRASGO_TESTS_AND_TOOLS/ARCHIVE_MANIFEST.md) | Simulates strip response and compares fitted position/width with generated truth. Treat results as a model study until its response assumptions are checked against the current detector. |

The reserved [`CALIBRATION_LUT_GENERATION`](../../PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/CALIBRATION_LUT_GENERATION/) location is for future simulation-derived calibration LUT work. None of these legacy scripts currently generates a production LUT for `MINGO_ANALYSIS`.

## Data versus data and external reference measurements

| Study | Current copy | Legacy source | Status and caveats |
|---|---|---|---|
| Pressure correction of Oulu neutron-monitor rates | [`pressure_CALMA.py`](../../PIPELINE/MINGO_COMPARISONS/MINGO_DATA_VS_DATA/EXTERNAL_REFERENCE_STUDIES/OULU_PRESSURE_RATE/pressure_CALMA.py) | TRASGO source blob `15ebe61…` in the [archive manifest](../../legacy/TRASGO_TESTS_AND_TOOLS/ARCHIVE_MANIFEST.md) | This is the most complete local version, from the 2025-03-10 TRASGO source snapshot; it adds daily beta extraction and smoothed R² analyses. The older 2024 `MINGO_PRESSURE` working copy was removed as superseded; its blob remains recorded in [`legacy/MINGO_PRESSURE/README.md`](../../legacy/MINGO_PRESSURE/README.md). The local, Git-excluded archive preserves `pressure_OULU.csv` and `rate_OULU.csv`; derived filtered CSVs are absent. |

## Out-of-pipeline physical studies

These studies concern detector physics or other instrumentation but are not part of the MINGO event-processing pipeline.

| Study | Current copy | Legacy source | Status and caveats |
|---|---|---|---|
| Molière scattering in RPC material | [`moliere.py`](../../OUT_OF_PIPELINE/PHYSICAL_TESTS/MOLIERE_SCATTERING/moliere.py) | Original source path and blob `f43097b…` in the [archive manifest](../../legacy/TRASGO_TESTS_AND_TOOLS/ARCHIVE_MANIFEST.md) | Standalone physical Monte Carlo. Two additional variants, including distinct layout CSVs and historical figures, are preserved in [`HISTORICAL_VARIANTS`](../../OUT_OF_PIPELINE/PHYSICAL_TESTS/MOLIERE_SCATTERING/HISTORICAL_VARIANTS/); see that directory's README before selecting a version. |
| Geomagnetic cutoff rigidity lookup | [`cutoff_rigidity_calculator.py`](../../OUT_OF_PIPELINE/PHYSICAL_TESTS/GEOMAGNETIC_CUTOFF/cutoff_rigidity_calculator.py) | `legacy/TRASGO_TESTS_AND_TOOLS/Magnetic calculations/cutoff_rigidity_calculator.py` | Interpolates a stored location table; useful as a small standalone calculator, with the original site assumptions retained. |
| Scintillator energy-loss toy model | [`muon_electron_sim.py`](../../OUT_OF_PIPELINE/PHYSICAL_TESTS/MIPS_IN_SCINTILLATORS/muon_electron_sim.py) | Original source path and blob `f1ff49b…` in the [archive manifest](../../legacy/TRASGO_TESTS_AND_TOOLS/ARCHIVE_MANIFEST.md) | Simplified energy-loss/light-yield model. Its formulae and particle-mass choices need a dedicated physics review before quantitative use. |
| SCIMIN scintillator position reconstruction | [`SCIMIN/`](../../OUT_OF_PIPELINE/PHYSICAL_TESTS/SCINTILLATOR_POSITION_RECONSTRUCTION/SCIMIN/) | Original source paths and blobs in the [archive manifest](../../legacy/TRASGO_TESTS_AND_TOOLS/ARCHIVE_MANIFEST.md) | Contains a position study and neural-network script. Required measurement files are absent; the neural-network script also contains an old machine-specific package path. This is separate instrumentation and remains outside the MINGO pipeline. |

## Kept only in the legacy archive

- `Neutrons_tests/pyscript/neutrons.py`: not copied as an executable study because it deletes every PDF in its current working directory at startup, and its expected `neutron_time_energy.dat` input is absent. It needs a safe output-directory redesign before revival.
- `Waiting time - Mistaken analysis/fixed_waiting.py`: retained only as provenance because the archive explicitly labels the analysis mistaken, and its expected MAT input is absent.
- `ORIGINAL_README.md`, the archive manifest, and all source snapshots remain under `legacy/TRASGO_TESTS_AND_TOOLS`.

## Promotion policy

The copies above preserve the original scripts for review and future recovery. They are not aliases or symlinks to `legacy`, and no generated datasets were copied. Before adapting one into an active study, retain a link to its legacy source, restore and document its inputs, and validate its scientific assumptions without changing the archived snapshot.
