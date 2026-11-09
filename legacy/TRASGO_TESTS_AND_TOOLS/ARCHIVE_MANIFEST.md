# Archive manifest

Source repository: `csoneira/TRASGO_TESTS_AND_TOOLS`  
Source commit: `01f2bb487dcea8d06417377543d70c91a7a469d9`

The SHA column is the Git blob SHA from the source repository; matching SHAs mean the file content is byte-for-byte identical. Exact duplicate working copies were removed from this legacy folder after canonical copies were placed in the active scientific organization. The blob IDs retain provenance and can be checked against the source repository commit.

| Original source path | Current disposition | Source blob SHA | Concept |
| --- | --- | --- |
| `README.md` | `legacy/TRASGO_TESTS_AND_TOOLS/ORIGINAL_README.md` | `a831ee8c7dc1713ca90f6af0b3f5aa6f51c84894` | Original repository overview |
| `Efficiency and acceptance studies/Geometric_acc/geometric_acceptance.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/EFFICIENCY_AND_ACCEPTANCE/geometric_acceptance.py` | `11032f026919866c238a313bed4137cbe109ced5` | Geometrical acceptance |
| `Efficiency and acceptance studies/eff_simple_toy_model.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/EFFICIENCY_AND_ACCEPTANCE/eff_simple_toy_model.py` | `3e8e2ebb33700f1a51f14409e33b9f7e454e2f7e` | Detector-efficiency toy model |
| `Energy from timing study/energy_from_timing_ar18.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/ENERGY_FROM_TIMING/HISTORICAL/energy_from_timing_ar18.py` | `28a46e6c52c8871ef03208b17410957b90be79d5` | Energy inference from timing |
| `MIPs losing energy in scintillators/muon_electron_sim.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/MIPS_IN_SCINTILLATORS/muon_electron_sim.py` | `f1ff49b2ddcc6078d50c9d0914581c1a5dacb111` | Energy loss in scintillator |
| `MOLIÉRE/moliere.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/MOLIERE_SCATTERING/moliere.py` | `f43097b06588ca3812f4bd29a0ac849b11e64809` | Molière scattering |
| `Magnetic calculations/cutoff_rigidity_calculator.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/GEOMAGNETIC_CUTOFF/cutoff_rigidity_calculator.py` | `26c54dbd03e23ea16dcbe25a65c04cb8b27a64bf` | Geomagnetic cutoff rigidity |
| `Neutrons_tests/pyscript/neutrons.py` | `legacy/TRASGO_TESTS_AND_TOOLS/Neutrons_tests/pyscript/neutrons.py` | `92577311bfc6e429027329454c41e5f0aa303a2f` | Neutron energy/rate analysis; retained but not promoted because it deletes PDFs in its working directory |
| `PID/naive_deltas.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_DATA/PARTICLE_IDENTIFICATION/PID/naive_deltas.py` | `df0de4f2962b757a31526ad87d7ae18b171547d6` | PID exploratory analysis |
| `PSD/pseudoPSA.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_DATA/PARTICLE_IDENTIFICATION/PSD/pseudoPSA.py` | `1674a670598c9b3ea569e65969bc0aa5a380859f` | Pulse-shape / charge analysis |
| `Pressure NMDB study/pressure_CALMA.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_DATA_VS_DATA/EXTERNAL_REFERENCE_STUDIES/OULU_PRESSURE_RATE/pressure_CALMA.py` | `15ebe61c4bcfb80983270e0e160e52fef40fcc99` | Pressure-coefficient study |
| `SCIMIN/position_study_in_scint.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/SCINTILLATOR_POSITION_RECONSTRUCTION/SCIMIN/position_study_in_scint.py` | `57e4024c8d470b189bec0606f28fbf37decacaca` | SiPM position reconstruction |
| `SCIMIN/NN_position_scint.py` | `OUT_OF_PIPELINE/PHYSICAL_TESTS/SCINTILLATOR_POSITION_RECONSTRUCTION/SCIMIN/NN_position_scint.py` | `7ca35f35166ee2d013daba512d1fa2830aa65329` | Neural-network position reconstruction |
| `Waiting time - Mistaken analysis/fixed_waiting.py` | `legacy/TRASGO_TESTS_AND_TOOLS/Waiting time - Mistaken analysis/fixed_waiting.py` | `15b723e030dd9e2739ef23b785d9b19855c3be5a` | Waiting-time / Poisson-process investigation; retained as a known mistaken analysis |
| `Y position studies/strip_width_simulation.py` | `PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/POSITION_RESOLUTION/strip_width_simulation.py` | `abf0f7f6ddd29bac51ce32dae4172707b0f0a76f` | Strip-width and position-resolution simulation |

## Deliberately not archived

The source repository also contains many alternative versions, scratch/test scripts and generated artifacts. They are intentionally omitted because this archive is for recovering concepts, not reproducing the old working directory exactly.

In particular, no `*.npy`, `*.npz`, `*.h5`, model checkpoints, tuner trials, large hidden temporary files, CSV/MAT/raw datasets, or generated outputs are retained.
