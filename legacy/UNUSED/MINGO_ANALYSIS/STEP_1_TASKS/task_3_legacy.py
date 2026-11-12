"""Archive plotting code retained from the former Task 3 implementation."""

# LEGACY CODE ARCHIVE FOR TASK 3
#
# This file stores code deliberately removed from the active task script.
# It is not imported by the pipeline and is not expected to execute.
# Dependencies and surrounding runtime context may be missing.
# Removed blocks are preserved substantially verbatim for historical reference.

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in fast mode.')

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in debug mode.')

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_F_left_pre_cal = T_side_left_pre_cal_debug
#     T_F_right_pre_cal = T_side_right_pre_cal_debug
#
#     T_B_left_pre_cal = T_side_left_pre_cal_debug
#     T_B_right_pre_cal = T_side_right_pre_cal_debug

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_clip_min = T_clip_min_debug
#     T_clip_max = T_clip_max_debug
#     Q_clip_min = Q_clip_min_debug
#     Q_clip_max = Q_clip_max_debug
#     num_bins = num_bins_debug

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in fast mode.')

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in debug mode.')

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_F_left_pre_cal = T_side_left_pre_cal_debug
#     T_F_right_pre_cal = T_side_right_pre_cal_debug
#
#     T_B_left_pre_cal = T_side_left_pre_cal_debug
#     T_B_right_pre_cal = T_side_right_pre_cal_debug

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_clip_min = T_clip_min_debug
#     T_clip_max = T_clip_max_debug
#     Q_clip_min = Q_clip_min_debug
#     Q_clip_max = Q_clip_max_debug
#     num_bins = num_bins_debug

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in fast mode.')

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in debug mode.')

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_F_left_pre_cal = T_side_left_pre_cal_debug
#     T_F_right_pre_cal = T_side_right_pre_cal_debug
#
#     T_B_left_pre_cal = T_side_left_pre_cal_debug
#     T_B_right_pre_cal = T_side_right_pre_cal_debug

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_clip_min = T_clip_min_debug
#     T_clip_max = T_clip_max_debug
#     Q_clip_min = Q_clip_min_debug
#     Q_clip_max = Q_clip_max_debug
#     num_bins = num_bins_debug

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (filtered_rpc_tsum_vs_qsum_scatter_per_combination)
# ============================================================================
#     if save_plots:
#         name_of_file = "filtered_rpc_tsum_vs_qsum_scatter_per_combination"
#         final_filename = f"{fig_idx_value}_{name_of_file}.png"
#         fig_idx_value += 1
#         save_fig_path = os.path.join(figure_directory, final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (y_position_by_tt_task2_cal)
# ============================================================================
# if task3_plot_enabled("y_position_by_tt_task2_cal"):
#
#     for tt_task2_cal in [ 12, 23, 34, 1234, 123, 234, 124, 13, 14, 24, 134]:
#         mask = working_df['tt_task2_cal'] == tt_task2_cal
#         filtered_df = working_df[mask].copy()  # Work on a copy for fitting
#
#         plt.figure(figsize=(12, 8))
#         for i, plane_id in enumerate(range(1, 5), 1):
#             plt.subplot(2, 2, i)
#             column_name = f'p{plane_id}_ypos'
#             data = filtered_df[column_name]
#
#             plt.hist(data[data != 0], bins=100, histtype='stepfilled', alpha=0.6)
#
#             # Plot the strip boundaries
#             boundaries = strip_boundaries_1_3 if plane_id in [1, 3] else strip_boundaries_2_4
#             for boundary in boundaries:
#                 plt.axvline(boundary, color='red', linestyle='--', linewidth=1)
#
#             # Plot the strip centers
#             centers = y_pos_P1_and_P3 if plane_id in [1, 3] else y_pos_P2_and_P4
#             for center in centers:
#                 plt.axvline(center, color='green', linestyle=':', linewidth=0.5)
#
#             plt.title(f'Y Position Distribution - Plane {plane_id}')
#             plt.xlabel('Y Position (a.u.)')
#             plt.ylabel('Counts')
#             plt.grid(True)
#
#         plt.suptitle(f'Y Position Distribution for tt_task2_cal = {tt_task2_cal}', fontsize=16)
#         plt.tight_layout()
#         if save_plots:
#             name_of_file = f'Y_{tt_task2_cal}'
#             final_filename = f'{fig_idx}_{name_of_file}.png'
#             fig_idx += 1
#             save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#             plot_list.append(save_fig_path)
#             save_plot_figure(save_fig_path, format='png')
#         if show_plots:
#             plt.show()
#         plt.close()

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (strip_variable_pairgrid)
# ============================================================================
# if task3_plot_enabled("strip_variable_pairgrid"):
#
#     for i_plane in range(1, 5):
#
#         fig, axes = plt.subplots(4, 6, figsize=(30, 20))
#         axes = axes.flatten()
#
#         for strip in range(1, 5):
#             # Column names
#             t_sum_col = f'p{i_plane}_s{strip}_tsum'
#             t_dif_col = f'p{i_plane}_s{strip}_tdif'
#             q_sum_col = f'p{i_plane}_s{strip}_qsum'
#             q_dif_col = f'p{i_plane}_s{strip}_qdif'
#
#             # Filter valid rows (non-zero)
#             valid_rows = working_df[[t_sum_col, t_dif_col, q_sum_col, q_dif_col]].replace(0, np.nan).dropna()
#
#             # Extract variables and filter low charge
#             cond = valid_rows[q_sum_col] < charge_per_strip_plot_threshold
#             t_sum  = valid_rows.loc[cond, t_sum_col]
#             t_diff = valid_rows.loc[cond, t_dif_col]
#             q_sum  = valid_rows.loc[cond, q_sum_col]
#             q_diff = valid_rows.loc[cond, q_dif_col]
#
#             base_idx = (strip - 1) * 6
#
#             plot_pairs = [
#                 (t_sum,  t_diff, f'{t_sum_col} vs {t_dif_col}'),
#                 (t_sum,  q_sum,  f'{t_sum_col} vs {q_sum_col}'),
#                 (t_diff, q_sum,  f'{t_dif_col} vs {q_sum_col}'),
#                 (t_sum,  q_diff, f'{t_sum_col} vs {q_dif_col}'),
#                 (t_diff, q_diff, f'{t_dif_col} vs {q_dif_col}'),
#                 (q_sum,  q_diff, f'{q_sum_col} vs {q_dif_col}')
#             ]
#
#             for offset, (x, yv, title) in enumerate(plot_pairs):
#                 ax = axes[base_idx + offset]
#                 ax.hexbin(x, yv, gridsize=50, cmap='turbo')
#                 # ax.scatter(x, yv)
#                 ax.set_title(title)
#
#         plt.tight_layout()
#         plt.subplots_adjust(top=0.92)
#         plt.suptitle(f'Hexbin Plots for All Variable Combinations by strip for plane {i_plane}', fontsize=18)
#
#         if save_plots:
#             name_of_file = f'strip_check_hexbin_combinations_filtered_{i_plane}'
#             final_filename = f'{fig_idx}_{name_of_file}.png'
#             fig_idx += 1
#
#             save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#             plot_list.append(save_fig_path)
#             save_plot_figure(save_fig_path, format='png')
#
#         if show_plots: plt.show()
#         plt.close()

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (self_trigger_strip_variable_pairgrid)
# ============================================================================
# if self_trigger:
#     if task3_plot_enabled("self_trigger_strip_variable_pairgrid"):
#
#         for i_plane in range(1, 5):
#
#             fig, axes = plt.subplots(4, 6, figsize=(30, 20))
#             axes = axes.flatten()
#
#             for strip in range(1, 5):
#                 # Column names
#                 t_sum_col = f'p{i_plane}_s{strip}_tsum'
#                 t_dif_col = f'p{i_plane}_s{strip}_tdif'
#                 q_sum_col = f'p{i_plane}_s{strip}_qsum'
#                 q_dif_col = f'p{i_plane}_s{strip}_qdif'
#
#                 # Filter valid rows (non-zero)
#                 valid_rows = working_st_df[[t_sum_col, t_dif_col, q_sum_col, q_dif_col]].replace(0, np.nan).dropna()
#
#                 # Extract variables and filter low charge
#                 cond = valid_rows[q_sum_col] < 40
#                 t_sum  = valid_rows.loc[cond, t_sum_col]
#                 t_diff = valid_rows.loc[cond, t_dif_col]
#                 q_sum  = valid_rows.loc[cond, q_sum_col]
#                 q_diff = valid_rows.loc[cond, q_dif_col]
#
#                 base_idx = (strip - 1) * 6
#
#                 plot_pairs = [
#                     (t_sum,  t_diff, f'{t_sum_col} vs {t_dif_col}'),
#                     (t_sum,  q_sum,  f'{t_sum_col} vs {q_sum_col}'),
#                     (t_diff, q_sum,  f'{t_dif_col} vs {q_sum_col}'),
#                     (t_sum,  q_diff, f'{t_sum_col} vs {q_dif_col}'),
#                     (t_diff, q_diff, f'{t_dif_col} vs {q_dif_col}'),
#                     (q_sum,  q_diff, f'{q_sum_col} vs {q_dif_col}')
#                 ]
#
#                 for offset, (x, yv, title) in enumerate(plot_pairs):
#                     ax = axes[base_idx + offset]
#                     ax.hexbin(x, yv, gridsize=50, cmap='turbo')
#                     # ax.scatter(x, yv)
#                     ax.set_title(title)
#
#             plt.tight_layout()
#             plt.subplots_adjust(top=0.92)
#             plt.suptitle(f'SELF TRIGGER Hexbin Plots for All Variable Combinations by strip for plane {i_plane}', fontsize=18)
#
#             if save_plots:
#                 name_of_file = f'strip_check_hexbin_combinations_filtered_{i_plane}_ST'
#                 final_filename = f'{fig_idx}_{name_of_file}.png'
#                 fig_idx += 1
#
#                 save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                 plot_list.append(save_fig_path)
#                 save_plot_figure(save_fig_path, format='png')
#
#             if show_plots: plt.show()
#             plt.close()

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (rpc_variables_hexbin)
# ============================================================================
# if task3_plot_enabled("rpc_variables_hexbin"):
#     _plot_task3_rpc_variables_hexbin(
#         working_df,
#         title='Hexbin Plots for All Variable Combinations by Plane',
#         filename_stem='rpc_variables_hexbin_combinations',
#     )

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (rpc_variables_hexbin_low_charge)
# ============================================================================
# if task3_plot_enabled("rpc_variables_hexbin_low_charge"):
#     fig, axes = plt.subplots(4, 10, figsize=(40, 20))  # 10 combinations per plane
#     axes = axes.flatten()
#
#     for i_plane in range(1, 5):
#         # Column names
#         t_sum_col = f'p{i_plane}_tsum'
#         t_dif_col = f'p{i_plane}_tdif'
#         q_sum_col = f'p{i_plane}_qsum'
#         q_dif_col = f'p{i_plane}_qdif'
#         y_col = f'p{i_plane}_ypos'
#
#         # Filter valid rows (non-zero)
#         valid_rows = working_df[[t_sum_col, t_dif_col, q_sum_col, q_dif_col, y_col]].replace(0, np.nan).dropna()
#
#         # Extract variables and filter low charge
#         cond = valid_rows[q_sum_col] < charge_per_plane_plot_threshold / 4
#         t_sum  = valid_rows.loc[cond, t_sum_col]
#         t_diff = valid_rows.loc[cond, t_dif_col]
#         q_sum  = valid_rows.loc[cond, q_sum_col]
#         q_diff = valid_rows.loc[cond, q_dif_col]
#         y      = valid_rows.loc[cond, y_col]
#
#         base_idx = (i_plane - 1) * 10  # 10 plots per plane
#
#         plot_pairs = [
#             (t_sum,  t_diff, f'{t_sum_col} vs {t_dif_col}'),
#             (t_sum,  q_sum,  f'{t_sum_col} vs {q_sum_col}'),
#             (t_sum,  y,      f'{t_sum_col} vs {y_col}'),
#             (t_diff, q_sum,  f'{t_dif_col} vs {q_sum_col}'),
#             (t_diff, y,      f'{t_dif_col} vs {y_col}'),
#             (q_sum,  y,      f'{q_sum_col} vs {y_col}'),
#             (t_sum,  q_diff, f'{t_sum_col} vs {q_dif_col}'),
#             (t_diff, q_diff, f'{t_dif_col} vs {q_dif_col}'),
#             (q_diff, y,      f'{q_dif_col} vs {y_col}'),
#             (q_sum,  q_diff, f'{q_sum_col} vs {q_dif_col}')
#         ]
#
#         for offset, (x, yv, title) in enumerate(plot_pairs):
#             ax = axes[base_idx + offset]
#             _task3_plot_quantile_hexbin(ax, x, yv, title, gridsize=50, cmap="turbo")
#
#     plt.tight_layout()
#     plt.subplots_adjust(top=0.92)
#     plt.suptitle('Hexbin Plots for All Variable Combinations by Plane', fontsize=18)
#
#     if save_plots:
#         name_of_file = 'rpc_variables_hexbin_combinations'
#         final_filename = f'{fig_idx}_{name_of_file}.png'
#         fig_idx += 1
#
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format='png')
#
#     if show_plots: plt.show()
#     plt.close()

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (filtered_rpc_tsum_vs_qsum_scatter)
# ============================================================================
# if task3_plot_enabled("filtered_rpc_tsum_vs_qsum_scatter"):
#     fig_idx = plot_task3_filtered_rpc_tsum_vs_qsum(
#         working_df,
#         fig_idx,
#         plot_kind="scatter",
#         charge_threshold=150.0,
#         figure_directory=base_directories["figure_directory"],
#         show_plots=show_plots,
#         save_plots=save_plots,
#         plot_list=plot_list,
#     )

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (filtered_rpc_tsum_vs_qsum_scatter_per_combination)
# ============================================================================
# if task3_plot_enabled("filtered_rpc_tsum_vs_qsum_scatter_per_combination"):
#     fig_idx = plot_task3_filtered_rpc_tsum_vs_qsum_per_combination(
#         working_df,
#         fig_idx,
#         charge_threshold=150.0,
#         figure_directory=base_directories["figure_directory"],
#         show_plots=show_plots,
#         save_plots=save_plots,
#         plot_list=plot_list,
#         basename=basename_no_ext,
#     )

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (filtered_rpc_tsum_vs_qsum_hexbin)
# ============================================================================
# if task3_plot_enabled("filtered_rpc_tsum_vs_qsum_hexbin"):
#     fig_idx = plot_task3_filtered_rpc_tsum_vs_qsum(
#         working_df,
#         fig_idx,
#         plot_kind="hexbin",
#         charge_threshold=150.0,
#         figure_directory=base_directories["figure_directory"],
#         show_plots=show_plots,
#         save_plots=save_plots,
#         plot_list=plot_list,
#     )

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (filtered_rpc_variables_hexbin)
# ============================================================================
# if task3_plot_enabled("filtered_rpc_variables_hexbin"):
#
#     fig, axes = plt.subplots(4, 10, figsize=(40, 20))  # 10 combinations per plane
#     axes_grid = np.asarray(axes)
#     plot_pairs_by_plane: dict[int, list[tuple[pd.Series, pd.Series, str, str, str]]] = {}
#     shared_axis_values: list[dict[str, list[np.ndarray]]] = [
#         {"x": [], "y": []}
#         for _ in range(10)
#     ]
#     configured_axis_limits = {
#         "t_sum": (float(T_sum_RPC_left), float(T_sum_RPC_right)),
#         "t_diff": (float(T_dif_RPC_left), float(T_dif_RPC_right)),
#         "q_sum": (float(Q_RPC_left), float(Q_RPC_right)),
#         "q_diff": (float(Q_dif_RPC_left), float(Q_dif_RPC_right)),
#         "y": (float(Y_RPC_left), float(Y_RPC_right)),
#     }
#
#     def _valid_configured_axis_limit(variable_key: str) -> tuple[float, float] | None:
#         limits = configured_axis_limits.get(variable_key)
#         if limits is None:
#             return None
#         left, right = limits
#         if not np.isfinite(left) or not np.isfinite(right) or left >= right:
#             return None
#         return left, right
#
#     def _filter_hexbin_pair_to_configured_limits(
#         x: pd.Series,
#         yv: pd.Series,
#         x_key: str,
#         y_key: str,
#     ) -> tuple[pd.Series, pd.Series]:
#         x_values = pd.to_numeric(x, errors="coerce")
#         y_values = pd.to_numeric(yv, errors="coerce")
#         mask = np.isfinite(x_values) & np.isfinite(y_values)
#         x_limit = _valid_configured_axis_limit(x_key)
#         y_limit = _valid_configured_axis_limit(y_key)
#         if x_limit is not None:
#             mask &= (x_values >= x_limit[0]) & (x_values <= x_limit[1])
#         if y_limit is not None:
#             mask &= (y_values >= y_limit[0]) & (y_values <= y_limit[1])
#         return x_values.loc[mask], y_values.loc[mask]
#
#     for i_plane in range(1, 5):
#         # Column names
#         t_sum_col = f'p{i_plane}_tsum'
#         t_dif_col = f'p{i_plane}_tdif'
#         q_sum_col = f'p{i_plane}_qsum'
#         q_dif_col = f'p{i_plane}_qdif'
#         y_col = f'p{i_plane}_ypos'
#
#         # Filter valid rows (non-zero)
#         valid_rows = working_df[[t_sum_col, t_dif_col, q_sum_col, q_dif_col, y_col]].replace(0, np.nan).dropna()
#
#         # Extract variables and filter low charge
#         cond = valid_rows[q_sum_col] < 150
#         t_sum  = valid_rows.loc[cond, t_sum_col]
#         t_diff = valid_rows.loc[cond, t_dif_col]
#         q_sum  = valid_rows.loc[cond, q_sum_col]
#         q_diff = valid_rows.loc[cond, q_dif_col]
#         y      = valid_rows.loc[cond, y_col]
#
#         plot_pairs = [
#             (t_sum,  t_diff, f'{t_sum_col} vs {t_dif_col}', "t_sum", "t_diff"),
#             (t_sum,  q_sum,  f'{t_sum_col} vs {q_sum_col}', "t_sum", "q_sum"),
#             (t_sum,  y,      f'{t_sum_col} vs {y_col}', "t_sum", "y"),
#             (t_diff, q_sum,  f'{t_dif_col} vs {q_sum_col}', "t_diff", "q_sum"),
#             (t_diff, y,      f'{t_dif_col} vs {y_col}', "t_diff", "y"),
#             (q_sum,  y,      f'{q_sum_col} vs {y_col}', "q_sum", "y"),
#             (t_sum,  q_diff, f'{t_sum_col} vs {q_dif_col}', "t_sum", "q_diff"),
#             (t_diff, q_diff, f'{t_dif_col} vs {q_dif_col}', "t_diff", "q_diff"),
#             (q_diff, y,      f'{q_dif_col} vs {y_col}', "q_diff", "y"),
#             (q_sum,  q_diff, f'{q_sum_col} vs {q_dif_col}', "q_sum", "q_diff")
#         ]
#
#         filtered_plot_pairs: list[tuple[pd.Series, pd.Series, str, str, str]] = []
#         for offset, (x, yv, title, x_key, y_key) in enumerate(plot_pairs):
#             x, yv = _filter_hexbin_pair_to_configured_limits(x, yv, x_key, y_key)
#             filtered_plot_pairs.append((x, yv, title, x_key, y_key))
#             x_values = pd.to_numeric(x, errors="coerce").to_numpy(dtype=float)
#             y_values = pd.to_numeric(yv, errors="coerce").to_numpy(dtype=float)
#             finite = np.isfinite(x_values) & np.isfinite(y_values)
#             if np.any(finite):
#                 shared_axis_values[offset]["x"].append(x_values[finite])
#                 shared_axis_values[offset]["y"].append(y_values[finite])
#         plot_pairs_by_plane[i_plane] = filtered_plot_pairs
#
#     def _shared_hexbin_axis_limit(value_chunks: list[np.ndarray]) -> tuple[float, float] | None:
#         if not value_chunks:
#             return None
#         values = np.concatenate(value_chunks)
#         values = values[np.isfinite(values)]
#         if values.size == 0:
#             return None
#         left = float(np.nanpercentile(values, 1.0))
#         right = float(np.nanpercentile(values, 99.0))
#         if not np.isfinite(left) or not np.isfinite(right) or left >= right:
#             left = float(np.nanmin(values))
#             right = float(np.nanmax(values))
#         if not np.isfinite(left) or not np.isfinite(right):
#             return None
#         if left == right:
#             padding = 0.5 if left == 0 else 0.05 * abs(left)
#             return left - padding, right + padding
#         padding = 0.03 * (right - left)
#         return left - padding, right + padding
#
#     shared_axis_limits: list[tuple[tuple[float, float] | None, tuple[float, float] | None]] = []
#     for offset, axis_values in enumerate(shared_axis_values):
#         x_limit = _shared_hexbin_axis_limit(axis_values["x"])
#         y_limit = _shared_hexbin_axis_limit(axis_values["y"])
#         shared_axis_limits.append((x_limit, y_limit))
#
#     for i_plane in range(1, 5):
#         plot_pairs = plot_pairs_by_plane.get(i_plane, [])
#         for offset, (x, yv, title, _x_key, _y_key) in enumerate(plot_pairs):
#             ax = axes_grid[i_plane - 1, offset]
#             ax.set_facecolor(plt.get_cmap("turbo")(0.0))
#             _task3_plot_quantile_hexbin(ax, x, yv, title, gridsize=50, cmap="turbo")
#             xlim, ylim = shared_axis_limits[offset]
#             if xlim is not None:
#                 ax.set_xlim(xlim)
#             if ylim is not None:
#                 ax.set_ylim(ylim)
#
#     plt.tight_layout()
#     plt.subplots_adjust(top=0.92)
#     plt.suptitle('Hexbin Plots for All Variable Combinations by Plane, filtered', fontsize=18)
#     if save_plots:
#         name_of_file = 'rpc_variables_hexbin_combinations_filtered'
#         final_filename = f'{fig_idx}_{name_of_file}.png'
#         fig_idx += 1
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format='png')
#     if show_plots: plt.show()
#     plt.close()

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (rpc_variables_hexbin_per_plane_combination)
# ============================================================================
# if task3_plot_enabled("rpc_variables_hexbin_per_plane_combination"):
#     tt_values = pd.to_numeric(working_df["tt_task3_list"], errors="coerce")
#     generated_per_tt_figures = 0
#     for tt_value in sorted(tt_values[np.isfinite(tt_values)].unique()):
#         tt_mask = tt_values.eq(tt_value)
#         if not bool(tt_mask.any()):
#             continue
#         tt_label = normalize_tt_label(tt_value)
#         title = f"tt_task3_list = {tt_label}"
#         if joined_input_records:
#             title = f"{title} (files processed={len(joined_input_records)})"
#         _plot_task3_rpc_variables_hexbin(
#             working_df.loc[tt_mask],
#             title=title,
#             filename_stem=f'rpc_variables_hexbin_per_plane_combination_tt_{tt_label}',
#         )
#         generated_per_tt_figures += 1
#     print(
#         "rpc_variables_hexbin_per_plane_combination: "
#         f"generated {generated_per_tt_figures} figures."
#     )

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (all_events_charge_threshold_population, charge_asymmetry_vs_threshold, charge_by_strip_multiplicity_adj, charge_by_strip_multiplicity_dis, efficiency_anatomy_by_charge_band, fourplane_weakest_charge, fourplane_weakest_plane_identity, full_topology_class_fraction, full_topology_exact_retention, full_topology_threshold_retention, interplane_timing_correlation, multiplicity_charge_landscape, plane_charge_fraction_vs_total_charge_threshold_scan, source_tt_task3_list_charge_threshold_population, streamer_charge_histograms, streamer_contagion_matrix, streamer_efficiency_comparison, streamer_multiplicity, streamer_prevalence_by_plane, tsum_coincidence_window_histograms, tsum_coincidence_window_vs_threshold, tt_task3_list_empirical_efficiency_vs_threshold, tt_task3_list_minimum_charge_distributions, tt_task3_list_qsum_pairgrid, tt_task3_list_retention_curves, tt_task3_list_transition_matrices)
# ============================================================================
# if "tt_task3_list" in working_df.columns and task3_any_plot_enabled(
#     "tt_task3_list_qsum_pairgrid",
#     "all_events_charge_threshold_population",
#     "source_tt_task3_list_charge_threshold_population",
#     "tt_task3_list_transition_matrices",
#     "tt_task3_list_retention_curves",
#     "tt_task3_list_minimum_charge_distributions",
#     "tt_task3_list_empirical_efficiency_vs_threshold",
#     "charge_asymmetry_vs_threshold",
#     "interplane_timing_correlation",
#     "multiplicity_charge_landscape",
#     "streamer_charge_histograms",
#     "streamer_prevalence_by_plane",
#     "streamer_multiplicity",
#     "streamer_contagion_matrix",
#     "streamer_efficiency_comparison",
#     "fourplane_weakest_charge",
#     "fourplane_weakest_plane_identity",
#     "efficiency_anatomy_by_charge_band",
#     "charge_by_strip_multiplicity_adj",
#     "charge_by_strip_multiplicity_dis",
# ):
#     q_sum_final_cols = [
#         f"p{i_plane}_qsum" for i_plane in range(1, 5) if f"p{i_plane}_qsum" in working_df.columns
#     ]
#     if q_sum_final_cols:
#         tt_task3_list_charge_limit_effective_runtime = tt_task3_list_charge_limit_effective
#         if (
#             task3_streamer_threshold is not None
#             and np.isfinite(task3_streamer_threshold)
#             and task3_streamer_threshold > 0
#         ):
#             tt_task3_list_charge_limit_effective_runtime = float(task3_streamer_threshold)
#             print(
#                 f"Task 3: using {task3_streamer_threshold_source}-selected streamer threshold "
#                 f"as charge-threshold cap: {float(task3_streamer_threshold):.3g}"
#             )
#
#         if tt_task3_list_charge_threshold_mode in {"auto", "quantile"}:
#             positive_charge_arrays: list[np.ndarray] = []
#             for col_name in q_sum_final_cols:
#                 q_vals = pd.to_numeric(working_df[col_name], errors="coerce").to_numpy(dtype=float)
#                 finite_positive = q_vals[np.isfinite(q_vals) & (q_vals > 0)]
#                 if tt_task3_list_charge_limit_effective_runtime is not None:
#                     finite_positive = finite_positive[finite_positive <= float(tt_task3_list_charge_limit_effective_runtime)]
#                 if finite_positive.size:
#                     positive_charge_arrays.append(finite_positive)
#
#             if positive_charge_arrays:
#                 auto_qmax = float(
#                     np.nanpercentile(
#                         np.concatenate(positive_charge_arrays),
#                         tt_task3_list_charge_threshold_auto_quantile,
#                     )
#                 )
#                 if np.isfinite(auto_qmax) and auto_qmax > 0:
#                     if tt_task3_list_charge_limit_effective_runtime is not None:
#                         auto_qmax = min(auto_qmax, float(tt_task3_list_charge_limit_effective_runtime))
#                     auto_thresholds = np.linspace(0.0, auto_qmax, tt_task3_list_charge_threshold_auto_steps)
#                     auto_thresholds = np.unique(np.round(auto_thresholds, 6))
#                     tt_task3_list_charge_thresholds = [float(v) for v in auto_thresholds if np.isfinite(v) and v >= 0]
#                     if len(tt_task3_list_charge_thresholds) >= 2:
#                         print(
#                             "Task 3: auto tt_task3_list_charge_thresholds generated from 0 to "
#                             f"Q{tt_task3_list_charge_threshold_auto_quantile:g} ({auto_qmax:.3g}) with "
#                             f"{len(tt_task3_list_charge_thresholds)} steps."
#                         )
#                     else:
#                         print(
#                             "Warning: auto threshold generation produced too few values; "
#                             "falling back to manual tt_task3_list_charge_thresholds."
#                         )
#                         tt_task3_list_charge_thresholds = list(manual_tt_task3_list_charge_thresholds)
#                 else:
#                     print(
#                         "Warning: auto threshold quantile is invalid/non-positive; "
#                         "using manual tt_task3_list_charge_thresholds."
#                     )
#                     tt_task3_list_charge_thresholds = list(manual_tt_task3_list_charge_thresholds)
#             else:
#                 print(
#                     "Warning: no positive Q_sum_final values found for auto threshold generation; "
#                     "using manual tt_task3_list_charge_thresholds."
#                 )
#                 tt_task3_list_charge_thresholds = list(manual_tt_task3_list_charge_thresholds)
#
#         tt_task3_list_charge_thresholds = sorted({float(v) for v in tt_task3_list_charge_thresholds if np.isfinite(v) and v >= 0})
#         if tt_task3_list_charge_limit_effective_runtime is not None:
#             cap_val = float(tt_task3_list_charge_limit_effective_runtime)
#             tt_task3_list_charge_thresholds = [thr for thr in tt_task3_list_charge_thresholds if thr <= cap_val]
#             if 0.0 not in tt_task3_list_charge_thresholds:
#                 tt_task3_list_charge_thresholds.insert(0, 0.0)
#             if len(tt_task3_list_charge_thresholds) < 2 and cap_val > 0:
#                 tt_task3_list_charge_thresholds = [0.0, cap_val]
#         if not tt_task3_list_charge_thresholds:
#             tt_task3_list_charge_thresholds = [0.0, 5.0, 10.0, 20.0, 50.0]
#
#         tt_numeric = pd.to_numeric(working_df["tt_task3_list"], errors="coerce").fillna(0).astype(int)
#         present_tt_values = set(tt_numeric.unique().tolist())
#         ordered_tt_values = [
#             tt_value for tt_value in TT_COUNT_VALUES if tt_value >= 10 and tt_value in present_tt_values
#         ]
#         ordered_tt_values.extend(
#             sorted(tt_value for tt_value in present_tt_values if tt_value >= 10 and tt_value not in TT_COUNT_VALUES)
#         )
#
#         if task3_plot_enabled("tt_task3_list_qsum_pairgrid"):
#             if tt_task3_list_qsum_pair_plot_charge_cap is not None:
#                 qsum_plot_max = float(tt_task3_list_qsum_pair_plot_charge_cap)
#             else:
#                 positive_charge_arrays = []
#                 for col_name in q_sum_final_cols:
#                     charge_vals = pd.to_numeric(working_df[col_name], errors="coerce").to_numpy(dtype=float)
#                     finite_positive = charge_vals[np.isfinite(charge_vals) & (charge_vals > 0)]
#                     if tt_task3_list_charge_limit_effective_runtime is not None:
#                         finite_positive = finite_positive[finite_positive <= float(tt_task3_list_charge_limit_effective_runtime)]
#                     if finite_positive.size:
#                         positive_charge_arrays.append(finite_positive)
#
#                 if positive_charge_arrays:
#                     qsum_plot_max = float(np.nanpercentile(np.concatenate(positive_charge_arrays), 99.5))
#                     if not np.isfinite(qsum_plot_max) or qsum_plot_max <= 0:
#                         qsum_plot_max = 10.0
#                 else:
#                     qsum_plot_max = 10.0
#                 qsum_plot_max = float(max(10.0, math.ceil(qsum_plot_max / 10.0) * 10.0))
#                 if tt_task3_list_charge_limit_effective_runtime is not None:
#                     qsum_plot_max = float(min(qsum_plot_max, float(tt_task3_list_charge_limit_effective_runtime)))
#
#             for tt_value in ordered_tt_values:
#                 tt_subset = working_df.loc[tt_numeric == tt_value, q_sum_final_cols]
#                 if tt_subset.empty:
#                     continue
#
#                 fig, axes = plt.subplots(4, 4, figsize=(14, 14), squeeze=False)
#                 last_hexbin = None
#
#                 for i_plane in range(1, 5):
#                     y_col = f"p{i_plane}_qsum"
#                     for j_plane in range(1, 5):
#                         x_col = f"p{j_plane}_qsum"
#                         ax = axes[i_plane - 1, j_plane - 1]
#
#                         if j_plane > i_plane:
#                             ax.set_axis_off()
#                             continue
#
#                         if x_col not in tt_subset.columns or y_col not in tt_subset.columns:
#                             ax.set_axis_off()
#                             continue
#
#                         x_vals = pd.to_numeric(tt_subset[x_col], errors="coerce").to_numpy(dtype=float)
#                         y_vals = pd.to_numeric(tt_subset[y_col], errors="coerce").to_numpy(dtype=float)
#
#                         if i_plane == j_plane:
#                             diag_valid = np.isfinite(x_vals) & (x_vals > 0)
#                             if tt_task3_list_qsum_pair_plot_charge_cap is not None:
#                                 diag_valid &= x_vals < tt_task3_list_qsum_pair_plot_charge_cap
#                             diag_vals = x_vals[diag_valid]
#                             if diag_vals.size:
#                                 ax.hist(
#                                     diag_vals,
#                                     bins=50,
#                                     range=(0, qsum_plot_max),
#                                     color="tab:blue",
#                                     alpha=0.75,
#                                 )
#                             else:
#                                 ax.text(
#                                     0.5,
#                                     0.5,
#                                     "No positive charge",
#                                     ha="center",
#                                     va="center",
#                                     transform=ax.transAxes,
#                                 )
#                             ax.set_xlim(0, qsum_plot_max)
#                             ax.set_title(f"P{i_plane}", fontsize=12)
#                             ax.grid(True, alpha=0.2)
#                             if j_plane == 1:
#                                 ax.set_ylabel("Count")
#                             if i_plane == 4:
#                                 ax.set_xlabel("Q_sum_final")
#                             continue
#
#                         valid = (
#                             np.isfinite(x_vals)
#                             & np.isfinite(y_vals)
#                             & (x_vals > 0)
#                             & (y_vals > 0)
#                         )
#                         if tt_task3_list_qsum_pair_plot_charge_cap is not None:
#                             valid &= (x_vals < tt_task3_list_qsum_pair_plot_charge_cap)
#                             valid &= (y_vals < tt_task3_list_qsum_pair_plot_charge_cap)
#                         if np.any(valid):
#                             if tt_task3_list_qsum_pair_plot_mode == "hexbin":
#                                 last_hexbin = ax.hexbin(
#                                     x_vals[valid],
#                                     y_vals[valid],
#                                     gridsize=40,
#                                     extent=(0, qsum_plot_max, 0, qsum_plot_max),
#                                     mincnt=1,
#                                     cmap="turbo",
#                                 )
#                                 diag_color = "white"
#                             else:
#                                 ax.scatter(
#                                     x_vals[valid],
#                                     y_vals[valid],
#                                     s=2,
#                                     alpha=0.25,
#                                     color="tab:blue",
#                                     linewidths=0,
#                                     rasterized=True,
#                                 )
#                                 diag_color = "black"
#                             ax.plot(
#                                 [0, qsum_plot_max],
#                                 [0, qsum_plot_max],
#                                 linestyle="--",
#                                 linewidth=0.8,
#                                 color=diag_color,
#                                 alpha=0.7,
#                             )
#                         else:
#                             ax.text(
#                                 0.5,
#                                 0.5,
#                                 "No overlap",
#                                 ha="center",
#                                 va="center",
#                                 transform=ax.transAxes,
#                             )
#
#                         ax.set_xlim(0, qsum_plot_max)
#                         ax.set_ylim(0, qsum_plot_max)
#                         ax.grid(True, alpha=0.15)
#                         if i_plane == 4:
#                             ax.set_xlabel(f"P{j_plane} Q_sum_final")
#                         if j_plane == 1:
#                             ax.set_ylabel(f"P{i_plane} Q_sum_final")
#
#                 cap_label = (
#                     f", Q < {tt_task3_list_qsum_pair_plot_charge_cap:g}"
#                     if tt_task3_list_qsum_pair_plot_charge_cap is not None
#                     else ""
#                 )
#                 fig.suptitle(
#                     "Task 3 Q_sum lower-triangular plot for "
#                     f"tt_task3_list {tt_value} ({tt_task3_list_qsum_pair_plot_mode}, N={len(tt_subset)}{cap_label})",
#                     fontsize=16,
#                 )
#                 if tt_task3_list_qsum_pair_plot_mode == "hexbin" and last_hexbin is not None:
#                     fig.subplots_adjust(left=0.08, right=0.89, bottom=0.07, top=0.93, wspace=0.28, hspace=0.28)
#                     cbar_ax = fig.add_axes([0.91, 0.12, 0.018, 0.74])
#                     fig.colorbar(last_hexbin, cax=cbar_ax, label="Counts")
#                 else:
#                     fig.subplots_adjust(left=0.08, right=0.95, bottom=0.07, top=0.93, wspace=0.28, hspace=0.28)
#
#                 if save_plots:
#                     mode_slug = tt_task3_list_qsum_pair_plot_mode
#                     cap_slug = (
#                         f"_qcap_{tt_task3_list_qsum_pair_plot_charge_cap:g}".replace(".", "p")
#                         if tt_task3_list_qsum_pair_plot_charge_cap is not None
#                         else ""
#                     )
#                     name_of_file = f"tt_task3_list_{tt_value}_qsum_lower_triangular_{mode_slug}{cap_slug}.png"
#                     final_filename = f"{fig_idx}_{name_of_file}"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig)
#
#         threshold_labels = [f"Q > {threshold:g}" for threshold in tt_task3_list_charge_thresholds]
#         threshold_tt_by_label: dict[str, pd.Series] = {}
#         if task3_any_plot_enabled(
#             "all_events_charge_threshold_population",
#             "tt_task3_list_transition_matrices",
#             "tt_task3_list_empirical_efficiency_vs_threshold",
#             "full_topology_threshold_retention",
#             "tsum_coincidence_window_histograms",
#             "tsum_coincidence_window_vs_threshold",
#         ):
#             for threshold, threshold_label in zip(tt_task3_list_charge_thresholds, threshold_labels):
#                 threshold_tt_by_label[threshold_label] = compute_qsum_threshold_tt(
#                     working_df[q_sum_final_cols], threshold
#                 )
#
#         threshold_full_patterns_by_label: dict[str, pd.Series] = {}
#         if task3_any_plot_enabled(
#             "full_topology_threshold_retention",
#             "full_topology_exact_retention",
#             "full_topology_class_fraction",
#         ):
#             for threshold, threshold_label in zip(tt_task3_list_charge_thresholds, threshold_labels):
#                 threshold_full_patterns_by_label[threshold_label] = compute_qsum_threshold_full_strip_patterns(
#                     working_df,
#                     threshold,
#                 )
#
#         threshold_tsum_window_by_label: dict[str, pd.Series] = {}
#         threshold_tsum_active_counts_by_label: dict[str, pd.Series] = {}
#         if task3_any_plot_enabled(
#             "tsum_coincidence_window_histograms",
#             "tsum_coincidence_window_vs_threshold",
#         ):
#             for threshold, threshold_label in zip(tt_task3_list_charge_thresholds, threshold_labels):
#                 window_series, active_counts = compute_qsum_threshold_tsum_window(working_df, threshold)
#                 threshold_tsum_window_by_label[threshold_label] = window_series
#                 threshold_tsum_active_counts_by_label[threshold_label] = active_counts
#
#         if task3_plot_enabled("all_events_charge_threshold_population"):
#             overall_threshold_counts = {
#                 threshold_label: threshold_tt_by_label[threshold_label].value_counts()
#                 for threshold_label in threshold_labels
#             }
#             overall_counts_df = pd.DataFrame(overall_threshold_counts).fillna(0).astype(int)
#             overall_row_order = [
#                 tt_value for tt_value in TT_COUNT_VALUES if tt_value in overall_counts_df.index
#             ]
#             overall_row_order.extend(
#                 sorted(tt_value for tt_value in overall_counts_df.index if tt_value not in TT_COUNT_VALUES)
#             )
#             if overall_row_order:
#                 overall_counts_df = overall_counts_df.reindex(index=overall_row_order, fill_value=0)
#                 overall_counts_df = overall_counts_df.loc[overall_counts_df.sum(axis=1) > 0]
#                 fig_idx = plot_population_table(
#                     overall_counts_df,
#                     title=(
#                         "All events: charge-filtered plane combinations "
#                         "(all planes in row satisfy Q > threshold)"
#                     ),
#                     filename_suffix="all_events_charge_threshold_combo_population",
#                     fig_idx=fig_idx,
#                     base_dir=base_directories["figure_directory"],
#                     show_plots=show_plots,
#                     save_plots=save_plots,
#                     plot_list=plot_list,
#                 )
#
#         if task3_plot_enabled("source_tt_task3_list_charge_threshold_population"):
#             for source_tt in ordered_tt_values:
#                 source_subset = working_df.loc[tt_numeric == source_tt, q_sum_final_cols]
#                 if source_subset.empty:
#                     continue
#
#                 source_threshold_counts: dict[str, pd.Series] = {}
#                 for threshold, threshold_label in zip(tt_task3_list_charge_thresholds, threshold_labels):
#                     threshold_tt = compute_qsum_threshold_tt(source_subset, threshold)
#                     source_threshold_counts[threshold_label] = threshold_tt.value_counts()
#
#                 source_counts_df = pd.DataFrame(source_threshold_counts).fillna(0).astype(int)
#                 source_row_order = [
#                     tt_value for tt_value in TT_COUNT_VALUES if tt_value in source_counts_df.index
#                 ]
#                 source_row_order.extend(
#                     sorted(tt_value for tt_value in source_counts_df.index if tt_value not in TT_COUNT_VALUES)
#                 )
#                 if not source_row_order:
#                     continue
#                 source_counts_df = source_counts_df.reindex(index=source_row_order, fill_value=0)
#                 source_counts_df = source_counts_df.loc[source_counts_df.sum(axis=1) > 0]
#                 if source_counts_df.empty:
#                     continue
#
#                 fig_idx = plot_population_table(
#                     source_counts_df,
#                     title=(
#                         f"Source tt_task3_list {source_tt}: charge-filtered plane combinations "
#                         f"(N={len(source_subset)})"
#                     ),
#                     filename_suffix=f"tt_task3_list_{source_tt}_charge_threshold_combo_population",
#                     fig_idx=fig_idx,
#                     base_dir=base_directories["figure_directory"],
#                     show_plots=show_plots,
#                     save_plots=save_plots,
#                     plot_list=plot_list,
#                 )
#
#         if task3_plot_enabled("tt_task3_list_transition_matrices"):
#             transition_row_order = ordered_tt_values
#             transition_col_order = list(TT_COUNT_VALUES)
#             for threshold_label in threshold_labels:
#                 threshold_tt = threshold_tt_by_label[threshold_label]
#                 transition_counts = pd.crosstab(tt_numeric, threshold_tt)
#                 transition_counts = transition_counts.reindex(
#                     index=transition_row_order,
#                     columns=transition_col_order,
#                     fill_value=0,
#                 )
#                 transition_counts = transition_counts.loc[:, transition_counts.sum(axis=0) > 0]
#                 transition_counts = transition_counts.loc[transition_counts.sum(axis=1) > 0]
#                 if transition_counts.empty:
#                     continue
#
#                 threshold_value = threshold_label.replace("Q > ", "")
#                 fig_idx = plot_population_table(
#                     transition_counts,
#                     title=f"Source tt_task3_list to charge-filtered combination at {threshold_label}",
#                     filename_suffix=f"tt_task3_list_transition_matrix_qgt_{threshold_value}".replace(".", "p"),
#                     fig_idx=fig_idx,
#                     base_dir=base_directories["figure_directory"],
#                     row_label="Source tt_task3_list",
#                     col_label="Charge-filtered combination",
#                     show_plots=show_plots,
#                     save_plots=save_plots,
#                     plot_list=plot_list,
#                 )
#
#         min_charge_by_source_tt: dict[int, pd.Series] = {}
#         if task3_any_plot_enabled(
#             "tt_task3_list_retention_curves",
#             "tt_task3_list_minimum_charge_distributions",
#         ):
#             for source_tt in ordered_tt_values:
#                 source_mask = tt_numeric == source_tt
#                 source_subset = working_df.loc[source_mask, q_sum_final_cols]
#                 if source_subset.empty:
#                     continue
#                 min_charge_by_source_tt[source_tt] = compute_source_tt_min_charge(source_subset, source_tt)
#
#         if task3_plot_enabled("tt_task3_list_retention_curves") and min_charge_by_source_tt:
#             fig, ax = plt.subplots(figsize=(11, 6.5))
#             cmap = plt.get_cmap("tab20")
#             for idx, source_tt in enumerate(ordered_tt_values):
#                 min_charge = min_charge_by_source_tt.get(source_tt)
#                 if min_charge is None:
#                     continue
#                 min_charge_vals = pd.to_numeric(min_charge, errors="coerce").to_numpy(dtype=float)
#                 baseline_mask = np.isfinite(min_charge_vals) & (min_charge_vals > 0)
#                 baseline_count = int(baseline_mask.sum())
#                 if baseline_count == 0:
#                     continue
#                 retention = [
#                     float(np.count_nonzero(np.isfinite(min_charge_vals) & (min_charge_vals > threshold))) / baseline_count
#                     for threshold in tt_task3_list_charge_thresholds
#                 ]
#                 ax.plot(
#                     tt_task3_list_charge_thresholds,
#                     retention,
#                     marker="o",
#                     linewidth=1.7,
#                     alpha=0.9,
#                     color=cmap(idx % 20),
#                     label=f"{source_tt}",
#                 )
#
#             ax.set_xlabel("Charge threshold")
#             ax.set_ylabel("Retention fraction relative to Q > 0")
#             ax.set_title("Retention curves by source tt_task3_list")
#             ax.set_ylim(0, 1.05)
#             ax.grid(True, alpha=0.25)
#             ax.legend(title="Source tt_task3_list", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
#             fig.tight_layout(rect=[0, 0, 0.84, 1])
#
#             if save_plots:
#                 final_filename = f"{fig_idx}_tt_task3_list_retention_curves.png"
#                 fig_idx += 1
#                 save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                 plot_list.append(save_fig_path)
#                 save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#             if show_plots:
#                 plt.show()
#             plt.close(fig)
#
#         if task3_plot_enabled("tt_task3_list_minimum_charge_distributions") and min_charge_by_source_tt:
#             positive_min_charge_arrays = []
#             for min_charge in min_charge_by_source_tt.values():
#                 min_charge_vals = pd.to_numeric(min_charge, errors="coerce").to_numpy(dtype=float)
#                 positive_min_charge = min_charge_vals[np.isfinite(min_charge_vals) & (min_charge_vals > 0)]
#                 if positive_min_charge.size:
#                     positive_min_charge_arrays.append(positive_min_charge)
#
#             if positive_min_charge_arrays:
#                 min_charge_plot_max = float(np.nanpercentile(np.concatenate(positive_min_charge_arrays), 99.5))
#                 min_charge_plot_max = max(min_charge_plot_max, max(tt_task3_list_charge_thresholds) if tt_task3_list_charge_thresholds else 0)
#                 if not np.isfinite(min_charge_plot_max) or min_charge_plot_max <= 0:
#                     min_charge_plot_max = 10.0
#             else:
#                 min_charge_plot_max = max(max(tt_task3_list_charge_thresholds), 10.0) if tt_task3_list_charge_thresholds else 10.0
#             min_charge_plot_max = float(max(10.0, math.ceil(min_charge_plot_max / 10.0) * 10.0))
#             if tt_task3_list_charge_limit_effective_runtime is not None:
#                 min_charge_plot_max = float(min(min_charge_plot_max, float(tt_task3_list_charge_limit_effective_runtime)))
#
#             n_sources = len(min_charge_by_source_tt)
#             ncols = 4
#             nrows = int(math.ceil(n_sources / ncols))
#             fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.2 * nrows), squeeze=False)
#             axes_flat = axes.flatten()
#
#             for ax, source_tt in zip(axes_flat, ordered_tt_values):
#                 min_charge = min_charge_by_source_tt.get(source_tt)
#                 if min_charge is None:
#                     ax.set_axis_off()
#                     continue
#                 min_charge_vals = pd.to_numeric(min_charge, errors="coerce").to_numpy(dtype=float)
#                 hist_vals = min_charge_vals[np.isfinite(min_charge_vals) & (min_charge_vals > 0)]
#                 if hist_vals.size:
#                     ax.hist(
#                         hist_vals,
#                         bins=50,
#                         range=(0, min_charge_plot_max),
#                         color="tab:blue",
#                         alpha=0.75,
#                     )
#                     for threshold in tt_task3_list_charge_thresholds:
#                         ax.axvline(threshold, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
#                 else:
#                     ax.text(0.5, 0.5, "No positive charge", ha="center", va="center", transform=ax.transAxes)
#                 ax.set_xlim(0, min_charge_plot_max)
#                 ax.set_title(f"tt_task3_list {source_tt} (N={len(hist_vals)})", fontsize=10)
#                 ax.grid(True, alpha=0.2)
#
#             for ax in axes_flat[n_sources:]:
#                 ax.set_axis_off()
#
#             for row_idx in range(nrows):
#                 axes[row_idx, 0].set_ylabel("Counts")
#             for col_idx in range(ncols):
#                 axes[-1, col_idx].set_xlabel("Minimum active-plane Q_sum_final")
#
#             fig.suptitle("Minimum active-plane charge by source tt_task3_list", fontsize=16)
#             fig.tight_layout(rect=[0, 0.03, 1, 0.95])
#
#             if save_plots:
#                 final_filename = f"{fig_idx}_tt_task3_list_minimum_charge_distributions.png"
#                 fig_idx += 1
#                 save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                 plot_list.append(save_fig_path)
#                 save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#             if show_plots:
#                 plt.show()
#             plt.close(fig)
#
#         if task3_plot_enabled("tt_task3_list_empirical_efficiency_vs_threshold"):
#             plane_to_thresholds: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: []}
#             plane_to_efficiencies: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: []}
#             plane_to_errors: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: []}
#             plane_to_counts: dict[int, list[tuple[int, int]]] = {1: [], 2: [], 3: [], 4: []}
#             for threshold, threshold_label in zip(tt_task3_list_charge_thresholds, threshold_labels):
#                 tt_counts = threshold_tt_by_label[threshold_label].value_counts()
#                 per_plane = compute_empirical_efficiency_from_tt_counts(tt_counts)
#                 for plane in (1, 2, 3, 4):
#                     efficiency, error, n_three, n_four = per_plane[plane]
#                     plane_to_thresholds[plane].append(float(threshold))
#                     plane_to_efficiencies[plane].append(float(efficiency))
#                     plane_to_errors[plane].append(float(error))
#                     plane_to_counts[plane].append((n_three, n_four))
#
#             has_any_valid = False
#             y_low_candidates: list[float] = []
#             y_high_candidates: list[float] = []
#             for plane in (1, 2, 3, 4):
#                 x_vals = np.asarray(plane_to_thresholds[plane], dtype=float)
#                 y_vals = np.asarray(plane_to_efficiencies[plane], dtype=float)
#                 y_errs = np.asarray(plane_to_errors[plane], dtype=float)
#                 valid = np.isfinite(x_vals) & np.isfinite(y_vals) & np.isfinite(y_errs)
#                 if np.any(valid):
#                     has_any_valid = True
#                     y_low_candidates.append(float(np.nanmin(y_vals[valid] - y_errs[valid])))
#                     y_high_candidates.append(float(np.nanmax(y_vals[valid] + y_errs[valid])))
#
#             if has_any_valid:
#                 fig, axes = plt.subplots(2, 1, figsize=(10.5, 9.0), sharex=True)
#                 ax_top, ax_bottom = axes
#                 plane_colors = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
#                 missing_plane_tt_label = {1: "234", 2: "134", 3: "124", 4: "123"}
#                 for plane in (1, 2, 3, 4):
#                     x_vals = np.asarray(plane_to_thresholds[plane], dtype=float)
#                     y_vals = np.asarray(plane_to_efficiencies[plane], dtype=float)
#                     y_errs = np.asarray(plane_to_errors[plane], dtype=float)
#                     valid = np.isfinite(x_vals) & np.isfinite(y_vals) & np.isfinite(y_errs)
#                     if not np.any(valid):
#                         continue
#
#                     for axis in (ax_top, ax_bottom):
#                         axis.errorbar(
#                             x_vals[valid],
#                             y_vals[valid],
#                             yerr=y_errs[valid],
#                             fmt="o-",
#                             linewidth=1.6,
#                             markersize=4.5,
#                             capsize=3.5,
#                             color=plane_colors[plane],
#                             label=f"eff_{plane} = 1 - N({missing_plane_tt_label[plane]})/N(1234)",
#                         )
#
#                     valid_indices = [idx for idx, ok in enumerate(valid) if ok]
#                     for idx in valid_indices:
#                         x_val = x_vals[idx]
#                         y_val = y_vals[idx]
#                         n_three, n_four = plane_to_counts[plane][idx]
#                         for axis in (ax_top, ax_bottom):
#                             axis.annotate(
#                                 f"{n_three}/{n_four}",
#                                 xy=(x_val, y_val),
#                                 xytext=(0, 6),
#                                 textcoords="offset points",
#                                 ha="center",
#                                 fontsize=7,
#                                 alpha=0.8,
#                                 color=plane_colors[plane],
#                             )
#
#                 ax_top.set_ylabel("Empirical efficiency")
#                 ax_top.set_title("Threshold scan: per-plane empirical efficiencies (zoom 0-1)")
#                 ax_top.grid(True, alpha=0.25)
#                 ax_top.axhline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.4)
#                 ax_top.set_ylim(0.0, 1.0)
#                 ax_top.legend(loc="upper right", fontsize=9)
#
#                 ax_bottom.set_xlabel("Charge threshold")
#                 ax_bottom.set_ylabel("Empirical efficiency")
#                 ax_bottom.set_title("Threshold scan: per-plane empirical efficiencies (full range)")
#                 ax_bottom.grid(True, alpha=0.25)
#                 ax_bottom.axhline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.4)
#                 ax_bottom.legend(loc="upper right", fontsize=9)
#
#                 y_low = float(min(y_low_candidates))
#                 y_high = float(max(y_high_candidates))
#                 y_margin = max(0.03, 0.08 * max(y_high - y_low, 0.1))
#                 ax_bottom.set_ylim(y_low - y_margin, y_high + y_margin)
#
#                 fig.tight_layout()
#
#                 if save_plots:
#                     final_filename = f"{fig_idx}_tt_task3_list_empirical_efficiency_vs_threshold.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig)
#
#         if task3_plot_enabled("tsum_coincidence_window_histograms") and threshold_tsum_window_by_label:
#             all_window_vals: list[np.ndarray] = []
#             for threshold_label in threshold_labels:
#                 w_vals = threshold_tsum_window_by_label[threshold_label].to_numpy(dtype=float)
#                 valid = np.isfinite(w_vals)
#                 if np.any(valid):
#                     all_window_vals.append(w_vals[valid])
#
#             if all_window_vals:
#                 window_max = float(np.nanpercentile(np.concatenate(all_window_vals), 99.5))
#                 if not np.isfinite(window_max) or window_max <= 0:
#                     window_max = float(max(tsum_window_cut_values_ns) * 1.5)
#             else:
#                 window_max = float(max(tsum_window_cut_values_ns) * 1.5)
#             window_max = max(window_max, float(max(tsum_window_cut_values_ns) * 1.1))
#
#             baseline_label = threshold_labels[0]
#             combo_counts = threshold_tt_by_label.get(baseline_label, pd.Series(dtype=int)).value_counts().to_dict()
#             combo_order = [
#                 int(tt_value)
#                 for tt_value, count in sorted(combo_counts.items(), key=lambda item: item[1], reverse=True)
#                 if len(tt_value_to_planes(tt_value)) >= 2 and int(count) >= tsum_window_combo_min_count
#             ][:tsum_window_max_plane_combinations]
#
#             if combo_order:
#                 nrows = len(combo_order)
#                 ncols = len(threshold_labels)
#                 fig, axes = plt.subplots(
#                     nrows,
#                     ncols,
#                     figsize=(3.0 * max(1, ncols), 2.2 * max(1, nrows)),
#                     squeeze=False,
#                     sharex=True,
#                     sharey=True,
#                 )
#                 panel_density_max: list[float] = []
#
#                 for i_row, combo_tt in enumerate(combo_order):
#                     for j_col, threshold_label in enumerate(threshold_labels):
#                         ax = axes[i_row, j_col]
#                         tt_vals = threshold_tt_by_label[threshold_label].to_numpy(dtype=int)
#                         w_vals = threshold_tsum_window_by_label[threshold_label].to_numpy(dtype=float)
#                         valid = np.isfinite(w_vals) & (tt_vals == int(combo_tt))
#                         hist_vals = w_vals[valid]
#
#                         if hist_vals.size > 0:
#                             hist_n, _, _ = ax.hist(
#                                 hist_vals,
#                                 bins=tsum_window_hist_bins,
#                                 range=(0.0, window_max),
#                                 color="tab:blue",
#                                 alpha=0.8,
#                                 density=True,
#                             )
#                             if hist_n.size > 0 and np.isfinite(hist_n).any():
#                                 panel_density_max.append(float(np.nanmax(hist_n)))
#                             for cut_val in tsum_window_cut_values_ns:
#                                 ax.axvline(cut_val, color="black", linestyle="--", linewidth=0.7, alpha=0.4)
#                         else:
#                             ax.text(0.5, 0.5, "No events", ha="center", va="center", transform=ax.transAxes, fontsize=7)
#
#                         ax.set_xlim(0.0, window_max)
#                         ax.grid(True, alpha=0.2)
#
#                         if i_row == 0:
#                             ax.set_title(f"{threshold_label}", fontsize=9)
#                         if j_col == 0:
#                             base_count = int(combo_counts.get(combo_tt, 0))
#                             ax.set_ylabel(f"TT {combo_tt}\nN0={base_count}\nDensity", fontsize=8)
#
#                 # Use a robust shared y-limit so sparse single-bin panels remain readable.
#                 if panel_density_max:
#                     y_ref = float(np.nanpercentile(np.asarray(panel_density_max, dtype=float), 90))
#                     if not np.isfinite(y_ref) or y_ref <= 0:
#                         y_ref = float(np.nanmax(np.asarray(panel_density_max, dtype=float)))
#                     if np.isfinite(y_ref) and y_ref > 0:
#                         y_top = max(0.05, 1.2 * y_ref)
#                         axes[0, 0].set_ylim(0.0, y_top)
#
#                 for j_col in range(ncols):
#                     axes[-1, j_col].set_xlabel("T_sum coincidence window [ns]")
#
#                 fig.suptitle(
#                     "T_sum coincidence-window histograms\n"
#                     "Rows: plane combinations (TT), Columns: Q thresholds",
#                     fontsize=13,
#                 )
#                 fig.tight_layout(rect=[0, 0, 1, 0.95])
#
#                 if save_plots:
#                     final_filename = f"{fig_idx}_tsum_coincidence_window_histograms_by_plane_combination.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig)
#
#         if task3_plot_enabled("tsum_coincidence_window_vs_threshold") and threshold_tsum_window_by_label:
#             x_vals = np.asarray(tt_task3_list_charge_thresholds, dtype=float)
#             percentile_curves: dict[float, list[float]] = {pct: [] for pct in tsum_window_percentiles}
#             acceptance_curves: dict[float, list[float]] = {cut_val: [] for cut_val in tsum_window_cut_values_ns}
#             reference_acceptance: list[float] = []
#             n_events_per_threshold: list[int] = []
#
#             for threshold_label in threshold_labels:
#                 w_vals = threshold_tsum_window_by_label[threshold_label].to_numpy(dtype=float)
#                 valid = np.isfinite(w_vals)
#                 hist_vals = w_vals[valid]
#                 n_events_per_threshold.append(int(hist_vals.size))
#
#                 if hist_vals.size == 0:
#                     for pct in tsum_window_percentiles:
#                         percentile_curves[pct].append(np.nan)
#                     for cut_val in tsum_window_cut_values_ns:
#                         acceptance_curves[cut_val].append(np.nan)
#                     reference_acceptance.append(np.nan)
#                     continue
#
#                 for pct in tsum_window_percentiles:
#                     percentile_curves[pct].append(float(np.nanpercentile(hist_vals, pct)))
#                 for cut_val in tsum_window_cut_values_ns:
#                     acceptance_curves[cut_val].append(float(np.mean(hist_vals <= cut_val)))
#                 reference_acceptance.append(float(np.mean(hist_vals <= tsum_window_reference_ns)))
#
#             fig, axes = plt.subplots(2, 1, figsize=(10.5, 8.5), sharex=True)
#             ax_top, ax_bottom = axes
#
#             pct_cmap = plt.get_cmap("viridis")
#             for idx, pct in enumerate(tsum_window_percentiles):
#                 y_vals = np.asarray(percentile_curves[pct], dtype=float)
#                 valid = np.isfinite(y_vals)
#                 if np.any(valid):
#                     ax_top.plot(
#                         x_vals[valid],
#                         y_vals[valid],
#                         marker="o",
#                         linewidth=1.9,
#                         color=pct_cmap(idx / max(len(tsum_window_percentiles) - 1, 1)),
#                         label=f"P{pct:g}",
#                     )
#             ax_top.set_ylabel("Coincidence window [ns]")
#             ax_top.set_title("T_sum coincidence-window quantiles vs Q threshold")
#             ax_top.grid(True, alpha=0.25)
#             ax_top.legend(loc="upper right", fontsize=9)
#
#             cut_cmap = plt.get_cmap("plasma")
#             for idx, cut_val in enumerate(tsum_window_cut_values_ns):
#                 y_vals = np.asarray(acceptance_curves[cut_val], dtype=float)
#                 valid = np.isfinite(y_vals)
#                 if np.any(valid):
#                     ax_bottom.plot(
#                         x_vals[valid],
#                         y_vals[valid],
#                         marker="o",
#                         linewidth=1.9,
#                         color=cut_cmap(idx / max(len(tsum_window_cut_values_ns) - 1, 1)),
#                         label=f"window <= {cut_val:g} ns",
#                     )
#
#             y_ref = np.asarray(reference_acceptance, dtype=float)
#             valid_ref = np.isfinite(y_ref)
#             if np.any(valid_ref):
#                 ax_bottom.plot(
#                     x_vals[valid_ref],
#                     y_ref[valid_ref],
#                     linestyle="--",
#                     linewidth=1.5,
#                     color="black",
#                     alpha=0.75,
#                     label=f"window <= {tsum_window_reference_ns:g} ns (reference)",
#                 )
#
#             ax_bottom.set_xlabel("Charge threshold")
#             ax_bottom.set_ylabel("Fraction within window")
#             ax_bottom.set_ylim(0.0, 1.05)
#             ax_bottom.set_title("Coincidence-window acceptance vs Q threshold")
#             ax_bottom.grid(True, alpha=0.25)
#             ax_bottom.legend(loc="upper right", fontsize=8)
#
#             # Annotate usable event counts for context.
#             for x_val, n_val in zip(x_vals, n_events_per_threshold):
#                 ax_bottom.annotate(
#                     f"N={n_val}",
#                     xy=(x_val, 0.02),
#                     xycoords=("data", "axes fraction"),
#                     xytext=(0, 0),
#                     textcoords="offset points",
#                     ha="center",
#                     va="bottom",
#                     fontsize=7,
#                     alpha=0.7,
#                 )
#
#             fig.tight_layout()
#
#             if save_plots:
#                 final_filename = f"{fig_idx}_tsum_coincidence_window_vs_threshold.png"
#                 fig_idx += 1
#                 save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                 plot_list.append(save_fig_path)
#                 save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#             if show_plots:
#                 plt.show()
#             plt.close(fig)
#
#             # Same study split by plane combination (thresholded TT code).
#             if threshold_tt_by_label:
#                 baseline_label = threshold_labels[0]
#                 baseline_tt = threshold_tt_by_label[baseline_label]
#                 baseline_window = threshold_tsum_window_by_label[baseline_label]
#                 baseline_valid = np.isfinite(baseline_window.to_numpy(dtype=float))
#
#                 combo_counts = (
#                     baseline_tt[baseline_valid]
#                     .value_counts()
#                     .to_dict()
#                 )
#                 combo_order = [
#                     int(tt_value)
#                     for tt_value, count in sorted(combo_counts.items(), key=lambda item: item[1], reverse=True)
#                     if len(tt_value_to_planes(tt_value)) >= 2 and int(count) >= tsum_window_combo_min_count
#                 ][:tsum_window_max_plane_combinations]
#
#                 if combo_order:
#                     fig, axes = plt.subplots(2, 1, figsize=(10.8, 8.6), sharex=True)
#                     ax_top, ax_bottom = axes
#                     cmap = plt.get_cmap("tab20")
#
#                     for idx, combo_tt in enumerate(combo_order):
#                         combo_window_median: list[float] = []
#                         combo_window_p90: list[float] = []
#                         combo_acceptance_ref: list[float] = []
#
#                         for threshold_label in threshold_labels:
#                             tt_series = threshold_tt_by_label[threshold_label]
#                             w_series = threshold_tsum_window_by_label[threshold_label]
#                             mask = tt_series.eq(combo_tt).to_numpy(dtype=bool)
#                             w_vals = w_series.to_numpy(dtype=float)
#                             valid = mask & np.isfinite(w_vals)
#                             combo_vals = w_vals[valid]
#                             if combo_vals.size == 0:
#                                 combo_window_median.append(np.nan)
#                                 combo_window_p90.append(np.nan)
#                                 combo_acceptance_ref.append(np.nan)
#                                 continue
#                             combo_window_median.append(float(np.nanpercentile(combo_vals, 50)))
#                             combo_window_p90.append(float(np.nanpercentile(combo_vals, 90)))
#                             combo_acceptance_ref.append(float(np.mean(combo_vals <= tsum_window_reference_ns)))
#
#                         color = cmap(idx % 20)
#                         median_vals = np.asarray(combo_window_median, dtype=float)
#                         p90_vals = np.asarray(combo_window_p90, dtype=float)
#                         acc_vals = np.asarray(combo_acceptance_ref, dtype=float)
#                         valid_median = np.isfinite(median_vals)
#                         valid_p90 = np.isfinite(p90_vals)
#                         valid_acc = np.isfinite(acc_vals)
#
#                         base_count = int(combo_counts.get(combo_tt, 0))
#                         label_base = f"TT {combo_tt} (N0={base_count})"
#                         if np.any(valid_median):
#                             ax_top.plot(
#                                 x_vals[valid_median],
#                                 median_vals[valid_median],
#                                 marker="o",
#                                 linewidth=1.8,
#                                 color=color,
#                                 label=f"{label_base} median",
#                             )
#                         if np.any(valid_p90):
#                             ax_top.plot(
#                                 x_vals[valid_p90],
#                                 p90_vals[valid_p90],
#                                 marker=".",
#                                 linestyle="--",
#                                 linewidth=1.1,
#                                 color=color,
#                                 alpha=0.8,
#                                 label=f"TT {combo_tt} P90",
#                             )
#                         if np.any(valid_acc):
#                             ax_bottom.plot(
#                                 x_vals[valid_acc],
#                                 acc_vals[valid_acc],
#                                 marker="o",
#                                 linewidth=1.9,
#                                 color=color,
#                                 label=label_base,
#                             )
#
#                     ax_top.set_ylabel("Coincidence window [ns]")
#                     ax_top.set_title("T_sum window vs Q threshold by plane combination (TT)")
#                     ax_top.grid(True, alpha=0.25)
#                     ax_top.legend(loc="upper right", fontsize=7, ncol=2)
#
#                     ax_bottom.set_xlabel("Charge threshold")
#                     ax_bottom.set_ylabel(f"Fraction with window <= {tsum_window_reference_ns:g} ns")
#                     ax_bottom.set_ylim(0.0, 1.05)
#                     ax_bottom.set_title("Coincidence-window acceptance by plane combination")
#                     ax_bottom.grid(True, alpha=0.25)
#                     ax_bottom.legend(loc="upper right", fontsize=8)
#
#                     fig.tight_layout()
#
#                     if save_plots:
#                         final_filename = f"{fig_idx}_tsum_coincidence_window_vs_threshold_by_plane_combination.png"
#                         fig_idx += 1
#                         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                         plot_list.append(save_fig_path)
#                         save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#                     if show_plots:
#                         plt.show()
#                     plt.close(fig)
#
#         if task3_plot_enabled("plane_charge_fraction_vs_total_charge_threshold_scan"):
#             q_cols = [f"p{plane}_qsum" for plane in range(1, 5) if f"p{plane}_qsum" in working_df.columns]
#             if len(q_cols) >= 2:
#                 q_df = working_df[q_cols].apply(pd.to_numeric, errors="coerce")
#                 q_df = q_df.where(q_df > 0, 0.0).fillna(0.0)
#                 q_total = q_df.sum(axis=1)
#
#                 scan_thresholds = sorted(tt_task3_list_charge_thresholds)[:plane_charge_fraction_max_panels]
#                 ncols = len(scan_thresholds)
#                 nrows = len(q_cols)
#                 fig, axes = plt.subplots(
#                     nrows,
#                     ncols,
#                     figsize=(3.1 * max(1, ncols), 2.5 * max(1, nrows)),
#                     squeeze=False,
#                     sharex=True,
#                     sharey=True,
#                 )
#
#                 plane_colors = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
#                 plane_labels = {1: "Plane 1", 2: "Plane 2", 3: "Plane 3", 4: "Plane 4"}
#
#                 q_total_max = float(np.nanpercentile(q_total.to_numpy(dtype=float), 99.5)) if len(q_total) else 0.0
#                 if not np.isfinite(q_total_max) or q_total_max <= 0:
#                     q_total_max = float(max(scan_thresholds) * 5.0 + 50.0)
#
#                 threshold_to_idx: dict[float, np.ndarray] = {}
#                 for thr in scan_thresholds:
#                     # Apply threshold plane-by-plane with logical AND, consistent with
#                     # the charge-threshold logic used elsewhere in Task 3.
#                     mask = pd.Series(True, index=q_df.index, dtype=bool)
#                     for q_col in q_cols:
#                         mask &= q_df[q_col].gt(float(thr))
#                     idx = np.flatnonzero(mask.to_numpy(dtype=bool))
#                     if idx.size > plane_charge_fraction_scatter_max_points:
#                         keep = np.linspace(0, idx.size - 1, plane_charge_fraction_scatter_max_points, dtype=int)
#                         idx = idx[keep]
#                     threshold_to_idx[float(thr)] = idx
#
#                 for i_row, q_col in enumerate(q_cols):
#                     plane = int(q_col.split("_", 1)[0][1:])
#                     color = plane_colors.get(plane, "black")
#                     for j_col, thr in enumerate(scan_thresholds):
#                         ax = axes[i_row, j_col]
#                         idx = threshold_to_idx.get(float(thr), np.array([], dtype=int))
#                         if idx.size == 0:
#                             ax.text(0.5, 0.5, "No events", ha="center", va="center", transform=ax.transAxes, fontsize=8)
#                             ax.grid(True, alpha=0.2)
#                             continue
#
#                         x_vals = q_total.to_numpy(dtype=float)[idx]
#                         denom = np.where(x_vals > 0, x_vals, np.nan)
#
#                         plane_q = q_df[q_col].to_numpy(dtype=float)[idx]
#                         frac = np.divide(plane_q, denom, out=np.full_like(plane_q, np.nan), where=np.isfinite(denom))
#                         valid = np.isfinite(frac) & np.isfinite(x_vals)
#                         if np.any(valid):
#                             ax.scatter(
#                                 x_vals[valid],
#                                 frac[valid],
#                                 s=4,
#                                 alpha=0.25,
#                                 color=color,
#                                 linewidths=0,
#                                 rasterized=True,
#                             )
#
#                         ax.set_ylim(0.0, 1.02)
#                         ax.set_xlim(0.0, q_total_max)
#                         ax.grid(True, alpha=0.2)
#
#                         if i_row == 0:
#                             ax.set_title(f"All planes Q > {thr:g}\nN={len(idx)}", fontsize=9)
#                         if j_col == 0:
#                             ax.set_ylabel(f"{plane_labels.get(plane, f'Plane {plane}')}\nQ_plane / Q_total", fontsize=9)
#
#                 for j_col in range(ncols):
#                     axes[-1, j_col].set_xlabel("Total event charge Q_total")
#
#                 fig.suptitle(
#                     "Per-plane charge fraction vs total event charge\n"
#                     "Rows: planes, Columns: charge thresholds",
#                     fontsize=14,
#                 )
#                 fig.tight_layout(rect=[0, 0, 1, 0.95])
#
#                 if save_plots:
#                     final_filename = f"{fig_idx}_plane_charge_fraction_vs_total_charge_threshold_scan.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig)
#
#         if task3_any_plot_enabled(
#             "full_topology_threshold_retention",
#             "full_topology_exact_retention",
#             "full_topology_class_fraction",
#         ) and threshold_full_patterns_by_label:
#             baseline_label = threshold_labels[0]
#             baseline_counts = threshold_full_patterns_by_label[baseline_label].value_counts()
#             threshold_counts_by_label = {
#                 label: threshold_full_patterns_by_label[label].value_counts()
#                 for label in threshold_labels
#             }
#
#             per_mask_class_patterns: dict[str, dict[str, list[str]]] = {}
#             per_mask_class_baseline: dict[str, dict[str, int]] = {}
#             per_mask_total_baseline: dict[str, int] = {}
#             for pattern, count in baseline_counts.items():
#                 active_mask, topo_class, _ = classify_full_strip_topology(str(pattern))
#                 if active_mask == "0000" or topo_class in {"empty", "invalid"}:
#                     continue
#                 if active_mask not in per_mask_class_patterns:
#                     per_mask_class_patterns[active_mask] = {}
#                     per_mask_class_baseline[active_mask] = {}
#                     per_mask_total_baseline[active_mask] = 0
#                 per_mask_class_patterns[active_mask].setdefault(topo_class, []).append(str(pattern))
#                 per_mask_class_baseline[active_mask][topo_class] = (
#                     per_mask_class_baseline[active_mask].get(topo_class, 0) + int(count)
#                 )
#                 per_mask_total_baseline[active_mask] += int(count)
#
#             mask_order = [
#                 mask
#                 for mask, total in sorted(
#                     per_mask_total_baseline.items(),
#                     key=lambda item: item[1],
#                     reverse=True,
#                 )
#                 if total >= full_topology_min_baseline_count
#             ][:full_topology_max_masks]
#
#             if mask_order:
#                 ncols = 2
#                 nrows = int(math.ceil(len(mask_order) / ncols))
#                 fig, axes = plt.subplots(nrows, ncols, figsize=(7.2 * ncols, 4.1 * nrows), squeeze=False, sharex=True)
#                 axes_flat = axes.flatten()
#                 class_colors = {
#                     "single_strip_smooth": "tab:blue",
#                     "single_strip_rough": "tab:orange",
#                     "single_strip_zigzag": "tab:red",
#                     "multi_strip": "tab:gray",
#                 }
#                 class_labels = {
#                     "single_strip_smooth": "single-strip smooth",
#                     "single_strip_rough": "single-strip rough",
#                     "single_strip_zigzag": "single-strip zigzag",
#                     "multi_strip": "multi-strip",
#                 }
#                 class_order = [
#                     "single_strip_smooth",
#                     "single_strip_rough",
#                     "single_strip_zigzag",
#                     "multi_strip",
#                 ]
#
#                 for ax, mask in zip(axes_flat, mask_order):
#                     class_to_patterns = per_mask_class_patterns.get(mask, {})
#                     class_to_baseline = per_mask_class_baseline.get(mask, {})
#                     drawn = 0
#                     for topo_class in class_order:
#                         baseline_n = int(class_to_baseline.get(topo_class, 0))
#                         if baseline_n <= 0:
#                             continue
#                         patterns_in_class = class_to_patterns.get(topo_class, [])
#                         if not patterns_in_class:
#                             continue
#
#                         retention_vals: list[float] = []
#                         for threshold_label in threshold_labels:
#                             counts = threshold_counts_by_label[threshold_label]
#                             surviving = int(sum(int(counts.get(pattern, 0)) for pattern in patterns_in_class))
#                             retention_vals.append(float(surviving) / float(baseline_n))
#
#                         ax.plot(
#                             tt_task3_list_charge_thresholds,
#                             retention_vals,
#                             marker="o",
#                             linewidth=1.9,
#                             markersize=4,
#                             color=class_colors[topo_class],
#                             label=f"{class_labels[topo_class]} (N0={baseline_n})",
#                         )
#                         drawn += 1
#
#                     ax.set_title(f"Active mask {mask} (N0={per_mask_total_baseline.get(mask, 0)})")
#                     ax.set_ylim(0.0, 1.05)
#                     ax.grid(True, alpha=0.25)
#                     if drawn > 0:
#                         ax.legend(loc="upper right", fontsize=8)
#                     else:
#                         ax.text(0.5, 0.5, "No classes above baseline threshold", ha="center", va="center", transform=ax.transAxes)
#
#                 for ax in axes_flat[len(mask_order):]:
#                     ax.set_axis_off()
#
#                 for row_idx in range(nrows):
#                     axes[row_idx, 0].set_ylabel("Retention vs baseline (Q > first threshold)")
#                 for col_idx in range(ncols):
#                     axes[-1, col_idx].set_xlabel("Charge threshold")
#
#                 fig.suptitle(
#                     "Full topology threshold study by active-plane combination\n"
#                     "(faster zigzag/rough decay may indicate noise-like behavior)",
#                     fontsize=14,
#                 )
#                 fig.tight_layout(rect=[0, 0, 1, 0.95])
#
#                 if save_plots:
#                     final_filename = f"{fig_idx}_full_topology_threshold_retention.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig)
#
#             if task3_plot_enabled("full_topology_exact_retention") and mask_order:
#                 ncols = 2
#                 nrows = int(math.ceil(len(mask_order) / ncols))
#                 fig, axes = plt.subplots(nrows, ncols, figsize=(7.4 * ncols, 4.4 * nrows), squeeze=False, sharex=True)
#                 axes_flat = axes.flatten()
#                 cmap = plt.get_cmap("tab20")
#
#                 for ax, mask in zip(axes_flat, mask_order):
#                     baseline_by_pattern = {
#                         str(pattern): int(count)
#                         for pattern, count in baseline_counts.items()
#                         if classify_full_strip_topology(str(pattern))[0] == mask
#                     }
#                     top_patterns = [
#                         pattern
#                         for pattern, count in sorted(
#                             baseline_by_pattern.items(),
#                             key=lambda item: item[1],
#                             reverse=True,
#                         )
#                         if count >= full_topology_min_baseline_count
#                     ][:full_topology_max_patterns_per_mask]
#
#                     if not top_patterns:
#                         ax.text(0.5, 0.5, "No topologies above baseline threshold", ha="center", va="center", transform=ax.transAxes)
#                         ax.set_title(f"Active mask {mask}")
#                         ax.grid(True, alpha=0.2)
#                         continue
#
#                     for idx, pattern in enumerate(top_patterns):
#                         baseline_n = float(baseline_by_pattern[pattern])
#                         retention_vals: list[float] = []
#                         for threshold_label in threshold_labels:
#                             counts = threshold_counts_by_label[threshold_label]
#                             surviving = float(int(counts.get(pattern, 0)))
#                             retention_vals.append(surviving / baseline_n)
#
#                         _, topo_class, path_label = classify_full_strip_topology(pattern)
#                         class_short = {
#                             "single_strip_smooth": "smooth",
#                             "single_strip_rough": "rough",
#                             "single_strip_zigzag": "zigzag",
#                             "multi_strip": "multi",
#                         }.get(topo_class, topo_class)
#                         suffix = f"{class_short}:{path_label}" if path_label else class_short
#                         label = f"{pattern[:8]}.. {suffix} (N0={int(baseline_n)})"
#                         ax.plot(
#                             tt_task3_list_charge_thresholds,
#                             retention_vals,
#                             marker="o",
#                             linewidth=1.4,
#                             markersize=3.5,
#                             color=cmap(idx % 20),
#                             label=label,
#                             alpha=0.95,
#                         )
#
#                     ax.set_title(f"Active mask {mask}: top exact topologies")
#                     ax.set_ylim(0.0, 1.05)
#                     ax.grid(True, alpha=0.25)
#                     ax.legend(loc="upper right", fontsize=7)
#
#                 for ax in axes_flat[len(mask_order):]:
#                     ax.set_axis_off()
#
#                 for row_idx in range(nrows):
#                     axes[row_idx, 0].set_ylabel("Retention vs baseline (Q > first threshold)")
#                 for col_idx in range(ncols):
#                     axes[-1, col_idx].set_xlabel("Charge threshold")
#
#                 fig.suptitle(
#                     "Exact topology decay by active-plane combination\n"
#                     "(which specific patterns disappear faster?)",
#                     fontsize=14,
#                 )
#                 fig.tight_layout(rect=[0, 0, 1, 0.95])
#
#                 if save_plots:
#                     final_filename = f"{fig_idx}_full_topology_exact_retention.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig)
#
#             if task3_plot_enabled("full_topology_class_fraction") and mask_order:
#                 ncols = 2
#                 nrows = int(math.ceil(len(mask_order) / ncols))
#                 fig, axes = plt.subplots(nrows, ncols, figsize=(7.2 * ncols, 4.1 * nrows), squeeze=False, sharex=True)
#                 axes_flat = axes.flatten()
#                 class_order = [
#                     "single_strip_smooth",
#                     "single_strip_rough",
#                     "single_strip_zigzag",
#                     "multi_strip",
#                 ]
#                 class_labels = {
#                     "single_strip_smooth": "single-strip smooth",
#                     "single_strip_rough": "single-strip rough",
#                     "single_strip_zigzag": "single-strip zigzag",
#                     "multi_strip": "multi-strip",
#                 }
#                 class_colors = {
#                     "single_strip_smooth": "tab:blue",
#                     "single_strip_rough": "tab:orange",
#                     "single_strip_zigzag": "tab:red",
#                     "multi_strip": "tab:gray",
#                 }
#
#                 for ax, mask in zip(axes_flat, mask_order):
#                     class_fraction_values: dict[str, list[float]] = {key: [] for key in class_order}
#                     for threshold_label in threshold_labels:
#                         counts = threshold_counts_by_label[threshold_label]
#                         class_totals = {key: 0 for key in class_order}
#                         mask_total = 0
#                         for pattern, count in counts.items():
#                             active_mask, topo_class, _ = classify_full_strip_topology(str(pattern))
#                             if active_mask != mask:
#                                 continue
#                             if topo_class not in class_totals:
#                                 continue
#                             class_totals[topo_class] += int(count)
#                             mask_total += int(count)
#
#                         if mask_total <= 0:
#                             for topo_class in class_order:
#                                 class_fraction_values[topo_class].append(np.nan)
#                         else:
#                             for topo_class in class_order:
#                                 class_fraction_values[topo_class].append(
#                                     float(class_totals[topo_class]) / float(mask_total)
#                                 )
#
#                     for topo_class in class_order:
#                         y_vals = np.asarray(class_fraction_values[topo_class], dtype=float)
#                         valid = np.isfinite(y_vals)
#                         if not np.any(valid):
#                             continue
#                         ax.plot(
#                             np.asarray(tt_task3_list_charge_thresholds, dtype=float)[valid],
#                             y_vals[valid],
#                             marker="o",
#                             linewidth=1.9,
#                             markersize=4,
#                             color=class_colors[topo_class],
#                             label=class_labels[topo_class],
#                         )
#
#                     ax.set_title(f"Active mask {mask}: class composition")
#                     ax.set_ylim(0.0, 1.05)
#                     ax.grid(True, alpha=0.25)
#                     ax.legend(loc="upper right", fontsize=8)
#
#                 for ax in axes_flat[len(mask_order):]:
#                     ax.set_axis_off()
#
#                 for row_idx in range(nrows):
#                     axes[row_idx, 0].set_ylabel("Class fraction within mask")
#                 for col_idx in range(ncols):
#                     axes[-1, col_idx].set_xlabel("Charge threshold")
#
#                 fig.suptitle(
#                     "Topology class composition vs charge threshold\n"
#                     "(within each active-plane combination)",
#                     fontsize=14,
#                 )
#                 fig.tight_layout(rect=[0, 0, 1, 0.95])
#
#                 if save_plots:
#                     final_filename = f"{fig_idx}_full_topology_class_fraction.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig)
#
#         # -----------------------------------------------------------------
#         # Noise-discovery diagnostics block
#         # -----------------------------------------------------------------
#
#         # --- 1. Charge asymmetry (Q_diff / Q_sum) vs threshold ---
#         if task3_plot_enabled("charge_asymmetry_vs_threshold"):
#             q_sum_cols_asym = [f"p{p}_qsum" for p in range(1, 5) if f"p{p}_qsum" in working_df.columns]
#             q_dif_cols_asym = [f"p{p}_qdif" for p in range(1, 5) if f"p{p}_qdif" in working_df.columns]
#             paired_planes = [
#                 (int(qs.split("_", 1)[0][1:]), qs, qd)
#                 for qs, qd in zip(q_sum_cols_asym, q_dif_cols_asym)
#             ]
#             if paired_planes:
#                 scan_thrs = sorted(tt_task3_list_charge_thresholds)[:plane_charge_fraction_max_panels]
#
#                 # Shared x-range for all asymmetry panels (auto, with optional manual override).
#                 _asym_x_abs_raw = config.get("charge_asymmetry_x_abs_max", None)
#                 asym_x_abs_max = None
#                 try:
#                     if _asym_x_abs_raw not in (None, ""):
#                         asym_x_abs_max = abs(float(_asym_x_abs_raw))
#                 except (TypeError, ValueError):
#                     asym_x_abs_max = None
#                 if asym_x_abs_max is not None and (not np.isfinite(asym_x_abs_max) or asym_x_abs_max <= 0):
#                     asym_x_abs_max = None
#
#                 if asym_x_abs_max is None:
#                     _asym_q_low_raw = config.get("charge_asymmetry_x_low_quantile", 0.5)
#                     _asym_q_high_raw = config.get("charge_asymmetry_x_high_quantile", 99.5)
#                     try:
#                         asym_q_low = float(_asym_q_low_raw)
#                     except (TypeError, ValueError):
#                         asym_q_low = 0.5
#                     try:
#                         asym_q_high = float(_asym_q_high_raw)
#                     except (TypeError, ValueError):
#                         asym_q_high = 99.5
#                     asym_q_low = float(np.clip(asym_q_low, 0.0, 49.9))
#                     asym_q_high = float(np.clip(asym_q_high, 50.1, 100.0))
#                     if asym_q_low >= asym_q_high:
#                         asym_q_low, asym_q_high = 0.5, 99.5
#
#                     asym_pool: list[np.ndarray] = []
#                     for _, qs_col, qd_col in paired_planes:
#                         qs_arr = pd.to_numeric(working_df[qs_col], errors="coerce").to_numpy(dtype=float)
#                         qd_arr = pd.to_numeric(working_df[qd_col], errors="coerce").to_numpy(dtype=float)
#                         for thr in scan_thrs:
#                             keep = np.isfinite(qs_arr) & np.isfinite(qd_arr) & (qs_arr > float(thr))
#                             if not np.any(keep):
#                                 continue
#                             asym_vals = qd_arr[keep] / qs_arr[keep]
#                             finite_vals = asym_vals[np.isfinite(asym_vals)]
#                             if finite_vals.size:
#                                 asym_pool.append(finite_vals)
#
#                     if asym_pool:
#                         asym_all = np.concatenate(asym_pool)
#                         q_lo, q_hi = np.nanpercentile(asym_all, [asym_q_low, asym_q_high])
#                         ref_abs = max(abs(float(q_lo)), abs(float(q_hi)))
#                         if not np.isfinite(ref_abs) or ref_abs <= 0:
#                             ref_abs = 1.0
#                         asym_x_abs_max = max(0.05, 1.10 * ref_abs)
#                     else:
#                         asym_x_abs_max = 1.0
#
#                 asym_x_left = -float(asym_x_abs_max)
#                 asym_x_right = float(asym_x_abs_max)
#
#                 nrows_a = len(paired_planes)
#                 ncols_a = len(scan_thrs)
#                 fig_a, axes_a = plt.subplots(
#                     nrows_a, ncols_a,
#                     figsize=(3.1 * max(1, ncols_a), 2.5 * max(1, nrows_a)),
#                     squeeze=False, sharex=True, sharey=True,
#                 )
#                 plane_colors = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
#                 for i_row, (plane, qs_col, qd_col) in enumerate(paired_planes):
#                     qs_arr = pd.to_numeric(working_df[qs_col], errors="coerce").to_numpy(dtype=float)
#                     qd_arr = pd.to_numeric(working_df[qd_col], errors="coerce").to_numpy(dtype=float)
#                     for j_col, thr in enumerate(scan_thrs):
#                         ax = axes_a[i_row, j_col]
#                         keep = np.isfinite(qs_arr) & np.isfinite(qd_arr) & (qs_arr > float(thr))
#                         if not np.any(keep):
#                             ax.text(0.5, 0.5, "No events", ha="center", va="center",
#                                     transform=ax.transAxes, fontsize=8)
#                             ax.grid(True, alpha=0.2)
#                             continue
#                         asym = qd_arr[keep] / qs_arr[keep]
#                         asym = asym[np.isfinite(asym)]
#                         if asym.size == 0:
#                             ax.text(0.5, 0.5, "No finite asymmetry", ha="center", va="center",
#                                     transform=ax.transAxes, fontsize=8)
#                             ax.grid(True, alpha=0.2)
#                             continue
#                         ax.hist(asym, bins=60, range=(asym_x_left, asym_x_right),
#                                 color=plane_colors.get(plane, "grey"), alpha=0.7,
#                                 edgecolor="none", density=True)
#                         ax.axvline(0, color="black", linestyle="--", linewidth=0.6, alpha=0.5)
#                         ax.grid(True, alpha=0.2)
#                         if i_row == 0:
#                             ax.set_title(f"Q > {thr:g}\nN={int(np.sum(keep))}", fontsize=9)
#                         if j_col == 0:
#                             ax.set_ylabel(f"Plane {plane}\nPDF", fontsize=9)
#                 axes_a[0, 0].set_xlim(asym_x_left, asym_x_right)
#                 for j_col in range(ncols_a):
#                     axes_a[-1, j_col].set_xlabel("Q_diff / Q_sum")
#                 fig_a.suptitle(
#                     "Charge asymmetry (Q_diff/Q_sum) per plane vs threshold\n"
#                     "Noise: flat / bimodal at |A|→1; signal: peaked near 0",
#                     fontsize=13,
#                 )
#                 fig_a.tight_layout(rect=[0, 0, 1, 0.93])
#                 if save_plots:
#                     final_filename = f"{fig_idx}_charge_asymmetry_vs_threshold.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig_a, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig_a)
#
#         # --- 2. Inter-plane T_sum correlation ---
#         if task3_plot_enabled("interplane_timing_correlation"):
#             t_sum_corr_cols = {
#                 p: f"p{p}_tsum"
#                 for p in range(1, 5)
#                 if f"p{p}_tsum" in working_df.columns
#             }
#             plane_pairs = list(combinations(sorted(t_sum_corr_cols.keys()), 2))
#             # Use a sparse selection of thresholds to keep the figure readable.
#             corr_thrs = sorted(tt_task3_list_charge_thresholds)[::max(1, len(tt_task3_list_charge_thresholds) // 4)][:4]
#             if plane_pairs and corr_thrs:
#                 nrows_t = len(plane_pairs)
#                 ncols_t = len(corr_thrs)
#                 fig_t, axes_t = plt.subplots(
#                     nrows_t, ncols_t,
#                     figsize=(3.5 * max(1, ncols_t), 3.0 * max(1, nrows_t)),
#                     squeeze=False,
#                 )
#                 max_scatter_pts = int(config.get("interplane_timing_scatter_max_points", 80000))
#                 max_scatter_pts = max(2000, max_scatter_pts)
#                 for i_row, (pA, pB) in enumerate(plane_pairs):
#                     tA = pd.to_numeric(working_df[t_sum_corr_cols[pA]], errors="coerce").to_numpy(dtype=float)
#                     tB = pd.to_numeric(working_df[t_sum_corr_cols[pB]], errors="coerce").to_numpy(dtype=float)
#                     qA_col = f"p{pA}_qsum"
#                     qB_col = f"p{pB}_qsum"
#                     qA = pd.to_numeric(working_df.get(qA_col, pd.Series(dtype=float)), errors="coerce").to_numpy(dtype=float)
#                     qB = pd.to_numeric(working_df.get(qB_col, pd.Series(dtype=float)), errors="coerce").to_numpy(dtype=float)
#                     for j_col, thr in enumerate(corr_thrs):
#                         ax = axes_t[i_row, j_col]
#                         keep = (
#                             np.isfinite(tA) & np.isfinite(tB) &
#                             (tA != 0) & (tB != 0) &
#                             np.isfinite(qA) & np.isfinite(qB) &
#                             (qA > float(thr)) & (qB > float(thr))
#                         )
#                         n_keep = int(np.sum(keep))
#                         if n_keep < 5:
#                             ax.text(0.5, 0.5, "Too few", ha="center", va="center",
#                                     transform=ax.transAxes, fontsize=8)
#                             ax.grid(True, alpha=0.2)
#                             continue
#                         xv = tA[keep]
#                         yv = tB[keep]
#                         if n_keep > max_scatter_pts:
#                             sel = np.linspace(0, n_keep - 1, max_scatter_pts, dtype=int)
#                             xv, yv = xv[sel], yv[sel]
#                         ax.scatter(xv, yv, s=2, alpha=0.15, color="steelblue",
#                                    linewidths=0, rasterized=True)
#                         # Reference diagonal
#                         lo = min(float(np.nanmin(xv)), float(np.nanmin(yv)))
#                         hi = max(float(np.nanmax(xv)), float(np.nanmax(yv)))
#                         ax.plot([lo, hi], [lo, hi], "r--", linewidth=0.7, alpha=0.5)
#                         ax.grid(True, alpha=0.2)
#                         if i_row == 0:
#                             ax.set_title(f"Q > {thr:g}\nN={n_keep}", fontsize=9)
#                         if j_col == 0:
#                             ax.set_ylabel(f"P{pA}-P{pB}\nT_sum P{pB}", fontsize=9)
#                 for j_col in range(ncols_t):
#                     axes_t[-1, j_col].set_xlabel("T_sum (earlier plane)")
#                 fig_t.suptitle(
#                     "Inter-plane T_sum correlation vs threshold\n"
#                     "Noise: diffuse cloud; signal: tight diagonal band",
#                     fontsize=13,
#                 )
#                 fig_t.tight_layout(rect=[0, 0, 1, 0.93])
#                 if save_plots:
#                     final_filename = f"{fig_idx}_interplane_timing_correlation.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig_t, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig_t)
#
#         # --- 3. Multiplicity–charge landscape ---
#         if task3_plot_enabled("multiplicity_charge_landscape"):
#             q_land_cols = [f"p{p}_qsum" for p in range(1, 5) if f"p{p}_qsum" in working_df.columns]
#             if len(q_land_cols) >= 2:
#                 q_land = working_df[q_land_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
#                 scan_thrs_m = sorted(tt_task3_list_charge_thresholds)[:plane_charge_fraction_max_panels]
#                 ncols_m = len(scan_thrs_m)
#                 fig_m, axes_m = plt.subplots(
#                     1, ncols_m,
#                     figsize=(3.5 * max(1, ncols_m), 4.0),
#                     squeeze=False, sharey=True,
#                 )
#                 q_arr = q_land.to_numpy(dtype=float)
#                 hb = None
#                 for j_col, thr in enumerate(scan_thrs_m):
#                     ax = axes_m[0, j_col]
#                     active = q_arr > float(thr)
#                     n_active = active.sum(axis=1)
#                     # Minimum charge across active planes (nan where none active)
#                     masked = np.where(active, q_arr, np.nan)
#                     with np.errstate(all="ignore"):
#                         min_q = np.nanmin(masked, axis=1)
#                     valid = (n_active >= 1) & np.isfinite(min_q)
#                     if not np.any(valid):
#                         ax.text(0.5, 0.5, "No events", ha="center", va="center",
#                                 transform=ax.transAxes, fontsize=8)
#                         continue
#                     # 2D histogram
#                     mult_vals = n_active[valid].astype(float)
#                     min_q_vals = min_q[valid]
#                     q99 = float(np.nanpercentile(min_q_vals, 99))
#                     if not np.isfinite(q99) or q99 <= 0:
#                         q99 = float(thr * 5 + 50)
#                     hb = ax.hexbin(
#                         mult_vals, min_q_vals,
#                         gridsize=(4, 30), cmap="inferno",
#                         mincnt=1, extent=(0.5, 4.5, 0, q99),
#                     )
#                     ax.set_xticks([1, 2, 3, 4])
#                     ax.set_xlabel("Active planes")
#                     ax.set_title(f"Q > {thr:g}\nN={int(np.sum(valid))}", fontsize=9)
#                     ax.grid(True, alpha=0.2)
#                     if j_col == 0:
#                         ax.set_ylabel("Min Q_sum across\nactive planes")
#                 fig_m.suptitle(
#                     "Multiplicity–charge landscape vs threshold\n"
#                     "Noise: piles up at low multiplicity + low charge",
#                     fontsize=13,
#                 )
#                 fig_m.tight_layout(rect=[0, 0, 1, 0.92])
#                 if ncols_m > 0 and hb is not None:
#                     fig_m.colorbar(
#                         hb, ax=axes_m[0, -1], pad=0.02, label="Counts",
#                         shrink=0.85,
#                     )
#                 if save_plots:
#                     final_filename = f"{fig_idx}_multiplicity_charge_landscape.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig_m, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig_m)
#
#         # --- Charge by strip multiplicity (adj / dis events) ---
#         if task3_any_plot_enabled(
#             "charge_by_strip_multiplicity_adj",
#             "charge_by_strip_multiplicity_dis",
#         ):
#             _cbsm_have_adj_dis = len(_adj_dis_label_series) == len(working_df)
#             _cbsm_mult_colors = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
#             _cbsm_mult_labels = {1: "single", 2: "double", 3: "triple", 4: "quad"}
#
#             for _cbsm_label, _cbsm_alias in [
#                 ("adj", "charge_by_strip_multiplicity_adj"),
#                 ("dis", "charge_by_strip_multiplicity_dis"),
#             ]:
#                 if not task3_plot_enabled(_cbsm_alias):
#                     continue
#                 if not _cbsm_have_adj_dis:
#                     continue
#
#                 _cbsm_df = working_df.loc[_adj_dis_label_series == _cbsm_label]
#                 if _cbsm_df.empty:
#                     continue
#
#                 _cbsm_tt = pd.to_numeric(_cbsm_df["tt_task3_list"], errors="coerce").fillna(0).astype(int)
#                 _cbsm_present = set(_cbsm_tt.unique().tolist())
#                 _cbsm_ordered_tt = [tt for tt in ordered_tt_values if tt in _cbsm_present]
#                 _n_cbsm_cols = len(_cbsm_ordered_tt)
#                 if _n_cbsm_cols == 0:
#                     continue
#
#                 # Common x range from 99th percentile across all planes
#                 _cbsm_all_charges: list[np.ndarray] = []
#                 for p in range(1, 5):
#                     _cbsm_qcol = f"p{p}_qsum"
#                     if _cbsm_qcol in _cbsm_df.columns:
#                         _cbsm_qv = pd.to_numeric(_cbsm_df[_cbsm_qcol], errors="coerce").to_numpy(float)
#                         _cbsm_pos = _cbsm_qv[np.isfinite(_cbsm_qv) & (_cbsm_qv > 0)]
#                         if _cbsm_pos.size > 0:
#                             _cbsm_all_charges.append(_cbsm_pos)
#                 if _cbsm_all_charges:
#                     _cbsm_qmax = float(np.nanpercentile(np.concatenate(_cbsm_all_charges), 99.0))
#                 else:
#                     _cbsm_qmax = 100.0
#                 _cbsm_qmin = max(
#                     float(np.nanmin(np.concatenate(_cbsm_all_charges))) if _cbsm_all_charges else 0.1,
#                     0.1,
#                 )
#                 _cbsm_bins = np.logspace(np.log10(_cbsm_qmin), np.log10(max(_cbsm_qmax, _cbsm_qmin * 10)), 60)
#
#                 fig_cbsm, axes_cbsm = plt.subplots(
#                     4, _n_cbsm_cols,
#                     figsize=(max(2.5 * _n_cbsm_cols, 8), 12),
#                     sharex=True, sharey=True,
#                     squeeze=False,
#                 )
#
#                 for j_col, tt_val in enumerate(_cbsm_ordered_tt):
#                     _cbsm_mask_tt = _cbsm_tt == tt_val
#                     _cbsm_sub = _cbsm_df.loc[_cbsm_mask_tt]
#                     axes_cbsm[0, j_col].set_title(
#                         f"tt={tt_val}\nN={int(_cbsm_mask_tt.sum())}",
#                         fontsize=8,
#                     )
#                     for i_row, p in enumerate(range(1, 5)):
#                         ax = axes_cbsm[i_row, j_col]
#                         _cbsm_qcol = f"p{p}_qsum"
#                         _cbsm_scol = f"active_strips_P{p}"
#                         if _cbsm_qcol not in _cbsm_sub.columns or _cbsm_scol not in _cbsm_sub.columns:
#                             ax.text(0.5, 0.5, "N/A", ha="center", va="center",
#                                     transform=ax.transAxes, fontsize=9, color="gray")
#                             ax.set_axis_off()
#                             continue
#                         _cbsm_q = pd.to_numeric(_cbsm_sub[_cbsm_qcol], errors="coerce").to_numpy(float)
#                         _cbsm_s = _cbsm_sub[_cbsm_scol].astype(str).str.count("1").to_numpy(int)
#                         _cbsm_valid = np.isfinite(_cbsm_q) & (_cbsm_q > 0)
#                         for mult in [1, 2, 3, 4]:
#                             _cbsm_m = _cbsm_valid & (_cbsm_s == mult)
#                             if _cbsm_m.sum() == 0:
#                                 continue
#                             ax.hist(
#                                 _cbsm_q[_cbsm_m],
#                                 bins=_cbsm_bins,
#                                 histtype="step",
#                                 color=_cbsm_mult_colors[mult],
#                                 label=_cbsm_mult_labels[mult],
#                                 linewidth=1.2,
#                             )
#                         ax.set_xscale("log")
#                         ax.set_yscale("log")
#                         if j_col == 0:
#                             ax.set_ylabel(f"Plane {p}", fontsize=9)
#                         if i_row == 3:
#                             ax.set_xlabel("Q sum final [a.u.]", fontsize=8)
#                         ax.tick_params(labelsize=7)
#
#                 _cbsm_legend_handles = [
#                     plt.Line2D([0], [0], color=_cbsm_mult_colors[m], linewidth=1.5,
#                                label=_cbsm_mult_labels[m])
#                     for m in [1, 2, 3, 4]
#                 ]
#                 fig_cbsm.legend(
#                     handles=_cbsm_legend_handles,
#                     loc="upper right", fontsize=8,
#                     title="Strip mult.", title_fontsize=8,
#                     ncol=2,
#                 )
#                 _cbsm_title = "Adjacent" if _cbsm_label == "adj" else "Dispersed"
#                 fig_cbsm.suptitle(
#                     f"{_cbsm_title} events – charge by plane and strip multiplicity\n"
#                     f"Station {station}  (N={len(_cbsm_df):,})",
#                     fontsize=12,
#                 )
#                 fig_cbsm.tight_layout(rect=[0, 0, 1, 0.93])
#                 if save_plots:
#                     final_filename = f"{fig_idx}_{_cbsm_alias}.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig_cbsm, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig_cbsm)
#
#         # -----------------------------------------------------------------
#         # Streamer investigation block
#         # -----------------------------------------------------------------
#         streamer_q_cols = [
#             f"p{p}_qsum" for p in range(1, 5)
#             if f"p{p}_qsum" in working_df.columns
#         ]
#         streamer_thr = task3_streamer_threshold
#
#         plane_q_arr: dict[int, np.ndarray] = {}
#         plane_is_active: dict[int, np.ndarray] = {}
#         plane_is_streamer: dict[int, np.ndarray] = {}
#         any_streamer = np.zeros(len(working_df), dtype=bool)
#         n_streamer_planes = np.zeros(len(working_df), dtype=int)
#         for p in range(1, 5):
#             col = f"p{p}_qsum"
#             if col not in working_df.columns:
#                 continue
#
#             arr = pd.to_numeric(working_df[col], errors="coerce").to_numpy(dtype=float)
#             plane_q_arr[p] = arr
#             plane_active = np.isfinite(arr) & (arr > 0)
#             plane_is_active[p] = plane_active
#
#             if streamer_thr is None:
#                 continue
#
#             plane_streamer = task3_topology_digits_by_plane.get(
#                 p,
#                 np.zeros(len(working_df), dtype=np.int8),
#             ) == 2
#             plane_is_streamer[p] = plane_streamer
#             any_streamer |= plane_streamer
#             n_streamer_planes += plane_streamer.astype(int)
#
#         streamer_plots_requested = task3_any_plot_enabled(
#             "streamer_charge_histograms",
#             "streamer_prevalence_by_plane",
#             "streamer_multiplicity",
#             "streamer_contagion_matrix",
#             "streamer_efficiency_comparison",
#         )
#
#         plane_is_high_charge: dict[int, np.ndarray] = {}
#         streamer_high_charge_limit = None
#         if streamer_thr is not None and plane_is_streamer:
#             streamer_high_charge_limit = float(streamer_thr) * float(streamer_high_charge_factor)
#             for p, arr in plane_q_arr.items():
#                 plane_is_high_charge[p] = plane_is_active[p] & (arr > streamer_high_charge_limit)
#
#         if streamer_plots_requested:
#             if streamer_thr is not None:
#                 print(
#                     f"Task 3 streamer threshold ({task3_streamer_threshold_source}) "
#                     f"= {streamer_thr:.1f}"
#                 )
#
#                 # --- Plot 0: Per-plane charge histogram with streamer line ---
#                 if task3_plot_enabled("streamer_charge_histograms"):
#                     plane_colors_h = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
#                     fig_sh, axes_sh = plt.subplots(2, 2, figsize=(12, 9))
#                     axes_sh = axes_sh.flatten()
#                     for idx_p, p in enumerate(sorted(plane_q_arr.keys())):
#                         ax = axes_sh[idx_p]
#                         vals = plane_q_arr[p]
#                         valid = np.isfinite(vals) & (vals > 0)
#                         if not np.any(valid):
#                             ax.text(0.5, 0.5, "No data", ha="center", va="center",
#                                     transform=ax.transAxes)
#                             continue
#                         v = vals[valid]
#                         q_max = float(np.nanpercentile(v, 99.9))
#                         ax.hist(
#                             v, bins=150, range=(0, q_max),
#                             color=plane_colors_h[p], alpha=0.75,
#                             edgecolor="none", log=True,
#                         )
#                         ax.axvline(
#                             streamer_thr, color="red", linestyle="--", linewidth=1.8,
#                             label=f"Streamer boundary = {streamer_thr:.1f}",
#                         )
#                         n_str = int(np.sum(valid & (vals > streamer_thr)))
#                         n_tot = int(np.sum(valid))
#                         ax.set_xlabel("Q_sum_final")
#                         ax.set_ylabel("Counts (log)")
#                         ax.set_title(
#                             f"Plane {p}  (N={n_tot}, streamers={n_str}, "
#                             f"{100*n_str/n_tot:.1f}%)"
#                         )
#                         ax.legend(fontsize=9)
#                         ax.grid(True, alpha=0.2, which="both")
#                     fig_sh.suptitle(
#                         "Per-plane charge spectrum with streamer boundary",
#                         fontsize=14,
#                     )
#                     fig_sh.tight_layout(rect=[0, 0, 1, 0.95])
#                     if save_plots:
#                         final_filename = f"{fig_idx}_streamer_charge_histograms.png"
#                         fig_idx += 1
#                         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                         plot_list.append(save_fig_path)
#                         save_plot_figure(save_fig_path, fig=fig_sh, format="png", dpi=150)
#                     if show_plots:
#                         plt.show()
#                     plt.close(fig_sh)
#
#                 # --- Plot 1: Streamer prevalence by plane ---
#                 if task3_plot_enabled("streamer_prevalence_by_plane"):
#                     plane_colors_s = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
#                     fig_sp, ax_sp = plt.subplots(figsize=(8, 5))
#                     for p in sorted(plane_is_streamer.keys()):
#                         fracs = []
#                         for thr in sorted(tt_task3_list_charge_thresholds):
#                             active_mask = plane_q_arr[p] > float(thr)
#                             n_act = int(np.sum(active_mask))
#                             n_str = int(np.sum(active_mask & plane_is_streamer[p]))
#                             fracs.append(n_str / n_act if n_act > 0 else np.nan)
#                         ax_sp.plot(
#                             sorted(tt_task3_list_charge_thresholds), fracs,
#                             "o-", color=plane_colors_s[p], label=f"Plane {p}",
#                             markersize=4, linewidth=1.5,
#                         )
#                     ax_sp.set_xlabel("Lower charge threshold")
#                     ax_sp.set_ylabel("Fraction of active hits that are streamers")
#                     ax_sp.set_title(
#                         f"Streamer prevalence by plane (auto threshold = {streamer_thr:.1f})"
#                     )
#                     ax_sp.legend()
#                     ax_sp.grid(True, alpha=0.25)
#                     ax_sp.set_ylim(bottom=0)
#                     fig_sp.tight_layout()
#                     if save_plots:
#                         final_filename = f"{fig_idx}_streamer_prevalence_by_plane.png"
#                         fig_idx += 1
#                         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                         plot_list.append(save_fig_path)
#                         save_plot_figure(save_fig_path, fig=fig_sp, format="png", dpi=150)
#                     if show_plots:
#                         plt.show()
#                     plt.close(fig_sp)
#
#                 # --- Plot 2: Streamer multiplicity histogram (excluding 0) ---
#                 if task3_plot_enabled("streamer_multiplicity"):
#                     # Only among events with at least one streamer
#                     mult_vals = n_streamer_planes[any_streamer]
#                     n_with_streamer = int(np.sum(any_streamer))
#                     n_total_events = int(len(working_df))
#
#                     fig_sm, ax_sm = plt.subplots(figsize=(7, 5))
#                     bins_m = np.arange(0.5, 5.5, 1)
#                     counts_m, _, patches_m = ax_sm.hist(
#                         mult_vals, bins=bins_m, color="steelblue",
#                         edgecolor="white", alpha=0.85,
#                     )
#                     for i_b, count_val in enumerate(counts_m):
#                         if count_val > 0:
#                             frac_pct = 100.0 * count_val / n_total_events if n_total_events > 0 else 0.0
#                             ax_sm.text(
#                                 i_b + 1, count_val, f"{frac_pct:.1f}%",
#                                 ha="center", va="bottom", fontsize=9,
#                             )
#                     ax_sm.set_xticks([1, 2, 3, 4])
#                     ax_sm.set_xlabel("Number of planes with streamer")
#                     ax_sm.set_ylabel("Events")
#                     ax_sm.set_title(
#                         f"Streamer multiplicity among streamer events "
#                         f"(threshold = {streamer_thr:.1f}, N_streamer={n_with_streamer}, N_total={n_total_events})"
#                     )
#                     ax_sm.grid(True, alpha=0.25, axis="y")
#                     fig_sm.tight_layout()
#                     if save_plots:
#                         final_filename = f"{fig_idx}_streamer_multiplicity.png"
#                         fig_idx += 1
#                         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                         plot_list.append(save_fig_path)
#                         save_plot_figure(save_fig_path, fig=fig_sm, format="png", dpi=150)
#                     if show_plots:
#                         plt.show()
#                     plt.close(fig_sm)
#
#                 # --- Plot 3: Streamer contagion matrix ---
#                 if task3_plot_enabled("streamer_contagion_matrix"):
#                     planes_list = sorted(plane_is_streamer.keys())
#                     n_planes = len(planes_list)
#                     cond_prob = np.full((n_planes, n_planes), np.nan)
#                     for i, pi in enumerate(planes_list):
#                         mask_i = plane_is_streamer[pi]
#                         n_i = int(np.sum(mask_i))
#                         if n_i == 0:
#                             continue
#                         for j, pj in enumerate(planes_list):
#                             if i == j:
#                                 cond_prob[i, j] = 1.0
#                             else:
#                                 cond_prob[i, j] = float(np.sum(mask_i & plane_is_streamer[pj])) / n_i
#
#                     fig_sc, ax_sc = plt.subplots(figsize=(6, 5))
#                     im_sc = ax_sc.imshow(cond_prob, cmap="YlOrRd", vmin=0, vmax=1, aspect="equal")
#                     ax_sc.set_xticks(range(n_planes))
#                     ax_sc.set_xticklabels([f"P{p}" for p in planes_list])
#                     ax_sc.set_yticks(range(n_planes))
#                     ax_sc.set_yticklabels([f"P{p}" for p in planes_list])
#                     ax_sc.set_xlabel("Target plane (streamer?)")
#                     ax_sc.set_ylabel("Given streamer in this plane")
#                     for i in range(n_planes):
#                         for j in range(n_planes):
#                             val = cond_prob[i, j]
#                             if np.isfinite(val):
#                                 text_color = "white" if val > 0.6 else "black"
#                                 ax_sc.text(
#                                     j, i, f"{val:.2f}", ha="center", va="center",
#                                     fontsize=11, color=text_color,
#                                 )
#                     fig_sc.colorbar(im_sc, ax=ax_sc, label="P(streamer in target | streamer in given)")
#                     ax_sc.set_title(
#                         f"Streamer contagion matrix (threshold = {streamer_thr:.1f})"
#                     )
#                     fig_sc.tight_layout()
#                     if save_plots:
#                         final_filename = f"{fig_idx}_streamer_contagion_matrix.png"
#                         fig_idx += 1
#                         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                         plot_list.append(save_fig_path)
#                         save_plot_figure(save_fig_path, fig=fig_sc, format="png", dpi=150)
#                     if show_plots:
#                         plt.show()
#                     plt.close(fig_sc)
#
#                 # --- Plot 4: Efficiency with vs without streamers ---
#                 if task3_plot_enabled("streamer_efficiency_comparison"):
#                     plane_colors_e = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
#                     policy_specs = (
#                         (
#                             "Streamers counted as avalanche",
#                             "streamer_as_avalanche",
#                             task3_topology_tt_streamer_as_avalanche,
#                             "tab:blue",
#                         ),
#                         (
#                             "Streamers counted as invalid",
#                             "streamer_as_invalid",
#                             task3_topology_tt_streamer_as_invalid,
#                             "tab:red",
#                         ),
#                         (
#                             "Streamers invalid, no transference",
#                             "streamer_as_invalid_no_transference",
#                             task3_topology_tt_streamer_as_invalid_no_transference,
#                             "tab:green",
#                         ),
#                     )
#                     missing_plane_tt_label = {1: "234", 2: "134", 3: "124", 4: "123"}
#                     fig_se, axes_se = plt.subplots(1, 2, figsize=(12, 5.5), sharey=False)
#                     x_positions = np.arange(1, 5, dtype=float)
#                     offsets = {
#                         "streamer_as_avalanche": -0.18,
#                         "streamer_as_invalid": 0.0,
#                         "streamer_as_invalid_no_transference": 0.18,
#                     }
#                     efficiency_by_policy: dict[str, list[float]] = {}
#                     excluded_count_by_policy: dict[str, int] = {}
#
#                     for label, policy_name, tt_series, color in policy_specs:
#                         tt_counts = tt_series.value_counts()
#                         excluded_count_by_policy[policy_name] = int(tt_series.isna().sum())
#                         per_plane_eff = compute_empirical_efficiency_from_tt_counts(tt_counts)
#                         eff_values: list[float] = []
#                         err_values: list[float] = []
#                         n_four = int(tt_counts.get(1234, 0))
#                         for plane in range(1, 5):
#                             eff_value, eff_error, n_three, _ = per_plane_eff[plane]
#                             eff_values.append(float(eff_value))
#                             err_values.append(float(eff_error))
#                             if np.isfinite(eff_value):
#                                 axes_se[0].errorbar(
#                                     [plane + offsets[policy_name]],
#                                     [eff_value],
#                                     yerr=[eff_error] if np.isfinite(eff_error) else None,
#                                     fmt="o",
#                                     markersize=7,
#                                     capsize=4,
#                                     color=color,
#                                     label=label if plane == 1 else None,
#                                 )
#                                 axes_se[0].annotate(
#                                     f"N({missing_plane_tt_label[plane]})={n_three}\nN(1234)={n_four}",
#                                     (plane + offsets[policy_name], eff_value),
#                                     xytext=(
#                                         0,
#                                         11 if policy_name == "streamer_as_avalanche"
#                                         else (-30 if policy_name == "streamer_as_invalid" else 14),
#                                     ),
#                                     textcoords="offset points",
#                                     ha="center",
#                                     fontsize=7,
#                                     color=color,
#                                 )
#                         efficiency_by_policy[policy_name] = eff_values
#                         axes_se[0].plot(
#                             x_positions + offsets[policy_name],
#                             eff_values,
#                             "-",
#                             color=color,
#                             linewidth=1.5,
#                             alpha=0.85,
#                         )
#
#                     delta_eff_invalid = (
#                         np.asarray(efficiency_by_policy.get("streamer_as_avalanche", [np.nan] * 4), dtype=float)
#                         - np.asarray(efficiency_by_policy.get("streamer_as_invalid", [np.nan] * 4), dtype=float)
#                     )
#                     delta_eff_no_transfer = (
#                         np.asarray(efficiency_by_policy.get("streamer_as_avalanche", [np.nan] * 4), dtype=float)
#                         - np.asarray(
#                             efficiency_by_policy.get("streamer_as_invalid_no_transference", [np.nan] * 4),
#                             dtype=float,
#                         )
#                     )
#                     axes_se[1].bar(
#                         x_positions - 0.12,
#                         delta_eff_invalid,
#                         width=0.22,
#                         color="tab:red",
#                         alpha=0.75,
#                         label="Avalanche - invalid",
#                     )
#                     axes_se[1].bar(
#                         x_positions + 0.12,
#                         delta_eff_no_transfer,
#                         width=0.22,
#                         color="tab:green",
#                         alpha=0.75,
#                         label="Avalanche - invalid no transfer",
#                     )
#                     axes_se[1].axhline(0, color="black", linestyle="--", linewidth=0.8)
#
#                     axes_se[0].set_xlabel("Plane")
#                     axes_se[0].set_ylabel("Empirical efficiency")
#                     axes_se[0].set_xticks([1, 2, 3, 4])
#                     axes_se[0].set_ylim(0, 1.05)
#                     axes_se[0].grid(True, alpha=0.25)
#                     axes_se[0].legend(fontsize=8)
#                     axes_se[0].set_title("Per-plane efficiency by streamer policy")
#
#                     axes_se[1].set_xlabel("Plane")
#                     axes_se[1].set_ylabel("Efficiency difference")
#                     axes_se[1].set_xticks([1, 2, 3, 4])
#                     axes_se[1].grid(True, alpha=0.25, axis="y")
#                     axes_se[1].legend(fontsize=8)
#                     axes_se[1].set_title("Delta relative to avalanche policy")
#
#                     fig_se.suptitle(
#                         "Efficiency from topology code under streamer treatment\n"
#                         f"(streamer threshold = {streamer_thr:.1f}, source = {task3_streamer_threshold_source}, "
#                         f"events with any streamer = {int(np.sum(any_streamer))}/{len(working_df)}, "
#                         f"excluded in no-transfer = "
#                         f"{excluded_count_by_policy.get('streamer_as_invalid_no_transference', 0)})",
#                         fontsize=13,
#                     )
#                     fig_se.tight_layout(rect=[0, 0, 1, 0.93])
#                     if save_plots:
#                         final_filename = f"{fig_idx}_streamer_efficiency_comparison.png"
#                         fig_idx += 1
#                         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                         plot_list.append(save_fig_path)
#                         save_plot_figure(save_fig_path, fig=fig_se, format="png", dpi=150)
#                     if show_plots:
#                         plt.show()
#                     plt.close(fig_se)
#
#             else:
#                 print("Streamer auto-detection: no valley found in Q_sum spectrum. Skipping streamer plots.")
#
#         # -----------------------------------------------------------------
#         # Efficiency anatomy block — probing the dip mechanism
#         # -----------------------------------------------------------------
#
#         # --- Weakest-plane charge distribution for 4-plane events ---
#         if task3_plot_enabled("fourplane_weakest_charge"):
#             q_anat_cols = [
#                 f"p{p}_qsum" for p in range(1, 5)
#                 if f"p{p}_qsum" in working_df.columns
#             ]
#             if len(q_anat_cols) == 4:
#                 q_anat = working_df[q_anat_cols].apply(pd.to_numeric, errors="coerce")
#                 q_arr_a = q_anat.to_numpy(dtype=float)
#                 # 4-plane events: all planes have Q > 0
#                 is_4plane = np.all((q_arr_a > 0) & np.isfinite(q_arr_a), axis=1)
#                 if np.any(is_4plane):
#                     q_4p = q_arr_a[is_4plane]
#                     q_min_per_event = np.min(q_4p, axis=1)
#                     q_max_per_event = np.max(q_4p, axis=1)
#                     q_ratio = q_min_per_event / np.where(q_max_per_event > 0, q_max_per_event, np.nan)
#
#                     fig_wc, axes_wc = plt.subplots(1, 3, figsize=(16, 5))
#
#                     # Panel 1: min(Q) histogram
#                     ax = axes_wc[0]
#                     q99 = float(np.nanpercentile(q_min_per_event, 99))
#                     ax.hist(q_min_per_event, bins=100, range=(0, max(q99, 1)),
#                             color="steelblue", edgecolor="none", alpha=0.8, log=True)
#                     ax.set_xlabel("Weakest-plane Q_sum")
#                     ax.set_ylabel("4-plane events (log)")
#                     ax.set_title(f"Min charge across 4 planes\n(N={int(np.sum(is_4plane))})")
#                     ax.grid(True, alpha=0.2, which="both")
#
#                     # Panel 2: max(Q) histogram for context
#                     ax = axes_wc[1]
#                     q99h = float(np.nanpercentile(q_max_per_event, 99))
#                     ax.hist(q_max_per_event, bins=100, range=(0, max(q99h, 1)),
#                             color="coral", edgecolor="none", alpha=0.8, log=True)
#                     ax.set_xlabel("Strongest-plane Q_sum")
#                     ax.set_ylabel("4-plane events (log)")
#                     ax.set_title("Max charge across 4 planes")
#                     ax.grid(True, alpha=0.2, which="both")
#
#                     # Panel 3: Q_min / Q_max ratio
#                     ax = axes_wc[2]
#                     valid_ratio = q_ratio[np.isfinite(q_ratio)]
#                     if valid_ratio.size > 0:
#                         ax.hist(valid_ratio, bins=80, range=(0, 1),
#                                 color="mediumpurple", edgecolor="none", alpha=0.8, log=True)
#                     ax.set_xlabel("Q_min / Q_max")
#                     ax.set_ylabel("4-plane events (log)")
#                     ax.set_title("Charge balance (1 = uniform, →0 = one weak plane)")
#                     ax.grid(True, alpha=0.2, which="both")
#
#                     fig_wc.suptitle(
#                         "4-plane events: weakest-plane charge anatomy\n"
#                         "Crosstalk/noise → excess at low Q_min and low Q_min/Q_max",
#                         fontsize=13,
#                     )
#                     fig_wc.tight_layout(rect=[0, 0, 1, 0.92])
#                     if save_plots:
#                         final_filename = f"{fig_idx}_fourplane_weakest_charge.png"
#                         fig_idx += 1
#                         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                         plot_list.append(save_fig_path)
#                         save_plot_figure(save_fig_path, fig=fig_wc, format="png", dpi=150)
#                     if show_plots:
#                         plt.show()
#                     plt.close(fig_wc)
#
#         # --- Which plane is weakest in 4-plane events vs threshold ---
#         if task3_plot_enabled("fourplane_weakest_plane_identity"):
#             q_anat_cols = [
#                 f"p{p}_qsum" for p in range(1, 5)
#                 if f"p{p}_qsum" in working_df.columns
#             ]
#             if len(q_anat_cols) == 4:
#                 q_anat = working_df[q_anat_cols].apply(pd.to_numeric, errors="coerce")
#                 q_arr_a = q_anat.to_numpy(dtype=float)
#                 plane_colors_w = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
#
#                 scan_thrs = sorted(tt_task3_list_charge_thresholds)
#                 fig_wp, axes_wp = plt.subplots(1, 2, figsize=(14, 5.5))
#
#                 # Left: fraction of 4-plane events where each plane is the weakest
#                 ax_left = axes_wp[0]
#                 for p_idx in range(4):
#                     fracs = []
#                     for thr in scan_thrs:
#                         above = (q_arr_a > float(thr)) & np.isfinite(q_arr_a)
#                         is_4p = np.all(above, axis=1)
#                         n_4p = int(np.sum(is_4p))
#                         if n_4p == 0:
#                             fracs.append(np.nan)
#                             continue
#                         argmin_plane = np.argmin(q_arr_a[is_4p], axis=1)
#                         fracs.append(float(np.sum(argmin_plane == p_idx)) / n_4p)
#                     ax_left.plot(
#                         scan_thrs, fracs, "o-",
#                         color=plane_colors_w[p_idx + 1],
#                         label=f"Plane {p_idx + 1}", markersize=4, linewidth=1.5,
#                     )
#                 ax_left.axhline(0.25, color="grey", linestyle=":", linewidth=1, alpha=0.6,
#                                 label="Uniform (0.25)")
#                 ax_left.set_xlabel("Lower charge threshold")
#                 ax_left.set_ylabel("Fraction of 4-plane events\nwhere this plane is weakest")
#                 ax_left.set_title("Which plane is weakest?")
#                 ax_left.legend(fontsize=8)
#                 ax_left.grid(True, alpha=0.25)
#                 ax_left.set_ylim(0, 0.65)
#
#                 # Right: for events that transition 4-plane→3-plane between
#                 # consecutive thresholds, which plane dropped out?
#                 ax_right = axes_wp[1]
#                 for p_idx in range(4):
#                     dropout_fracs = []
#                     for k in range(len(scan_thrs) - 1):
#                         thr_lo = float(scan_thrs[k])
#                         thr_hi = float(scan_thrs[k + 1])
#                         above_lo = (q_arr_a > thr_lo) & np.isfinite(q_arr_a)
#                         above_hi = (q_arr_a > thr_hi) & np.isfinite(q_arr_a)
#                         was_4p = np.all(above_lo, axis=1)
#                         now_3p = was_4p & (above_hi.sum(axis=1) == 3)
#                         n_trans = int(np.sum(now_3p))
#                         if n_trans == 0:
#                             dropout_fracs.append(np.nan)
#                             continue
#                         # Which plane dropped: was active at lo, inactive at hi
#                         dropped = above_lo[now_3p] & ~above_hi[now_3p]
#                         dropout_fracs.append(float(np.sum(dropped[:, p_idx])) / n_trans)
#                     # Plot at midpoint of threshold interval
#                     midpoints = [0.5 * (scan_thrs[k] + scan_thrs[k + 1]) for k in range(len(scan_thrs) - 1)]
#                     ax_right.plot(
#                         midpoints, dropout_fracs, "s-",
#                         color=plane_colors_w[p_idx + 1],
#                         label=f"Plane {p_idx + 1}", markersize=4, linewidth=1.5,
#                     )
#                 ax_right.axhline(0.25, color="grey", linestyle=":", linewidth=1, alpha=0.6,
#                                  label="Uniform (0.25)")
#                 ax_right.set_xlabel("Threshold midpoint")
#                 ax_right.set_ylabel("Fraction of 4→3 transitions\nwhere this plane dropped")
#                 ax_right.set_title("Which plane drops out first?")
#                 ax_right.legend(fontsize=8)
#                 ax_right.grid(True, alpha=0.25)
#                 ax_right.set_ylim(0, 0.65)
#
#                 fig_wp.suptitle(
#                     "4-plane event anatomy: weakest plane identity\n"
#                     "Crosstalk target → one plane disproportionately weak / drops first",
#                     fontsize=13,
#                 )
#                 fig_wp.tight_layout(rect=[0, 0, 1, 0.91])
#                 if save_plots:
#                     final_filename = f"{fig_idx}_fourplane_weakest_plane_identity.png"
#                     fig_idx += 1
#                     save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                     plot_list.append(save_fig_path)
#                     save_plot_figure(save_fig_path, fig=fig_wp, format="png", dpi=150)
#                 if show_plots:
#                     plt.show()
#                 plt.close(fig_wp)
#
#         # --- Efficiency anatomy by charge band ---
#         if task3_plot_enabled("efficiency_anatomy_by_charge_band"):
#             q_anat_cols = [
#                 f"p{p}_qsum" for p in range(1, 5)
#                 if f"p{p}_qsum" in working_df.columns
#             ]
#             if len(q_anat_cols) == 4:
#                 q_anat = working_df[q_anat_cols].apply(pd.to_numeric, errors="coerce")
#                 q_arr_a = q_anat.to_numpy(dtype=float)
#                 # Q_min across active planes (planes with Q > 0)
#                 q_active = np.where((q_arr_a > 0) & np.isfinite(q_arr_a), q_arr_a, np.nan)
#                 with np.errstate(all="ignore"):
#                     q_min_all = np.nanmin(q_active, axis=1)
#
#                 # Define charge bands from data quantiles
#                 valid_qmin = q_min_all[np.isfinite(q_min_all) & (q_min_all > 0)]
#                 if valid_qmin.size > 100:
#                     band_edges = [0.0] + [
#                         float(np.nanpercentile(valid_qmin, p))
#                         for p in (25, 50, 75)
#                     ] + [float(np.nanmax(valid_qmin)) + 1.0]
#                     # Remove duplicate edges
#                     band_edges = sorted(set(band_edges))
#                     if len(band_edges) < 3:
#                         band_edges = [0.0, float(np.nanmedian(valid_qmin)), float(np.nanmax(valid_qmin)) + 1.0]
#
#                     n_bands = len(band_edges) - 1
#                     plane_colors_b = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
#                     fig_ea, axes_ea = plt.subplots(1, n_bands, figsize=(5.5 * n_bands, 5.5),
#                                                    sharey=True, squeeze=False)
#
#                     scan_thrs = sorted(tt_task3_list_charge_thresholds)
#                     for b_idx in range(n_bands):
#                         ax = axes_ea[0, b_idx]
#                         lo = band_edges[b_idx]
#                         hi = band_edges[b_idx + 1]
#                         # Events whose Q_min (at threshold=0) falls in this band
#                         in_band = np.isfinite(q_min_all) & (q_min_all > lo) & (q_min_all <= hi)
#                         n_band = int(np.sum(in_band))
#                         band_df = working_df.loc[in_band, q_anat_cols]
#
#                         for plane in (1, 2, 3, 4):
#                             effs = []
#                             for thr in scan_thrs:
#                                 tt_s = compute_qsum_threshold_tt(band_df, thr)
#                                 tt_c = tt_s.value_counts()
#                                 per_p = compute_empirical_efficiency_from_tt_counts(tt_c)
#                                 eff, err, _, _ = per_p[plane]
#                                 effs.append(float(eff))
#                             ax.plot(
#                                 scan_thrs, effs, "o-",
#                                 color=plane_colors_b[plane],
#                                 label=f"Plane {plane}", markersize=3.5, linewidth=1.3,
#                             )
#                         ax.set_xlabel("Charge threshold")
#                         if b_idx == 0:
#                             ax.set_ylabel("Empirical efficiency")
#                         ax.set_title(
#                             f"Q_min band ({lo:.0f}, {hi:.0f}]\nN = {n_band}",
#                             fontsize=10,
#                         )
#                         ax.legend(fontsize=7)
#                         ax.grid(True, alpha=0.25)
#                         ax.set_ylim(0, 1.05)
#
#                     fig_ea.suptitle(
#                         "Efficiency anatomy: threshold scan split by weakest-plane charge band\n"
#                         "Low Q_min → noise/crosstalk candidates; high Q_min → clean signal",
#                         fontsize=13,
#                     )
#                     fig_ea.tight_layout(rect=[0, 0, 1, 0.90])
#                     if save_plots:
#                         final_filename = f"{fig_idx}_efficiency_anatomy_by_charge_band.png"
#                         fig_idx += 1
#                         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                         plot_list.append(save_fig_path)
#                         save_plot_figure(save_fig_path, fig=fig_ea, format="png", dpi=150)
#                     if show_plots:
#                         plt.show()
#                     plt.close(fig_ea)

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: FINAL/report plot block moved to standalone final plotting (acquisition_rate_vs_time_by_task_tt_with_histograms)
# ============================================================================
# if save_plots and task3_plot_enabled("acquisition_rate_vs_time_by_task_tt_with_histograms"):
#     rate_fig = create_rate_vs_time_by_task_tt_with_histograms(
#         working_df,
#         tt_column="tt_task3_list",
#         title=(
#             f"Task 3 acquisition rate by tt_task3_list, {basename_no_ext} "
#             f"(files processed={len(joined_input_records)})"
#         ),
#         accumulation_window_seconds=config.get("acquisition_rate_accumulation_window_seconds", 60),
#         rate_histogram_bins=config.get("acquisition_rate_task_tt_histogram_bins", 80),
#         y_limit_left=config.get("acquisition_rate_task_tt_ylim_left", 0),
#         y_limit_right=config.get("acquisition_rate_task_tt_ylim_right", 4),
#     )
#     if rate_fig is not None:
#         final_filename = f"{fig_idx}_acquisition_rate_vs_time_by_task_tt_with_histograms.png"
#         fig_idx += 1
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, fig=rate_fig, dpi=140)
#         plt.close(rate_fig)
#     else:
#         print("Task 3 acquisition-rate-by-task-tt plot skipped: no valid tt_task3_list/datetime rows.")

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: runtime PDF branch disabled by the PNG-only runtime plotting contract
# ============================================================================
#     if globals().get("create_pdf", False) and direct_pdf_path:
#         if _direct_pdf_pages is None:
#             _direct_pdf_target_path = str(direct_pdf_path)
#             _direct_pdf_temp_path = _build_temp_pdf_path(_direct_pdf_target_path)
#             _direct_pdf_pages = PdfPages(_direct_pdf_temp_path)
#         pdf_kwargs = dict(savefig_kwargs)
#         dpi = int(pdf_kwargs.pop("dpi", 150))
#         pdf_kwargs.pop("format", None)
#         pdf_save_rasterized_page(_direct_pdf_pages, target_fig, dpi=dpi, **pdf_kwargs)
#         _direct_pdf_page_count += 1
#         return

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: runtime PDF branch disabled by the PNG-only runtime plotting contract
# ============================================================================
#     if not create_pdf:
#         close_direct_pdf_writer()
#         if os.path.exists(figure_directory):
#             shutil.rmtree(figure_directory)
#         return

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: plot_task3_filtered_rpc_tsum_vs_qsum
# ============================================================================
# def plot_task3_filtered_rpc_tsum_vs_qsum(
#     df_input: pd.DataFrame,
#     fig_idx_value: int,
#     *,
#     plot_kind: str,
#     charge_threshold: float,
#     figure_directory: str,
#     show_plots: bool,
#     save_plots: bool,
#     plot_list: list[str],
# ) -> int:
#     fig, axes = plt.subplots(2, 2, figsize=(12, 10))
#     axes = np.asarray(axes).reshape(2, 2)
#
#     for i_plane in range(1, 5):
#         ax = axes.flat[i_plane - 1]
#         t_sum_col = f"p{i_plane}_tsum"
#         t_dif_col = f"p{i_plane}_tdif"
#         q_sum_col = f"p{i_plane}_qsum"
#         q_dif_col = f"p{i_plane}_qdif"
#         y_col = f"p{i_plane}_ypos"
#         required_cols = [t_sum_col, t_dif_col, q_sum_col, q_dif_col, y_col]
#
#         if not all(col in df_input.columns for col in required_cols):
#             ax.set_visible(False)
#             continue
#
#         valid_rows = df_input[required_cols].replace(0, np.nan).dropna()
#         filtered_rows = valid_rows.loc[valid_rows[q_sum_col] < charge_threshold]
#         t_sum = filtered_rows[t_sum_col]
#         q_sum = filtered_rows[q_sum_col]
#         title = f"Plane {i_plane}: {t_sum_col} vs {q_sum_col}"
#
#         if plot_kind == "hexbin":
#             _task3_plot_quantile_hexbin(ax, t_sum, q_sum, title, gridsize=50, cmap="turbo")
#         else:
#             _task3_plot_quantile_scatter(ax, t_sum, q_sum, title)
#
#         ax.set_xlabel(t_sum_col)
#         ax.set_ylabel(q_sum_col)
#         ax.grid(True, alpha=0.25)
#
#     plt.tight_layout()
#     plt.subplots_adjust(top=0.92)
#     plt.suptitle(f"Filtered RPC T_sum vs Q_sum by plane ({plot_kind})", fontsize=18)
#
#     if save_plots:
#         name_of_file = f"filtered_rpc_tsum_vs_qsum_{plot_kind}"
#         final_filename = f"{fig_idx_value}_{name_of_file}.png"
#         fig_idx_value += 1
#         save_fig_path = os.path.join(figure_directory, final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format="png")
#
#     if show_plots:
#         plt.show()
#     plt.close(fig)
#     return fig_idx_value

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: plot_task3_filtered_rpc_tsum_vs_qsum_per_combination
# ============================================================================
# def plot_task3_filtered_rpc_tsum_vs_qsum_per_combination(
#     df_input: pd.DataFrame,
#     fig_idx_value: int,
#     *,
#     charge_threshold: float,
#     figure_directory: str,
#     show_plots: bool,
#     save_plots: bool,
#     plot_list: list[str],
#     basename: str,
# ) -> int:
#     tt_column = "tt_task3_list" if "tt_task3_list" in df_input.columns else "tt_task2_cal"
#     if tt_column not in df_input.columns:
#         print(
#             "Warning: cannot create filtered_rpc_tsum_vs_qsum_scatter_per_combination "
#             "because neither 'tt_task3_list' nor 'tt_task2_cal' exists."
#         )
#         return fig_idx_value
#
#     target_tt_labels = ["1234", "123", "234", "12", "23", "34"]
#     tt_labels = df_input[tt_column].map(normalize_tt_label)
#     fig, axes = plt.subplots(
#         len(target_tt_labels),
#         4,
#         figsize=(20, 24),
#         sharex=False,
#         sharey=False,
#         squeeze=False,
#     )
#
#     for row_idx, tt_label in enumerate(target_tt_labels):
#         tt_mask = tt_labels == tt_label
#         for col_idx, i_plane in enumerate(range(1, 5)):
#             ax = axes[row_idx, col_idx]
#             t_sum_col = f"p{i_plane}_tsum"
#             t_dif_col = f"p{i_plane}_tdif"
#             q_sum_col = f"p{i_plane}_qsum"
#             q_dif_col = f"p{i_plane}_qdif"
#             y_col = f"p{i_plane}_ypos"
#             required_cols = [t_sum_col, t_dif_col, q_sum_col, q_dif_col, y_col]
#
#             if not all(col in df_input.columns for col in required_cols):
#                 ax.text(
#                     0.5,
#                     0.5,
#                     "Missing columns",
#                     ha="center",
#                     va="center",
#                     transform=ax.transAxes,
#                 )
#                 ax.set_title(f"TT={tt_label}, P{i_plane}, N=0")
#                 ax.grid(True, alpha=0.25)
#                 continue
#
#             valid_rows = df_input.loc[tt_mask, required_cols].replace(0, np.nan).dropna()
#             filtered_rows = valid_rows.loc[valid_rows[q_sum_col] < charge_threshold]
#             t_sum = pd.to_numeric(filtered_rows[t_sum_col], errors="coerce")
#             q_sum = pd.to_numeric(filtered_rows[q_sum_col], errors="coerce")
#             valid = np.isfinite(t_sum) & np.isfinite(q_sum)
#             t_sum = t_sum[valid]
#             q_sum = q_sum[valid]
#             n_points = int(len(t_sum))
#             title = f"TT={tt_label}, P{i_plane}, N={n_points}"
#
#             if n_points == 0:
#                 ax.text(
#                     0.5,
#                     0.5,
#                     "No valid events",
#                     ha="center",
#                     va="center",
#                     transform=ax.transAxes,
#                 )
#                 ax.set_title(title)
#             else:
#                 _task3_plot_quantile_scatter(ax, t_sum, q_sum, title)
#
#             if row_idx == len(target_tt_labels) - 1:
#                 ax.set_xlabel("T_sum")
#             if col_idx == 0:
#                 ax.set_ylabel("Q_sum")
#             ax.grid(True, alpha=0.25)
#
#     fig.suptitle(
#         f"Filtered RPC T_sum vs Q_sum per {tt_column} - {basename}",
#         fontsize=16,
#     )
#     fig.tight_layout(rect=[0, 0, 1, 0.96])
#
#     # FINAL plot block moved out of the runtime flow: filtered_rpc_tsum_vs_qsum_scatter_per_combination
#     pass
#
#     if show_plots:
#         plt.show()
#     plt.close(fig)
#     return fig_idx_value

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: plot_population_table
# ============================================================================
# def plot_population_table(
#     counts_df: pd.DataFrame,
#     title: str,
#     filename_suffix: str,
#     fig_idx: int,
#     base_dir: str,
#     *,
#     row_label: str = "Charge-filtered plane combination",
#     col_label: str = "Charge threshold",
#     colorbar_label: str = "log10(count + 1)",
#     show_plots: bool = False,
#     save_plots: bool = False,
#     plot_list: list[str] | None = None,
# ) -> int:
#     """Render an annotated heatmap-style table for threshold population counts."""
#     if counts_df.empty:
#         return fig_idx
#
#     display_values = counts_df.to_numpy(dtype=float)
#     color_values = np.log10(display_values + 1.0)
#     fig_width = max(7.0, 1.35 * counts_df.shape[1] + 2.5)
#     fig_height = max(4.0, 0.45 * counts_df.shape[0] + 1.8)
#     fig, ax = plt.subplots(figsize=(fig_width, fig_height))
#
#     im = ax.imshow(color_values, cmap="turbo", aspect="auto")
#     ax.set_xticks(np.arange(counts_df.shape[1]))
#     ax.set_yticks(np.arange(counts_df.shape[0]))
#     ax.set_xticklabels(counts_df.columns)
#     ax.set_yticklabels(counts_df.index.astype(str))
#     ax.set_xlabel(col_label)
#     ax.set_ylabel(row_label)
#     ax.set_title(title)
#
#     max_color = float(np.nanmax(color_values)) if color_values.size else 0.0
#     for i_row in range(counts_df.shape[0]):
#         for j_col in range(counts_df.shape[1]):
#             value = int(display_values[i_row, j_col])
#             if value <= 0:
#                 continue
#             color_value = float(color_values[i_row, j_col])
#             text_color = "black" if max_color > 0 and color_value > 0.55 * max_color else "white"
#             ax.text(j_col, i_row, f"{value}", ha="center", va="center", color=text_color)
#
#     cbar = fig.colorbar(im, ax=ax, pad=0.02)
#     cbar.set_label(colorbar_label)
#     fig.tight_layout()
#
#     if save_plots:
#         final_filename = f"{fig_idx}_{filename_suffix}.png"
#         save_fig_path = os.path.join(base_dir, final_filename)
#         if plot_list is not None:
#             plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
#     if show_plots:
#         plt.show()
#     plt.close(fig)
#     return fig_idx + 1

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: _plot_task3_rpc_variables_hexbin
# ============================================================================
# def _plot_task3_rpc_variables_hexbin(
#     plot_source_df: pd.DataFrame,
#     *,
#     title: str,
#     filename_stem: str,
# ) -> None:
#     global fig_idx
#     fig, axes = plt.subplots(4, 10, figsize=(40, 20))  # 10 combinations per plane
#     axes = axes.flatten()
#
#     for i_plane in range(1, 5):
#         # Column names
#         t_sum_col = f'p{i_plane}_tsum'
#         t_dif_col = f'p{i_plane}_tdif'
#         q_sum_col = f'p{i_plane}_qsum'
#         q_dif_col = f'p{i_plane}_qdif'
#         y_col = f'p{i_plane}_ypos'
#
#         required_columns = [t_sum_col, t_dif_col, q_sum_col, q_dif_col, y_col]
#         if not all(col in plot_source_df.columns for col in required_columns):
#             continue
#
#         # Filter valid rows (non-zero)
#         valid_rows = plot_source_df[required_columns].replace(0, np.nan).dropna()
#
#         # Extract variables and filter low charge
#         cond = valid_rows[q_sum_col] < charge_per_plane_plot_threshold
#         t_sum  = valid_rows.loc[cond, t_sum_col]
#         t_diff = valid_rows.loc[cond, t_dif_col]
#         q_sum  = valid_rows.loc[cond, q_sum_col]
#         q_diff = valid_rows.loc[cond, q_dif_col]
#         y      = valid_rows.loc[cond, y_col]
#
#         base_idx = (i_plane - 1) * 10  # 10 plots per plane
#
#         plot_pairs = [
#             (t_sum,  t_diff, f'{t_sum_col} vs {t_dif_col}'),
#             (t_sum,  q_sum,  f'{t_sum_col} vs {q_sum_col}'),
#             (t_sum,  y,      f'{t_sum_col} vs {y_col}'),
#             (t_diff, q_sum,  f'{t_dif_col} vs {q_sum_col}'),
#             (t_diff, y,      f'{t_dif_col} vs {y_col}'),
#             (q_sum,  y,      f'{q_sum_col} vs {y_col}'),
#             (t_sum,  q_diff, f'{t_sum_col} vs {q_dif_col}'),
#             (t_diff, q_diff, f'{t_dif_col} vs {q_dif_col}'),
#             (q_diff, y,      f'{q_dif_col} vs {y_col}'),
#             (q_sum,  q_diff, f'{q_sum_col} vs {q_dif_col}')
#         ]
#
#         for offset, (x, yv, subplot_title) in enumerate(plot_pairs):
#             ax = axes[base_idx + offset]
#             _task3_plot_quantile_hexbin(ax, x, yv, subplot_title, gridsize=50, cmap="turbo")
#
#     plt.tight_layout()
#     plt.subplots_adjust(top=0.92)
#     plt.suptitle(title, fontsize=18)
#
#     if save_plots:
#         final_filename = f'{fig_idx}_{filename_stem}.png'
#         fig_idx += 1
#
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, fig=fig, format='png')
#
#     if show_plots: plt.show()
#     plt.close(fig)

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: dead runtime PDF helper after PNG-only split: _build_temp_pdf_path
# ============================================================================
# def _build_temp_pdf_path(target_path: str) -> str:
#     """Return a non-colliding temporary PDF path near the final target."""
#     base = f"{target_path}.tmp.{os.getpid()}"
#     candidate = base
#     counter = 1
#     while os.path.exists(candidate):
#         candidate = f"{base}.{counter}"
#         counter += 1
#     return candidate

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: dead runtime PDF helper after PNG-only split: close_direct_pdf_writer
# ============================================================================
# def close_direct_pdf_writer() -> None:
#     global _direct_pdf_pages, _direct_pdf_page_count, _direct_pdf_target_path, _direct_pdf_temp_path
#     if _direct_pdf_pages is not None:
#         _direct_pdf_pages.close()
#         _direct_pdf_pages = None
#
#     if _direct_pdf_temp_path and os.path.exists(_direct_pdf_temp_path):
#         if _direct_pdf_page_count > 0 and _direct_pdf_target_path:
#             os.replace(_direct_pdf_temp_path, _direct_pdf_target_path)
#         else:
#             os.remove(_direct_pdf_temp_path)
#
#     _direct_pdf_page_count = 0
#     _direct_pdf_target_path = None
#     _direct_pdf_temp_path = None

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: dead runtime PDF helper after PNG-only split: finalize_saved_plots_to_pdf
# ============================================================================
# def finalize_saved_plots_to_pdf() -> None:
#     figure_directory = base_directories["figure_directory"]
#     # Runtime PDF branch removed: runtime plots are PNG-only.
#     pass
#
#     if _direct_pdf_pages is not None:
#         print(f"Finalizing PDF with all plots in {save_pdf_path}")
#         close_direct_pdf_writer()
#         if os.path.exists(figure_directory):
#             shutil.rmtree(figure_directory)
#         return
#
#     existing_pngs = collect_saved_plot_paths(plot_list, figure_directory)
#     if not existing_pngs:
#         print(
#             "Warning: Plotting is enabled for Task 3 but no plot pages were generated "
#             f"for {basename_no_ext}; skipping PDF creation: {save_pdf_path}"
#         )
#         if os.path.exists(figure_directory):
#             shutil.rmtree(figure_directory)
#         return
#
#     print(f"Creating PDF with all plots in {save_pdf_path}")
#
#     temp_pdf_path = _build_temp_pdf_path(save_pdf_path)
#     try:
#         with PdfPages(temp_pdf_path) as pdf:
#             for png in existing_pngs:
#                 img = Image.open(png)
#                 fig, ax = plt.subplots(figsize=(img.width / 100, img.height / 100), dpi=100)
#                 ax.imshow(img)
#                 ax.axis('off')
#                 pdf_save_rasterized_page(pdf, fig, bbox_inches='tight')
#                 plt.close(fig)
#         os.replace(temp_pdf_path, save_pdf_path)
#     finally:
#         if os.path.exists(temp_pdf_path):
#             os.remove(temp_pdf_path)
#
#     for png in existing_pngs:
#         try:
#             os.remove(png)
#         except OSError as e:
#             print(f"Error: {e.filename} - {e.strerror}.")
#
#     if os.path.exists(figure_directory):
#         shutil.rmtree(figure_directory)

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_pages: PdfPages | None = None

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_page_count = 0

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_target_path: str | None = None

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_temp_path: str | None = None

# ============================================================================
# ARCHIVED FROM: script_3_cal_to_list.py
# REASON: dead runtime PDF atexit registration after PNG-only split
# ============================================================================
# atexit.register(close_direct_pdf_writer)


# 2026-10-30: obsolete runtime PDF callback removed; target function no longer exists.
# finalize_saved_plots_to_pdf()


# Archived dead runtime PDF path setup removed after the PNG-only split.
# "pdf_directory": os.path.join(raw_to_list_working_directory, "PLOTS/PDF_DIRECTORY"),
# save_pdf_filename = f"mingo{station}_task3_{basename_no_ext}_{date_execution}.pdf"
# save_pdf_path = os.path.join(base_directories["pdf_directory"], save_pdf_filename)
