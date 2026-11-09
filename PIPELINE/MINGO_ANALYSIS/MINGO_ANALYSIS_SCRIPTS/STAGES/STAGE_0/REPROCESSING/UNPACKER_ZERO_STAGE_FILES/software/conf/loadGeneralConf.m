% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/conf/loadGeneralConf.m
% Purpose: Configuration.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

%% Configuration

# Display the HOME variable
disp(['loadGeneralConf.m --> Current HOME used: ' HOME]);  % <-- Echo HOME to stdout/log

path(path,[HOME 'software/']);
path(path,[HOME 'software/conf/']);
path(path,[HOME 'software/utils/IO/']);
path(path,[HOME 'software/utils/plot/']);
path(path,[HOME 'software/utils/var/']);
path(path,[HOME 'software/utils/sejda-console-3.2.14/']);path4sejda = [HOME 'software/utils/sejda-console-3.2.14/'];
path(path,[HOME 'software/dc/']);
path(path,[HOME 'software/daq/']);
path(path,[HOME 'software/ana/']);
path(path,[HOME 'software/online/']);

