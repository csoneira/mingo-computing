% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/distributeAnaVars.m
% Purpose: distributeAnaVars function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [outputVars] = distributeAnaVars(inputVars)

%2023-11-17 Created versioning capable function
%
%
%
%
%
%

conf              = inputVars{5};
scriptVersions    = conf.Versioning;


if(findVersion(scriptVersions,'distributeAnaVars') == 0)
    [outputVars] = distributeAnaVars_0(inputVars);%no DB distribution
elseif(findVersion(scriptVersions,'distributeAnaVars') == 1)
    [outputVars] = distributeAnaVars_1(inputVars);%With DB distribution capability
else
end

return