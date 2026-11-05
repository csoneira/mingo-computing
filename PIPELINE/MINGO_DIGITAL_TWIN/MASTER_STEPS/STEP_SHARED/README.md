# STEP_SHARED

Purpose:
- Shared utilities for sim-run bookkeeping, metadata, chunked I/O, and geometry helpers.

Key modules:
- `sim_utils.py`:
  - `save_with_metadata`, `iter_input_frames`, `write_chunked_output`.
  - SIM_RUN registry helpers: `register_sim_run`, `find_sim_run`, `resolve_sim_run`.
  - Parameter mesh helpers: `resolve_param_mesh`, `normalize_param_mesh_ids`.
  - Geometry model: `RectBounds`, `StripBounds`, `PlaneReadoutGeometry`.
  - Normalizers: `resolve_active_area_bounds`, `build_readout_geometry`; `get_strip_geometry` is a legacy-compatible array view.
  - `Y_WIDTHS` and `DEFAULT_BOUNDS` remain compatibility aliases only and are not used by the new Step 4 physics path.
- `sim_run_summary.py`:
  - Summarizes SIM_RUN registries and row counts across INTERSTEPS.

Notes:
- Chunked outputs are tracked by `.chunks.json` manifests with embedded metadata.
- Metadata includes `config_hash` and `upstream_hash` to preserve lineage.
