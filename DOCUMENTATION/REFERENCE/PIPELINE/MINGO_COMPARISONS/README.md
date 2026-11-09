# MINGO comparisons

Independent comparison studies live here, classified by the datasets they use:

- `MINGO_DATA_VS_DATA/`: studies of experimental measurements only.
- `MINGO_SIMULATION_VS_DATA/`: studies that compare simulation with experimental data.
- `MINGO_SIMULATION_VS_SIMULATION/`: simulation validation, simulation-to-simulation studies, and reconstruction comparisons against simulation truth.
- `COMMON/STAGE_1_PRODUCTS_TESTS/`: reusable Stage-1 product-analysis tools and configurations. These tools can process either real or simulated products; each dated study/report belongs in the matching comparison category above.

The common Stage-1 tools write generated products beneath the relevant station's `STAGE_1_PRODUCTS_TESTS` data area. They do not put generated reports in this source directory.

## Stage-1 study index

### Experimental data only

- `MINGO_DATA_VS_DATA/DATED_STUDIES/2026-10-29/task2_selftrigger_tt_maps/`
- `MINGO_DATA_VS_DATA/DATED_STUDIES/2026-11-01/tt13_chronological_windows_20261101/`
- `MINGO_DATA_VS_DATA/DATED_STUDIES/2026-11-05/task2_offset_stability/`

### Simulation compared with experimental data

- `MINGO_SIMULATION_VS_DATA/TT13_STUDIES/DATED_STUDIES/2026-11-01/tt13_geometry_corrected_20261101/`
- `MINGO_SIMULATION_VS_DATA/TT13_STUDIES/DATED_STUDIES/2026-11-01/tt13_stage_rank_topology_20261101/`

The Oct 30 and Nov 1 study bundles already in `MINGO_SIMULATION_VS_DATA/TT13_STUDIES/` remain there. The Oct 30 cleaner and storage-recovery records, and the Nov 2 station cleanup record, are operational history and are archived under `CONTEXTUAL/OPERATIONS/OPERATIONS_ARCHIVE/REPOSITORY_MIGRATIONS/STAGE_1_PRODUCTS_TESTS/`.

The `tt13_extended_chronological_20261101` and `tt13_plane_charge_correlations_20261101` directories had no files or tracked contents and are not represented as completed studies here.
