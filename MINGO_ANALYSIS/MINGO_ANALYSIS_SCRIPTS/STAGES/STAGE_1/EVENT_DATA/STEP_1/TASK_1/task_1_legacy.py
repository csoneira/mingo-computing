# LEGACY CODE ARCHIVE FOR TASK 1
#
# This file stores code deliberately removed from the active task script.
# It is not imported by the pipeline and is not expected to execute.
# Dependencies and surrounding runtime context may be missing.
# Removed blocks are preserved substantially verbatim for historical reference.

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in fast mode.')

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in debug mode.')

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_F_left_pre_cal = T_side_left_pre_cal_debug
#     T_F_right_pre_cal = T_side_right_pre_cal_debug
#
#     T_B_left_pre_cal = T_side_left_pre_cal_debug
#     T_B_right_pre_cal = T_side_right_pre_cal_debug
#
#     Q_F_left_pre_cal = Q_side_left_pre_cal_debug
#     Q_F_right_pre_cal = Q_side_right_pre_cal_debug
#
#     Q_B_left_pre_cal = Q_side_left_pre_cal_debug
#     Q_B_right_pre_cal = Q_side_right_pre_cal_debug

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_clip_min = T_clip_min_debug
#     T_clip_max = T_clip_max_debug
#     Q_clip_min = Q_clip_min_debug
#     Q_clip_max = Q_clip_max_debug
#     num_bins = num_bins_debug

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: FINAL/report plot block moved to standalone final plotting (event_total_charge_raw)
# ============================================================================
# if task1_plot_enabled("event_total_charge_raw"):
#     raw_total_charge_columns = [
#         *(f"column_{idx}" for idx in range(15, 23)),
#         *(f"column_{idx}" for idx in range(31, 39)),
#         *(f"column_{idx}" for idx in range(47, 55)),
#         *(f"column_{idx}" for idx in range(63, 71)),
#         *(
#             f"p{plane}_s{strip}_{endpoint}_q"
#             for plane in range(1, 5)
#             for strip in range(1, 5)
#             for endpoint in ("ef", "eb")
#         ),
#     ]
#     raw_total_charge_columns = [col for col in raw_total_charge_columns if col in working_df.columns]
#     if raw_total_charge_columns:
#         raw_total_charge = working_df.loc[:, raw_total_charge_columns].sum(axis=1, skipna=True)
#         raw_total_charge = raw_total_charge[np.isfinite(raw_total_charge.to_numpy())]
#         if not raw_total_charge.empty:
#             raw_total_charge_plot = raw_total_charge.clip(lower=0, upper=2000)
#             plt.figure(figsize=(10, 6))
#             plt.hist(raw_total_charge_plot, bins=100, alpha=0.8, color='tab:blue')
#             plt.yscale('log')
#             plt.xlim(0, 2000)
#             plt.title(f"Raw total charge per event, {basename_no_ext}")
#             plt.xlabel("Total event charge (sum of raw Q channels)")
#             plt.ylabel("Number of events")
#             plt.tight_layout()
#
#             if save_plots:
#                 final_filename = f'{fig_idx}_raw_total_event_charge.png'
#                 fig_idx += 1
#                 save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                 plot_list.append(save_fig_path)
#                 save_plot_figure(save_fig_path, format='png')
#
#             if show_plots:
#                 plt.show()
#             plt.close()

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: FINAL/report plot block moved to standalone final plotting (tq_scatter_raw_by_tt)
# ============================================================================
# if task1_plot_enabled("tq_scatter_raw_by_tt"):
#     _tt_vals = sorted(working_df["tt_task0_raw"].dropna().unique()) if "tt_task0_raw" in working_df.columns else []
#     for _tt_v in _tt_vals:
#         _tt_sub = working_df[working_df["tt_task0_raw"] == _tt_v]
#         if len(_tt_sub) < 10:
#             continue
#         _ttl = normalize_tt_label(_tt_v)
#         fig_TQ, axes_TQ = plt.subplots(4, 4, figsize=(20, 10))
#         axes_TQ = axes_TQ.flatten()
#         for plane in range(1, 5):
#             for strip in range(1, 5):
#                 panel_idx = (plane - 1) * 4 + (strip - 1)
#                 col_F = f'p{plane}_s{strip}_ef_t'
#                 col_B = f'p{plane}_s{strip}_eb_t'
#                 y_F = _tt_sub[col_F]
#                 y_B = _tt_sub[col_B]
#                 charge_col_F = f'p{plane}_s{strip}_ef_q'
#                 charge_col_B = f'p{plane}_s{strip}_eb_q'
#                 charge_F = _tt_sub[charge_col_F]
#                 charge_B = _tt_sub[charge_col_B]
#                 mask_F = (y_F != 0) & (y_F > T_clip_min) & (y_F < T_clip_max) & (charge_F > Q_clip_min) & (charge_F < Q_clip_max)
#                 mask_B = (y_B != 0) & (y_B > T_clip_min) & (y_B < T_clip_max) & (charge_B > Q_clip_min) & (charge_B < Q_clip_max)
#                 axes_TQ[panel_idx].scatter(charge_F[mask_F], y_F[mask_F], alpha=0.5, label=f'{col_F} (F)', color='green', s=1)
#                 axes_TQ[panel_idx].scatter(charge_B[mask_B], y_B[mask_B], alpha=0.5, label=f'{col_B} (B)', color='orange', s=1)
#                 axes_TQ[panel_idx].axhline(y=T_F_left_pre_cal, color='red', linestyle='--', label='T_left_pre_cal')
#                 axes_TQ[panel_idx].axhline(y=T_F_right_pre_cal, color='blue', linestyle='--', label='T_right_pre_cal')
#                 axes_TQ[panel_idx].axvline(x=Q_F_left_pre_cal, color='red', linestyle='--', label='Q_left_pre_cal')
#                 axes_TQ[panel_idx].axvline(x=Q_F_right_pre_cal, color='blue', linestyle='--', label='Q_right_pre_cal')
#                 axes_TQ[panel_idx].set_title(f'{col_F} vs {col_B}')
#                 axes_TQ[panel_idx].legend()
#         plt.tight_layout()
#         plt.subplots_adjust(top=0.9)
#         plt.suptitle(f"Scatter T vs Q [tt_task0_raw={_ttl}, N={len(_tt_sub)}], mingo0{station}\n{start_time}", fontsize=16)
#         if save_plots:
#             final_filename = f'{fig_idx}_scatter_plot_TQ_tt{_ttl}.png'
#             fig_idx += 1
#             save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#             plot_list.append(save_fig_path)
#             save_plot_figure(save_fig_path, format='png')
#         if show_plots:
#             plt.show()
#         plt.close(fig_TQ)

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: FINAL/report plot block moved to standalone final plotting (tq_scatter_filtered_by_tt)
# ============================================================================
# if task1_plot_enabled("tq_scatter_filtered_by_tt"):
#     _tt_vals = sorted(working_df["tt_task0_raw"].dropna().unique()) if "tt_task0_raw" in working_df.columns else []
#     for _tt_v in _tt_vals:
#         _tt_sub = working_df[working_df["tt_task0_raw"] == _tt_v]
#         if len(_tt_sub) < 10:
#             continue
#         _ttl = normalize_tt_label(_tt_v)
#         fig_TQ, axes_TQ = plt.subplots(4, 4, figsize=(20, 10))
#         axes_TQ = axes_TQ.flatten()
#         for plane in range(1, 5):
#             for strip in range(1, 5):
#                 panel_idx = (plane - 1) * 4 + (strip - 1)
#                 col_F = f'p{plane}_s{strip}_ef_t'
#                 col_B = f'p{plane}_s{strip}_eb_t'
#                 y_F = _tt_sub[col_F]
#                 y_B = _tt_sub[col_B]
#                 charge_col_F = f'p{plane}_s{strip}_ef_q'
#                 charge_col_B = f'p{plane}_s{strip}_eb_q'
#                 charge_F = _tt_sub[charge_col_F]
#                 charge_B = _tt_sub[charge_col_B]
#                 mask_F = (y_F != 0) & (y_F > T_clip_min) & (y_F < T_clip_max) & (charge_F > Q_clip_min) & (charge_F < Q_clip_max)
#                 mask_B = (y_B != 0) & (y_B > T_clip_min) & (y_B < T_clip_max) & (charge_B > Q_clip_min) & (charge_B < Q_clip_max)
#                 axes_TQ[panel_idx].scatter(charge_F[mask_F], y_F[mask_F], alpha=0.5, label=f'{col_F} (F)', color='green', s=1)
#                 axes_TQ[panel_idx].scatter(charge_B[mask_B], y_B[mask_B], alpha=0.5, label=f'{col_B} (B)', color='orange', s=1)
#                 axes_TQ[panel_idx].axhline(y=T_F_left_pre_cal, color='red', linestyle='--', label='T_left_pre_cal')
#                 axes_TQ[panel_idx].axhline(y=T_F_right_pre_cal, color='blue', linestyle='--', label='T_right_pre_cal')
#                 axes_TQ[panel_idx].axvline(x=Q_F_left_pre_cal, color='red', linestyle='--', label='Q_left_pre_cal')
#                 axes_TQ[panel_idx].axvline(x=Q_F_right_pre_cal, color='blue', linestyle='--', label='Q_right_pre_cal')
#                 axes_TQ[panel_idx].set_title(f'{col_F} vs {col_B}')
#                 axes_TQ[panel_idx].legend()
#         plt.tight_layout()
#         plt.subplots_adjust(top=0.9)
#         plt.suptitle(f"Scatter T vs Q filtered [tt_task0_raw={_ttl}, N={len(_tt_sub)}], mingo0{station}\n{start_time}", fontsize=16)
#         if save_plots:
#             final_filename = f'{fig_idx}_scatter_plot_TQ_filtered_tt{_ttl}.png'
#             fig_idx += 1
#             save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#             plot_list.append(save_fig_path)
#             save_plot_figure(save_fig_path, format='png')
#         if show_plots:
#             plt.show()
#         plt.close(fig_TQ)

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: FINAL/report plot block moved to standalone final plotting (channel_tq_matrix_by_planepair)
# ============================================================================
# if _plot_channel_tq_matrix_by_planepair or _plot_channel_combination_filter_by_tt:
#     (
#         channel_plot_original_df,
#         channel_plot_precombination_df,
#         channel_plot_final_df,
#     ) = build_task1_channel_filter_stage_frames(
#         working_df,
#         original_reference_df=None,
#         relation_limits_by_type=task1_channel_combination_limits_by_relation,
#     )

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: FINAL/report plot block moved to standalone final plotting (channel_tq_matrix_by_planepair)
# ============================================================================
# if _plot_channel_tq_matrix_by_planepair:
#     # Sectorized approach per CHANNEL (plane,strip,side): 2×2 (Q,T) matrix per channel-pair
#     # Improve image definition and aesthetics: larger DPI, larger markers, color per plane-pair,
#     # histogram drawn with histtype='step' and log-counts.
#     _MM1 = 1000
#     raw_noise_limit_line_kwargs = {
#         "color": "red",
#         "linestyle": "--",
#         "linewidth": 1.4,
#         "alpha": 0.9,
#         "zorder": 6,
#     }
#     _self_relation_limits = task1_channel_combination_limits_by_relation.get("self", {})
#     raw_var_limits: dict[int, tuple[float | None, float | None]] = {
#         0: (
#             float(_self_relation_limits.get("q_sum_left", channel_combination_q_sum_left)),
#             float(_self_relation_limits.get("q_sum_right", channel_combination_q_sum_right)),
#         ),
#         1: (
#             float(_self_relation_limits.get("t_sum_left", channel_combination_t_sum_left)),
#             float(_self_relation_limits.get("t_sum_right", channel_combination_t_sum_right)),
#         ),
#     }
#
#     pair_list = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]
#     CHANNEL_PAIR_FIGSIZE = (7, 7)
#     channel_pair_min_events = int(config.get("channel_pair_min_events", 10))
#     channel_pair_sector_payloads: list[dict[str, object]] = []
#     channel_pair_candidate_counts: list[tuple[int, int, int, int, int, int]] = []
#
#     for _pi, _pj in pair_list:
#         if "tt_task0_raw" in channel_plot_original_df.columns:
#             _tts_all = channel_plot_original_df["tt_task0_raw"].apply(normalize_tt_label)
#             _pmask_all = _tts_all.str.contains(str(_pi)) & _tts_all.str.contains(str(_pj))
#             _df_pp_all = channel_plot_original_df.loc[_pmask_all]
#         else:
#             _df_pp_all = channel_plot_original_df
#         # Previously we gated on the raw number of events for the plane-pair
#         # directly from `working_df`. That counted many rows that would later
#         # produce blank plots because their channel values were zero. Instead,
#         # require that the per-pair threshold is applied to the number of
#         # events that actually have non-zero (Q,T) data for at least one
#         # channel in the plane-pair. Build the retained preview frame first
#         # and then compute the effective count of non-zero channel pairs.
#         if "tt_task0_raw" in channel_plot_final_df.columns:
#             _tts_retained = channel_plot_final_df["tt_task0_raw"].apply(normalize_tt_label)
#             _pmask_retained = _tts_retained.str.contains(str(_pi)) & _tts_retained.str.contains(str(_pj))
#             _df_pp1 = channel_plot_final_df.loc[_pmask_retained]
#         else:
#             _df_pp1 = channel_plot_final_df
#         if "tt_task0_raw" in channel_plot_precombination_df.columns:
#             _tts_precombination = channel_plot_precombination_df["tt_task0_raw"].apply(normalize_tt_label)
#             _pmask_precombination = _tts_precombination.str.contains(str(_pi)) & _tts_precombination.str.contains(str(_pj))
#             _df_precombination_pp1 = channel_plot_precombination_df.loc[_pmask_precombination]
#         else:
#             _df_precombination_pp1 = channel_plot_precombination_df.iloc[0:0].copy()
#
#         # Compute how many events actually contain at least one channel with
#         # both Q and T non-zero for this plane-pair. Apply the minimum-event
#         # gating to that effective count to avoid producing blank figures.
#         channels_check = [(p, s, sd) for p in (_pi, _pj) for s in range(1, 5) for sd in ("F", "B")]
#         if not _df_pp_all.empty or not _df_precombination_pp1.empty or not _df_pp1.empty:
#             # Vectorized per-column checks are faster than row-wise Python loops.
#             any_channel_original_both_nonzero = (
#                 np.zeros(len(_df_pp_all), dtype=bool)
#                 if not _df_pp_all.empty
#                 else np.zeros(0, dtype=bool)
#             )
#             any_channel_precombination_both_nonzero = (
#                 np.zeros(len(_df_precombination_pp1), dtype=bool)
#                 if not _df_precombination_pp1.empty
#                 else np.zeros(0, dtype=bool)
#             )
#             any_channel_both_nonzero = np.zeros(len(_df_pp1), dtype=bool) if not _df_pp1.empty else np.zeros(0, dtype=bool)
#             for (pl, ss, sd) in channels_check:
#                 qcol = f"Q{pl}_{sd}_{ss}"
#                 tcol = f"T{pl}_{sd}_{ss}"
#                 if qcol in _df_pp_all.columns and tcol in _df_pp_all.columns:
#                     q_original_nonzero = _df_pp_all[qcol].fillna(0).to_numpy(dtype=float) != 0
#                     t_original_nonzero = _df_pp_all[tcol].fillna(0).to_numpy(dtype=float) != 0
#                     any_channel_original_both_nonzero |= (q_original_nonzero & t_original_nonzero)
#                 if qcol in _df_precombination_pp1.columns and tcol in _df_precombination_pp1.columns:
#                     q_precombination_nonzero = _df_precombination_pp1[qcol].fillna(0).to_numpy(dtype=float) != 0
#                     t_precombination_nonzero = _df_precombination_pp1[tcol].fillna(0).to_numpy(dtype=float) != 0
#                     any_channel_precombination_both_nonzero |= (q_precombination_nonzero & t_precombination_nonzero)
#                 if qcol in _df_pp1.columns and tcol in _df_pp1.columns:
#                     q_nonzero = _df_pp1[qcol].fillna(0).to_numpy(dtype=float) != 0
#                     t_nonzero = _df_pp1[tcol].fillna(0).to_numpy(dtype=float) != 0
#                     any_channel_both_nonzero |= (q_nonzero & t_nonzero)
#             effective_events = max(
#                 int(any_channel_original_both_nonzero.sum()),
#                 int(any_channel_precombination_both_nonzero.sum()),
#                 int(any_channel_both_nonzero.sum()),
#             )
#         else:
#             effective_events = 0
#
#         if effective_events < channel_pair_min_events:
#             # Nothing worth plotting for this plane-pair after non-zero filtering
#             continue
#
#         if not _df_pp1.empty:
#             sampled_index = _df_pp1.sample(n=min(len(_df_pp1), _MM1), random_state=42).index
#         elif not _df_precombination_pp1.empty:
#             sampled_index = _df_precombination_pp1.sample(n=min(len(_df_precombination_pp1), _MM1), random_state=42).index
#         elif not _df_pp_all.empty:
#             sampled_index = _df_pp_all.sample(n=min(len(_df_pp_all), _MM1), random_state=42).index
#         else:
#             sampled_index = _df_pp1.index
#         _df_s1 = _df_pp1.reindex(sampled_index).copy()
#         _df_precombination_s1 = _df_precombination_pp1.reindex(sampled_index).copy()
#         _df_original_s1 = _df_pp_all.reindex(sampled_index).copy()
#
#         # Map event plane-combination (normalized tt_task0_raw) to colors for per-point coloring
#         if "tt_task0_raw" in _df_s1.columns:
#             _row_tt = _df_s1["tt_task0_raw"].apply(normalize_tt_label).astype(str)
#         else:
#             _row_tt = pd.Series([f"{_pi}{_pj}"] * len(_df_s1), index=_df_s1.index)
#         if "tt_task0_raw" in _df_precombination_s1.columns:
#             _precombination_row_tt = _df_precombination_s1["tt_task0_raw"].apply(normalize_tt_label).astype(str)
#         else:
#             _precombination_row_tt = pd.Series([f"{_pi}{_pj}"] * len(_df_precombination_s1), index=_df_precombination_s1.index)
#         unique_tts = sorted(set(_row_tt.unique()).union(set(_precombination_row_tt.unique())))
#         if not unique_tts:
#             unique_tts = [f"{_pi}{_pj}"]
#         tt_color_map: dict[str, tuple[float, float, float, float]] = {
#             tt_label: get_tt_color(tt_label) for tt_label in unique_tts
#         }
#         # Per-row color array aligned with _df_s1
#         _row_colors = np.array([tt_color_map[str(lbl)] for lbl in _row_tt], dtype=object)
#         _precombination_row_colors = np.array([tt_color_map[str(lbl)] for lbl in _precombination_row_tt], dtype=object)
#
#         # Build channels including side: ('plane', strip, 'F'/'B')
#         channels = [(p, s, sd) for p in (_pi, _pj) for s in range(1, 5) for sd in ("F", "B")]
#
#         # Precompute retained and pre-zeroing reference arrays for each (channel_idx, var_idx)
#         _chan_var_arr: dict[tuple[int, int], np.ndarray] = {}
#         _precombination_chan_var_arr: dict[tuple[int, int], np.ndarray] = {}
#         _original_chan_var_arr: dict[tuple[int, int], np.ndarray] = {}
#         for ch_idx, (pl, ss, sd) in enumerate(channels):
#             q_col = f"Q{pl}_{sd}_{ss}"
#             t_col = f"T{pl}_{sd}_{ss}"
#             for var_idx, col in enumerate((q_col, t_col)):
#                 if col in _df_s1.columns:
#                     arr = _df_s1[col].fillna(0).to_numpy(dtype=float)
#                     _chan_var_arr[(ch_idx, var_idx)] = arr
#                 else:
#                     _chan_var_arr[(ch_idx, var_idx)] = np.zeros(len(_df_s1), dtype=float)
#                 if col in _df_precombination_s1.columns:
#                     arr_precombination = _df_precombination_s1[col].fillna(0).to_numpy(dtype=float)
#                     _precombination_chan_var_arr[(ch_idx, var_idx)] = arr_precombination
#                 else:
#                     _precombination_chan_var_arr[(ch_idx, var_idx)] = np.zeros(len(_df_precombination_s1), dtype=float)
#                 if col in _df_original_s1.columns:
#                     arr_original = _df_original_s1[col].fillna(0).to_numpy(dtype=float)
#                     _original_chan_var_arr[(ch_idx, var_idx)] = arr_original
#                 else:
#                     _original_chan_var_arr[(ch_idx, var_idx)] = np.zeros(len(_df_original_s1), dtype=float)
#
#         # Compute per-variable ranges from the full retained+removed raw values and
#         # ensure they always include the active configured Q/T limits.
#         col_ranges: dict[int, tuple[float, float]] = {}
#         for var_idx in (0, 1):
#             retained_vals = [
#                 _chan_var_arr.get((ch, var_idx), np.zeros(0, dtype=float))
#                 for ch in range(len(channels))
#             ]
#             precombination_vals = [
#                 _precombination_chan_var_arr.get((ch, var_idx), np.zeros(0, dtype=float))
#                 for ch in range(len(channels))
#             ]
#             original_vals = [
#                 _original_chan_var_arr.get((ch, var_idx), np.zeros(0, dtype=float))
#                 for ch in range(len(channels))
#             ]
#             all_vals = np.concatenate([*retained_vals, *precombination_vals, *original_vals])
#             nonzero = all_vals[all_vals != 0]
#             col_ranges[var_idx] = _task1_capped_plot_range(
#                 nonzero if nonzero.size else all_vals,
#                 raw_var_limits.get(var_idx, (None, None)),
#             )
#
#         pair_plot_candidates: list[tuple[int, int, int, int]] = []
#         for ai in range(len(channels)):
#             for bj in range(ai, len(channels)):
#                 ai_q = _chan_var_arr.get((ai, 0), np.zeros(0, dtype=float))
#                 ai_t = _chan_var_arr.get((ai, 1), np.zeros(0, dtype=float))
#                 bj_q = _chan_var_arr.get((bj, 0), np.zeros(0, dtype=float))
#                 bj_t = _chan_var_arr.get((bj, 1), np.zeros(0, dtype=float))
#                 ai_q_precombination = _precombination_chan_var_arr.get((ai, 0), np.zeros(0, dtype=float))
#                 ai_t_precombination = _precombination_chan_var_arr.get((ai, 1), np.zeros(0, dtype=float))
#                 bj_q_precombination = _precombination_chan_var_arr.get((bj, 0), np.zeros(0, dtype=float))
#                 bj_t_precombination = _precombination_chan_var_arr.get((bj, 1), np.zeros(0, dtype=float))
#                 ai_q_original = _original_chan_var_arr.get((ai, 0), np.zeros(0, dtype=float))
#                 ai_t_original = _original_chan_var_arr.get((ai, 1), np.zeros(0, dtype=float))
#                 bj_q_original = _original_chan_var_arr.get((bj, 0), np.zeros(0, dtype=float))
#                 bj_t_original = _original_chan_var_arr.get((bj, 1), np.zeros(0, dtype=float))
#                 figure_effective_events = max(
#                     int((((ai_q_original != 0) & (ai_t_original != 0)) | ((bj_q_original != 0) & (bj_t_original != 0))).sum()),
#                     int((((ai_q_precombination != 0) & (ai_t_precombination != 0)) | ((bj_q_precombination != 0) & (bj_t_precombination != 0))).sum()),
#                     int((((ai_q != 0) & (ai_t != 0)) | ((bj_q != 0) & (bj_t != 0))).sum()),
#                 )
#                 combination_removed_events = int(
#                     (
#                         (
#                             ((ai_q_precombination != 0) & (ai_t_precombination != 0))
#                             | ((bj_q_precombination != 0) & (bj_t_precombination != 0))
#                         )
#                         & ~(
#                             ((ai_q != 0) & (ai_t != 0))
#                             | ((bj_q != 0) & (bj_t != 0))
#                         )
#                     ).sum()
#                 )
#                 if figure_effective_events < channel_pair_min_events:
#                     continue
#                 pair_plot_candidates.append((ai, bj, figure_effective_events, combination_removed_events))
#                 channel_pair_candidate_counts.append(
#                     (combination_removed_events, figure_effective_events, _pi, _pj, ai, bj)
#                 )
#
#         if not pair_plot_candidates:
#             continue
#
#         channel_pair_sector_payloads.append(
#             {
#                 "plane_a": _pi,
#                 "plane_b": _pj,
#                 "plane_pair_event_count": len(_df_pp_all),
#                 "pair_plot_candidates": pair_plot_candidates,
#                 "row_tt": _row_tt,
#                 "precombination_row_tt": _precombination_row_tt,
#                 "unique_tts": unique_tts,
#                 "tt_color_map": tt_color_map,
#                 "row_colors": _row_colors,
#                 "precombination_row_colors": _precombination_row_colors,
#                 "channels": channels,
#                 "chan_var_arr": _chan_var_arr,
#                 "precombination_chan_var_arr": _precombination_chan_var_arr,
#                 "original_chan_var_arr": _original_chan_var_arr,
#                 "col_ranges": col_ranges,
#             }
#         )
#
#     selected_channel_pair_keys: set[tuple[int, int, int, int]] | None = None
#     selected_channel_pair_order: list[tuple[int, int, int, int]] | None = None
#     if channel_pair_plot_top_n is not None:
#         ranked_channel_pair_candidates = sorted(
#             channel_pair_candidate_counts,
#             key=lambda item: (-item[0], -item[1], item[2], item[3], item[4], item[5]),
#         )
#         selected_channel_pair_order = [
#             (plane_a, plane_b, ai, bj)
#             for _, _, plane_a, plane_b, ai, bj in ranked_channel_pair_candidates[:channel_pair_plot_top_n]
#         ]
#         selected_channel_pair_keys = {
#             (plane_a, plane_b, ai, bj)
#             for plane_a, plane_b, ai, bj in selected_channel_pair_order
#         }
#         print(
#             "Task 1 channel T/Q matrix plot cap: "
#             f"plotting top {len(selected_channel_pair_keys)} of {len(channel_pair_candidate_counts)} "
#             "eligible channel-pair figures ranked by combination-filter removals."
#         )
#     else:
#         print(
#             "Task 1 channel T/Q matrix plot cap: plotting all "
#             f"{len(channel_pair_candidate_counts)} eligible channel-pair figures."
#         )
#
#     sector_payload_lookup = {
#         (int(sector_payload["plane_a"]), int(sector_payload["plane_b"])): sector_payload
#         for sector_payload in channel_pair_sector_payloads
#     }
#
#     if selected_channel_pair_order is not None:
#         pair_iteration_order: list[tuple[int, int, int, int, int, int]] = []
#         for _pi, _pj, ai, bj in selected_channel_pair_order:
#             sector_payload = sector_payload_lookup.get((_pi, _pj))
#             if sector_payload is None:
#                 continue
#             for candidate_ai, candidate_bj, figure_effective_events, combination_removed_events in sector_payload["pair_plot_candidates"]:
#                 if candidate_ai == ai and candidate_bj == bj:
#                     pair_iteration_order.append(
#                         (_pi, _pj, candidate_ai, candidate_bj, figure_effective_events, combination_removed_events)
#                     )
#                     break
#     else:
#         pair_iteration_order = []
#         for sector_payload in channel_pair_sector_payloads:
#             _pi = int(sector_payload["plane_a"])
#             _pj = int(sector_payload["plane_b"])
#             for ai, bj, figure_effective_events, combination_removed_events in sector_payload["pair_plot_candidates"]:
#                 pair_iteration_order.append(
#                     (_pi, _pj, ai, bj, figure_effective_events, combination_removed_events)
#                 )
#
#     for _pi, _pj, ai, bj, figure_effective_events, combination_removed_events in pair_iteration_order:
#         sector_payload = sector_payload_lookup.get((_pi, _pj))
#         if sector_payload is None:
#             continue
#         plane_pair_event_count = int(sector_payload["plane_pair_event_count"])
#         _row_tt = sector_payload["row_tt"]
#         _precombination_row_tt = sector_payload["precombination_row_tt"]
#         unique_tts = list(sector_payload["unique_tts"])
#         tt_color_map = dict(sector_payload["tt_color_map"])
#         _row_colors = sector_payload["row_colors"]
#         _precombination_row_colors = sector_payload["precombination_row_colors"]
#         channels = list(sector_payload["channels"])
#         _chan_var_arr = dict(sector_payload["chan_var_arr"])
#         _precombination_chan_var_arr = dict(sector_payload["precombination_chan_var_arr"])
#         _original_chan_var_arr = dict(sector_payload["original_chan_var_arr"])
#         col_ranges = dict(sector_payload["col_ranges"])
#
#         if (
#             selected_channel_pair_keys is not None
#             and (_pi, _pj, ai, bj) not in selected_channel_pair_keys
#         ):
#             continue
#
#         ai_channel_key = (channels[ai][0], channels[ai][2], channels[ai][1])
#         bj_channel_key = (channels[bj][0], channels[bj][2], channels[bj][1])
#         ai_noise_limit = task1_effective_channel_q_left_limits.get(ai_channel_key)
#         bj_noise_limit = task1_effective_channel_q_left_limits.get(bj_channel_key)
#         _fig, _axes = plt.subplots(2, 2, figsize=CHANNEL_PAIR_FIGSIZE, squeeze=False, sharex='col', sharey='row')
#         same_channel = ai == bj
#         for r in range(2):
#             for c in range(2):
#                 ax = _axes[r][c]
#                 if same_channel and c > r:
#                     ax.set_visible(False)
#                     continue
#                 for sp in ax.spines.values():
#                     sp.set_linewidth(0.4)
#
#                 col_x = _chan_var_arr.get((ai, c), np.zeros(0, dtype=float))
#                 col_y = _chan_var_arr.get((bj, r), np.zeros(0, dtype=float))
#                 precombination_col_x = np.clip(
#                     _precombination_chan_var_arr.get((ai, c), np.zeros(0, dtype=float)),
#                     *col_ranges[c],
#                 )
#                 precombination_col_y = np.clip(
#                     _precombination_chan_var_arr.get((bj, r), np.zeros(0, dtype=float)),
#                     *col_ranges[r],
#                 )
#                 original_col_x = np.clip(
#                     _original_chan_var_arr.get((ai, c), np.zeros(0, dtype=float)),
#                     *col_ranges[c],
#                 )
#                 original_col_y = np.clip(
#                     _original_chan_var_arr.get((bj, r), np.zeros(0, dtype=float)),
#                     *col_ranges[r],
#                 )
#
#                 if same_channel and c == r:
#                     vals_all = col_x[col_x != 0]
#                     var_name = 'Q' if c == 0 else 'T'
#                     prefilter_removed_vals_all = original_col_x[(original_col_x != 0) & (precombination_col_x == 0)]
#                     combination_removed_vals_all = precombination_col_x[(precombination_col_x != 0) & (col_x == 0)]
#                     if vals_all.size > 1 or prefilter_removed_vals_all.size > 0 or combination_removed_vals_all.size > 0:
#                         if prefilter_removed_vals_all.size > 0:
#                             hist_kwargs = dict(
#                                 bins=30,
#                                 histtype='step',
#                                 color='lightgrey',
#                                 linewidth=1.4,
#                                 linestyle='--',
#                                 log=True,
#                                 alpha=0.65,
#                                 label='Removed before combination',
#                             )
#                             if var_name == 'T':
#                                 hist_kwargs["orientation"] = 'horizontal'
#                             ax.hist(prefilter_removed_vals_all, **hist_kwargs)
#                         for tt_label in unique_tts:
#                             precombination_mask_tt = (_precombination_row_tt.values == tt_label)
#                             removed_vals_tt = precombination_col_x[precombination_mask_tt]
#                             removed_vals_tt = removed_vals_tt[(removed_vals_tt != 0) & (col_x[precombination_mask_tt] == 0)]
#                             if removed_vals_tt.size > 1:
#                                 combo_hist_kwargs = dict(
#                                     bins=30,
#                                     histtype='step',
#                                     color=tt_color_map[tt_label],
#                                     linewidth=1.0,
#                                     linestyle='--',
#                                     log=True,
#                                     alpha=0.7,
#                                     label=f"TT={tt_label} removed" if len(unique_tts) > 1 else None,
#                                 )
#                                 if var_name == 'T':
#                                     combo_hist_kwargs["orientation"] = 'horizontal'
#                                 ax.hist(removed_vals_tt, **combo_hist_kwargs)
#                             mask_tt = (_row_tt.values == tt_label)
#                             vals_tt = col_x[mask_tt]
#                             vals_tt = vals_tt[vals_tt != 0]
#                             if vals_tt.size > 1:
#                                 if var_name == 'T':
#                                     ax.hist(
#                                         vals_tt,
#                                         bins=30,
#                                         histtype='step',
#                                         color=tt_color_map[tt_label],
#                                         linewidth=1.2,
#                                         log=True,
#                                         orientation='horizontal',
#                                         label=f"TT={tt_label}" if len(unique_tts) > 1 else None,
#                                     )
#                                 else:
#                                     ax.hist(
#                                         vals_tt,
#                                         bins=30,
#                                         histtype='step',
#                                         color=tt_color_map[tt_label],
#                                         linewidth=1.2,
#                                         log=True,
#                                         label=f"TT={tt_label}" if len(unique_tts) > 1 else None,
#                                     )
#                         if len(unique_tts) > 1 or prefilter_removed_vals_all.size > 0 or combination_removed_vals_all.size > 0:
#                             ax.legend(fontsize=6)
#                         if var_name == 'T':
#                             ax.set_xlabel('Counts (log)', fontsize=7)
#                             ax.set_ylabel('T (ns)', fontsize=7)
#                             ax.set_ylim(col_ranges[c])
#                             try:
#                                 tl_lo = float(raw_var_limits[1][0])
#                                 tl_hi = float(raw_var_limits[1][1])
#                                 ax.axhline(tl_lo, color='lightgrey', linestyle='--', linewidth=0.8)
#                                 ax.axhline(tl_hi, color='lightgrey', linestyle='--', linewidth=0.8)
#                             except Exception:
#                                 pass
#                         else:
#                             ax.set_xlabel('Q (ns)', fontsize=7)
#                             ax.set_ylabel('Counts (log)', fontsize=7)
#                             ax.set_xlim(col_ranges[c])
#                             try:
#                                 ql_lo = float(raw_var_limits[0][0])
#                                 ql_hi = float(raw_var_limits[0][1])
#                                 ax.axvline(ql_lo, color='lightgrey', linestyle='--', linewidth=0.8)
#                                 ax.axvline(ql_hi, color='lightgrey', linestyle='--', linewidth=0.8)
#                             except Exception:
#                                 pass
#                             if ai_noise_limit is not None and np.isfinite(ai_noise_limit):
#                                 ax.axvline(
#                                     float(ai_noise_limit),
#                                     **raw_noise_limit_line_kwargs,
#                                 )
#                 else:
#                     prefilter_removed_mask = (
#                         (original_col_x != 0)
#                         & (original_col_y != 0)
#                         & ~((precombination_col_x != 0) & (precombination_col_y != 0))
#                     )
#                     if np.any(prefilter_removed_mask):
#                         ax.scatter(
#                             original_col_x[prefilter_removed_mask],
#                             original_col_y[prefilter_removed_mask],
#                             s=4,
#                             alpha=0.08,
#                             linewidths=0,
#                             color='grey',
#                             edgecolors='none',
#                             zorder=1,
#                         )
#                     if col_x.size and col_y.size:
#                         mask = (col_x != 0) & (col_y != 0)
#                         if np.any(mask):
#                             ax.scatter(
#                                 col_x[mask],
#                                 col_y[mask],
#                                 s=12,
#                                 alpha=0.75,
#                                 linewidths=0,
#                                 c=_row_colors[mask].tolist(),
#                                 edgecolors='none',
#                             )
#                     if precombination_col_x.size and precombination_col_y.size:
#                         removed_mask = (
#                             (precombination_col_x != 0)
#                             & (precombination_col_y != 0)
#                             & ~((col_x != 0) & (col_y != 0))
#                         )
#                         if np.any(removed_mask):
#                             ax.scatter(
#                                 precombination_col_x[removed_mask],
#                                 precombination_col_y[removed_mask],
#                                 s=removed_marker_size,
#                                 marker=removed_marker,
#                                 alpha=removed_marker_alpha,
#                                 linewidths=1.0,
#                                 c=_precombination_row_colors[removed_mask].tolist(),
#                                 zorder=3,
#                             )
#                     ax.set_xlim(col_ranges[c])
#                     ax.set_ylim(col_ranges[r])
#                     try:
#                         ql_lo = float(raw_var_limits[0][0])
#                         ql_hi = float(raw_var_limits[0][1])
#                         ax.axvline(ql_lo, color='lightgrey', linestyle='--', linewidth=0.8)
#                         ax.axvline(ql_hi, color='lightgrey', linestyle='--', linewidth=0.8)
#                     except Exception:
#                         pass
#                     if c == 0 and ai_noise_limit is not None and np.isfinite(ai_noise_limit):
#                         ax.axvline(
#                             float(ai_noise_limit),
#                             **raw_noise_limit_line_kwargs,
#                         )
#                     try:
#                         tl_lo = float(raw_var_limits[1][0])
#                         tl_hi = float(raw_var_limits[1][1])
#                         ax.axhline(tl_lo, color='lightgrey', linestyle='--', linewidth=0.8)
#                         ax.axhline(tl_hi, color='lightgrey', linestyle='--', linewidth=0.8)
#                     except Exception:
#                         pass
#                     if r == 0 and bj_noise_limit is not None and np.isfinite(bj_noise_limit):
#                         ax.axhline(
#                             float(bj_noise_limit),
#                             **raw_noise_limit_line_kwargs,
#                         )
#                     if r == 1:
#                         ax.set_xlabel("Q" if c == 0 else "T", fontsize=7)
#                     else:
#                         ax.set_xlabel("")
#                     if c == 0:
#                         ax.set_ylabel("Q" if r == 0 else "T", fontsize=7)
#                     else:
#                         ax.set_ylabel("")
#
#                     if ax.get_xscale() == "linear":
#                         ax.xaxis.set_major_locator(mpl.ticker.MaxNLocator(nbins=5, min_n_ticks=3))
#                         ax.xaxis.set_major_formatter(mpl.ticker.ScalarFormatter())
#                     if ax.get_yscale() == "linear":
#                         ax.yaxis.set_major_locator(mpl.ticker.MaxNLocator(nbins=5, min_n_ticks=3))
#                         ax.yaxis.set_major_formatter(mpl.ticker.ScalarFormatter())
#                     ax.tick_params(
#                         axis="x",
#                         which="both",
#                         labelsize=6,
#                         labelbottom=True,
#                         bottom=True,
#                     )
#                     ax.tick_params(
#                         axis="y",
#                         which="both",
#                         labelsize=6,
#                         labelleft=True,
#                         left=True,
#                     )
#                     for _tick_label in ax.get_xticklabels():
#                         _tick_label.set_visible(True)
#                     for _tick_label in ax.get_yticklabels():
#                         _tick_label.set_visible(True)
#
#         plt.subplots_adjust(wspace=0.08, hspace=0.08, left=0.08, right=0.98, top=0.95, bottom=0.08)
#         a_pl, a_strip, a_side = channels[ai]
#         b_pl, b_strip, b_side = channels[bj]
#         a_addr = f"P{a_pl}S{a_strip}{a_side}"
#         b_addr = f"P{b_pl}S{b_strip}{b_side}"
#         _fig.suptitle(
#             f"{a_addr} vs {b_addr} — Channel Sector: P{_pi}×P{_pj} "
#             f"[{plane_pair_event_count} events, combo-removed={combination_removed_events}] · mingo0{station}",
#             fontsize=9,
#         )
#
#         if save_plots:
#             fname = f"{fig_idx:03d}_channel_pair_P{_pi}P{_pj}_ch{ai+1}_ch{bj+1}.png"
#             fig_idx += 1
#             fpath = os.path.join(base_directories["figure_directory"], fname)
#             plot_list.append(fpath)
#             save_plot_figure(fpath, fig=_fig, format="png", dpi=150, bbox_inches='tight')
#         if show_plots:
#             plt.show()
#         plt.close(_fig)

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: FINAL/report plot block moved to standalone final plotting (acquisition_rate_vs_time_by_task_tt_with_histograms)
# ============================================================================
# if save_plots and task1_plot_enabled("acquisition_rate_vs_time_by_task_tt_with_histograms"):
#     rate_fig = create_rate_vs_time_by_task_tt_with_histograms(
#         working_df,
#         tt_column="tt_task0_raw",
#         title=(
#             f"Task 1 acquisition rate by tt_task0_raw, {basename_no_ext} "
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
#         print("Task 1 acquisition-rate-by-task-tt plot skipped: no valid tt_task0_raw/datetime rows.")

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
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
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: runtime PDF branch disabled by the PNG-only runtime plotting contract
# ============================================================================
#     if not create_pdf:
#         if os.path.exists(figure_directory):
#             shutil.rmtree(figure_directory)
#         return

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
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
# ARCHIVED FROM: script_1_raw_to_clean.py
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
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: dead runtime PDF helper after PNG-only split: finalize_saved_plots_to_pdf
# ============================================================================
# def finalize_saved_plots_to_pdf() -> None:
#     figure_directory = base_directories["figure_directory"]
#     # Runtime PDF branch removed: runtime plots are PNG-only.
#     pass
#
#     print(f"Creating PDF with all plots in {save_pdf_path}")
#     existing_pngs = collect_saved_plot_paths(plot_list, figure_directory)
#
#     if _direct_pdf_pages is not None:
#         # Direct PDF mode already wrote each page incrementally via save_plot_figure.
#         close_direct_pdf_writer()
#     elif existing_pngs:
#         temp_pdf_path = _build_temp_pdf_path(save_pdf_path)
#         try:
#             with PdfPages(temp_pdf_path) as pdf:
#                 for png in existing_pngs:
#                     img = Image.open(png)
#                     fig, ax = plt.subplots(figsize=(img.width / 100, img.height / 100), dpi=100)
#                     ax.imshow(img)
#                     ax.axis('off')
#                     pdf_save_rasterized_page(pdf, fig, bbox_inches='tight')
#                     plt.close(fig)
#             os.replace(temp_pdf_path, save_pdf_path)
#         finally:
#             if os.path.exists(temp_pdf_path):
#                 os.remove(temp_pdf_path)
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
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_pages: PdfPages | None = None

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_page_count = 0

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_target_path: str | None = None

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_temp_path: str | None = None

# ============================================================================
# ARCHIVED FROM: script_1_raw_to_clean.py
# REASON: dead runtime PDF atexit registration after PNG-only split
# ============================================================================
# atexit.register(close_direct_pdf_writer)


# 2026-10-30: obsolete runtime PDF callback removed; target function no longer exists.
# finalize_saved_plots_to_pdf()
