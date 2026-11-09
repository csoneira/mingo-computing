# Task 5 event gates

Task 5 is the final event-processing task in the Stage-1 flow. Its gates are
evaluated in `script_5_fit_to_post.py` and written into the Task-5 output parquet
as `gate_mask` (bit field) and `gate` (pipe-separated labels). They label events
for analysis; they do not reject rows or change the regular processing output.

Edit `config_gates_task_5.yaml` to configure the gates. Each entry has a unique
bit, a description, and a vectorized pandas expression. Gates may overlap; the
bitmask records every gate an event satisfies.

## Strip-topology gates

Task 5 derives temporary topology fields from the 16 calibrated strip
`pN_sM_qsum` columns before evaluating the expressions. A strip is active when
its Q_sum is finite and non-zero, matching the existing pipeline topology
convention. Temporary helper fields are removed before the output parquet is
written; gate labels and bits remain.

- `at_most_1_strip_per_plane`: every plane has zero or one active strip.
- `at_most_2_adjacent_strips_per_plane`: every plane has at most two active
  strips; if two are active, their strip numbers are consecutive.
- `at_most_3_adjacent_strips_per_plane`: every plane has at most three active
  strips, forming one contiguous cluster.
- `at_most_4_adjacent_strips_per_plane`: every plane's active strips form one
  contiguous cluster, including the four-strip case.
- `any_plane_has_nonadjacent_strips`: at least one plane has two or more active
  strips with a gap between them.

The first four are inclusive maximum-multiplicity selections and therefore
nested. The non-adjacent selection is mutually exclusive with those four
adjacent-only selections (apart from the broad `all_events` gate).

## Charge spectra

The Task-5 FINAL plotter includes a 4-plane-by-TT charge spectrum for each new
topology gate. Each page compares gate-passing events (solid) against failing
events (dashed), using the canonical plane `pN_qsum` columns. These plots use
only Task-5 output quantities, so they remain available with
`keep_all_columns_output: false`.

Run the standalone plotter on a Task-5 parquet:

```bash
python final_plots_task_5.py /path/to/postprocessed_file.parquet
```

The parquet path is its only argument. Final plot selection is configured in
`config_final_plots_task_5.yaml` using explicit `-plot` and `-not_plot` alias
lists.
