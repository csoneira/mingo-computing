# mingo-computing

legacy
DOCUMENTATION

------------
CONTEXTUAL
- CONFIG
- OPERATIONS

PIPELINE
----------------------------------------------------------------------------------------------------------------------------------------------------------
                                                                                              Uncertainty, systematics and other studies
                                                                                                               ^
                                                                                                               |
                                                                                                               |
                                "sidecar" ---------------------------------------------------->  MINGO_SIMULATION_VS_SIMULATION ---------> correction LUTs
                                    ^                                                                          ^                                 |
                               		|                                                                          |                                 |
------------------------         	|                                                                          |                                 |
-- MINGO_DIGITAL_TWIN -- --> Simulated events --> mingo-like data format ---                           Analyzed simulated events                 |
------------------------                                                    \                         /               |                          |
                                                                             -------------------------                v                          |
                                                                             ---- MINGO_ANALYSIS -----      MINGO_SIMULATION_VS_DATA             |
                                                                             -------------------------                ^                          |
                                                                            /                         \               |                          v
"Real measurement" ----------> hld events ----> mingo-like data format -----                           Analyzed real events -----------> MINGO_CORRECTIONS
         ^                                                                                                     |                                 |
         |                                                                                                     |                                 v
         |                                                                                                     |                        Real corrected data
         |                                                                                                     v
         |                                                                                             MINGO_DATA_VS_DATA
---------|-------------------------------------------------------------------------------------------------------------------------------------------------
         |
    mingo station
    (makes use of
  FOR_MINGO_SYSTEMS)
