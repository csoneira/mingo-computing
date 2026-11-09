# Review of the `ALL_MINITRASGO_from_fistensor2` archive

Reviewed on 2026-11-09. The local archive at `legacy/ALL_MINITRASGO_from_fistensor2/` was initially about 405 MiB and contains historical scripts, generated plots, data products, raw pulse recordings, and three nested Git repositories. It is a local recovery archive, not a supported software checkout. Its path is listed in this machine's `.git/info/exclude` so a broad `git add` cannot accidentally add the archive, its nested `.git` directories, or large data files. The review index and current scientific copies remain in the repository documentation and classified code directories.

## Exact duplicates removed

Files were removed only after a SHA-256 match against an existing canonical copy elsewhere in the repository. The active/canonical copy remains available.

| Removed from `ALL_MINITRASGO_from_fistensor2` | Canonical copy retained |
|---|---|
| `HV_SCAN_APP/.gitignore`, `CONFIG/drive_links.txt`, `README.md`, `hv_scan_analysis.py`, `requirements.list` | `legacy/HV_SCAN_APP/` |
| `MINGO_PRESSURE/pressure_CALMA.py` | The superseded 2024 copy was removed; the selected later implementation is `PIPELINE/MINGO_COMPARISONS/MINGO_DATA_VS_DATA/EXTERNAL_REFERENCE_STUDIES/OULU_PRESSURE_RATE/pressure_CALMA.py` |
| `TRASGO_TESTS_AND_TOOLS/Efficiency and acceptance studies/Geometric_acc/geometric_acceptance.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/EFFICIENCY_AND_ACCEPTANCE/` |
| `TRASGO_TESTS_AND_TOOLS/Efficiency and acceptance studies/eff_simple_toy_model.py` | Same simulation-versus-simulation directory |
| `TRASGO_TESTS_AND_TOOLS/MIPs losing energy in scintillators/muon_electron_sim.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/MIPS_IN_SCINTILLATORS/` |
| `TRASGO_TESTS_AND_TOOLS/MOLIÉRE/moliere.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/MOLIERE_SCATTERING/` |
| `TRASGO_TESTS_AND_TOOLS/Magnetic calculations/cutoff_rigidity_calculator.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/GEOMAGNETIC_CUTOFF/` |
| `TRASGO_TESTS_AND_TOOLS/Neutrons_tests/pyscript/neutrons.py` | `legacy/TRASGO_TESTS_AND_TOOLS/Neutrons_tests/pyscript/` |
| `TRASGO_TESTS_AND_TOOLS/PID/naive_deltas.py` and `PSD/pseudoPSA.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_DATA/PARTICLE_IDENTIFICATION/{PID,PSD}/` |
| `TRASGO_TESTS_AND_TOOLS/Pressure NMDB study/pressure_CALMA.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_DATA_VS_DATA/EXTERNAL_REFERENCE_STUDIES/OULU_PRESSURE_RATE/` |
| `TRASGO_TESTS_AND_TOOLS/SCIMIN/NN_position_scint.py` and `position_study_in_scint.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/SCINTILLATOR_POSITION_RECONSTRUCTION/SCIMIN/` |
| `TRASGO_TESTS_AND_TOOLS/Y position studies/strip_width_simulation.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/POSITION_RESOLUTION/` |

The same 11 exact source duplicates were removed from the curated `legacy/TRASGO_TESTS_AND_TOOLS/` working tree. Their original source paths and upstream Git blob IDs remain recorded in its [archive manifest](../../legacy/TRASGO_TESTS_AND_TOOLS/ARCHIVE_MANIFEST.md); the classified copies are unchanged byte-for-byte. Nested Git metadata in the large local archive was retained. No unique data or plots were removed. One additional 2.86 MiB `minitrasgo_efficiency/long_consolidated_df.csv` was byte-identical to `consolidated_df.csv`; no script referenced the former name, so that redundant copy was removed and `consolidated_df.csv` retained.

## Unique material retained for later review

