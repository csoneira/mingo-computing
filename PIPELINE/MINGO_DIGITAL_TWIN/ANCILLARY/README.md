# Digital Twin ancillary operations

This directory contains supporting operations and analyses that do not belong
to a specific simulation step.

## Operations

- `interstep_simulation_cleaner.sh` removes the Digital Twin
  `SIMULATION_OUTPUTS/INTERSTEPS` tree. Use it only after confirming those
  intermediate files are no longer needed.
- `restart_simulation_pipeline_totally.sh` archives and resets station and
  simulation outputs. Review its confirmation and archive destination before
  running it.

## Analysis utilities under review

- `CALCULATIONS/calculate_limits.py` reads online-run geometry configurations
  and writes a transverse-limit CSV and plot beside the script.
- `TESTS/TRIGGER_RATE_VALUES/plot_trigger_rate_factors.py` plots decomposed
  simulated trigger-rate factors against detector efficiencies and writes a
  PDF and CSV beside the script.

These analysis utilities have no tracked in-repository callers; their presence
alone does not mean they are run by the simulation pipeline.
