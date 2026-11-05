# COMPARE_METHODS_ADVANCED

This directory compares the real-data outputs of:

- `AN_EVEN_EASIER_VARIATION_ADVANCED`
- `ANOTHER_METHOD_ADVANCED`

The initial comparison is focused on the two scale definitions:

- `AN_EVEN_EASIER_VARIATION_ADVANCED`: `1 / eff_reference`
- `ANOTHER_METHOD_ADVANCED`: `lut_scale_factor`

The comparison script reads the already-produced CSV outputs from both methods,
matches rows by `filename_base` plus `file_timestamp_utc`, writes a merged CSV,
and produces comparison plots.

Current outputs:

- `OUTPUTS/FILES/method_comparison_merged.csv`
- `OUTPUTS/FILES/method_comparison_meta.json`
- `OUTPUTS/PLOTS/step1_inverse_eff_reference_vs_lut_scale_factor.png`
- `OUTPUTS/PLOTS/step2_scale_factor_comparison_vs_time.png`

Run:

```bash
cd /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/COMPARE_METHODS_ADVANCED
python3 run_all.py
```

Edit `config.json` if the source output paths or join keys need to change.