| Archive location | Possible home / scientific classification | Why it may be useful; current status |
|---|---|---|
| `MINGO_PRESSURE/pressure_OULU.csv`, `rate_OULU.csv` | `MINGO_DATA_VS_DATA` external reference study | These are the unique inputs for the Oulu pressure/rate analysis. They remain in the local archive rather than being copied into a pipeline dataset directory. The filtered derived CSV is absent. |
| Older `legacy/MINGO_PRESSURE/pressure_CALMA.py` source blob | Historical provenance only | This version's blob matches the December 2024 nested-repository snapshot and was removed from its working path after comparison. The selected March 2025 implementation is more complete and remains at the MINGO_DATA_VS_DATA destination. |
| `legacy/HV_SCAN_APP/` | Data-versus-data / HV-scan tooling candidate | A separate historical HV-scan analysis app remains in `legacy`; inspect its input format and intended operator workflow before deciding whether it belongs with the experimental comparison studies or operational tooling. |
| `MOLIERE_CALCULATION/` | [`OUT_OF_PIPELINE/PHYSICAL_TESTS/MOLIERE_SCATTERING/HISTORICAL_VARIANTS/MOLIERE_CALCULATION/`](../../OUT_OF_PIPELINE/PHYSICAL_TESTS/MOLIERE_SCATTERING/HISTORICAL_VARIANTS/MOLIERE_CALCULATION/) | Moved from the local archive. Contains a distinct configurable simulation, its unique `rpc_layout.csv`, source figures, and original launcher. Keep separate from the compact script until assumptions/results are compared. Its `run_moliere.sh` loops 1,000 times; do not use that wrapper casually. |
| `MOLIÉRE/` | [`OUT_OF_PIPELINE/PHYSICAL_TESTS/MOLIERE_SCATTERING/HISTORICAL_VARIANTS/MOLIÉRE/`](../../OUT_OF_PIPELINE/PHYSICAL_TESTS/MOLIERE_SCATTERING/HISTORICAL_VARIANTS/MOLIÉRE/) | Moved from the local archive. A second distinct parameter set and figure set; retain as a version to compare, not as an automatic replacement. |
| `SIMULATION_ENERGY_TIMING/sim.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/ENERGY_FROM_TIMING/` | Independent timing-resolution/geometry simulation. It complements the historical energy-from-timing scripts already indexed there; it is not a MINGO processing stage. |
| `MINITRASGO_EFF/` and `minitrasgo_efficiency/` | `MINGO_SIMULATION_VS_SIMULATION` candidate | Efficiency/acceptance toy studies compare estimates against configured/generated truth and include generated result plots and CSVs. These are candidate methods, not current production estimators. |
| `TRASGO_TESTS_AND_TOOLS/Efficiency and acceptance studies/` | Mostly `MINGO_SIMULATION_VS_SIMULATION`; some scripts may be `MINGO_DATA_VS_DATA` | Unique GeneDigitAna, angular/azimuth, variable-efficiency, and acceptance studies remain. Classify each implementation by its actual input population before promotion. |
| `TRASGO_TESTS_AND_TOOLS/PID/`, `PSD/` | `MINGO_SIMULATION_VS_DATA` candidates | Additional charge-PID and pulse-analysis scripts exist beyond the already indexed examples. They need their data labels and simulation-truth inputs identified before promotion. |
| `TRASGO_TESTS_AND_TOOLS/Slewing correction/` | `MINGO_ANALYSIS` calibration-method review | Historical slewing correction methods may inform calibration, but they are not moved into production calibration without an algorithm and schema review. |
| `TRASGO_TESTS_AND_TOOLS/TimTrack results analysis/` and `Y position studies/` | `MINGO_ANALYSIS` history or simulation comparisons | These contain old tracking diagnostics, position corrections, and test scripts. They are useful for provenance, but should not be mixed into current reconstruction without checking their assumptions and data format. |
| `TRASGO_TESTS_AND_TOOLS/CFD Simulation/` | `OUT_OF_PIPELINE/PHYSICAL_TESTS` | A standalone CFD timing study, separate from the MINGO pipeline. |
| `TRASGO_TESTS_AND_TOOLS/SCIMIN/` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/SCINTILLATOR_POSITION_RECONSTRUCTION/` | Has unique model/checkpoint and training artifacts in addition to the promoted scripts. Inputs, package paths, and checkpoint provenance need review before use. |
| `minitrasgo_madrid/` | Historical pipeline archive | Contains an older Madrid analysis/dataflow and many generated outputs. It is valuable as provenance but is not moved wholesale into the current `MINGO_ANALYSIS` tree. |
| `minitrasgo_RPC2024/` | Historical pipeline and weather-correction archive | Contains another old processing line, a merged data sample, and meteorological NetCDF inputs. Preserve it for provenance; do not treat it as current pipeline code. |
| `pulse-mingo-test/mingo_pulses/MingoFondo.dat`, `MingoCesio.dat` | Out-of-pipeline pulse/electronics test data | Two unique raw pulse files of about 124 MiB each, plus associated test outputs. They were preserved and not copied or deleted. |
| `bot/bot.py` | Operational legacy code, review separately | Unique bot snapshot. Do not execute or promote until its configuration and any embedded credentials are checked. This review did not inspect or print its contents. |

The archive also has exact duplicates among historical snapshots (for example helper scripts repeated under different old dataflow variants). Those copies were retained where each version directory may depend on its local file. This pass removed only exact copies with an established canonical copy elsewhere, plus the superseded pressure script after selecting the later implementation; it did not rewrite old version trees or delete generated results based on names alone.

## Recovery guidance

The archive remains local and excluded from Git because it contains nested repositories, raw scientific data, generated results, and neural-network checkpoints. Before any later cleanup, compare file hashes and check whether scripts refer to their sibling files. Promote one study at a time, copy only the required inputs/results, and keep a provenance note. The curated [legacy study index](LEGACY_STUDIES_REVIVAL.md) gives the current destinations and scientific caveats for the selected recovered scripts.
