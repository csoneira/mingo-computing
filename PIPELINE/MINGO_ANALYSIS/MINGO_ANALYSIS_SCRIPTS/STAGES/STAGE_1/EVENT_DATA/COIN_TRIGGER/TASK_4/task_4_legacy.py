# LEGACY CODE ARCHIVE FOR TASK 4
# This file is not imported and is not expected to execute.

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (trigger_types_raw_and_list, trigger_types_tracking_and_list, trigger_types_tracking_and_raw)
# ============================================================================
# if create_plots:
#     fig_idx = plot_tt_correlation(
#         df=working_df,
#         row_label='tt_task0_raw',
#         col_label='tt_task3_list',
#         title='Event counts per (tt_task0_raw, tt_task3_list) combination',
#         filename_suffix='trigger_types_raw_and_list',
#         fig_idx=fig_idx,
#         base_dir=base_directories["figure_directory"],
#         show_plots=show_plots,
#         save_plots=save_plots,
#         plot_list=plot_list
#     )
#
#     fig_idx = plot_tt_correlation(
#         df=working_df,
#         row_label='tt_task4_fit',
#         col_label='tt_task3_list',
#         title='Event counts per (tt_task4_fit, tt_task3_list) combination',
#         filename_suffix='trigger_types_tracking_and_list',
#         fig_idx=fig_idx,
#         base_dir=base_directories["figure_directory"],
#         show_plots=show_plots,
#         save_plots=save_plots,
#         plot_list=plot_list
#     )
#
#     fig_idx = plot_tt_correlation(
#         df=working_df,
#         row_label='tt_task4_fit',
#         col_label='tt_task0_raw',
#         title='Event counts per (tt_task4_fit, tt_task0_raw) combination',
#         filename_suffix='trigger_types_tracking_and_raw',
#         fig_idx=fig_idx,
#         base_dir=base_directories["figure_directory"],
#         show_plots=show_plots,
#         save_plots=save_plots,
#         plot_list=plot_list
#     )

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (trigger_types_definitive_tt_and_raw)
# ============================================================================
# if (
#     (create_plots or create_essential_plots)
#     and task4_plot_enabled("trigger_types_definitive_tt_and_raw")
# ):
#     fig_idx = plot_tt_correlation(
#         df=working_df,
#         row_label='tt_task0_raw',
#         col_label=task4_plot_tt_column,
#         title=f'Event counts per (tt_task0_raw, {task4_plot_tt_column}) combination',
#         filename_suffix='trigger_types_tt_task4_fit_and_raw',
#         fig_idx=fig_idx,
#         base_dir=base_directories["figure_directory"],
#         show_plots=show_plots,
#         save_plots=save_plots,
#         plot_list=plot_list
#     )

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (timtrack_residuals_gaussian)
# ============================================================================
# if (create_essential_plots or create_plots) and task4_plot_enabled("timtrack_residuals_gaussian"):
#
#     # Combined methods --------------------------------------------------------------------------------------------
#     residual_columns = [
#         'tim_res_ystr_1', 'tim_res_ystr_2', 'tim_res_ystr_3', 'tim_res_ystr_4',
#         'tim_res_tsum_1', 'tim_res_tsum_2', 'tim_res_tsum_3', 'tim_res_tsum_4',
#         'tim_res_tdif_1', 'tim_res_tdif_2', 'tim_res_tdif_3', 'tim_res_tdif_4'
#     ]
#
#     unique_types = df_plot_ancillary[task4_plot_tt_column].unique()
#     for t in unique_types:
#         if t < 1000:
#             continue
#         subset_data = df_plot_ancillary[df_plot_ancillary[task4_plot_tt_column] == t]
#         plot_histograms_and_gaussian(subset_data, residual_columns, f"TimTrack Residuals with Gaussian for Processed Type {t}", figure_number=2, fit_gaussian=True, quantile=0.99)

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (external_residuals_gaussian)
# ============================================================================
# if (create_essential_plots or create_plots) and task4_plot_enabled("external_residuals_gaussian"):
#     # Combined methods - External residues -------------------------------------------------------------------------
#     residual_columns = [
#         'tim_ext_res_ystr_1', 'tim_ext_res_ystr_2', 'tim_ext_res_ystr_3', 'tim_ext_res_ystr_4',
#         'tim_ext_res_tsum_1', 'tim_ext_res_tsum_2', 'tim_ext_res_tsum_3', 'tim_ext_res_tsum_4',
#         'tim_ext_res_tdif_1', 'tim_ext_res_tdif_2', 'tim_ext_res_tdif_3', 'tim_ext_res_tdif_4'
#     ]
#
#     unique_types = df_plot_ancillary[task4_plot_tt_column].unique()
#     for t in unique_types:
#         if t < 1000:
#             continue
#         subset_data = df_plot_ancillary[df_plot_ancillary[task4_plot_tt_column] == t]
#         plot_histograms_and_gaussian(subset_data, residual_columns, f"External Residuals with Gaussian for Processed Type {t}", figure_number=2, fit_gaussian=True, quantile=0.99)

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (polar_theta_phi_definitive_tt_2d)
# ============================================================================
# if (
#     (create_plots or create_essential_plots)
#     and task4_plot_enabled("polar_theta_phi_definitive_tt_2d")
# ):
#     df_filtered = df_plot_ancillary
#     # tt_values = sorted(df_filtered['definitive_tt'].dropna().unique(), key=lambda x: int(x))
#
#     tt_values = [13, 12, 23, 34, 123, 124, 134, 234, 1234]
#
#     n_tt = len(tt_values)
#     ncols = 3
#     nrows = (n_tt + 1) // ncols
#
#     fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 7 * nrows), squeeze=False)
#     phi_nbins = 28
#     # theta_nbins = int(round(phi_nbins / 2) + 1)
#     theta_nbins = 40
#     theta_bins = np.linspace(theta_left_filter, theta_right_filter, theta_nbins )
#     phi_bins = np.linspace(phi_left_filter, phi_right_filter, phi_nbins)
#     colors = plt.cm.turbo
#
#     # Select theta/phi range (optional filtering)
#     theta_min, theta_max = theta_left_filter, theta_right_filter    # adjust as needed
#     phi_min, phi_max     = phi_left_filter, phi_right_filter        # adjust as needed
#
#     vmax_global = (
#         df_filtered.groupby(task4_plot_tt_column)[['theta', 'phi']]
#         .apply(
#             lambda df: np.histogram2d(
#                 df['theta'],
#                 df['phi'],
#                 bins=[theta_bins, phi_bins],
#             )[0].max()
#         )
#         .max()
#     )
#
#     for idx, tt_val in enumerate(tt_values):
#         row_idx, col_idx = divmod(idx, ncols)
#         ax = axes[row_idx][col_idx]
#
#         df_tt = df_filtered[df_filtered[task4_plot_tt_column] == tt_val]
#         theta_vals = df_tt['theta'].dropna()
#         phi_vals = df_tt['phi'].dropna()
#
#         # Apply range filtering
#         mask = (theta_vals >= theta_min) & (theta_vals <= theta_max) & \
#                (phi_vals >= phi_min) & (phi_vals <= phi_max)
#         theta_vals = theta_vals[mask]
#         phi_vals   = phi_vals[mask]
#
#         if len(theta_vals) < 10 or len(phi_vals) < 10:
#             ax.set_visible(False)
#             continue
#
#         # Polar plot settings
#         fig.delaxes(axes[row_idx][col_idx])  # remove the original non-polar Axes
#         ax = fig.add_subplot(nrows, ncols, idx + 1, polar=True)  # add a polar Axes
#         axes[row_idx][col_idx] = ax  # update reference for consistency
#
#         ax.set_facecolor(colors(0.0))  # darkest background in colormap
#
#         # 2D histogram: use phi as angle, theta as radius
#         h, r_edges, phi_edges = np.histogram2d(theta_vals, phi_vals, bins=[theta_bins, phi_bins])
#         r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
#         phi_centers = 0.5 * (phi_edges[:-1] + phi_edges[1:])
#         R, PHI = np.meshgrid(r_centers, phi_centers, indexing='ij')
#         c = ax.pcolormesh(PHI, R, h, cmap='viridis', vmin=0, vmax=vmax_global)
#         local_max = h.max()
#         cb = fig.colorbar(c, ax=ax, pad=0.1)
#         cb.ax.hlines(local_max, *cb.ax.get_xlim(), colors='white', linewidth=2, linestyles='dashed')
#         ax.set_title(f'Plane combination ({task4_plot_tt_column}) {tt_val}', fontsize=10)
#
#     plt.suptitle(
#         rf'2D Histogram of $\theta$ vs. $\phi$ for each {task4_plot_tt_column} Type',
#         fontsize=16,
#     )
#     plt.tight_layout(rect=[0, 0, 1, 0.95])
#     if save_plots:
#         final_filename = f'{fig_idx}_polar_theta_phi_tt_task4_fit_2D.png'
#         fig_idx += 1
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format='png')
#     if show_plots:
#         plt.show()
#     plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (event_display_sample)
# ============================================================================
# if (create_essential_plots or create_plots) and task4_plot_enabled("event_display_sample"):
#     _evd_y_cols = [f"p{p}_ypos" for p in range(1, 5)]
#     _evd_td_cols = [f"p{p}_tdif" for p in range(1, 5)]
#     _evd_q_cols = [f"p{p}_qsum" for p in range(1, 5)]
#     _evd_have = all(c in df_plot_ancillary.columns for c in _evd_y_cols + _evd_td_cols + _evd_q_cols)
#     _evd_have_track = all(c in df_plot_ancillary.columns for c in ("x", "y", "xp", "yp"))
#     if _evd_have and _evd_have_track:
#         _evd_pool = df_plot_ancillary[df_plot_ancillary[task4_plot_tt_column] == 1234]
#         n_evd = min(16, len(_evd_pool))
#         if n_evd > 0:
#             rng_evd = np.random.default_rng(42)
#             idx_evd = rng_evd.choice(len(_evd_pool), size=n_evd, replace=False)
#             _evd_sample = _evd_pool.iloc[sorted(idx_evd)]
#
#             z_arr = np.asarray(z_positions, dtype=float)
#             z_margin = 25.0
#             z_lo = z_arr.min() - z_margin
#             z_hi = z_arr.max() + z_margin
#             z_span = z_hi - z_lo                       # mm
#             x_span = 2.0 * strip_half                  # mm
#             y_span = 2.0 * width_half                  # mm
#
#             # Figure sized so that 1 mm ≈ px_per_mm inches on screen
#             # → GridSpec columns proportional to physical width → set_aspect('equal')
#             #   will fill each subplot box exactly, showing true detector proportions.
#             px_per_mm = 0.008
#             col_h_in = z_span * px_per_mm
#             col_xz_w_in = x_span * px_per_mm
#             col_yz_w_in = y_span * px_per_mm
#             events_per_row = 4
#             n_rows_evd = 4
#             fig_w = (col_xz_w_in + col_yz_w_in) * events_per_row + 1.5
#             fig_h = col_h_in * n_rows_evd + 1.5
#
#             fig = plt.figure(figsize=(fig_w, fig_h))
#             # Columns alternate [XZ, YZ] for each of the 4 events per row
#             gs = GridSpec(
#                 n_rows_evd, events_per_row * 2,
#                 figure=fig,
#                 width_ratios=[x_span, y_span] * events_per_row,
#                 hspace=0.55,
#                 wspace=0.20,
#             )
#
#             z_line = np.linspace(z_lo, z_hi, 80)
#
#             for ev_i, (_, row) in enumerate(_evd_sample.iterrows()):
#                 r_idx = ev_i // events_per_row
#                 c_ev = ev_i % events_per_row
#                 ax_xz = fig.add_subplot(gs[r_idx, c_ev * 2])
#                 ax_yz = fig.add_subplot(gs[r_idx, c_ev * 2 + 1])
#
#                 y_meas = np.array([row.get(c, np.nan) for c in _evd_y_cols], dtype=float)
#                 td_meas = np.array([row.get(c, np.nan) for c in _evd_td_cols], dtype=float)
#                 x_meas = td_meas * tdiff_to_x
#                 q_meas = np.array([row.get(c, 0.0) for c in _evd_q_cols], dtype=float)
#                 active = np.isfinite(y_meas) & (y_meas != 0)
#
#                 x0_ev = float(row.get("x", 0.0))
#                 y0_ev = float(row.get("y", 0.0))
#                 xp_ev = float(row.get("xp", 0.0))
#                 yp_ev = float(row.get("yp", 0.0))
#                 x_line = x0_ev + xp_ev * z_line
#                 y_line = y0_ev + yp_ev * z_line
#
#                 # Plane-position guidelines (horizontal lines at each plane's Z)
#                 for zp in z_arr:
#                     ax_xz.axhline(zp, color="lightgray", lw=0.4, zorder=0)
#                     ax_yz.axhline(zp, color="lightgray", lw=0.4, zorder=0)
#                 # Strip Y-centre guidelines on YZ panel
#                 for sy in y_pos_P1_and_P3:
#                     ax_yz.axvline(sy, color="lightgray", lw=0.4, ls="--", zorder=0)
#
#                 # Measured hits — errorbar (behind) + marker (in front)
#                 # X (T_dif): the "better" direction  → thin, subtle bar
#                 # Y (strip): the "worse"  direction  → slightly thicker/opaque bar
#                 for pp in range(4):
#                     if active[pp]:
#                         sz_ev = float(np.clip(q_meas[pp] * 4, 20, 200)) if q_meas[pp] > 0 else 20
#                         ax_xz.errorbar(
#                             x_meas[pp], z_arr[pp], xerr=anc_sx,
#                             fmt="none", ecolor=f"C{pp}",
#                             elinewidth=0.7, capsize=1.5, capthick=0.6,
#                             alpha=0.30, zorder=2,
#                         )
#                         ax_yz.errorbar(
#                             y_meas[pp], z_arr[pp], xerr=anc_sy,
#                             fmt="none", ecolor=f"C{pp}",
#                             elinewidth=1.1, capsize=2.5, capthick=0.9,
#                             alpha=0.45, zorder=2,
#                         )
#                         ax_xz.scatter(x_meas[pp], z_arr[pp], s=sz_ev,
#                                       c=f"C{pp}", zorder=3, alpha=0.9)
#                         ax_yz.scatter(y_meas[pp], z_arr[pp], s=sz_ev,
#                                       c=f"C{pp}", zorder=3, alpha=0.9)
#
#                 # Fitted track line
#                 ax_xz.plot(x_line, z_line, "r-", lw=0.9, alpha=0.8, zorder=2)
#                 ax_yz.plot(y_line, z_line, "r-", lw=0.9, alpha=0.8, zorder=2)
#
#                 # Axis limits — real mm detector dimensions
#                 ax_xz.set_xlim(-strip_half, strip_half)
#                 ax_xz.set_ylim(z_lo, z_hi)
#                 ax_xz.set_aspect("equal")
#                 ax_xz.set_xlabel("X (mm)", fontsize=5)
#                 ax_xz.set_ylabel("Z (mm)", fontsize=5)
#                 ax_xz.tick_params(labelsize=4)
#                 ax_xz.set_title(f"ev{ev_i + 1} XZ", fontsize=6)
#
#                 ax_yz.set_xlim(-width_half, width_half)
#                 ax_yz.set_ylim(z_lo, z_hi)
#                 ax_yz.set_aspect("equal")
#                 ax_yz.set_xlabel("Y (mm)", fontsize=5)
#                 ax_yz.set_ylabel("Z (mm)", fontsize=5)
#                 ax_yz.tick_params(labelsize=4)
#                 ax_yz.set_title(f"ev{ev_i + 1} YZ", fontsize=6)
#
#             plt.suptitle(
#                 "Sample 4-fold event displays — equal mm scale (Z vertical)\n"
#                 "C0–C3 = planes 1–4  |  marker size ~ charge  |  red line = fitted track  |  "
#                 f"detector: X={x_span:.0f} mm  Y={y_span:.0f} mm  Z={z_arr[-1]:.0f} mm\n"
#                 f"errorbars: XZ = ±σ_X (T_dif, {anc_sx:.0f} mm, thin)  ·  "
#                 f"YZ = ±σ_Y (strip, {anc_sy:.0f} mm, thick)",
#                 fontsize=8,
#             )
#             plt.tight_layout(rect=[0, 0, 1, 0.96])
#             if save_plots:
#                 final_filename = f"{fig_idx}_event_display_sample.png"
#                 fig_idx += 1
#                 save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#                 plot_list.append(save_fig_path)
#                 save_plot_figure(save_fig_path, format="png", alias="event_display_sample")
#             if show_plots:
#                 plt.show()
#             plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (track_consistency_loo_residuals)
# ============================================================================
# if (create_essential_plots or create_plots) and task4_plot_enabled("track_consistency_loo_residuals"):
#     _loo_y_cols = [f"tim_ext_res_ystr_{p}" for p in range(1, 5)]
#     _loo_td_cols = [f"tim_ext_res_tdif_{p}" for p in range(1, 5)]
#     _loo_have = all(c in df_plot_ancillary.columns for c in _loo_y_cols + _loo_td_cols + [task4_plot_tt_column])
#     if _loo_have:
#         # 3-fold combos containing each plane — removing that plane leaves a 2-plane telescope,
#         # which is nearly degenerate (5 params, 6 equations → residuals ≈ 0).
#         # 4-fold events (1234) — removing any plane leaves a proper 3-plane telescope.
#         _loo_3fold_by_plane = {
#             1: [123, 124, 134],
#             2: [123, 124, 234],
#             3: [123, 134, 234],
#             4: [124, 134, 234],
#         }
#         _loo_row_defs = [
#             (lambda p: [1234],                  "4-fold  (3-plane telescope — non-degenerate)"),
#             (lambda p: _loo_3fold_by_plane[p],  "3-fold  (2-plane telescope — degenerate, residuals → 0)"),
#         ]
#
#         fig_loo, axes_loo = plt.subplots(
#             2, 4, figsize=(18, 9), squeeze=False,
#             gridspec_kw={"hspace": 0.50, "wspace": 0.35},
#         )
#         _loo_df_all = df_plot_ancillary.copy()
#
#         for _ri, (tt_fn, row_label) in enumerate(_loo_row_defs):
#             for _pi in range(4):
#                 p = _pi + 1
#                 ax = axes_loo[_ri][_pi]
#                 _tt_filter = tt_fn(p)
#                 _mask_tt = _loo_df_all[task4_plot_tt_column].isin(_tt_filter)
#                 _sub = _loo_df_all[_mask_tt]
#
#                 ry = pd.to_numeric(_sub[f"tim_ext_res_ystr_{p}"], errors="coerce")
#                 rx = pd.to_numeric(_sub[f"tim_ext_res_tdif_{p}"], errors="coerce") * tdiff_to_x
#                 _mask_loo = ry.notna() & rx.notna()
#
#                 ry = ry[_mask_loo]
#                 rx = rx[_mask_loo]
#
#                 if len(rx) < 5:
#                     ax.text(0.5, 0.5, "no data", ha="center", va="center",
#                             transform=ax.transAxes, fontsize=9)
#                     ax.set_title(f"Plane {p}", fontsize=9)
#                     ax.set_visible(False)
#                     continue
#
#                 xlim = max(float(rx.abs().quantile(0.99)), 1.0)
#                 ylim = max(float(ry.abs().quantile(0.99)), 1.0)
#                 hb = ax.hexbin(rx, ry, gridsize=40, cmap="viridis",
#                                extent=(-xlim, xlim, -ylim, ylim), mincnt=1)
#                 plt.colorbar(hb, ax=ax, label="counts", pad=0.02)
#                 ax.axhline(0, color="red", lw=0.8, ls="--", alpha=0.6)
#                 ax.axvline(0, color="red", lw=0.8, ls="--", alpha=0.6)
#                 ax.set_xlabel("LOO X residual (mm)", fontsize=8)
#                 if _pi == 0:
#                     ax.set_ylabel(f"LOO Y residual (mm)\n[{row_label}]", fontsize=7)
#                 else:
#                     ax.set_ylabel("LOO Y residual (mm)", fontsize=8)
#                 ax.set_xlim(-xlim, xlim)
#                 ax.set_ylim(-ylim, ylim)
#                 ax.set_title(
#                     f"Plane {p}  |  tt∈{_tt_filter}\nn={len(rx):,}",
#                     fontsize=8,
#                 )
#                 ax.grid(True, alpha=0.3)
#
#         fig_loo.suptitle(
#             "Track-consistency: leave-one-out (LOO) residuals per plane\n"
#             "Top: 4-fold events — 3-plane telescope (proper, non-degenerate)  |  "
#             "Bottom: 3-fold events — 2-plane telescope (degenerate → residuals collapse to 0)\n"
#             "X residual = (predicted − measured) × strip_speed  |  Y residual = predicted − measured strip Y",
#             fontsize=9,
#         )
#         plt.tight_layout(rect=[0, 0, 1, 0.90])
#         if save_plots:
#             final_filename = f"{fig_idx}_track_consistency_loo_residuals.png"
#             fig_idx += 1
#             save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#             plot_list.append(save_fig_path)
#             save_plot_figure(save_fig_path, format="png", alias="track_consistency_loo_residuals")
#         if show_plots:
#             plt.show()
#         plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (strip_hit_occupancy)
# ============================================================================
# if (create_essential_plots or create_plots) and task4_plot_enabled("strip_hit_occupancy"):
#     _occ_y_cols = [f"p{p}_ypos" for p in range(1, 5)]
#     _occ_td_cols = [f"p{p}_tdif" for p in range(1, 5)]
#     _occ_have = all(c in df_plot_ancillary.columns for c in _occ_y_cols + _occ_td_cols)
#     if _occ_have:
#         fig, axes = plt.subplots(1, 4, figsize=(16, 4), squeeze=False)
#         for pp in range(4):
#             ax = axes[0][pp]
#             y_hits = pd.to_numeric(df_plot_ancillary[f"p{pp + 1}_ypos"], errors="coerce")
#             x_hits = pd.to_numeric(df_plot_ancillary[f"p{pp + 1}_tdif"], errors="coerce") * tdiff_to_x
#             mask_occ = y_hits.notna() & x_hits.notna() & (y_hits != 0) & (x_hits != 0)
#             x_hits = x_hits[mask_occ]
#             y_hits = y_hits[mask_occ]
#             if len(x_hits) < 5:
#                 ax.set_title(f"Plane {pp + 1}: no data", fontsize=9)
#                 ax.set_visible(False)
#                 continue
#             hb = ax.hexbin(x_hits, y_hits, gridsize=30, cmap="hot_r", mincnt=1,
#                            extent=(-strip_half, strip_half, -width_half, width_half))
#             plt.colorbar(hb, ax=ax, label="hits")
#             y_centers = y_pos_P1_and_P3 if pp % 2 == 0 else y_pos_P2_and_P4
#             for sy in y_centers:
#                 ax.axhline(sy, color="cyan", lw=0.7, ls="--", alpha=0.8)
#             ax.set_xlim(-strip_half, strip_half)
#             ax.set_ylim(-width_half, width_half)
#             ax.set_xlabel("X from T_dif (mm)", fontsize=9)
#             ax.set_ylabel("Y_final (mm)", fontsize=9)
#             ax.set_title(f"Plane {pp + 1} hit map  (n={len(x_hits)})", fontsize=9)
#             ax.grid(True, alpha=0.2)
#         plt.suptitle(
#             "Strip hit occupancy: 2D hit density per plane\n"
#             "Cyan dashed = strip Y centres",
#             fontsize=11,
#         )
#         plt.tight_layout(rect=[0, 0, 1, 0.90])
#         if save_plots:
#             final_filename = f"{fig_idx}_strip_hit_occupancy.png"
#             fig_idx += 1
#             save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#             plot_list.append(save_fig_path)
#             save_plot_figure(save_fig_path, format="png", alias="strip_hit_occupancy")
#         if show_plots:
#             plt.show()
#         plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (tim_th_chi_sigmafit_1234_histogram)
# ============================================================================
# if (
#     (create_essential_plots or create_plots)
#     and task4_plot_enabled("tim_th_chi_sigmafit_1234_histogram")
# ):
#     fig_idx = render_task4_chi2_four_plane_histogram(
#         working_df=working_df,
#         base_cond=base_cond,
#         tt_column=task4_plot_tt_column,
#         global_variables=global_variables,
#         fiducial_pass_index=track_efficiency_four_plane_fiducial_index,
#         fig_idx=fig_idx,
#         figure_directory=base_directories["figure_directory"],
#         save_plot_figure=save_plot_figure,
#         save_plots=save_plots,
#         show_plots=show_plots,
#         plot_list=plot_list,
#     )

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (track_based_efficiency)
# ============================================================================
# if (
#     (create_essential_plots or create_plots)
#     and task4_plot_enabled("track_based_efficiency")
#     and (
#         bool(efficiency_metadata_payload.get("available", False))
#         or bool(efficiency_metadata_payload_fullplane.get("available", False))
#     )
# ):
#     edges_eff = (
#         efficiency_metadata_payload["edges"]
#         if bool(efficiency_metadata_payload.get("available", False))
#         else efficiency_metadata_payload_fullplane["edges"]
#     )
#     fig, axes = plt.subplots(3, 4, figsize=(18, 13), squeeze=False)
#
#     for plane_idx, plane in enumerate(range(1, 5)):
#         plane_result = efficiency_metadata_payload["plane_results"].get(plane, {})
#         plane_result_full = efficiency_metadata_payload_fullplane["plane_results"].get(plane, {})
#         ax_2d = axes[0][plane_idx]
#         ax_1dy = axes[1][plane_idx]
#         ax_1dx = axes[2][plane_idx]
#
#         n_denom = int(plane_result.get("n_denom", 0) or 0)
#         n_denom_full = int(plane_result_full.get("n_denom", 0) or 0)
#         if max(n_denom, n_denom_full) < int(efficiency_metadata_cfg["min_accepted_events"]):
#             ax_2d.set_visible(False)
#             ax_1dy.set_visible(False)
#             ax_1dx.set_visible(False)
#             continue
#
#         overall_eff = plane_result.get("overall_eff", np.nan)
#         overall_eff_full = plane_result_full.get("overall_eff", np.nan)
#         representative_eff, representative_label, _, _, _ = _resolve_track_efficiency_representative(
#             plane_result
#         )
#         sim_eff_percent = (
#             float(track_efficiency_simulated_efficiencies_percent[plane - 1])
#             if plane - 1 < len(track_efficiency_simulated_efficiencies_percent)
#             else np.nan
#         )
#         plane_color = f"C{plane - 1}"
#         y_reference = np.asarray(
#             plane_result_full.get("y_reference", plane_result.get("y_reference", [])),
#             dtype=float,
#         )
#         eff_2d = np.asarray(
#             plane_result_full.get("eff_2d", plane_result.get("eff_2d", np.empty((0, 0)))),
#             dtype=float,
#         )
#
#         im = ax_2d.imshow(
#             eff_2d.T,
#             origin="lower",
#             aspect="auto",
#             extent=[
#                 float(edges_eff["x"][0]),
#                 float(edges_eff["x"][-1]),
#                 float(edges_eff["y"][0]),
#                 float(edges_eff["y"][-1]),
#             ],
#             vmin=0,
#             vmax=1,
#             cmap="RdYlGn",
#         )
#         plt.colorbar(im, ax=ax_2d, label="efficiency")
#         for sy in y_reference:
#             ax_2d.axhline(float(sy), color="cyan", lw=0.7, ls="--", alpha=0.7)
#         if track_efficiency_fiducial_active:
#             # x_left, x_right = _task4_resolve_region_bounds(
#             #     track_efficiency_fiducial_cfg.get("x_left", None),
#             #     track_efficiency_fiducial_cfg.get("x_right", None),
#             #     -float(strip_half),
#             #     float(strip_half),
#             # )
#             plane_x_cfg = track_efficiency_fiducial_cfg.get("x_by_plane", {}).get(plane, {})
#             x_left, x_right = _task4_resolve_region_bounds(
#                 plane_x_cfg.get("left", None),
#                 plane_x_cfg.get("right", None),
#                 -float(width_half),
#                 float(width_half),
#             )
#             plane_y_cfg = track_efficiency_fiducial_cfg.get("y_by_plane", {}).get(plane, {})
#             y_left, y_right = _task4_resolve_region_bounds(
#                 plane_y_cfg.get("left", None),
#                 plane_y_cfg.get("right", None),
#                 -float(width_half),
#                 float(width_half),
#             )
#             ax_2d.vlines((x_left, x_right), y_left, y_right, colors="black", linestyles="--", linewidth=1.1, alpha=0.85)
#             ax_2d.hlines((y_left, y_right), x_left, x_right, colors="black", linestyles="--", linewidth=1.1, alpha=0.85)
#         ax_2d.set_xlabel("Projected X (mm)", fontsize=8)
#         ax_2d.set_ylabel("Projected Y (mm)", fontsize=8)
#         ax_2d.set_title(
#             (
#                 f"Plane {plane}\n"
#                 f"fid={_format_task4_percent_label(overall_eff)}  "
#                 f"full={_format_task4_percent_label(overall_eff_full)}"
#                 + (
#                     f"  sim={_format_task4_percent_label(sim_eff_percent)}"
#                     if np.isfinite(sim_eff_percent)
#                     else ""
#                 )
#                 + f"\n(n_fid={n_denom}, n_full={n_denom_full})"
#             ),
#             fontsize=9,
#         )
#
#         for axis_payload, axis_payload_full, axis, xlabel, half_range in (
#             (plane_result.get("y", {}), plane_result_full.get("y", {}), ax_1dy, "Projected Y (mm)", float(width_half)),
#             (plane_result.get("x", {}), plane_result_full.get("x", {}), ax_1dx, "Projected X (mm)", float(strip_half)),
#         ):
#             centers = np.asarray(axis_payload.get("centers", []), dtype=float)
#             eff_vals = np.asarray(axis_payload.get("eff", []), dtype=float)
#             unc_vals = np.asarray(axis_payload.get("unc", []), dtype=float)
#             den_vals = np.asarray(axis_payload.get("den", []), dtype=float)
#             valid = np.isfinite(eff_vals) & (den_vals > 0)
#
#             centers_full = np.asarray(axis_payload_full.get("centers", []), dtype=float)
#             eff_vals_full = np.asarray(axis_payload_full.get("eff", []), dtype=float)
#             unc_vals_full = np.asarray(axis_payload_full.get("unc", []), dtype=float)
#             den_vals_full = np.asarray(axis_payload_full.get("den", []), dtype=float)
#             valid_full = np.isfinite(eff_vals_full) & (den_vals_full > 0)
#
#             if np.any(valid_full):
#                 axis.errorbar(
#                     centers_full[valid_full],
#                     eff_vals_full[valid_full],
#                     yerr=unc_vals_full[valid_full],
#                     fmt="o--",
#                     ms=3.5,
#                     color="0.45",
#                     alpha=0.80,
#                     label=(
#                         f"no fid  (n={n_denom_full}, "
#                         f"{_format_task4_percent_label(overall_eff_full)})"
#                     ),
#                 )
#             if np.any(valid):
#                 axis.errorbar(
#                     centers[valid],
#                     eff_vals[valid],
#                     yerr=unc_vals[valid],
#                     fmt="o-",
#                     ms=4,
#                     color=plane_color,
#                     alpha=0.85,
#                     label=f"fiducial  (n={n_denom}, {_format_task4_percent_label(overall_eff)})",
#                 )
#             if np.isfinite(representative_eff):
#                 _representative_line = axis.axhline(
#                     float(representative_eff),
#                     color=plane_color,
#                     lw=2.0,
#                     ls=_TRACK_EFF_REPRESENTATIVE_LINESTYLE,
#                     alpha=0.95,
#                     zorder=4,
#                     label=f"{representative_label}  {_format_task4_percent_label(representative_eff)}",
#                 )
#                 _representative_line.set_path_effects(
#                     [
#                         path_effects.Stroke(linewidth=4.2, foreground="white", alpha=0.95),
#                         path_effects.Normal(),
#                     ]
#                 )
#             if xlabel.startswith("Projected Y"):
#                 for sy in y_reference:
#                     axis.axvline(float(sy), color="lightgray", lw=0.9, ls="--", alpha=0.8)
#             if np.isfinite(sim_eff_percent):
#                 axis.axhline(
#                     float(sim_eff_percent) / 100.0,
#                     color="black",
#                     lw=1.0,
#                     ls=_TRACK_EFF_SIMULATION_LINESTYLE,
#                     alpha=0.75,
#                     zorder=3,
#                     label=f"simulation  {_format_task4_percent_label(sim_eff_percent)}",
#                 )
#             axis.set_ylim(0, 1.08)
#             axis.set_xlim(-half_range, half_range)
#             axis.set_xlabel(xlabel, fontsize=8)
#             axis.set_ylabel("Efficiency", fontsize=8)
#             handles, labels = axis.get_legend_handles_labels()
#             if handles:
#                 axis.legend(fontsize=7)
#             axis.grid(True, alpha=0.3)
#
#     plt.suptitle(
#         "Track-based single-plane efficiency (telescope method)\n"
#         "3 planes build a track → project to test plane → did the test plane fire?\n"
#         + ("Solid colour = active fiducial efficiency curve, dashed gray = no-fid/full-plane reference" if track_efficiency_fiducial_active else "No fiducial cut is active: solid and dashed-gray references should overlap")
#         + "; dashed plane-colour = fiducial representative efficiency"
#         + ("; dashed black = simulation overall reference" if track_efficiency_simulated_efficiencies_percent else "")
#         + ("\n" + track_efficiency_simulation_title_line if track_efficiency_simulated_efficiencies_percent else ""),
#         fontsize=11,
#     )
#     plt.tight_layout(rect=[0, 0, 1, 0.94])
#     if save_plots:
#         final_filename = f"{fig_idx}_track_based_efficiency.png"
#         fig_idx += 1
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format="png", alias="track_based_efficiency")
#     if show_plots:
#         plt.show()
#     plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (timtrack_projection_ellipse_contours)
# ============================================================================
# if (
#     (create_essential_plots or create_plots)
#     and task4_plot_enabled("timtrack_projection_ellipse_contours")
#     and bool(projection_ellipse_payload.get("tt_results", {}))
# ):
#     _projection_tt_results = projection_ellipse_payload["tt_results"]
#     _projection_tt_labels = tuple(projection_ellipse_cfg["focus_definitive_tt"])
#     _n_projection_panels = max(1, len(_projection_tt_labels))
#     _n_projection_cols = 3 if _n_projection_panels > 3 else _n_projection_panels
#     _n_projection_rows = int(math.ceil(_n_projection_panels / _n_projection_cols))
#     _projection_fig, _projection_axes = plt.subplots(
#         _n_projection_rows,
#         _n_projection_cols,
#         figsize=(6.2 * _n_projection_cols, 5.7 * _n_projection_rows),
#         squeeze=False,
#     )
#     _projection_axes_flat = list(_projection_axes.ravel())
#     _projection_colors = ("#40c9ff", "#f4d35e", "#ff6b6b", "#70e000")
#     _projection_im = None
#
#     for _ax, _tt_label in zip(_projection_axes_flat, _projection_tt_labels):
#         _result = _projection_tt_results.get(str(_tt_label), {})
#         _ax.axhline(0.0, color="white", lw=0.55, ls=":", alpha=0.5)
#         _ax.axvline(0.0, color="white", lw=0.55, ls=":", alpha=0.5)
#         _ax.set_xlabel("xp", fontsize=9)
#         _ax.set_ylabel("yp", fontsize=9)
#         _ax.tick_params(labelsize=8)
#
#         if not isinstance(_result, dict) or not bool(_result.get("available", False)):
#             _reason = str(_result.get("reason", "unavailable")) if isinstance(_result, dict) else "unavailable"
#             _n_points = int(_result.get("n_points", 0) or 0) if isinstance(_result, dict) else 0
#             _ax.text(
#                 0.5,
#                 0.5,
#                 f"TT {_tt_label}\nNo ellipse fit\nreason={_reason}\nn={_n_points}",
#                 transform=_ax.transAxes,
#                 ha="center",
#                 va="center",
#                 fontsize=9,
#                 color="0.82",
#                 bbox={"boxstyle": "round", "facecolor": "0.12", "edgecolor": "0.4", "alpha": 0.9},
#             )
#             _ax.set_title(f"tt_task4_fit = {_tt_label}", fontsize=10)
#             _ax.set_facecolor("0.05")
#             _ax.set_aspect("equal", adjustable="box")
#             continue
#
#         _norm_density = np.asarray(_result.get("normalized_density", np.empty((0, 0))), dtype=float)
#         _x_edges = np.asarray(_result.get("x_edges", np.empty(0)), dtype=float)
#         _y_edges = np.asarray(_result.get("y_edges", np.empty(0)), dtype=float)
#         _x_centers = np.asarray(_result.get("x_centers", np.empty(0)), dtype=float)
#         _y_centers = np.asarray(_result.get("y_centers", np.empty(0)), dtype=float)
#         _ellipse_model = _result.get("ellipse_model", {})
#         if not isinstance(_ellipse_model, dict):
#             _ellipse_model = {}
#
#         _projection_im = _ax.imshow(
#             _norm_density.T,
#             origin="lower",
#             aspect="equal",
#             extent=[float(_x_edges[0]), float(_x_edges[-1]), float(_y_edges[0]), float(_y_edges[-1])],
#             vmin=0.0,
#             vmax=1.0,
#             cmap=str(projection_ellipse_cfg["cmap"]),
#         )
#         _levels = np.asarray(_result.get("contour_fractions", np.empty(0)), dtype=float)
#         _level_colors = _projection_colors[: len(_levels)]
#         if _levels.size > 0:
#             _ax.contour(
#                 _x_centers,
#                 _y_centers,
#                 _norm_density.T,
#                 levels=_levels.tolist(),
#                 colors=_level_colors,
#                 linewidths=1.15,
#                 alpha=0.95,
#             )
#
#         _center_x = float(_ellipse_model.get("center_x", np.nan))
#         _center_y = float(_ellipse_model.get("center_y", np.nan))
#         _sigma_major = float(_ellipse_model.get("sigma_major", np.nan))
#         _sigma_minor = float(_ellipse_model.get("sigma_minor", np.nan))
#         _rotation_deg = float(_ellipse_model.get("rotation_deg", np.nan))
#         for _level, _color in zip(_levels, _level_colors):
#             _scale = _ellipse_scale_for_peak_fraction(float(_level))
#             if not np.isfinite(_scale):
#                 continue
#             _ellipse = Ellipse(
#                 (_center_x, _center_y),
#                 width=2.0 * _sigma_major * _scale,
#                 height=2.0 * _sigma_minor * _scale,
#                 angle=_rotation_deg,
#                 fill=False,
#                 lw=1.6,
#                 ls="--",
#                 ec=_color,
#                 alpha=0.95,
#             )
#             _ax.add_patch(_ellipse)
#
#         _ax.scatter([_center_x], [_center_y], s=14, color="white", marker="x", linewidths=1.0)
#         _ax.set_facecolor("0.05")
#         _ax.set_xlim(float(_result.get("plot_x_min", projection_ellipse_cfg["x_min"])), float(_result.get("plot_x_max", projection_ellipse_cfg["x_max"])))
#         _ax.set_ylim(float(_result.get("plot_y_min", projection_ellipse_cfg["y_min"])), float(_result.get("plot_y_max", projection_ellipse_cfg["y_max"])))
#         _ax.set_aspect("equal", adjustable="box")
#         _ax.set_title(f"tt_task4_fit = {_tt_label}", fontsize=10)
#         _ax.text(
#             0.02,
#             0.98,
#             "\n".join(
#                 (
#                     f"n={int(_result.get('n_points', 0)):,}",
#                     f"FWHM x/y={float(_result.get('fwhm_halfwidth_x_over_y', np.nan)):.3f}",
#                     f"FWHM a/b={float(_result.get('fwhm_axis_ratio_major_over_minor', np.nan)):.3f}",
#                     f"rot={_rotation_deg:.1f} deg",
#                 )
#             ),
#             transform=_ax.transAxes,
#             va="top",
#             ha="left",
#             fontsize=8,
#             color="white",
#             bbox={"boxstyle": "round", "facecolor": "0.08", "edgecolor": "0.35", "alpha": 0.84},
#         )
#
#     for _ax in _projection_axes_flat[len(_projection_tt_labels):]:
#         _ax.axis("off")
#
#     if _projection_im is not None:
#         _projection_cax = _projection_fig.add_axes([0.90, 0.22, 0.016, 0.52])
#         _projection_cbar = _projection_fig.colorbar(_projection_im, cax=_projection_cax)
#         _projection_cbar.set_label("normalized density", fontsize=9)
#         _projection_cbar.ax.tick_params(labelsize=8)
#
#     _projection_legend_handles = [
#         Line2D([0], [0], color=color, lw=1.4, ls="-", label=f"{int(round(level * 100.0))}% contour")
#         for level, color in zip(tuple(projection_ellipse_cfg["contour_fractions"]), _projection_colors)
#     ]
#     _projection_legend_handles.extend(
#         [
#             Line2D([0], [0], color="white", lw=1.4, ls="--", label="ellipse fit"),
#             Line2D([0], [0], color="white", marker="x", lw=0.0, markersize=6, label="density center"),
#         ]
#     )
#     _projection_fig.legend(
#         handles=_projection_legend_handles,
#         loc="lower center",
#         ncol=min(5, len(_projection_legend_handles)),
#         fontsize=8,
#         bbox_to_anchor=(0.5, 0.01),
#         frameon=False,
#     )
#     _projection_fig.suptitle(
#         "TimTrack projection contours with ellipse fit by tt_task4_fit\n"
#         "Solid contours = smoothed xp/yp density at fixed peak fractions; dashed ellipses = matched elliptical-Gaussian family\n"
#         f"{task4_efficiency_vector_title_line}",
#         fontsize=11,
#     )
#     _projection_fig.subplots_adjust(left=0.06, right=0.87, bottom=0.11, top=0.84, wspace=0.22, hspace=0.26)
#     if save_plots:
#         _projection_filename = f"{fig_idx}_timtrack_projection_ellipse_contours.png"
#         fig_idx += 1
#         _projection_path = os.path.join(base_directories["figure_directory"], _projection_filename)
#         plot_list.append(_projection_path)
#         save_plot_figure(
#             _projection_path,
#             format="png",
#             alias="timtrack_projection_ellipse_contours",
#         )
#     if show_plots:
#         plt.show()
#     plt.close(_projection_fig)

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (timtrack_projection_scaled_angle_comparison)
# ============================================================================
# if (
#     (create_essential_plots or create_plots)
#     and task4_plot_enabled("timtrack_projection_scaled_angle_comparison")
#     and bool(projection_ellipse_payload.get("tt_results", {}))
# ):
#     _xproj_all, _yproj_all, _projection_source_scaled = _extract_projection_arrays(df_plot_ancillary)
#     if (
#         _xproj_all is not None
#         and _yproj_all is not None
#         and task4_plot_tt_column in df_plot_ancillary.columns
#     ):
#         _def_tt_all_scaled = pd.to_numeric(
#             df_plot_ancillary[task4_plot_tt_column],
#             errors="coerce",
#         ).fillna(0).to_numpy(dtype=np.int32)
#         def _combined_quantile_limits(*arrays, q_lo=0.01, q_hi=0.99, fallback=(-1.0, 1.0)):
#             _parts = []
#             for _arr in arrays:
#                 _arr = np.asarray(_arr, dtype=float)
#                 _arr = _arr[np.isfinite(_arr)]
#                 if _arr.size > 0:
#                     _parts.append(_arr)
#             if not _parts:
#                 return fallback
#             _merged = np.concatenate(_parts)
#             _lo, _hi = np.quantile(_merged, [q_lo, q_hi])
#             _lo = float(_lo)
#             _hi = float(_hi)
#             if not np.isfinite(_lo) or not np.isfinite(_hi) or _hi <= _lo:
#                 return fallback
#             return (_lo, _hi)
#
#         _global_scale_factor = float(projection_scaling_summary.get("global_factor", np.nan))
#         _scaled_rows: list[dict[str, object]] = []
#         if np.isfinite(_global_scale_factor) and _global_scale_factor > 0.0:
#             for _tt_label in tuple(projection_ellipse_cfg.get("focus_definitive_tt", ())):
#                 _tt_result = projection_ellipse_payload.get("tt_results", {}).get(str(_tt_label), {})
#                 if not isinstance(_tt_result, dict) or not bool(_tt_result.get("available", False)):
#                     continue
#                 _tt_x_half = float(_tt_result.get("fwhm_halfwidth_xproj", np.nan))
#                 _tt_y_half = float(_tt_result.get("fwhm_halfwidth_yproj", np.nan))
#                 _tt_scale_factor_local = (
#                     float(_tt_y_half / _tt_x_half)
#                     if np.isfinite(_tt_x_half)
#                     and _tt_x_half > 0.0
#                     and np.isfinite(_tt_y_half)
#                     else np.nan
#                 )
#                 if not np.isfinite(_tt_scale_factor_local) or _tt_scale_factor_local <= 0.0:
#                     continue
#
#                 _tt_int = int(normalize_tt_label(_tt_label, default="0") or 0)
#                 _tt_mask = (
#                     (_def_tt_all_scaled == _tt_int)
#                     & np.isfinite(_xproj_all)
#                     & np.isfinite(_yproj_all)
#                     & (_xproj_all >= float(_tt_result.get("plot_x_min", -np.inf)))
#                     & (_xproj_all <= float(_tt_result.get("plot_x_max", np.inf)))
#                     & (_yproj_all >= float(_tt_result.get("plot_y_min", -np.inf)))
#                     & (_yproj_all <= float(_tt_result.get("plot_y_max", np.inf)))
#                 )
#                 _xproj_ref = np.asarray(_xproj_all[_tt_mask], dtype=float)
#                 _yproj_ref = np.asarray(_yproj_all[_tt_mask], dtype=float)
#                 if _xproj_ref.size < int(projection_ellipse_cfg["min_points"]):
#                     continue
#
#                 _xproj_scaled = _xproj_ref * _global_scale_factor
#                 _theta_ref, _phi_ref = calculate_angles(_xproj_ref, _yproj_ref)
#                 _theta_scaled, _phi_scaled = calculate_angles(_xproj_scaled, _yproj_ref)
#                 _theta_ref_deg = np.degrees(np.asarray(_theta_ref, dtype=float))
#                 _theta_scaled_deg = np.degrees(np.asarray(_theta_scaled, dtype=float))
#                 _phi_ref_deg = np.degrees(np.asarray(_phi_ref, dtype=float))
#                 _phi_scaled_deg = np.degrees(np.asarray(_phi_scaled, dtype=float))
#
#                 _scaled_rows.append(
#                     {
#                         "tt_label": str(_tt_label),
#                         "n_points": int(_xproj_ref.size),
#                         "scale_factor_local": float(_tt_scale_factor_local),
#                         "scale_factor_global": float(_global_scale_factor),
#                         "xproj_original": _xproj_ref,
#                         "xproj_scaled": _xproj_scaled,
#                         "yproj_original": _yproj_ref,
#                         "yproj_scaled": _yproj_ref,
#                         "theta_original_deg": _theta_ref_deg,
#                         "theta_scaled_deg": _theta_scaled_deg,
#                         "phi_original_deg": _phi_ref_deg,
#                         "phi_scaled_deg": _phi_scaled_deg,
#                     }
#                 )
#
#         if _scaled_rows:
#             _hist_bins = max(40, min(120, int(projection_ellipse_cfg["bin_count"])))
#             _scaled_fig, _scaled_axes = plt.subplots(
#                 len(_scaled_rows),
#                 4,
#                 figsize=(15, 2.5 * len(_scaled_rows) + 1.5),
#                 squeeze=False,
#             )
#             _column_defs = (
#                 ("xproj_original", "xproj_scaled", "xproj", (-1.0, 1.0)),
#                 ("yproj_original", "yproj_scaled", "yproj", (-1.0, 1.0)),
#                 ("theta_original_deg", "theta_scaled_deg", r"$\theta$ (deg)", (0.0, 90.0)),
#                 ("phi_original_deg", "phi_scaled_deg", r"$\phi$ (deg)", (-180.0, 180.0)),
#             )
#
#             for _row_idx, _row_payload in enumerate(_scaled_rows):
#                 for _col_idx, (_orig_key, _scaled_key, _xlabel, _fallback) in enumerate(_column_defs):
#                     _ax = _scaled_axes[_row_idx][_col_idx]
#                     _vals_orig = np.asarray(_row_payload[_orig_key], dtype=float)
#                     _vals_scaled = np.asarray(_row_payload[_scaled_key], dtype=float)
#                     _limits = _combined_quantile_limits(_vals_orig, _vals_scaled, fallback=_fallback)
#                     _bins = np.linspace(_limits[0], _limits[1], _hist_bins + 1)
#                     _vals_orig = _vals_orig[np.isfinite(_vals_orig)]
#                     _vals_scaled = _vals_scaled[np.isfinite(_vals_scaled)]
#
#                     _ax.hist(
#                         _vals_orig,
#                         bins=_bins,
#                         histtype="step",
#                         density=True,
#                         linewidth=1.6,
#                         color="#1f77b4",
#                         label="original" if _row_idx == 0 else None,
#                     )
#                     _ax.hist(
#                         _vals_scaled,
#                         bins=_bins,
#                         histtype="step",
#                         density=True,
#                         linewidth=1.6,
#                         color="#d62728",
#                         label="xproj_scaled" if _row_idx == 0 else None,
#                     )
#                     _ax.set_xlim(float(_bins[0]), float(_bins[-1]))
#                     _ax.grid(True, alpha=0.25)
#                     _ax.tick_params(labelsize=8)
#                     if _row_idx == 0:
#                         _ax.set_title(_xlabel, fontsize=10)
#                     if _row_idx == len(_scaled_rows) - 1:
#                         _ax.set_xlabel(_xlabel, fontsize=9)
#                     if _col_idx == 0:
#                         _ax.set_ylabel("density", fontsize=9)
#                         _ax.text(
#                             0.02,
#                             0.95,
#                             f"TT {_row_payload['tt_label']}\nn={_row_payload['n_points']:,}\nlocal={_row_payload['scale_factor_local']:.3f}",
#                             transform=_ax.transAxes,
#                             va="top",
#                             ha="left",
#                             fontsize=8,
#                             bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.78, "edgecolor": "0.8"},
#                         )
#
#             _scaled_axes[0][0].legend(fontsize=8, loc="upper right")
#             _scaled_fig.suptitle(
#                 "Original vs xproj-scaled projection/angle distributions by tt_task4_fit\n"
#                 f"One row per plane combination; one global xproj scale is applied to all rows: {_global_scale_factor:.3f} "
#                 f"({projection_scaling_summary.get('global_method', 'weighted_mean_by_n_points')})\n"
#                 f"{task4_efficiency_vector_title_line}",
#                 fontsize=11,
#             )
#             _scaled_fig.tight_layout(rect=[0, 0, 1, 0.94])
#             if save_plots:
#                 _scaled_filename = f"{fig_idx}_timtrack_projection_scaled_angle_comparison.png"
#                 fig_idx += 1
#                 _scaled_path = os.path.join(base_directories["figure_directory"], _scaled_filename)
#                 plot_list.append(_scaled_path)
#                 save_plot_figure(
#                     _scaled_path,
#                     format="png",
#                     alias="timtrack_projection_scaled_angle_comparison",
#                 )
#             if show_plots:
#                 plt.show()
#             plt.close(_scaled_fig)

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (track_based_efficiency_tt_stability)
# ============================================================================
# if (create_essential_plots or create_plots) and task4_plot_enabled("track_based_efficiency_tt_stability"):
#     _tts_cols_need = tuple(_required_track_efficiency_hit_columns()) + ("tt_task4_fit", "tt_task0_raw", "tt_task3_list")
#     _tts_have = all(c in df_efficiency_source.columns for c in _tts_cols_need)
#     if _tts_have:
#         z_arr_tts = np.asarray(z_positions, dtype=float)
#
#         plane_pool_tt_tts = {
#             1: [234, 1234],
#             2: [134, 1234],
#             3: [124, 1234],
#             4: [123, 1234],
#         }
#
#         fig, axes = plt.subplots(3, 4, figsize=(18, 13), squeeze=False)
#
#         x_hits_tts, y_hits_tts = _extract_track_efficiency_hit_arrays(df_efficiency_source, tdiff_to_x)
#         dtt_all_tts = pd.to_numeric(df_efficiency_source["tt_task4_fit"], errors="coerce").fillna(0).to_numpy(dtype=np.int32)
#         tt_task0_raw_tts = pd.to_numeric(df_efficiency_source["tt_task0_raw"], errors="coerce").fillna(0).to_numpy(dtype=np.int32)
#         tt_task3_list_tts = pd.to_numeric(df_efficiency_source["tt_task3_list"], errors="coerce").fillna(0).to_numpy(dtype=np.int32)
#         unchanged_mask_tts = (tt_task0_raw_tts == tt_task3_list_tts)
#
#         n_x_bins_tts = 15
#         n_y_bins_tts = 20
#         n_theta_bins_tts = 20
#         x_bins_tts = np.linspace(-strip_half, strip_half, n_x_bins_tts + 1)
#         y_bins_tts = np.linspace(-width_half, width_half, n_y_bins_tts + 1)
#         theta_bins_tts = np.linspace(0.0, 90.0, n_theta_bins_tts + 1)
#         theta_centers_tts = 0.5 * (theta_bins_tts[:-1] + theta_bins_tts[1:])
#
#         for plane_idx, p in enumerate(range(1, 5)):
#             ax_y = axes[0][plane_idx]
#             ax_x = axes[1][plane_idx]
#             ax_th = axes[2][plane_idx]
#
#             pool_mask_tts = np.isin(dtt_all_tts, plane_pool_tt_tts[p])
#
#             if pool_mask_tts.sum() < 20:
#                 ax_y.set_visible(False)
#                 ax_x.set_visible(False)
#                 ax_th.set_visible(False)
#                 continue
#
#             projection_tts = _fit_three_plane_telescope_projection(
#                 x_hits_tts,
#                 y_hits_tts,
#                 z_arr_tts,
#                 p - 1,
#             )
#
#             def _tts_1d(mask):
#                 """Return (x_pred, y_pred, theta_pred_deg, fired) for the accepted subset of mask."""
#                 x_p = projection_tts["x_pred"][mask]
#                 y_p = projection_tts["y_pred"][mask]
#                 th_p = projection_tts["theta_pred_deg"][mask]
#                 fired_p = (dtt_all_tts[mask] == 1234).astype(float)
#                 in_acc = (
#                     np.isfinite(x_p) & np.isfinite(y_p) & np.isfinite(th_p)
#                     & (np.abs(x_p) <= strip_half)
#                     & (np.abs(y_p) <= width_half)
#                 )
#                 return x_p[in_acc], y_p[in_acc], th_p[in_acc], fired_p[in_acc]
#
#             accepted_pool_mask = pool_mask_tts & projection_tts["valid"]
#             x_pred_all, y_pred_all, theta_pred_all, fired_all = _tts_1d(accepted_pool_mask)
#             x_pred_unc, y_pred_unc, theta_pred_unc, fired_unc = _tts_1d(
#                 accepted_pool_mask & unchanged_mask_tts
#             )
#
#             n_all = len(fired_all)
#             n_unc = len(fired_unc)
#             eff_all_glob = float(fired_all.mean()) * 100 if n_all > 0 else float("nan")
#             eff_unc_glob = float(fired_unc.mean()) * 100 if n_unc > 0 else float("nan")
#
#             y_ctrs_tts = y_pos_P1_and_P3 if (p - 1) % 2 == 0 else y_pos_P2_and_P4
#
#             for ax, pred_all, fired_all_1d, pred_unc, fired_unc_1d, xlabel, bins, half in [
#                 (ax_y, y_pred_all, fired_all, y_pred_unc, fired_unc, "Projected Y (mm)", y_bins_tts, width_half),
#                 (ax_x, x_pred_all, fired_all, x_pred_unc, fired_unc, "Projected X (mm)", x_bins_tts, strip_half),
#             ]:
#                 centers = 0.5 * (bins[:-1] + bins[1:])
#
#                 for data_pred, data_fired, color, label_str in [
#                     (pred_all,  fired_all_1d,  f"C{p - 1}",  f"all  (n={n_all}, {eff_all_glob:.1f}%)"),
#                     (pred_unc,  fired_unc_1d,  f"C{p + 3}",  f"unchanged  (n={n_unc}, {eff_unc_glob:.1f}%)"),
#                 ]:
#                     num_b, _ = np.histogram(data_pred[data_fired > 0.5], bins=bins)
#                     den_b, _ = np.histogram(data_pred, bins=bins)
#                     with np.errstate(invalid="ignore", divide="ignore"):
#                         eff_b = np.where(den_b > 0, num_b / den_b, np.nan)
#                         err_b = np.where(
#                             den_b > 0,
#                             np.sqrt(np.maximum(eff_b * (1.0 - eff_b) / np.maximum(den_b, 1), 0)),
#                             np.nan,
#                         )
#                     valid_b = np.isfinite(eff_b) & (den_b > 0)
#                     if valid_b.any():
#                         ax.errorbar(
#                             centers[valid_b], eff_b[valid_b], yerr=err_b[valid_b],
#                             fmt="o-", ms=4, color=color, alpha=0.85, label=label_str,
#                         )
#
#                 if xlabel.startswith("Projected Y"):
#                     for sy in y_ctrs_tts:
#                         ax.axvline(sy, color="lightgray", lw=0.9, ls="--", alpha=0.8)
#                 ax.set_ylim(0, 1.08)
#                 ax.set_xlim(-half, half)
#                 ax.set_xlabel(xlabel, fontsize=8)
#                 ax.set_ylabel("Efficiency", fontsize=8)
#                 ax.set_title(f"Plane {p}", fontsize=9)
#                 ax.legend(fontsize=7)
#                 ax.grid(True, alpha=0.3)
#
#             # --- row 3: efficiency vs theta ---
#             for th_acc, frd_acc, color_th, label_th in [
#                 (theta_pred_all, fired_all, f"C{p - 1}", f"all  (n={n_all}, {eff_all_glob:.1f}%)"),
#                 (theta_pred_unc, fired_unc, f"C{p + 3}", f"unchanged  (n={n_unc}, {eff_unc_glob:.1f}%)"),
#             ]:
#                 if len(th_acc) < 5:
#                     continue
#                 num_th_b, _ = np.histogram(th_acc[frd_acc > 0.5], bins=theta_bins_tts)
#                 den_th_b, _ = np.histogram(th_acc, bins=theta_bins_tts)
#                 with np.errstate(invalid="ignore", divide="ignore"):
#                     eff_th_b = np.where(den_th_b > 0, num_th_b / den_th_b, np.nan)
#                     err_th_b = np.where(
#                         den_th_b > 0,
#                         np.sqrt(np.maximum(eff_th_b * (1.0 - eff_th_b) / np.maximum(den_th_b, 1), 0)),
#                         np.nan,
#                     )
#                 valid_th_b = np.isfinite(eff_th_b) & (den_th_b > 0)
#                 if valid_th_b.any():
#                     ax_th.errorbar(
#                         theta_centers_tts[valid_th_b],
#                         eff_th_b[valid_th_b],
#                         yerr=err_th_b[valid_th_b],
#                         fmt="o-", ms=4, color=color_th, alpha=0.85, label=label_th,
#                     )
#             ax_th.set_ylim(0, 1.08)
#             ax_th.set_xlabel("θ (deg)", fontsize=8)
#             ax_th.set_ylabel("Efficiency", fontsize=8)
#             ax_th.set_title(f"Plane {p}", fontsize=9)
#             ax_th.legend(fontsize=7)
#             ax_th.grid(True, alpha=0.3)
#
#         plt.suptitle(
#             "Track-based efficiency: all events vs. tt-unchanged (raw\u2009tt == list\u2009tt)\n"
#             "Unchanged = events where the plane combination did not change from raw to listed stage",
#             fontsize=11,
#         )
#         plt.tight_layout(rect=[0, 0, 1, 0.93])
#         if save_plots:
#             final_filename = f"{fig_idx}_track_based_efficiency_tt_stability.png"
#             fig_idx += 1
#             save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#             plot_list.append(save_fig_path)
#             save_plot_figure(save_fig_path, format="png", alias="track_based_efficiency_tt_stability")
#         if show_plots:
#             plt.show()
#         plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (track_based_efficiency_vs_theta)
# ============================================================================
# if (
#     (create_essential_plots or create_plots)
#     and task4_plot_enabled("track_based_efficiency_vs_theta")
#     and (
#         bool(efficiency_metadata_payload.get("available", False))
#         or bool(efficiency_metadata_payload_fullplane.get("available", False))
#     )
# ):
#     fig, axes = plt.subplots(1, 4, figsize=(16, 4), squeeze=False)
#
#     for plane_idx, plane in enumerate(range(1, 5)):
#         ax = axes[0][plane_idx]
#         plane_result = efficiency_metadata_payload["plane_results"].get(plane, {})
#         plane_result_full = efficiency_metadata_payload_fullplane["plane_results"].get(plane, {})
#         theta_payload = plane_result.get("theta", {})
#         theta_payload_full = plane_result_full.get("theta", {})
#         centers = np.asarray(theta_payload.get("centers", []), dtype=float)
#         eff_vals = np.asarray(theta_payload.get("eff", []), dtype=float)
#         unc_vals = np.asarray(theta_payload.get("unc", []), dtype=float)
#         den_vals = np.asarray(theta_payload.get("den", []), dtype=float)
#         valid = np.isfinite(eff_vals) & (den_vals > 0)
#         centers_full = np.asarray(theta_payload_full.get("centers", []), dtype=float)
#         eff_vals_full = np.asarray(theta_payload_full.get("eff", []), dtype=float)
#         unc_vals_full = np.asarray(theta_payload_full.get("unc", []), dtype=float)
#         den_vals_full = np.asarray(theta_payload_full.get("den", []), dtype=float)
#         valid_full = np.isfinite(eff_vals_full) & (den_vals_full > 0)
#         if not np.any(valid) and not np.any(valid_full):
#             ax.set_visible(False)
#             continue
#
#         overall_eff = plane_result.get("overall_eff", np.nan)
#         overall_eff_full = plane_result_full.get("overall_eff", np.nan)
#         representative_eff, representative_label, _, _, _ = _resolve_track_efficiency_representative(
#             plane_result
#         )
#         sim_eff_percent = (
#             float(track_efficiency_simulated_efficiencies_percent[plane - 1])
#             if plane - 1 < len(track_efficiency_simulated_efficiencies_percent)
#             else np.nan
#         )
#         plane_color = f"C{plane - 1}"
#         if np.any(valid_full):
#             ax.errorbar(
#                 centers_full[valid_full],
#                 eff_vals_full[valid_full],
#                 yerr=unc_vals_full[valid_full],
#                 fmt="o--",
#                 ms=3.5,
#                 color="0.45",
#                 alpha=0.80,
#                 label=(
#                     f"no fid  (n={int(plane_result_full.get('n_denom', 0) or 0)}, "
#                     f"{_format_task4_percent_label(overall_eff_full)})"
#                 ),
#             )
#         if np.any(valid):
#             ax.errorbar(
#                 centers[valid],
#                 eff_vals[valid],
#                 yerr=unc_vals[valid],
#                 fmt="o-",
#                 ms=4,
#                 color=plane_color,
#                 alpha=0.85,
#                 label=(
#                     f"fiducial  (n={int(plane_result.get('n_denom', 0) or 0)}, "
#                     f"{_format_task4_percent_label(overall_eff)})"
#                 ),
#             )
#         if np.isfinite(representative_eff):
#             _representative_line = ax.axhline(
#                 float(representative_eff),
#                 color=plane_color,
#                 lw=2.0,
#                 ls=_TRACK_EFF_REPRESENTATIVE_LINESTYLE,
#                 alpha=0.95,
#                 zorder=4,
#                 label=f"{representative_label}  {_format_task4_percent_label(representative_eff)}",
#             )
#             _representative_line.set_path_effects(
#                 [
#                     path_effects.Stroke(linewidth=4.2, foreground="white", alpha=0.95),
#                     path_effects.Normal(),
#                 ]
#             )
#         if np.isfinite(sim_eff_percent):
#             ax.axhline(
#                 float(sim_eff_percent) / 100.0,
#                 color="black",
#                 lw=1.0,
#                 ls=_TRACK_EFF_SIMULATION_LINESTYLE,
#                 alpha=0.75,
#                 zorder=3,
#                 label=f"simulation  {_format_task4_percent_label(sim_eff_percent)}",
#             )
#         ax.set_ylim(0, 1.08)
#         ax.set_xlabel("θ (deg)", fontsize=9)
#         ax.set_ylabel("Efficiency", fontsize=9)
#         ax.set_title(
#             (
#                 f"Plane {plane}\n"
#                 f"fid={_format_task4_percent_label(overall_eff)}  "
#                 f"full={_format_task4_percent_label(overall_eff_full)}"
#                 + (
#                     f"  sim={_format_task4_percent_label(sim_eff_percent)}"
#                     if np.isfinite(sim_eff_percent)
#                     else ""
#                 )
#             ),
#             fontsize=10,
#         )
#         handles, labels = ax.get_legend_handles_labels()
#         if handles:
#             ax.legend(fontsize=8)
#         ax.grid(True, alpha=0.3)
#
#     plt.suptitle(
#         "Track-based efficiency vs polar angle θ (telescope method)\n"
#         "Useful for sim/data comparison of angular efficiency dependence\n"
#         + ("Solid colour = active fiducial efficiency curve, dashed gray = no-fid/full-plane reference" if track_efficiency_fiducial_active else "No fiducial cut is active: solid and dashed-gray references should overlap")
#         + "; dashed plane-colour = fiducial representative efficiency"
#         + ("; dashed black = simulation overall reference" if track_efficiency_simulated_efficiencies_percent else "")
#         + ("\n" + track_efficiency_simulation_title_line if track_efficiency_simulated_efficiencies_percent else ""),
#         fontsize=11,
#     )
#     plt.tight_layout(rect=[0, 0, 1, 0.91])
#     if save_plots:
#         final_filename = f"{fig_idx}_track_based_efficiency_vs_theta.png"
#         fig_idx += 1
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format="png", alias="track_based_efficiency_vs_theta")
#     if show_plots:
#         plt.show()
#     plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (track_efficiency_large_plot)
# ============================================================================
# if (
#     (create_essential_plots or create_plots)
#     and task4_plot_enabled("track_efficiency_large_plot")
#     and (
#         bool(efficiency_metadata_payload.get("available", False))
#         or bool(efficiency_metadata_payload_fullplane.get("available", False))
#     )
# ):
#     edges_eff = (
#         efficiency_metadata_payload["edges"]
#         if bool(efficiency_metadata_payload.get("available", False))
#         else efficiency_metadata_payload_fullplane["edges"]
#     )
#     fig, axes = plt.subplots(6, 4, figsize=(20, 24), squeeze=False)
#
#     for plane_idx, plane in enumerate(range(1, 5)):
#         plane_result = efficiency_metadata_payload["plane_results"].get(plane, {})
#         plane_result_full = efficiency_metadata_payload_fullplane["plane_results"].get(plane, {})
#         ax_xy = axes[0][plane_idx]
#         ax_y = axes[1][plane_idx]
#         ax_x = axes[2][plane_idx]
#         ax_theta = axes[3][plane_idx]
#         ax_phi = axes[4][plane_idx]
#         ax_theta_phi = axes[5][plane_idx]
#
#         n_denom = int(plane_result.get("n_denom", 0) or 0)
#         n_denom_full = int(plane_result_full.get("n_denom", 0) or 0)
#         if max(n_denom, n_denom_full) < int(efficiency_metadata_cfg["min_accepted_events"]):
#             for axis in (ax_xy, ax_y, ax_x, ax_theta, ax_phi, ax_theta_phi):
#                 axis.set_visible(False)
#             continue
#
#         overall_eff = plane_result.get("overall_eff", np.nan)
#         overall_eff_full = plane_result_full.get("overall_eff", np.nan)
#         representative_eff, representative_label, _, _, _ = _resolve_track_efficiency_representative(
#             plane_result
#         )
#         sim_eff_percent = (
#             float(track_efficiency_simulated_efficiencies_percent[plane - 1])
#             if plane - 1 < len(track_efficiency_simulated_efficiencies_percent)
#             else np.nan
#         )
#         plane_color = f"C{plane - 1}"
#         y_reference = np.asarray(
#             plane_result_full.get("y_reference", plane_result.get("y_reference", [])),
#             dtype=float,
#         )
#
#         eff_xy = np.asarray(
#             plane_result_full.get("eff_2d", plane_result.get("eff_2d", np.empty((0, 0)))),
#             dtype=float,
#         )
#         im_xy = ax_xy.imshow(
#             eff_xy.T,
#             origin="lower",
#             aspect="auto",
#             extent=[
#                 float(edges_eff["x"][0]),
#                 float(edges_eff["x"][-1]),
#                 float(edges_eff["y"][0]),
#                 float(edges_eff["y"][-1]),
#             ],
#             vmin=0.0,
#             vmax=1.0,
#             cmap="RdYlGn",
#         )
#         fig.colorbar(im_xy, ax=ax_xy, label="efficiency", fraction=0.045, pad=0.02)
#         for sy in y_reference:
#             ax_xy.axhline(float(sy), color="cyan", lw=0.7, ls="--", alpha=0.7)
#         if track_efficiency_fiducial_active:
#             plane_x_cfg = track_efficiency_fiducial_cfg.get("x_by_plane", {}).get(plane, {})
#             x_left, x_right = _task4_resolve_region_bounds(
#                 plane_x_cfg.get("left", None),
#                 plane_x_cfg.get("right", None),
#                 -float(width_half),
#                 float(width_half),
#             )
#             plane_y_cfg = track_efficiency_fiducial_cfg.get("y_by_plane", {}).get(plane, {})
#             y_left, y_right = _task4_resolve_region_bounds(
#                 plane_y_cfg.get("left", None),
#                 plane_y_cfg.get("right", None),
#                 -float(width_half),
#                 float(width_half),
#             )
#             ax_xy.vlines((x_left, x_right), y_left, y_right, colors="black", linestyles="--", linewidth=1.1, alpha=0.85)
#             ax_xy.hlines((y_left, y_right), x_left, x_right, colors="black", linestyles="--", linewidth=1.1, alpha=0.85)
#         ax_xy.set_xlabel("Projected X (mm)", fontsize=8)
#         ax_xy.set_ylabel("Projected Y (mm)", fontsize=8)
#         ax_xy.set_title(
#             (
#                 f"Plane {plane}\n"
#                 f"fid={_format_task4_percent_label(overall_eff)}  "
#                 f"full={_format_task4_percent_label(overall_eff_full)}"
#                 + (
#                     f"  sim={_format_task4_percent_label(sim_eff_percent)}"
#                     if np.isfinite(sim_eff_percent)
#                     else ""
#                 )
#                 + f"\n(n_fid={n_denom}, n_full={n_denom_full})"
#             ),
#             fontsize=9,
#         )
#
#         _plot_track_efficiency_curve_panel(
#             ax_y,
#             axis_payload=plane_result.get("y", {}),
#             axis_payload_full=plane_result_full.get("y", {}),
#             n_denom=n_denom,
#             n_denom_full=n_denom_full,
#             overall_eff=overall_eff,
#             overall_eff_full=overall_eff_full,
#             representative_eff=representative_eff,
#             representative_label=representative_label,
#             sim_eff_percent=sim_eff_percent,
#             plane_color=plane_color,
#             xlabel="Projected Y (mm)",
#             xlim=(-float(width_half), float(width_half)),
#             x_reference_values=y_reference,
#         )
#         _plot_track_efficiency_curve_panel(
#             ax_x,
#             axis_payload=plane_result.get("x", {}),
#             axis_payload_full=plane_result_full.get("x", {}),
#             n_denom=n_denom,
#             n_denom_full=n_denom_full,
#             overall_eff=overall_eff,
#             overall_eff_full=overall_eff_full,
#             representative_eff=representative_eff,
#             representative_label=representative_label,
#             sim_eff_percent=sim_eff_percent,
#             plane_color=plane_color,
#             xlabel="Projected X (mm)",
#             xlim=(-float(strip_half), float(strip_half)),
#         )
#         _plot_track_efficiency_curve_panel(
#             ax_theta,
#             axis_payload=plane_result.get("theta", {}),
#             axis_payload_full=plane_result_full.get("theta", {}),
#             n_denom=n_denom,
#             n_denom_full=n_denom_full,
#             overall_eff=overall_eff,
#             overall_eff_full=overall_eff_full,
#             representative_eff=representative_eff,
#             representative_label=representative_label,
#             sim_eff_percent=sim_eff_percent,
#             plane_color=plane_color,
#             xlabel="θ (deg)",
#             xlim=(float(edges_eff["theta"][0]), float(edges_eff["theta"][-1])),
#         )
#         _plot_track_efficiency_curve_panel(
#             ax_phi,
#             axis_payload=plane_result.get("phi", {}),
#             axis_payload_full=plane_result_full.get("phi", {}),
#             n_denom=n_denom,
#             n_denom_full=n_denom_full,
#             overall_eff=overall_eff,
#             overall_eff_full=overall_eff_full,
#             representative_eff=representative_eff,
#             representative_label=representative_label,
#             sim_eff_percent=sim_eff_percent,
#             plane_color=plane_color,
#             xlabel="φ (deg)",
#             xlim=(float(edges_eff["phi"][0]), float(edges_eff["phi"][-1])),
#         )
#
#         eff_theta_phi = np.asarray(
#             plane_result_full.get(
#                 "eff_theta_phi",
#                 plane_result.get("eff_theta_phi", np.empty((0, 0))),
#             ),
#             dtype=float,
#         )
#         im_theta_phi = ax_theta_phi.imshow(
#             eff_theta_phi.T,
#             origin="lower",
#             aspect="auto",
#             extent=[
#                 float(edges_eff["theta"][0]),
#                 float(edges_eff["theta"][-1]),
#                 float(edges_eff["phi"][0]),
#                 float(edges_eff["phi"][-1]),
#             ],
#             vmin=0.0,
#             vmax=1.0,
#             cmap="RdYlGn",
#         )
#         fig.colorbar(im_theta_phi, ax=ax_theta_phi, label="efficiency", fraction=0.045, pad=0.02)
#         if track_efficiency_fiducial_active:
#             theta_left_deg = track_efficiency_fiducial_cfg.get("theta_left_deg", None)
#             theta_right_deg = track_efficiency_fiducial_cfg.get("theta_right_deg", None)
#             if theta_left_deg is not None:
#                 ax_theta_phi.axvline(float(theta_left_deg), color="black", lw=1.1, ls="--", alpha=0.85)
#             if theta_right_deg is not None:
#                 ax_theta_phi.axvline(float(theta_right_deg), color="black", lw=1.1, ls="--", alpha=0.85)
#         ax_theta_phi.set_xlabel("θ (deg)", fontsize=8)
#         ax_theta_phi.set_ylabel("φ (deg)", fontsize=8)
#
#     plt.suptitle(
#         "Large track-based efficiency diagnostic (telescope method)\n"
#         "Rows: XY map, eff(Y), eff(X), eff(θ), eff(φ), θ–φ map\n"
#         + ("Solid colour = active fiducial efficiency curve, dashed gray = no-fid/full-plane reference" if track_efficiency_fiducial_active else "No fiducial cut is active: solid and dashed-gray references should overlap")
#         + "; dashed plane-colour = fiducial representative efficiency"
#         + ("; dashed black = simulation overall reference" if track_efficiency_simulated_efficiencies_percent else "")
#         + ("\n" + track_efficiency_simulation_title_line if track_efficiency_simulated_efficiencies_percent else ""),
#         fontsize=11,
#     )
#     plt.tight_layout(rect=[0, 0, 1, 0.97])
#     if save_plots:
#         final_filename = f"{fig_idx}_track_efficiency_large_plot.png"
#         fig_idx += 1
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format="png", alias="track_efficiency_large_plot")
#     if show_plots:
#         plt.show()
#     plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (timtrack_results_hexbin_combination_projections, timtrack_results_scatter_combination_projections)
# ============================================================================
# if (
#     (create_essential_plots or create_plots)
#     and (
#         task4_plot_enabled("timtrack_results_hexbin_combination_projections")
#         or task4_plot_enabled("timtrack_results_scatter_combination_projections")
#     )
# ):
#
#     def plot_hexbin_matrix(
#         df,
#         columns_of_interest,
#         filter_conditions,
#         title,
#         save_plots,
#         show_plots,
#         base_directories,
#         fig_idx,
#         plot_list,
#         num_bins=40,
#         plot_mode="hexbin",
#         filename_stem="timtrack_results_hexbin_combination_projections",
#         alias="timtrack_results_hexbin_combination_projections",
#     ):
#
#         axis_limits = {
#             # Static
#             'x': [-strip_half, strip_half],
#             'y': [-width_half, width_half],
#             'det_x': [-strip_half, strip_half],
#             'det_y': [-width_half, width_half],
#             'tim_x': [-strip_half, strip_half],
#             'tim_y': [-width_half, width_half],
#             'theta': [theta_left_filter, theta_right_filter],
#             'phi': [phi_left_filter, phi_right_filter],
#             'det_theta': [det_theta_left_filter, det_theta_right_filter],
#             'det_phi': [det_phi_left_filter, det_phi_right_filter],
#             'tim_theta': [theta_left_filter, theta_right_filter],
#             'tim_phi': [phi_left_filter, phi_right_filter],
#             'xp': [-1 * proj_filter, proj_filter],
#             'yp': [-1 * proj_filter, proj_filter],
#             'tim_xp': [-1 * proj_filter, proj_filter],
#             'tim_yp': [-1 * proj_filter, proj_filter],
#             's': [slowness_filter_left, slowness_filter_right],
#             'det_s': [det_slowness_filter_left, det_slowness_filter_right],
#             'tim_s': [slowness_filter_left, slowness_filter_right],
#             'event_s_err': [event_s_err_left, event_s_err_right],
#             # 'th_chi': [0, 0.03],
#             # 'det_th_chi': [0, 12],
#
#             # Dinamic
#             'event_charge': [charge_plot_limit_left, charge_plot_event_limit_right],
#             'p1_qsum': [charge_plot_limit_left, charge_plot_limit_right],
#             'p2_qsum': [charge_plot_limit_left, charge_plot_limit_right],
#             'p3_qsum': [charge_plot_limit_left, charge_plot_limit_right],
#             'p4_qsum': [charge_plot_limit_left, charge_plot_limit_right],
#             'res_ystr_1': [-res_ystr_filter, res_ystr_filter], 'res_ystr_2': [-res_ystr_filter, res_ystr_filter], 'res_ystr_3': [-res_ystr_filter, res_ystr_filter], 'res_ystr_4': [-res_ystr_filter, res_ystr_filter],
#             'res_tsum_1': [-res_tsum_filter, res_tsum_filter], 'res_tsum_2': [-res_tsum_filter, res_tsum_filter], 'res_tsum_3': [-res_tsum_filter, res_tsum_filter], 'res_tsum_4': [-res_tsum_filter, res_tsum_filter],
#             'res_tdif_1': [-res_tdif_filter, res_tdif_filter], 'res_tdif_2': [-res_tdif_filter, res_tdif_filter], 'res_tdif_3': [-res_tdif_filter, res_tdif_filter], 'res_tdif_4': [-res_tdif_filter, res_tdif_filter],
#             'det_res_ystr_1': [-det_res_ystr_filter, det_res_ystr_filter], 'det_res_ystr_2': [-det_res_ystr_filter, det_res_ystr_filter], 'det_res_ystr_3': [-det_res_ystr_filter, det_res_ystr_filter], 'det_res_ystr_4': [-det_res_ystr_filter, det_res_ystr_filter],
#             'det_res_tsum_1': [-det_res_tsum_filter, det_res_tsum_filter], 'det_res_tsum_2': [-det_res_tsum_filter, det_res_tsum_filter], 'det_res_tsum_3': [-det_res_tsum_filter, det_res_tsum_filter], 'det_res_tsum_4': [-det_res_tsum_filter, det_res_tsum_filter],
#             'det_res_tdif_1': [-det_res_tdif_filter, det_res_tdif_filter], 'det_res_tdif_2': [-det_res_tdif_filter, det_res_tdif_filter], 'det_res_tdif_3': [-det_res_tdif_filter, det_res_tdif_filter], 'det_res_tdif_4': [-det_res_tdif_filter, det_res_tdif_filter],
#             'ext_res_ystr_1': [-ext_res_ystr_filter, ext_res_ystr_filter], 'ext_res_ystr_2': [-ext_res_ystr_filter, ext_res_ystr_filter], 'ext_res_ystr_3': [-ext_res_ystr_filter, ext_res_ystr_filter], 'ext_res_ystr_4': [-ext_res_ystr_filter, ext_res_ystr_filter],
#             'ext_res_tsum_1': [-ext_res_tsum_filter, ext_res_tsum_filter], 'ext_res_tsum_2': [-ext_res_tsum_filter, ext_res_tsum_filter], 'ext_res_tsum_3': [-ext_res_tsum_filter, ext_res_tsum_filter], 'ext_res_tsum_4': [-ext_res_tsum_filter, ext_res_tsum_filter],
#             'ext_res_tdif_1': [-ext_res_tdif_filter, ext_res_tdif_filter], 'ext_res_tdif_2': [-ext_res_tdif_filter, ext_res_tdif_filter], 'ext_res_tdif_3': [-ext_res_tdif_filter, ext_res_tdif_filter], 'ext_res_tdif_4': [-ext_res_tdif_filter, ext_res_tdif_filter],
#             'det_ext_res_ystr_1': [-det_ext_res_ystr_filter, det_ext_res_ystr_filter], 'det_ext_res_ystr_2': [-det_ext_res_ystr_filter, det_ext_res_ystr_filter], 'det_ext_res_ystr_3': [-det_ext_res_ystr_filter, det_ext_res_ystr_filter], 'det_ext_res_ystr_4': [-det_ext_res_ystr_filter, det_ext_res_ystr_filter],
#             'det_ext_res_tsum_1': [-det_ext_res_tsum_filter, det_ext_res_tsum_filter], 'det_ext_res_tsum_2': [-det_ext_res_tsum_filter, det_ext_res_tsum_filter], 'det_ext_res_tsum_3': [-det_ext_res_tsum_filter, det_ext_res_tsum_filter], 'det_ext_res_tsum_4': [-det_ext_res_tsum_filter, det_ext_res_tsum_filter],
#             'det_ext_res_tdif_1': [-det_ext_res_tdif_filter, det_ext_res_tdif_filter], 'det_ext_res_tdif_2': [-det_ext_res_tdif_filter, det_ext_res_tdif_filter], 'det_ext_res_tdif_3': [-det_ext_res_tdif_filter, det_ext_res_tdif_filter], 'det_ext_res_tdif_4': [-det_ext_res_tdif_filter, det_ext_res_tdif_filter],
#         }
#
#         columns_of_interest = [col for col in columns_of_interest if col in df.columns]
#         if not columns_of_interest:
#             return fig_idx
#
#         x_like_cols = {"x", "det_x", "tim_x"}
#         y_like_cols = {"y", "det_y", "tim_y"}
#
#         def _finite_axis_limit(values: pd.Series) -> list[float] | None:
#             numeric_values = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
#             numeric_values = numeric_values[numeric_values != 0]
#             if numeric_values.empty:
#                 return None
#             left = float(numeric_values.min())
#             right = float(numeric_values.max())
#             if not np.isfinite(left) or not np.isfinite(right):
#                 return None
#             if left == right:
#                 pad = max(abs(left) * 0.05, 1.0)
#                 left -= pad
#                 right += pad
#             return [left, right]
#
#         def _safe_set_xlim(axis, limits) -> None:
#             if limits is None:
#                 return
#             left, right = float(limits[0]), float(limits[1])
#             if np.isfinite(left) and np.isfinite(right) and left < right:
#                 axis.set_xlim(left, right)
#
#         def _safe_set_ylim(axis, limits) -> None:
#             if limits is None:
#                 return
#             left, right = float(limits[0]), float(limits[1])
#             if np.isfinite(left) and np.isfinite(right) and left < right:
#                 axis.set_ylim(left, right)
#
#         # Apply filters
#         for col, min_val, max_val in filter_conditions:
#             if col not in df.columns:
#                 continue
#             df = df[(df[col] >= min_val) & (df[col] <= max_val)]
#
#         num_var = len(columns_of_interest)
#         fig, axes = plt.subplots(num_var, num_var, figsize=(15, 15))
#
#         auto_limits = {}
#         for col in columns_of_interest:
#             if col in axis_limits:
#                 configured_limits = axis_limits[col]
#                 if (
#                     len(configured_limits) == 2
#                     and np.isfinite(float(configured_limits[0]))
#                     and np.isfinite(float(configured_limits[1]))
#                     and float(configured_limits[0]) < float(configured_limits[1])
#                 ):
#                     auto_limits[col] = [float(configured_limits[0]), float(configured_limits[1])]
#                 else:
#                     auto_limits[col] = _finite_axis_limit(df[col])
#             else:
#                 auto_limits[col] = _finite_axis_limit(df[col])
#
#         for i in range(num_var):
#             for j in range(num_var):
#                 ax = axes[i, j]
#                 x_col = columns_of_interest[j]
#                 y_col = columns_of_interest[i]
#
#                 if i < j:
#                     ax.axis('off')  # Leave the lower triangle blank
#                 elif i == j:
#                     # Diagonal: 1D histogram
#                     hist_data = pd.to_numeric(df[x_col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
#                     # Remove zeroes
#                     hist_data = hist_data[hist_data != 0]
#                     if hist_data.empty:
#                         ax.text(0.5, 0.5, "no finite data", ha="center", va="center", transform=ax.transAxes)
#                         ax.set_xticks([])
#                         ax.set_yticks([])
#                         _safe_set_xlim(ax, auto_limits[x_col])
#                         continue
#                     hist, bins = np.histogram(hist_data, bins=num_bins)
#                     bin_centers = 0.5 * (bins[1:] + bins[:-1])
#                     norm = plt.Normalize(hist.min(), hist.max())
#                     cmap = plt.get_cmap('turbo')
#
#                     for k in range(len(hist)):
#                         ax.bar(bin_centers[k], hist[k], width=bins[1] - bins[0], color=cmap(norm(hist[k])))
#
#                     ax.set_xticks([])
#                     ax.set_yticks([])
#                     _safe_set_xlim(ax, auto_limits[x_col])
#
#                     # Use log-scale for count-heavy positive histograms.
#                     if x_col.startswith('charge') or x_col == 'tim_th_chi_sigmafit_1234':
#                         ax.set_yscale('log')
#
#                 else:
#                     # Lower triangle: density/scatter view
#                     x_data = pd.to_numeric(df[x_col], errors="coerce")
#                     y_data = pd.to_numeric(df[y_col], errors="coerce")
#                     # Remove zeroes and nans
#                     cond = (
#                         (x_data != 0)
#                         & (y_data != 0)
#                         & np.isfinite(x_data)
#                         & np.isfinite(y_data)
#                     )
#                     x_data = x_data[cond]
#                     y_data = y_data[cond]
#                     if plot_mode == "scatter":
#                         ax.scatter(x_data, y_data, s=3, alpha=0.20, color="tab:blue", linewidths=0, rasterized=True)
#                         ax.set_facecolor("white")
#                     else:
#                         if len(x_data) > 0:
#                             ax.hexbin(x_data, y_data, gridsize=num_bins, cmap='turbo')
#                         else:
#                             ax.text(0.5, 0.5, "no finite data", ha="center", va="center", transform=ax.transAxes)
#                         ax.set_facecolor(plt.cm.turbo(0))
#
#                     if (
#                         (x_col in {"s", "det_s", "tim_s"} and y_col in {"s", "det_s", "tim_s"})
#                         and x_col != y_col
#                     ):
#                         # Draw a line in the diagonal y = x
#                         line_x = np.linspace(-0.01, 0.015, 100)
#                         line_y = line_x
#                         ax.plot(line_x, line_y, color='white', linewidth=1)  # Thin white line
#
#                     if x_col in x_like_cols and y_col in y_like_cols:
#                         rect_x = [-strip_half, strip_half, strip_half, -strip_half, -strip_half]
#                         rect_y = [-width_half, -width_half, width_half, width_half, -width_half]
#                         ax.plot(rect_x, rect_y, color='white', linewidth=1)
#                     elif x_col in y_like_cols and y_col in x_like_cols:
#                         rect_x = [-width_half, width_half, width_half, -width_half, -width_half]
#                         rect_y = [-strip_half, -strip_half, strip_half, strip_half, -strip_half]
#                         ax.plot(rect_x, rect_y, color='white', linewidth=1)
#
#                     # Apply determined limits
#                     _safe_set_xlim(ax, auto_limits[x_col])
#                     _safe_set_ylim(ax, auto_limits[y_col])
#
#                 if i != num_var - 1:
#                     ax.set_xticklabels([])
#                 if j != 0:
#                     ax.set_yticklabels([])
#                 if i == num_var - 1:
#                     ax.set_xlabel(x_col)
#                 if j == 0:
#                     ax.set_ylabel(y_col)
#
#         plt.subplots_adjust(wspace=0.05, hspace=0.05)
#         plt.suptitle(title)
#         if save_plots:
#             final_filename = f'{fig_idx}_{filename_stem}.png'
#             fig_idx += 1
#             save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#             plot_list.append(save_fig_path)
#             save_plot_figure(save_fig_path, format='png', alias=alias)
#         # Show plot if enabled
#         if show_plots:
#             plt.show()
#         plt.close()
#         return fig_idx
#
#     # df_cases_2 = [
#     #     ([("tt_task3_list", 12, 12)], "1-2 cases"),
#     #     ([("tt_task3_list", 23, 23)], "2-3 cases"),
#     #     ([("tt_task3_list", 34, 34)], "3-4 cases"),
#     #     ([("tt_task3_list", 13, 13)], "1-3 cases"),
#     #     ([("tt_task3_list", 14, 14)], "1-4 cases"),
#     #     ([("tt_task3_list", 123, 123)], "1-2-3 cases"),
#     #     ([("tt_task3_list", 234, 234)], "2-3-4 cases"),
#     #     ([("tt_task3_list", 124, 124)], "1-2-4 cases"),
#     #     ([("tt_task3_list", 134, 134)], "1-3-4 cases"),
#     #     ([("tt_task3_list", 1234, 1234)], "1-2-3-4 cases"),
#     # ]
#
#
#     # df_cases_2 = [
#     #     ([("tt_task4_fit", 12, 12)], "1-2 cases"),
#     #     ([("tt_task4_fit", 23, 23)], "2-3 cases"),
#     #     ([("tt_task4_fit", 34, 34)], "3-4 cases"),
#     #     ([("tt_task4_fit", 123, 123)], "1-2-3 cases"),
#     #     ([("tt_task4_fit", 234, 234)], "2-3-4 cases"),
#     #     ([("tt_task4_fit", 1234, 1234)], "1-2-3-4 cases"),
#     # ]
#
#     _task4_projection_tt_order = (12, 13, 14, 23, 24, 34, 123, 124, 134, 234, 1234)
#
#     def _task4_available_tt_projection_cases(
#         df: pd.DataFrame,
#         tt_column: str,
#     ) -> list[tuple[list[tuple[str, int, int]], str]]:
#         if tt_column not in df.columns:
#             return []
#         tt_numeric = pd.to_numeric(df[tt_column], errors="coerce")
#         tt_counts = tt_numeric.value_counts(dropna=True)
#         available = {
#             int(tt_value): int(count)
#             for tt_value, count in tt_counts.items()
#             if np.isfinite(float(tt_value)) and int(tt_value) > 0 and int(count) > 0
#         }
#         ordered_values = [tt_value for tt_value in _task4_projection_tt_order if tt_value in available]
#         ordered_values.extend(sorted(tt_value for tt_value in available if tt_value not in ordered_values))
#         return [
#             (
#                 [(tt_column, int(tt_value), int(tt_value))],
#                 f"{tt_column} = {int(tt_value)} (n={available[int(tt_value)]})",
#             )
#             for tt_value in ordered_values
#         ]
#
#     df_cases_1 = _task4_available_tt_projection_cases(df_plot_ancillary, task4_plot_tt_column)
#     if df_cases_1:
#         print(
#             "Task 4 timtrack_results_hexbin_combination_projections TT cases: "
#             + ", ".join(title for _, title in df_cases_1)
#         )
#     else:
#         print(
#             "Task 4 timtrack_results_hexbin_combination_projections skipped: "
#             f"no positive {task4_plot_tt_column} cases found."
#         )
#
#
#     df_cases_1234 = [
#         ([("tt_task4_fit", 1234, 1234)], "1-2-3-4 tt_task4_fit cases"),
#     ]
#
#     df_cases_1234_chi_study = [
#         ([("tt_task4_fit", 1234, 1234), ("tim_th_chi_sigmafit_1234", 0, 20)], "1-2-3-4 tt_task4_fit cases, chi2 < 20"),
#         ([("tt_task4_fit", 1234, 1234), ("tim_th_chi_sigmafit_1234", 20, 40)], "1-2-3-4 tt_task4_fit cases, 20 < chi2 < 40"),
#         ([("tt_task4_fit", 1234, 1234), ("tim_th_chi_sigmafit_1234", 40, 1000)], "1-2-3-4 tt_task4_fit cases, 40 < chi2"),
#     ]
#
#     def _task4_relevant_charge_columns_for_title(title: str, df_columns: pd.Index) -> list[str]:
#         match = re.search(r"=\s*(\d+)", title)
#         plane_label = match.group(1) if match else title.split()[0]
#         planes = [int(value) for value in re.findall(r"[1-4]", plane_label)]
#         if not planes:
#             planes = [1, 2, 3, 4]
#         relevant_columns: list[str] = []
#         for plane in planes:
#             for candidate in (
#                 f"tim_charge_{plane}",
#                 f"p{plane}_qsum",
#                 f"charge_{plane}",
#             ):
#                 if candidate in df_columns:
#                     relevant_columns.append(candidate)
#                     break
#         return relevant_columns
#
#     df_cases_2 = [
#         ([(task4_plot_tt_column, 1234, 1234)], "1-2-3-4 cases"),
#         ([(task4_plot_tt_column, 123, 123)], "1-2-3 cases"),
#         ([(task4_plot_tt_column, 234, 234)], "2-3-4 cases"),
#         ([(task4_plot_tt_column, 124, 124)], "1-2-4 cases"),
#         ([(task4_plot_tt_column, 134, 134)], "1-3-4 cases"),
#     ]
#
#     df_cases_3 = [
#         ([(task4_plot_tt_column, 12, 12), ("timtrack_iterations", 2, 2)], "1-2 cases, timtrack_iterations = 2"),
#         ([(task4_plot_tt_column, 12, 12), ("timtrack_iterations", 3, 3)], "1-2 cases, timtrack_iterations = 3"),
#         ([(task4_plot_tt_column, 12, 12), ("timtrack_iterations", 4, 4)], "1-2 cases, timtrack_iterations = 4"),
#         ([(task4_plot_tt_column, 12, 12), ("timtrack_iterations", 5, 5)], "1-2 cases, timtrack_iterations = 5"),
#         ([(task4_plot_tt_column, 12, 12), ("timtrack_iterations", 6, iter_max)], f"1-2 cases, timtrack_iterations = 6 to {iter_max}"),
#
#         ([(task4_plot_tt_column, 23, 23), ("timtrack_iterations", 2, 2)], "2-3 cases, timtrack_iterations = 2"),
#         ([(task4_plot_tt_column, 23, 23), ("timtrack_iterations", 3, 3)], "2-3 cases, timtrack_iterations = 3"),
#         ([(task4_plot_tt_column, 23, 23), ("timtrack_iterations", 4, 4)], "2-3 cases, timtrack_iterations = 4"),
#         ([(task4_plot_tt_column, 23, 23), ("timtrack_iterations", 5, 5)], "2-3 cases, timtrack_iterations = 5"),
#         ([(task4_plot_tt_column, 23, 23), ("timtrack_iterations", 6, iter_max)], f"2-3 cases, timtrack_iterations = 6 to {iter_max}"),
#
#         ([(task4_plot_tt_column, 34, 34), ("timtrack_iterations", 2, 2)], "3-4 cases, timtrack_iterations = 2"),
#         ([(task4_plot_tt_column, 34, 34), ("timtrack_iterations", 3, 3)], "3-4 cases, timtrack_iterations = 3"),
#         ([(task4_plot_tt_column, 34, 34), ("timtrack_iterations", 4, 4)], "3-4 cases, timtrack_iterations = 4"),
#         ([(task4_plot_tt_column, 34, 34), ("timtrack_iterations", 5, 5)], "3-4 cases, timtrack_iterations = 5"),
#         ([(task4_plot_tt_column, 34, 34), ("timtrack_iterations", 6, iter_max)], f"3-4 cases, timtrack_iterations = 6 to {iter_max}"),
#
#         ([(task4_plot_tt_column, 123, 123), ("timtrack_iterations", 2, 2)], "1-2-3 cases, timtrack_iterations = 2"),
#         ([(task4_plot_tt_column, 123, 123), ("timtrack_iterations", 3, 3)], "1-2-3 cases, timtrack_iterations = 3"),
#         ([(task4_plot_tt_column, 123, 123), ("timtrack_iterations", 4, 4)], "1-2-3 cases, timtrack_iterations = 4"),
#         ([(task4_plot_tt_column, 123, 123), ("timtrack_iterations", 5, 5)], "1-2-3 cases, timtrack_iterations = 5"),
#         ([(task4_plot_tt_column, 123, 123), ("timtrack_iterations", 6, iter_max)], f"1-2-3 cases, timtrack_iterations = 6 to {iter_max}"),
#
#         ([(task4_plot_tt_column, 234, 234), ("timtrack_iterations", 2, 2)], "2-3-4 cases, timtrack_iterations = 2"),
#         ([(task4_plot_tt_column, 234, 234), ("timtrack_iterations", 3, 3)], "2-3-4 cases, timtrack_iterations = 3"),
#         ([(task4_plot_tt_column, 234, 234), ("timtrack_iterations", 4, 4)], "2-3-4 cases, timtrack_iterations = 4"),
#         ([(task4_plot_tt_column, 234, 234), ("timtrack_iterations", 5, 5)], "2-3-4 cases, timtrack_iterations = 5"),
#         ([(task4_plot_tt_column, 234, 234), ("timtrack_iterations", 6, iter_max)], f"2-3-4 cases, timtrack_iterations = 6 to {iter_max}"),
#
#         ([(task4_plot_tt_column, 1234, 1234), ("timtrack_iterations", 2, 2)], "1-2-3-4 cases, timtrack_iterations = 2"),
#         ([(task4_plot_tt_column, 1234, 1234), ("timtrack_iterations", 3, 3)], "1-2-3-4 cases, timtrack_iterations = 3"),
#         ([(task4_plot_tt_column, 1234, 1234), ("timtrack_iterations", 4, 4)], "1-2-3-4 cases, timtrack_iterations = 4"),
#         ([(task4_plot_tt_column, 1234, 1234), ("timtrack_iterations", 5, 5)], "1-2-3-4 cases, timtrack_iterations = 5"),
#         ([(task4_plot_tt_column, 1234, 1234), ("timtrack_iterations", 6, iter_max)], f"1-2-3-4 cases, timtrack_iterations = 6 to {iter_max}"),
#     ]
#
#     # df_cases_1 = [
#     #     # From original_tt = 1234
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 123, 123)], "original=1234, processed=123"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 124, 124)], "original=1234, processed=124"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 134, 134)], "original=1234, processed=134"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 234, 234)], "original=1234, processed=234"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 12, 12)],   "original=1234, processed=12"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 13, 13)],   "original=1234, processed=13"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 14, 14)],   "original=1234, processed=14"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 23, 23)],   "original=1234, processed=23"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 24, 24)],   "original=1234, processed=24"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 34, 34)],   "original=1234, processed=34"),
#     #     ([("original_tt", 1234, 1234), ("definitive_tt", 1234, 1234)], "original=1234, processed=1234"),
#
#     #     # From original_tt = 124
#     #     ([("original_tt", 124, 124), ("definitive_tt", 12, 12)], "original=124, processed=12"),
#     #     ([("original_tt", 124, 124), ("definitive_tt", 14, 14)], "original=124, processed=14"),
#     #     ([("original_tt", 124, 124), ("definitive_tt", 24, 24)], "original=124, processed=24"),
#     #     ([("original_tt", 124, 124), ("definitive_tt", 124, 124)], "original=124, processed=124"),
#
#     #     # From original_tt = 134
#     #     ([("original_tt", 134, 134), ("definitive_tt", 13, 13)], "original=134, processed=13"),
#     #     ([("original_tt", 134, 134), ("definitive_tt", 14, 14)], "original=134, processed=14"),
#     #     ([("original_tt", 134, 134), ("definitive_tt", 34, 34)], "original=134, processed=34"),
#     #     ([("original_tt", 134, 134), ("definitive_tt", 134, 134)], "original=134, processed=134"),
#
#     #     # From original_tt = 123
#     #     ([("original_tt", 123, 123), ("definitive_tt", 12, 12)], "original=123, processed=12"),
#     #     ([("original_tt", 123, 123), ("definitive_tt", 13, 13)], "original=123, processed=13"),
#     #     ([("original_tt", 123, 123), ("definitive_tt", 23, 23)], "original=123, processed=23"),
#     #     ([("original_tt", 123, 123), ("definitive_tt", 123, 123)], "original=123, processed=123"),
#
#     #     # From original_tt = 234
#     #     ([("original_tt", 234, 234), ("definitive_tt", 23, 23)], "original=234, processed=23"),
#     #     ([("original_tt", 234, 234), ("definitive_tt", 24, 24)], "original=234, processed=24"),
#     #     ([("original_tt", 234, 234), ("definitive_tt", 34, 34)], "original=234, processed=34"),
#     #     ([("original_tt", 234, 234), ("definitive_tt", 234, 234)], "original=234, processed=234"),
#
#     #     # From original_tt = 12
#     #     ([("original_tt", 12, 12), ("definitive_tt", 12, 12)], "original=12, processed=12"),
#
#     #     # From original_tt = 23
#     #     ([("original_tt", 23, 23), ("definitive_tt", 23, 23)], "original=23, processed=23"),
#
#     #     # From original_tt = 34
#     #     ([("original_tt", 34, 34), ("definitive_tt", 34, 34)], "original=34, processed=34"),
#
#     #     # From original_tt = 13
#     #     ([("original_tt", 13, 13), ("definitive_tt", 13, 13)], "original=13, processed=13"),
#     # ]
#
#     # # Charge of each plane -------------------------------------------------------------------
#     # for filters, title in df_cases_2:
#     #     # Extract the relevant charge numbers from the title (e.g., "1-2 cases" -> [1, 2])
#     #     relevant_charges = [f"charge_{n}" for n in map(int, title.split()[0].split('-'))]
#
#     #     # Define the columns - interest dynamically
#     #     # columns_of_interest = ['x', 'y', 'theta', 'phi', 'xp', 'yp'] + relevant_charges
#     #     columns_of_interest = relevant_charges
#
#     #     # Keep the original filters (if needed) and apply them
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         columns_of_interest,  # Dynamically set the columns to include relevant charges
#     #         filters,  # Keep original filters
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#     # # Residues --------------------------------------------------------------------------------------
#     # for filters, title in df_cases_2:
#     #     relevant_residues_tsum = [f"res_tsum_{n}" for n in map(int, title.split()[0].split('-'))]
#     #     relevant_residues_tdif = [f"res_tdif_{n}" for n in map(int, title.split()[0].split('-'))]
#     #     relevant_residues_ystr = [f"res_ystr_{n}" for n in map(int, title.split()[0].split('-'))]
#
#     #     columns_of_interest = ['x', 'y', 'theta', 'phi', 'xp', 'yp', 's'] + relevant_residues_tsum + relevant_residues_tdif + relevant_residues_ystr
#
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         columns_of_interest,
#     #         filters,
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#
#     # for filters, title in df_cases_2:
#     #     relevant_residues_tsum = [f"res_tsum_{n}" for n in map(int, title.split()[0].split('-'))]
#     #     relevant_residues_det_tsum = [f"det_res_tsum_{n}" for n in map(int, title.split()[0].split('-'))]
#     #     relevant_residues_ext_tsum = [f"ext_res_tsum_{n}" for n in map(int, title.split()[0].split('-'))]
#
#     #     columns_of_interest = relevant_residues_tsum + relevant_residues_det_tsum + relevant_residues_ext_tsum
#
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         columns_of_interest,
#     #         filters,
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#     # for filters, title in df_cases_2:
#     #     relevant_residues_tdif = [f"res_tdif_{n}" for n in map(int, title.split()[0].split('-'))]
#     #     relevant_residues_det_tdif = [f"det_res_tdif_{n}" for n in map(int, title.split()[0].split('-'))]
#     #     relevant_residues_ext_tdif = [f"ext_res_tdif_{n}" for n in map(int, title.split()[0].split('-'))]
#
#     #     columns_of_interest = relevant_residues_tdif + relevant_residues_det_tdif + relevant_residues_ext_tdif
#
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         columns_of_interest,
#     #         filters,
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#     # for filters, title in df_cases_2:
#     #     relevant_residues_ystr = [f"res_ystr_{n}" for n in map(int, title.split()[0].split('-'))]
#     #     relevant_residues_det_ystr = [f"det_res_ystr_{n}" for n in map(int, title.split()[0].split('-'))]
#     #     relevant_residues_ext_ystr = [f"ext_res_ystr_{n}" for n in map(int, title.split()[0].split('-'))]
#
#     #     columns_of_interest = relevant_residues_ystr + relevant_residues_det_ystr + relevant_residues_ext_ystr
#
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         columns_of_interest,
#     #         filters,
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#
#     # Comparison with alternative fitting -------------------------------------------------------------------
#     # plot_col = ['x', 'y', 'theta', 'phi', 's', 'event_s_err', 'det_s', 'det_phi', 'det_theta', 'det_y', 'det_x']
#     # for filters, title in df_cases_1:
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         plot_col,
#     #         filters,
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#     # plot_col = ['x', 'y', 'theta', 'phi', 's']
#     # plot_col = ['x', 'xp', 'event_s_err', 'yp', 'y']
#     # for filters, title in df_cases_1:
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         plot_col,
#     #         filters,
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#     # Comparison with alternative fitting -------------------------------------------------------------------
#     # plot_col = ['x', 'y', 'theta', 'phi', 's', 'event_s_err', 'det_s', 'det_phi', 'det_theta', 'det_y', 'det_x']
#     # for filters, title in df_cases_3:
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         plot_col,
#     #         filters,
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#
#     # # Comparison with alternative fitting -------------------------------------------------------------------
#     # plot_col = ['t0', 's', 'event_s_err', 'det_s', 'det_s_ordinate']
#     # for filters, title in df_cases_3:
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         plot_col,
#     #         filters,
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#
#     # # Comparison with alternative fitting -------------------------------------------------------------------
#     # plot_col = ['theta', 'det_theta']
#     # for filters, title in df_cases_2:
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         plot_col,
#     #         filters,
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#     _fit1234_all = pd.to_numeric(df_plot_ancillary.get("tt_task4_fit"), errors="coerce")
#     _fit1234_mask = _fit1234_all.eq(1234.0)
#     global_variables["tt_task4_fit_1234_scatter_source_n"] = int(_fit1234_mask.sum())
#     for _prefix, _xcol, _ycol in (
#         ("tim", "tim_x", "tim_y"),
#         ("det", "det_x", "det_y"),
#         ("legacy", "x", "y"),
#     ):
#         if _xcol in df_plot_ancillary.columns and _ycol in df_plot_ancillary.columns:
#             _xvals = pd.to_numeric(df_plot_ancillary[_xcol], errors="coerce").to_numpy(dtype=float)
#             _yvals = pd.to_numeric(df_plot_ancillary[_ycol], errors="coerce").to_numpy(dtype=float)
#             _finite = np.isfinite(_xvals) & np.isfinite(_yvals)
#             _outside = _fit1234_mask.to_numpy(dtype=bool, copy=False) & _finite & (
#                 (np.abs(_xvals) > float(strip_half)) | (np.abs(_yvals) > float(width_half))
#             )
#             _outside_count = int(np.count_nonzero(_outside))
#             global_variables[f"tt_task4_fit_1234_{_prefix}_outside_plane1_n"] = _outside_count
#             print(
#                 "[FIT_TT_1234_PLANE1_ACCEPTANCE] "
#                 f"source={_prefix} total={int(_fit1234_mask.sum())} outside={_outside_count} "
#                 f"x_half={float(strip_half):.1f} y_half={float(width_half):.1f}",
#                 force=True,
#             )
#
#     # TimTrack projections per actual fitted plane combination. Use the generic
#     # chi column here; tim_th_chi_sigmafit_1234 is only defined for 1234 events.
#     for filters, title in df_cases_1:
#         relevant_charges = _task4_relevant_charge_columns_for_title(title, df_plot_ancillary.columns)
#         plot_col = ['tim_x', 'tim_y', 'tim_xp', 'tim_yp', 'tim_s', 'tim_th_chi'] + relevant_charges
#         fig_idx = plot_hexbin_matrix(
#             df_plot_ancillary,
#             plot_col,
#             filters,
#             title,
#             save_plots,
#             show_plots,
#             base_directories,
#             fig_idx,
#             plot_list
#         )
#
#     # Charge of each plane -------------------------------------------------------------------
#     # for filters, title in df_cases_1234:
#     #     # Extract the relevant charge numbers from the title (e.g., "1-2 cases" -> [1, 2])
#     #     relevant_charges = [f"charge_{n}" for n in map(int, title.split()[0].split('-'))]
#
#     #     # Define the columns - interest dynamically
#     #     columns_of_interest = ['tim_x', 'tim_y', 'tim_theta', 'tim_phi', 'tim_s', 'tim_th_chi_sigmafit_1234'] + relevant_charges
#
#     #     # Keep the original filters (if needed) and apply them
#     #     fig_idx = plot_hexbin_matrix(
#     #         df_plot_ancillary,
#     #         columns_of_interest,  # Dynamically set the columns to include relevant charges
#     #         filters,  # Keep original filters
#     #         title,
#     #         save_plots,
#     #         show_plots,
#     #         base_directories,
#     #         fig_idx,
#     #         plot_list
#     #     )
#
#     #     columns_of_interest = ['tim_th_chi_sigmafit_1234'] + relevant_charges
#     #     if (create_essential_plots or create_plots) and task4_plot_enabled("timtrack_results_scatter_combination_projections"):
#     #         fig_idx = plot_hexbin_matrix(
#     #             df_plot_ancillary,
#     #             columns_of_interest,
#     #             filters,
#     #             f"{title} [scatter]",
#     #             save_plots,
#     #             show_plots,
#     #             base_directories,
#     #             fig_idx,
#     #             plot_list,
#     #             plot_mode="scatter",
#     #             filename_stem="timtrack_results_scatter_combination_projections",
#     #             alias="timtrack_results_scatter_combination_projections",
#     #         )
#
#
#     #     # Define the columns - interest dynamically
#     #     columns_of_interest = ['tim_x', 'tim_y', 'tim_theta', 'tim_phi', 'tim_s', 'tim_th_chi_sigmafit_1234'] + relevant_charges
#
#     #     if (create_essential_plots or create_plots) and task4_plot_enabled("timtrack_results_scatter_combination_projections"):
#     #         fig_idx = plot_hexbin_matrix(
#     #             df_plot_ancillary,
#     #             columns_of_interest,
#     #             filters,
#     #             f"{title} [scatter]",
#     #             save_plots,
#     #             show_plots,
#     #             base_directories,
#     #             fig_idx,
#     #             plot_list,
#     #             plot_mode="scatter",
#     #             filename_stem="timtrack_results_scatter_combination_projections",
#     #             alias="timtrack_results_scatter_combination_projections",
#     #         )
#
#
#     for filters, title in df_cases_1234_chi_study:
#
#         # Define the columns - interest dynamically
#         relevant_charges = _task4_relevant_charge_columns_for_title(title, df_plot_ancillary_1234_chi.columns)
#         columns_of_interest = ['tim_x', 'tim_y', 'tim_theta', 'tim_phi', 'tim_s', 'tim_th_chi_sigmafit_1234'] + relevant_charges
#
#         if (create_essential_plots or create_plots) and task4_plot_enabled("timtrack_results_scatter_combination_projections"):
#             fig_idx = plot_hexbin_matrix(
#                 df_plot_ancillary_1234_chi,
#                 columns_of_interest,
#                 filters,
#                 f"{title} [scatter]",
#                 save_plots,
#                 show_plots,
#                 base_directories,
#                 fig_idx,
#                 plot_list,
#                 plot_mode="scatter",
#                 filename_stem="timtrack_results_scatter_combination_projections",
#                 alias="timtrack_results_scatter_combination_projections",
#             )

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (events_per_second_by_plane_cardinality_double_row)
# ============================================================================
# if create_plots and task4_plot_enabled("events_per_second_by_plane_cardinality_double_row"):
#
#     fig, axes = plt.subplots(2, 3, figsize=(24, 12), sharey=True)
#     colors = plt.colormaps['tab10']
#     tt_types = ['tt_task0_raw', task4_plot_tt_column]
#     row_titles = ['Raw TT', task4_plot_tt_column]
#
#     for row_idx, column_chosen in enumerate(tt_types):
#         plot_ancillary_df = working_df.copy()
#
#         # Ensure datetime is proper and indexed
#         plot_ancillary_df['datetime'] = pd.to_datetime(plot_ancillary_df['datetime'], errors='coerce')
#         plot_ancillary_df = plot_ancillary_df.set_index('datetime')
#
#         grouped_data = {
#             "Two planes": defaultdict(list),
#             "Three planes": defaultdict(list),
#             "Four planes": defaultdict(list)
#         }
#
#         lambda_store = {}
#
#         for tt_code in plot_ancillary_df[column_chosen].dropna().unique():
#             planes = str(tt_code)
#             count = len(planes)
#             label = f'Case {tt_code}'
#             if count == 2:
#                 grouped_data["Two planes"][label] = plot_ancillary_df[plot_ancillary_df[column_chosen] == tt_code]
#             elif count == 3:
#                 if tt_code in (124, 134):
#                     grouped_data["Four planes"][label] = plot_ancillary_df[plot_ancillary_df[column_chosen] == tt_code]
#                 else:
#                     grouped_data["Three planes"][label] = plot_ancillary_df[plot_ancillary_df[column_chosen] == tt_code]
#             elif count == 4:
#                 grouped_data["Four planes"][label] = plot_ancillary_df[plot_ancillary_df[column_chosen] == tt_code]
#
#         for col_idx, (title, group_dict) in enumerate(grouped_data.items()):
#             ax = axes[row_idx, col_idx]
#             for i, (label, df) in enumerate(group_dict.items()):
#                 df.index = pd.to_datetime(df.index, errors='coerce')
#                 event_times = df.index.floor('s')
#                 full_range = pd.date_range(start=event_times.min(), end=event_times.max(), freq='s')
#                 events_per_second = event_times.value_counts().reindex(full_range, fill_value=0).sort_index()
#
#                 hist_data = events_per_second.value_counts().sort_index()
#                 lambda_estimate = events_per_second.mean()
#                 lambda_store[label] = lambda_estimate
#                 x_values = np.arange(0, hist_data.index.max() + 1)
#                 poisson_pmf = poisson.pmf(x_values, lambda_estimate)
#                 poisson_pmf_scaled = poisson_pmf * len(events_per_second)
#
#                 ax.plot(hist_data.index, hist_data.values, label=label, alpha=0.9, color=colors(i % 10), linewidth=3)
#                 ax.plot(x_values, poisson_pmf_scaled, '--', lw=1.5, color=colors(i % 10), alpha=0.6)
#                 ax.set_xlim(0, 8)
#
#             ax.set_title(f'{title} ({row_titles[row_idx]})')
#             ax.set_xlabel('Number of Events per Second')
#             ax.set_ylabel('Frequency')
#             ax.legend(fontsize='small', loc='upper right')
#             ax.grid(True)
#
#         # Annotate efficiency estimates on the rightmost plot
#         ax_right = axes[row_idx, 2]
#         lam_1234 = lambda_store.get('Case 1234', np.nan)
#         lam_124 = lambda_store.get('Case 124', np.nan)
#         lam_134 = lambda_store.get('Case 134', np.nan)
#         def safe_ratio(num, den):
#             return np.nan if (den is None or den == 0 or np.isnan(den)) else 1 - (num / den) if num is not None else np.nan
#         eff_plane3 = safe_ratio(lam_124, lam_1234)
#         eff_plane2 = safe_ratio(lam_134, lam_1234)
#         text_lines = [
#             f"λ1234 = {lam_1234:.3g}" if not np.isnan(lam_1234) else "λ1234 = n/a",
#             f"λ124  = {lam_124:.3g}" if not np.isnan(lam_124) else "λ124  = n/a",
#             f"λ134  = {lam_134:.3g}" if not np.isnan(lam_134) else "λ134  = n/a",
#             f"1 - λ134/λ1234 (eff P2) = {eff_plane2:.3g}" if not np.isnan(eff_plane2) else "1 - λ134/λ1234 (eff P2) = n/a",
#             f"1 - λ124/λ1234 (eff P3) = {eff_plane3:.3g}" if not np.isnan(eff_plane3) else "1 - λ124/λ1234 (eff P3) = n/a",
#         ]
#         ax_right.text(0.02, 0.98, "\n".join(text_lines), transform=ax_right.transAxes,
#                       va='top', ha='left', fontsize='small',
#                       bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
#
#     plt.tight_layout()
#     plt.subplots_adjust(top=0.92)
#     plt.suptitle('Event Rate Histograms by TT Type and Plane Cardinality with Poisson Fits', fontsize=18)
#
#     # Save and show
#     if save_plots:
#         final_filename = f'{fig_idx}_events_per_second_by_plane_cardinality_double_row.png'
#         fig_idx += 1
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format='png')
#
#     if show_plots:
#         plt.show()
#     plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (total_event_charge_histogram)
# ============================================================================
#     if save_plots:
#         _task4_charge_plot_name = f"{fig_idx}_total_event_charge_histogram.png"
#         fig_idx += 1
#         _task4_charge_plot_path = os.path.join(
#             base_directories["figure_directory"],
#             _task4_charge_plot_name,
#         )
#         plot_list.append(_task4_charge_plot_path)
#         save_plot_figure(
#             _task4_charge_plot_path,
#             format="png",
#             alias="total_event_charge_histogram",
#         )

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: FINAL/report plot block moved to standalone final plotting (acquisition_rate_vs_time_by_task_tt_with_histograms)
# ============================================================================
# if save_plots and task4_plot_enabled("acquisition_rate_vs_time_by_task_tt_with_histograms"):
#     rate_fig = create_rate_vs_time_by_task_tt_with_histograms(
#         working_df,
#         tt_column="tt_task4_fit",
#         title=(
#             f"Task 4 acquisition rate by tt_task4_fit, {basename_no_ext} "
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
#         save_plot_figure(
#             save_fig_path,
#             fig=rate_fig,
#             alias="acquisition_rate_vs_time_by_task_tt_with_histograms",
#             dpi=140,
#         )
#         plt.close(rate_fig)
#     else:
#         print("Task 4 acquisition-rate-by-task-tt plot skipped: no valid tt_task4_fit/datetime rows.")

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
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
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: runtime PDF branch disabled by the PNG-only runtime plotting contract
# ============================================================================
# if create_pdf:
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
#         # Remove PNG files after creating the PDF
#         for png in existing_pngs:
#             try:
#                 os.remove(png)
#             except OSError as e:
#                 print(f"Error: {e.filename} - {e.strerror}.")

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: plot_histograms_and_gaussian
# ============================================================================
# def plot_histograms_and_gaussian(df, columns, title, figure_number, quantile=0.99, fit_gaussian=False):
#     global fig_idx
#     nrows, ncols = (2, 3) if figure_number == 1 else (3, 4)
#     fig, axs = plt.subplots(nrows, ncols, figsize=(20, 5 * nrows), constrained_layout=True)
#     axs = axs.flatten()
#     def gaussian(x, mu, sigma, amplitude):
#         return amplitude * np.exp(-((x - mu) ** 2) / (2 * sigma ** 2))
#
#     # Precompute quantiles for faster filtering
#     if fit_gaussian:
#         quantile_bounds = {}
#         for col in columns:
#             data = df[col].values
#             data = data[data != 0]
#             if len(data) > 0:
#                 quantile_bounds[col] = np.quantile(data, [(1 - quantile), quantile])
#
#     # Plot histograms and fit Gaussian if needed
#     for i, col in enumerate(columns):
#
#         data = df[col].values
#         data = data[data != 0]  # Filter out zero values
#
#         if len(data) == 0:  # Skip if no data
#             axs[i].text(0.5, 0.5, "No data", transform=axs[i].transAxes, ha='center', va='center', color='gray')
#             continue
#
#         # Example color map per column type
#         color_map = {
#             "theta": "blue",
#             "phi": "green",
#             "x": "darkorange",
#             "y": "darkorange",
#             "det_y": "darkorange",
#             "s": "purple",
#             "det_s": "purple",
#             "th_chi": "red",
#             "res_ystr": "teal",
#             "res_tsum": "brown",
#             "res_tdif": "purple",
#             "t0": "black"
#         }
#
#         # Set default in case no match is found
#         selected_col = 'gray'
#
#         if "theta" in col:
#             left, right = theta_left_filter, theta_right_filter
#             selected_col = color_map["theta"]
#
#         elif "phi" in col:
#             left, right = phi_left_filter, phi_right_filter
#             selected_col = color_map["phi"]
#
#         elif col in ["x", "det_x", "y", "det_y"]:
#             left, right = -pos_filter, pos_filter
#             selected_col = color_map["x"]
#
#         elif col in ["s", "det_s"]:
#             left, right = slowness_filter_left, slowness_filter_right
#             selected_col = color_map["s"]
#
#         elif "th_chi" in col:
#             left, right = 0, 10
#             selected_col = color_map["th_chi"]
#
#         elif "res_ystr" in col:
#             left, right = -res_ystr_filter, res_ystr_filter
#             selected_col = color_map["res_ystr"]
#
#         elif "res_tsum" in col:
#             left, right = -res_tsum_filter, res_tsum_filter
#             selected_col = color_map["res_tsum"]
#
#         elif "res_tdif" in col:
#             left, right = -res_tdif_filter, res_tdif_filter
#             selected_col = color_map["res_tdif"]
#
#         elif "t0" in col:
#             left, right = t0_left_filter, t0_right_filter
#             selected_col = color_map["t0"]
#
#         # Plot histogram
#         cond = (data > left) & (data < right)
#         hist_data, bin_edges, _ = axs[i].hist(data, bins=50, alpha=0.7, label='Data', color=selected_col)
#
#         axs[i].set_title(col)
#         axs[i].set_xlabel('Value')
#         axs[i].set_ylabel('Frequency')
#
#         axs[i].set_xlim([left, right])
#
#         # Fit Gaussian if enabled and data is sufficient
#         if fit_gaussian and len(data) >= 10:
#             try:
#                 # Use precomputed quantile bounds
#                 if col in quantile_bounds:
#                     lower_bound, upper_bound = quantile_bounds[col]
#                     filt_data = data[(data >= lower_bound) & (data <= upper_bound)]
#                 else:
#                     lower_bound, upper_bound = left, right
#                     filt_data = data[(data >= lower_bound) & (data <= upper_bound)]
#
#                 if len(filt_data) < 2:
#                     axs[i].text(0.5, 0.5, "Not enough data to fit", transform=axs[i].transAxes, ha='center', va='center', color='gray')
#                     continue
#
#                 # Fit Gaussian to the histogram data
#                 bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
#                 popt, _ = _curve_fit_checked(
#                     gaussian,
#                     bin_centers,
#                     hist_data,
#                     p0=[np.mean(filt_data), np.std(filt_data), max(hist_data)],
#                 )
#                 mu, sigma, amplitude = popt
#
#                 # Plot Gaussian fit
#                 x = np.linspace(lower_bound, upper_bound, 1000)
#                 axs[i].plot(x, gaussian(x, mu, sigma, amplitude), 'r-', label=f'Gaussian Fit\nμ={mu:.2g}, σ={sigma:.2g}')
#                 axs[i].legend()
#             except (RuntimeError, ValueError):
#                 axs[i].text(0.5, 0.5, "Fit failed", transform=axs[i].transAxes, ha='center', va='center', color='red')
#
#     # Remove unused subplots
#     for j in range(i + 1, len(axs)):
#         fig.delaxes(axs[j])
#
#     plt.suptitle(title, fontsize=16)
#     if save_plots:
#         safe_title = re.sub(r'[\\\\/]+', '_', title).replace(' ', '_')
#         final_filename = f'{fig_idx}_{safe_title}.png'
#         fig_idx += 1
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format='png')
#     if show_plots:
#         plt.show()
#     plt.close()

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: plot_tt_correlation
# ============================================================================
# def plot_tt_correlation(df, row_label, col_label, title, filename_suffix, fig_idx, base_dir, show_plots=False, save_plots=False, plot_list=None):
#
#     analysis_data = df[[row_label, col_label]]
#     counts = analysis_data.groupby([row_label, col_label]).size().unstack(fill_value=0)
#
#     row_order = sorted(analysis_data[row_label].unique(), reverse=True)
#     col_unique = analysis_data[col_label].unique()
#     col_order = list(row_order) + [x for x in col_unique if x not in row_order]
#     counts = counts.reindex(index=row_order, columns=col_order, fill_value=0)
#
#     fig, ax = plt.subplots(figsize=(10, 8))
#     ax.set_xticks(np.arange(len(counts.columns)))
#     ax.set_yticks(np.arange(len(counts.index)))
#     ax.set_xticklabels(counts.columns)
#     ax.set_yticklabels(counts.index)
#
#     ax.set_xlabel(col_label)
#     ax.set_ylabel(row_label)
#     ax.set_title(title)
#
#     im = ax.imshow(counts, cmap='plasma', origin='lower')
#     total = counts.values.sum()
#
#     for i in range(len(counts.index)):
#         for j in range(len(counts.columns)):
#             value = counts.iloc[i, j]
#             if value > 0:
#                 pct = 100 * value / total
#                 if pct > 1:
#                     ax.text(j, i, f"{pct:.1f}%",
#                             ha="center", va="center",
#                             color="black" if value > counts.values.max() * 0.5 else "white")
#
#     plt.tight_layout()
#     if save_plots:
#         final_filename = f'{fig_idx}_{filename_suffix}.png'
#         save_fig_path = os.path.join(base_dir, final_filename)
#         if plot_list is not None:
#             plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format='png')
#     if show_plots:
#         plt.show()
#     plt.close()
#
#     return fig_idx + 1

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: _plot_track_efficiency_curve_panel
# ============================================================================
# def _plot_track_efficiency_curve_panel(
#     axis,
#     *,
#     axis_payload,
#     axis_payload_full,
#     n_denom,
#     n_denom_full,
#     overall_eff,
#     overall_eff_full,
#     representative_eff,
#     representative_label,
#     sim_eff_percent,
#     plane_color,
#     xlabel,
#     xlim,
#     x_reference_values=(),
#     label_fontsize=8,
#     legend_fontsize=7,
# ):
#     centers = np.asarray(axis_payload.get("centers", []), dtype=float)
#     eff_vals = np.asarray(axis_payload.get("eff", []), dtype=float)
#     unc_vals = np.asarray(axis_payload.get("unc", []), dtype=float)
#     den_vals = np.asarray(axis_payload.get("den", []), dtype=float)
#     valid = np.isfinite(eff_vals) & (den_vals > 0)
#
#     centers_full = np.asarray(axis_payload_full.get("centers", []), dtype=float)
#     eff_vals_full = np.asarray(axis_payload_full.get("eff", []), dtype=float)
#     unc_vals_full = np.asarray(axis_payload_full.get("unc", []), dtype=float)
#     den_vals_full = np.asarray(axis_payload_full.get("den", []), dtype=float)
#     valid_full = np.isfinite(eff_vals_full) & (den_vals_full > 0)
#
#     if np.any(valid_full):
#         axis.errorbar(
#             centers_full[valid_full],
#             eff_vals_full[valid_full],
#             yerr=unc_vals_full[valid_full],
#             fmt="o--",
#             ms=3.5,
#             color="0.45",
#             alpha=0.80,
#             label=(
#                 f"no fid  (n={int(n_denom_full)}, "
#                 f"{_format_task4_percent_label(overall_eff_full)})"
#             ),
#         )
#     if np.any(valid):
#         axis.errorbar(
#             centers[valid],
#             eff_vals[valid],
#             yerr=unc_vals[valid],
#             fmt="o-",
#             ms=4,
#             color=plane_color,
#             alpha=0.85,
#             label=f"fiducial  (n={int(n_denom)}, {_format_task4_percent_label(overall_eff)})",
#         )
#     if np.isfinite(representative_eff):
#         _representative_line = axis.axhline(
#             float(representative_eff),
#             color=plane_color,
#             lw=2.0,
#             ls=_TRACK_EFF_REPRESENTATIVE_LINESTYLE,
#             alpha=0.95,
#             zorder=4,
#             label=f"{representative_label}  {_format_task4_percent_label(representative_eff)}",
#         )
#         _representative_line.set_path_effects(
#             [
#                 path_effects.Stroke(linewidth=4.2, foreground="white", alpha=0.95),
#                 path_effects.Normal(),
#             ]
#         )
#     for x_reference in x_reference_values:
#         if np.isfinite(x_reference):
#             axis.axvline(float(x_reference), color="lightgray", lw=0.9, ls="--", alpha=0.8)
#     if np.isfinite(sim_eff_percent):
#         axis.axhline(
#             float(sim_eff_percent) / 100.0,
#             color="black",
#             lw=1.0,
#             ls=_TRACK_EFF_SIMULATION_LINESTYLE,
#             alpha=0.75,
#             zorder=3,
#             label=f"simulation  {_format_task4_percent_label(sim_eff_percent)}",
#         )
#     axis.set_ylim(0, 1.08)
#     axis.set_xlim(*xlim)
#     axis.set_xlabel(xlabel, fontsize=label_fontsize)
#     axis.set_ylabel("Efficiency", fontsize=label_fontsize)
#     axis.grid(True, alpha=0.3)
#     handles, labels = axis.get_legend_handles_labels()
#     if handles:
#         axis.legend(fontsize=legend_fontsize)

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: _plot_offender_cumulative_hist_panel
# ============================================================================
# def _plot_offender_cumulative_hist_panel(
#     ax: plt.Axes,
#     observable_values: np.ndarray,
#     offender_counts: np.ndarray,
#     thresholds: Iterable[int],
#     bins: np.ndarray,
#     *,
#     x_label: str,
#     panel_title: str = "",
#     show_legend: bool = False,
# ) -> None:
#     observable = np.asarray(observable_values, dtype=float)
#     counts = np.asarray(offender_counts, dtype=float)
#     valid = np.isfinite(observable) & np.isfinite(counts)
#
#     threshold_values = sorted({max(0, int(value)) for value in thresholds})
#     if not threshold_values:
#         threshold_values = [0]
#     colors = plt.cm.viridis(np.linspace(0.10, 0.92, len(threshold_values)))
#
#     plotted = False
#     selected_at_max = 0
#     for idx, threshold in enumerate(threshold_values):
#         selected = valid & (counts <= float(threshold))
#         values = observable[selected]
#         if values.size == 0:
#             continue
#         ax.hist(
#             values,
#             bins=bins,
#             density=True,
#             histtype="step",
#             lw=1.45,
#             color=colors[idx],
#             label=f"<= {threshold} (n={values.size:,})",
#         )
#         ax.axvline(float(np.median(values)), color=colors[idx], lw=0.9, ls="--", alpha=0.65)
#         plotted = True
#         if threshold == threshold_values[-1]:
#             selected_at_max = int(values.size)
#
#     if not plotted:
#         ax.text(
#             0.5,
#             0.5,
#             "No data",
#             transform=ax.transAxes,
#             ha="center",
#             va="center",
#             fontsize=8,
#             color="0.45",
#         )
#
#     total_count = int(np.count_nonzero(valid))
#     summary_lines = [f"n={total_count:,}"]
#     if total_count > 0:
#         summary_lines.append(
#             f"<= {threshold_values[-1]}: {100.0 * float(selected_at_max) / float(total_count):.1f}%"
#         )
#     ax.text(
#         0.02,
#         0.98,
#         "\n".join(summary_lines),
#         transform=ax.transAxes,
#         va="top",
#         ha="left",
#         fontsize=7,
#         bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.75, "edgecolor": "0.8"},
#     )
#
#     if panel_title:
#         ax.set_title(panel_title, fontsize=9)
#     ax.set_xlim(float(bins[0]), float(bins[-1]))
#     ax.set_xlabel(x_label, fontsize=8)
#     ax.set_ylabel("density", fontsize=8)
#     ax.grid(True, alpha=0.25)
#     ax.tick_params(labelsize=7)
#     if show_legend:
#         ax.legend(fontsize=7, loc="upper right")

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: _plot_offender_hist_panel
# ============================================================================
# def _plot_offender_hist_panel(
#     ax: plt.Axes,
#     zero_values: np.ndarray,
#     nonzero_values: np.ndarray,
#     bins: np.ndarray,
#     *,
#     x_label: str,
#     panel_title: str = "",
#     show_legend: bool = False,
# ) -> None:
#     zero_values = np.asarray(zero_values, dtype=float)
#     nonzero_values = np.asarray(nonzero_values, dtype=float)
#     zero_values = zero_values[np.isfinite(zero_values)]
#     nonzero_values = nonzero_values[np.isfinite(nonzero_values)]
#
#     plotted = False
#     for values, color, label in (
#         (zero_values, _OFFENDER_ZERO_COLOR, "0 offenders"),
#         (nonzero_values, _OFFENDER_NONZERO_COLOR, ">0 offenders"),
#     ):
#         if values.size == 0:
#             continue
#         ax.hist(
#             values,
#             bins=bins,
#             density=True,
#             histtype="stepfilled",
#             alpha=0.16,
#             color=color,
#         )
#         ax.hist(
#             values,
#             bins=bins,
#             density=True,
#             histtype="step",
#             lw=1.6,
#             color=color,
#             label=f"{label} (n={values.size:,})",
#         )
#         ax.axvline(float(np.median(values)), color=color, lw=1.0, ls="--", alpha=0.75)
#         plotted = True
#
#     if not plotted:
#         ax.text(
#             0.5,
#             0.5,
#             "No data",
#             transform=ax.transAxes,
#             ha="center",
#             va="center",
#             fontsize=8,
#             color="0.45",
#         )
#
#     total_count = int(zero_values.size + nonzero_values.size)
#     nonzero_fraction = (
#         100.0 * float(nonzero_values.size) / float(total_count)
#         if total_count > 0
#         else float("nan")
#     )
#     summary_lines = [f"n={total_count:,}"]
#     if total_count > 0:
#         summary_lines.append(f">0={nonzero_fraction:.1f}%")
#     if zero_values.size > 0:
#         summary_lines.append(f"m0={float(np.median(zero_values)):.2f}")
#     if nonzero_values.size > 0:
#         summary_lines.append(f"m>0={float(np.median(nonzero_values)):.2f}")
#     ax.text(
#         0.02,
#         0.98,
#         "\n".join(summary_lines),
#         transform=ax.transAxes,
#         va="top",
#         ha="left",
#         fontsize=7,
#         bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.75, "edgecolor": "0.8"},
#     )
#
#     if panel_title:
#         ax.set_title(panel_title, fontsize=9)
#     ax.set_xlim(float(bins[0]), float(bins[-1]))
#     ax.set_xlabel(x_label, fontsize=8)
#     ax.set_ylabel("density", fontsize=8)
#     ax.grid(True, alpha=0.25)
#     ax.tick_params(labelsize=7)
#     if show_legend:
#         ax.legend(fontsize=7, loc="upper right")

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
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
# ARCHIVED FROM: script_4_list_to_fit.py
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
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_pages: PdfPages | None = None

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_page_count = 0

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_target_path: str | None = None

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_temp_path: str | None = None

# ============================================================================
# ARCHIVED FROM: script_4_list_to_fit.py
# REASON: dead runtime PDF atexit registration after PNG-only split
# ============================================================================
# atexit.register(close_direct_pdf_writer)

