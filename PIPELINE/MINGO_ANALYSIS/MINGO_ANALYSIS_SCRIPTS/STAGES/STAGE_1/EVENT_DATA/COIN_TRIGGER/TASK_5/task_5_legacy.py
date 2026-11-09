# LEGACY CODE ARCHIVE FOR TASK 5
#
# This file stores code deliberately removed from the active task script.
# It is not imported by the pipeline and is not expected to execute.
# Dependencies and surrounding runtime context may be missing.
# Removed blocks are preserved substantially verbatim for historical reference.

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in fast mode.')

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in debug mode.')

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_F_left_pre_cal = T_side_left_pre_cal_debug
#     T_F_right_pre_cal = T_side_right_pre_cal_debug
#
#     T_B_left_pre_cal = T_side_left_pre_cal_debug
#     T_B_right_pre_cal = T_side_right_pre_cal_debug

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_clip_min = T_clip_min_debug
#     T_clip_max = T_clip_max_debug
#     Q_clip_min = Q_clip_min_debug
#     Q_clip_max = Q_clip_max_debug
#     num_bins = num_bins_debug

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in fast mode.')

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in debug mode.')

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_F_left_pre_cal = T_side_left_pre_cal_debug
#     T_F_right_pre_cal = T_side_right_pre_cal_debug
#
#     T_B_left_pre_cal = T_side_left_pre_cal_debug
#     T_B_right_pre_cal = T_side_right_pre_cal_debug

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_clip_min = T_clip_min_debug
#     T_clip_max = T_clip_max_debug
#     Q_clip_min = Q_clip_min_debug
#     Q_clip_max = Q_clip_max_debug
#     num_bins = num_bins_debug

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in fast mode.')

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     print('Working in debug mode.')

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_F_left_pre_cal = T_side_left_pre_cal_debug
#     T_F_right_pre_cal = T_side_right_pre_cal_debug
#
#     T_B_left_pre_cal = T_side_left_pre_cal_debug
#     T_B_right_pre_cal = T_side_right_pre_cal_debug

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: literal `if False:` branch; condition is unconditionally false
# ============================================================================
# if False:
#     T_clip_min = T_clip_min_debug
#     T_clip_max = T_clip_max_debug
#     Q_clip_min = Q_clip_min_debug
#     Q_clip_max = Q_clip_max_debug
#     num_bins = num_bins_debug

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: FINAL/report plot block moved to standalone final plotting (charge_tt_task4_fit_1234_per_plane_and_total)
# ============================================================================
# if (
#     (create_essential_plots or create_plots)
#     and task5_plot_enabled("charge_tt_task4_fit_1234_per_plane_and_total")
# ):
#     plane_charge_df = pd.DataFrame(index=working_df.index)
#     plane_charge_columns: list[str] = []
#     plane_charge_titles: list[str] = []
#     fallback_notes: list[str] = []
#
#     charge_candidates = [
#         col
#         for col in working_df.columns
#         if TASK5_PLANE_Q_SUM_COLUMN_RE.fullmatch(str(col))
#         or TASK5_STRIP_Q_COLUMN_RE.fullmatch(str(col))
#     ]
#     if charge_candidates:
#         print(
#             "Task 5: detected charge-related columns in input dataframe: "
#             + ", ".join(charge_candidates)
#         )
#     else:
#         possible_charge_cols = [
#             col
#             for col in working_df.columns
#             if re.search(r"Q|q", col)
#             and ("sum" in col.lower() or "charge" in col.lower() or "q_" in col.lower())
#         ]
#         print(
#             "Task 5: no exact charge-summary columns found; possible charge-like columns: "
#             + ", ".join(possible_charge_cols)
#         )
#
#     for i_plane in range(1, 5):
#         sum_col = f"p{i_plane}_qsum"
#         if sum_col in working_df.columns:
#             plane_charge_df.loc[:, sum_col] = pd.to_numeric(
#                 working_df[sum_col], errors="coerce"
#             )
#             plane_charge_columns.append(sum_col)
#             plane_charge_titles.append(f"Plane {i_plane} Q_sum_final")
#             continue
#
#         strip_cols = [
#             f"p{i_plane}_s{i_strip}_qsum"
#             for i_strip in range(1, 5)
#             if f"p{i_plane}_s{i_strip}_qsum" in working_df.columns
#         ]
#         if not strip_cols:
#             continue
#
#         fallback_col = f"p{i_plane}_qsum_from_strips"
#         strip_values = working_df[strip_cols].apply(pd.to_numeric, errors="coerce")
#         # Keep all-NaN rows as NaN so missing charge data is not misrepresented as 0.
#         plane_charge_df.loc[:, fallback_col] = strip_values.sum(axis=1, min_count=1)
#         plane_charge_columns.append(fallback_col)
#         plane_charge_titles.append(f"Plane {i_plane} Q sum from strips")
#         fallback_notes.append(f"p{i_plane}={' + '.join(strip_cols)}")
#
#     if plane_charge_columns:
#         if fallback_notes:
#             print(
#                 "Warning: Task 5 charge summary is using fallback charge columns: "
#                 + ", ".join(fallback_notes)
#             )
#
#         plane_charge_df["detector_total_charge"] = plane_charge_df[plane_charge_columns].sum(
#             axis=1,
#             min_count=1,
#         )
#
#         tt_task4_fit_values = pd.to_numeric(working_df["tt_task4_fit"], errors="coerce")
#         df_charge_1234 = plane_charge_df.loc[
#             tt_task4_fit_values == 1234,
#             plane_charge_columns + ["detector_total_charge"],
#         ].copy()
#         print(
#             f"Task 5: preparing charge summary for tt_task4_fit=1234 with {len(df_charge_1234)} matching rows"
#         )
#
#         if not df_charge_1234.empty:
#             for column_name in plane_charge_columns + ["detector_total_charge"]:
#                 df_charge_1234.loc[:, column_name] = pd.to_numeric(
#                     df_charge_1234[column_name], errors="coerce"
#                 )
#             df_charge_1234 = df_charge_1234.replace([np.inf, -np.inf], np.nan)
#             df_charge_1234["event_total_charge"] = df_charge_1234[
#                 plane_charge_columns
#             ].sum(axis=1, min_count=1)
#         else:
#             df_charge_1234 = pd.DataFrame(
#                 columns=plane_charge_columns + ["detector_total_charge", "event_total_charge"]
#             )
#
#         fig, axes = plt.subplots(
#             5,
#             2,
#             figsize=(14, 18),
#             constrained_layout=True,
#             sharex="col",
#         )
#         plot_columns = plane_charge_columns + ["event_total_charge"]
#         plot_titles = plane_charge_titles + ["Total event charge"]
#
#         for row_idx, (column_name, panel_title) in enumerate(zip(plot_columns, plot_titles)):
#             zoom_axis = axes[row_idx, 0]
#             full_axis = axes[row_idx, 1]
#             for axis, zoomed, title_suffix in [
#                 (zoom_axis, True, " (0-40 zoom)"),
#                 (full_axis, False, ""),
#             ]:
#                 if df_charge_1234.empty:
#                     axis.text(
#                         0.5,
#                         0.5,
#                         "No tt_task4_fit=1234 data available",
#                         ha="center",
#                         va="center",
#                     )
#                     axis.set_title(panel_title + title_suffix)
#                     axis.grid(alpha=0.25, which="both")
#                     axis.set_yscale("log")
#                     if zoomed:
#                         axis.set_xlim(0, 40)
#                     continue
#
#                 values = pd.to_numeric(df_charge_1234[column_name], errors="coerce")
#                 values = values[np.isfinite(values)]
#                 if values.empty:
#                     axis.text(0.5, 0.5, "No finite values", ha="center", va="center")
#                     axis.set_title(panel_title + title_suffix)
#                     axis.grid(alpha=0.25, which="both")
#                     axis.set_yscale("log")
#                     if zoomed:
#                         axis.set_xlim(0, 40)
#                     continue
#
#                 if zoomed:
#                     zoom_values = values[(values >= 0) & (values <= 40)]
#                     axis.hist(
#                         zoom_values,
#                         bins=np.linspace(0, 40, 121),
#                         color="tab:orange",
#                         alpha=0.75,
#                     )
#                 else:
#                     axis.hist(values, bins=120, color="tab:orange", alpha=0.75)
#                 axis.axvline(float(np.median(values)), color="black", ls="--", lw=1.0, alpha=0.8)
#                 axis.set_title(panel_title + title_suffix)
#                 axis.set_ylabel("Events")
#                 axis.set_yscale("log")
#                 axis.grid(alpha=0.25, which="both")
#                 if zoomed:
#                     axis.set_xlim(0, 40)
#                 if row_idx == len(plot_columns) - 1:
#                     axis.set_xlabel("Charge")
#
#         for row_idx in range(len(plot_columns), axes.shape[0]):
#             axes[row_idx, 0].axis("off")
#             axes[row_idx, 1].axis("off")
#
#         fig.suptitle(
#             "Task 5 charge summary for tt_task4_fit = 1234\n"
#             "Per-plane charge and total event charge\n"
#             f"Events: {len(df_charge_1234)} | Columns: {', '.join(plot_columns)}",
#             fontsize=12,
#         )
#
#         if save_plots:
#             final_filename = f"{fig_idx}_charge_tt_task4_fit_1234_per_plane_and_total.png"
#             fig_idx += 1
#             save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#             plot_list.append(save_fig_path)
#             save_plot_figure(
#                 save_fig_path,
#                 fig=fig,
#                 format="png",
#                 dpi=150,
#                 alias="charge_tt_task4_fit_1234_per_plane_and_total",
#             )
#         if show_plots:
#             plt.show()
#         plt.close(fig)
#     else:
#         print(
#             "Warning: Task 5 charge summary plot skipped because no per-plane charge "
#             "columns were found (neither p#_qsum nor p#_s#_qsum columns)."
#         )

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: FINAL/report plot block moved to standalone final plotting (acquisition_rate_vs_time_by_task_tt_with_histograms)
# ============================================================================
# if save_plots and task5_plot_enabled("acquisition_rate_vs_time_by_task_tt_with_histograms"):
#     rate_fig = create_rate_vs_time_by_task_tt_with_histograms(
#         working_df,
#         tt_column=POST_TT_COLUMN,
#         title=(
#             f"Task 5 acquisition rate by {POST_TT_COLUMN}, {basename_no_ext} "
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
#         print(f"Task 5 acquisition-rate-by-task-tt plot skipped: no valid {POST_TT_COLUMN}/datetime rows.")

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
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
# ARCHIVED FROM: script_5_fit_to_post.py
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
#     # Remove PNG files after creating the PDF (or after direct PDF append path).
#     for png in existing_pngs:
#         try:
#             os.remove(png)
#         except OSError as e:
#             print(f"Error: {e.filename} - {e.strerror}.")

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
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
# ARCHIVED FROM: script_5_fit_to_post.py
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
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_pages: PdfPages | None = None

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_page_count = 0

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_target_path: str | None = None

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: dead runtime PDF state after PNG-only split
# ============================================================================
# _direct_pdf_temp_path: str | None = None

# ============================================================================
# ARCHIVED FROM: script_5_fit_to_post.py
# REASON: dead runtime PDF atexit registration after PNG-only split
# ============================================================================
# atexit.register(close_direct_pdf_writer)

