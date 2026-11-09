% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/system/lookUpTables/mingo01export2asic.m
% Purpose: Mingo01export2asic.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

M = full([datevec(EBtime) triggerType T1_F T1_B Q1_F Q1_B T2_F T2_B Q2_F Q2_B T3_F T3_B Q3_F Q3_B T4_F T4_B Q4_F Q4_B]);% T1_F T1_B Q1_F Q1_B T2_F T2_B Q2_F Q2_B T3_F T3_B Q3_F Q3_B T4_F T4_B Q4_F Q4_B]);
fprintf(fp,...
    ['%04d %02d %02d %02d %02d %02d  %01d   ' ...
    '%09.4f %09.4f %09.4f %09.4f  %09.4f %09.4f %09.4f %09.4f   %09.4f %09.4f %09.4f %09.4f  %09.4f %09.4f %09.4f %09.4f   '...
    '%09.4f %09.4f %09.4f %09.4f  %09.4f %09.4f %09.4f %09.4f   %09.4f %09.4f %09.4f %09.4f  %09.4f %09.4f %09.4f %09.4f   '...
    '%09.4f %09.4f %09.4f %09.4f  %09.4f %09.4f %09.4f %09.4f   %09.4f %09.4f %09.4f %09.4f  %09.4f %09.4f %09.4f %09.4f   '...
    '%09.4f %09.4f %09.4f %09.4f  %09.4f %09.4f %09.4f %09.4f   %09.4f %09.4f %09.4f %09.4f  %09.4f %09.4f %09.4f %09.4f\n'],M');

