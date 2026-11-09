# mingo-computing

Repository for the MINGO detector software, including production processing, simulation, scientific comparisons, and standalone physical studies.

## Repository areas

- `CONTEXTUAL/` contains setup, configuration, and operational tools.
- `PIPELINE/` contains the digital twin, event analysis, and scientific comparisons.
- `OUT_OF_PIPELINE/PHYSICAL_TESTS/` contains standalone studies that do not participate in the production dataflow.
- `DOCUMENTATION/`, `FOR_MINGO_SYSTEMS/`, and `legacy/` contain documentation, station software, and preserved historical material.

## Scientific architecture

The diagram below records the intended flow and the relationship between simulation-derived calibration LUTs and their later use by analysis. The LUT generation studies belong with simulation comparisons; accepted LUTs used by calibration belong with analysis calibration assets.

```text
legacy
DOCUMENTATION

------------
CONTEXTUAL
- CONFIG
- OPERATIONS

OUT_OF_PIPELINE
- PHYSICAL_TESTS

PIPELINE
----------------------------------------------------------------------------------------------------------------------------------------------
                                                                                    Uncertainty, systematics and other studies
                                                                                                     ^
                                                                                                     |
                                                                                                     |
                                "sidecar" ----------------------------------->  MINGO_SIMULATION_VS_SIMULATION ------------> correction LUTs
                                    ^                                               |                ^                              |
                                    |                                               |                |                              |
------------------------            |                                             (LUTs)             |                              |
-- MINGO_DIGITAL_TWIN -- --> Simulated events --> mingo-like format ---             |        Analyzed simulated events              |
------------------------                                               \            v       /               |                       |
                                                                        --------------------                v                       |
                                                                        -- MINGO_ANALYSIS --      MINGO_SIMULATION_VS_DATA          |
                                                                        --------------------                ^                       |
                                                                       /                    \               |                       v
"Real measurement" ----------> hld events ----> mingo-like format -----                      Analyzed real events --------> MINGO_CORRECTIONS
         ^                                                                                           |                              |
         |                                                                                           |                              v
         |                                                                                           |                     Real corrected data
         |                                                                                           v
         |                                                                                   MINGO_DATA_VS_DATA
---------|------------------------------------------------------------------------------------------------------------------------------------
         |
    mingo station
    (makes use of
  FOR_MINGO_SYSTEMS)
```

Simulation-versus-simulation studies may derive candidate calibration LUTs using simulation truth. The analysis calibration area is the destination for LUTs that have been reviewed and selected for use; generated candidates should remain traceable to their producing study.
