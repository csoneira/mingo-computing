This directory is intended for comparison between simulation and data, but also for simulation checking by itself. We need, then, first a small common script with a config file that will make the matching between the real and simulated data.

The logic to follow must be the one in /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/SIMULATION_VS_DATA_AND_VALIDATION/TASK_5/METADATA_COMPARISON/TRIGGER_RATES/trigger_rate_similarity.py to compare files: first you read in the config file the siulation parameter ranges that we are interested in, you can see them

cos_n,flux_cm2_min, --> exclusively in simualted data, filter in range

z_plane_1,z_plane_2,z_plane_3,z_plane_4, trigger_combinations --> the match must be exact, we select the exact value we are interested in the config file

efficiencies, --> filter on range

in the /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv.

Then you are going to go to the /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1/EVENT_DATA/STEP_1/TASK_4/METADATA/task_4_metadata_robust_efficiency.csv and take P1_eff_robust_xyphi, P2_eff_robust_xyphi, P3_eff_robust_xyphi, P4_eff_robust_xyphi columns, in MINGO00 and take those columns.

Then you go to the same file for the station of study /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0*/STAGE_1/EVENT_DATA/STEP_1/TASK_4/METADATA/task_4_metadata_robust_efficiency.csv and take P1_eff_robust_xyphi, P2_eff_robust_xyphi, P3_eff_robust_xyphi, P4_eff_robust_xyphi columns.

Now we have two options. 1. If the script is in a METADATA_COMPARISON directory, then we have to establish a match for all the rows in the real data list. To do so, you calculate the euclidean distance between P1_eff_robust_xyphi, P2_eff_robust_xyphi, P3_eff_robust_xyphi, P4_eff_robust_xyphi for MINGO00 and the station of study and take only the ones that less than a boundary value defined in the config file.

Now the match correspondence between simulated and real data is established.

But 2. If the script used is in /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/SIMULATION_VS_DATA_AND_VALIDATION/TASK_5/FILEvFILE, only ONE data file will be randomly taken from the list, and a further filter must be passed: both parquet datafiles must be in the corresponding /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0*/STAGE_1/EVENT_DATA/STEP_1/TASK_*/INPUT_FILES/COMPLETED_DIRECTORY. If the script is about a task 4 datafile, then you must find in TASK_5/INPUT_FILES/COMPLETED_DIRECTORY (always one more because the output of the task i is in the input of the task i+1). Once this last filter is passed, then you can indeed use the parquets to do the analysis of each script.

It's important that this is common for any TASK and inside it, each FILEvFILE or METADATA_COMPARISON, because the basis is always the same: taking pairs of datafiles to compare.
