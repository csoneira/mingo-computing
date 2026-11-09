# Shared Stage-1 product-analysis tools

This directory contains reusable product-analysis drivers, their configurations, and unit tests. The tools accept experimental station products and simulated MINGO00 products. They are shared analysis utilities, so dated scientific results are stored under the appropriate `MINGO_COMPARISONS` category rather than mixed into this toolkit.

The three drivers are `test_1_plot_calibration_offsets.py`, `test_2_plot_event_distributions.py`, and `test_3_configurable_event_gates.py`. The `config_test_*.yaml` files define their inputs and selections. `calibration_context.py`, `environment_context.py`, `event_gate_streaming.py`, and `mingo00_product_selection.py` provide shared calculations and streaming helpers.

Repository paths are resolved from the checkout via `comparison_paths.py`; no checkout basename is assumed. The tools write generated products beneath the selected station's `STAGE_1_PRODUCTS_TESTS` data area. Do not copy source Parquet data into a report folder unless a test specifically requires a frozen fixture.

See [`DOCUMENTATION/REFERENCE/PIPELINE/MINGO_COMPARISONS/README.md`](../../README.md) for the study index and classification.
