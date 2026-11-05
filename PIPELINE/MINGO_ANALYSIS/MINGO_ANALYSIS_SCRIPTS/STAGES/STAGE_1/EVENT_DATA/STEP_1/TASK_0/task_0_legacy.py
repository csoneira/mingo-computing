# LEGACY CODE ARCHIVE FOR TASK 0
# This file is not imported and is not expected to execute.

# ============================================================================
# ARCHIVED FROM: script_0_acq_to_raw.py
# REASON: FINAL/report plot block moved to standalone final plotting (acquisition_rate_vs_time_by_trigger_type)
# ============================================================================
# if save_plots and task0_plot_enabled("acquisition_rate_vs_time_by_trigger_type"):
#     figure_directory = (
#         task_directory
#         / "PLOTS"
#         / "FIGURE_DIRECTORY"
#         / f"FIGURES_EXEC_ON_{date_execution}"
#     )
#     plot_path = figure_directory / f"acquisition_rate_vs_time_by_trigger_type_{basename_no_ext}.png"
#     plotted = plot_acquisition_rate_vs_time_by_trigger_type(
#         read_df,
#         plot_path,
#         title=f"Task 0 acquisition rate by trigger type, {basename_no_ext}",
#         accumulation_window_seconds=acquisition_rate_accumulation_window_seconds,
#     )
#     if plotted:
#         print(f"Task 0 acquisition-rate plot saved: {plot_path}", force=True)
#         saved_plot_paths.append(plot_path)
#     else:
#         print("Task 0 acquisition-rate plot skipped: no valid datetime rows.", force=True)

# ============================================================================
# ARCHIVED FROM: script_0_acq_to_raw.py
# REASON: FINAL/report plot block moved to standalone final plotting (acquisition_rate_vs_time_by_task_tt_with_histograms)
# ============================================================================
# if save_plots and task0_plot_enabled("acquisition_rate_vs_time_by_task_tt_with_histograms"):
#     if figure_directory is None:
#         figure_directory = (
#             task_directory
#             / "PLOTS"
#             / "FIGURE_DIRECTORY"
#             / f"FIGURES_EXEC_ON_{date_execution}"
#         )
#     plot_path = figure_directory / f"acquisition_rate_vs_time_by_task_tt_with_histograms_{basename_no_ext}.png"
#     plotted = plot_acquisition_rate_vs_time_by_task_tt_with_histograms(
#         read_df,
#         plot_path,
#         title=f"Task 0 acquisition rate by tt_task0_acq, {basename_no_ext} (files processed=1)",
#         tt_column="tt_task0_acq",
#         accumulation_window_seconds=acquisition_rate_accumulation_window_seconds,
#         rate_histogram_bins=acquisition_rate_task_tt_histogram_bins,
#         y_limit_left=config.get("acquisition_rate_task_tt_ylim_left", 0),
#         y_limit_right=config.get("acquisition_rate_task_tt_ylim_right", 4),
#     )
#     if plotted:
#         print(f"Task 0 acquisition-rate-by-task-tt plot saved: {plot_path}", force=True)
#         saved_plot_paths.append(plot_path)
#     else:
#         print("Task 0 acquisition-rate-by-task-tt plot skipped: no valid tt_task0_acq/datetime rows.", force=True)

# ============================================================================
# ARCHIVED FROM: script_0_acq_to_raw.py
# REASON: runtime PDF branch disabled by the PNG-only runtime plotting contract
# ============================================================================
# if create_pdf and saved_plot_paths and figure_directory is not None:
#     save_pdf_filename = f"mingo{str(station).zfill(2)}_task0_{basename_no_ext}_{date_execution}.pdf"
#     save_pdf_path = directories["pdf"] / save_pdf_filename
#     print(f"Creating Task 0 PDF with all plots in {save_pdf_path}", force=True)
#     _write_task0_pdf_from_pngs(saved_plot_paths, save_pdf_path, figure_directory)

# ============================================================================
# ARCHIVED FROM: script_0_acq_to_raw.py
# REASON: unreferenced plotting helper after runtime/FINAL separation: _write_task0_pdf_from_pngs
# ============================================================================
# def _write_task0_pdf_from_pngs(plot_paths: list[Path], pdf_path: Path, figure_directory: Path) -> None:
#     valid_plot_paths = [path for path in plot_paths if path.exists()]
#     if not valid_plot_paths:
#         return
#
#     import matplotlib.pyplot as plt
#
#     pdf_path.parent.mkdir(parents=True, exist_ok=True)
#     temp_pdf_path = _build_temp_pdf_path(pdf_path)
#     try:
#         with PdfPages(temp_pdf_path) as pdf:
#             for png_path in valid_plot_paths:
#                 img = Image.open(png_path)
#                 fig, ax = plt.subplots(figsize=(img.width / 100, img.height / 100), dpi=100)
#                 ax.imshow(img)
#                 ax.axis("off")
#                 pdf_save_rasterized_page(pdf, fig, bbox_inches="tight")
#                 plt.close(fig)
#         os.replace(temp_pdf_path, pdf_path)
#     finally:
#         if temp_pdf_path.exists():
#             temp_pdf_path.unlink()
#
#     for png_path in valid_plot_paths:
#         try:
#             png_path.unlink()
#         except OSError as exc:
#             print(f"Error removing temporary Task 0 PNG '{png_path}': {exc}", force=True)
#     if figure_directory.exists():
#         shutil.rmtree(figure_directory)

# ============================================================================
# ARCHIVED FROM: script_0_acq_to_raw.py
# REASON: dead runtime PDF helper after PNG-only split: _build_temp_pdf_path
# ============================================================================
# def _build_temp_pdf_path(target_path: Path) -> Path:
#     base = Path(f"{target_path}.tmp.{os.getpid()}")
#     candidate = base
#     counter = 1
#     while candidate.exists():
#         candidate = Path(f"{base}.{counter}")
#         counter += 1
#     return candidate

