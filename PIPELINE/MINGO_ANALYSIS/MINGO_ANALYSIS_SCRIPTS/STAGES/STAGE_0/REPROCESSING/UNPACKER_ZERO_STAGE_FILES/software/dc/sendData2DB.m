% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/sendData2DB.m
% Purpose: sendData2DB function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function sendData2DB(inputVars)

%2023-11-17 Created versioning capable function
%
%
%
%
%
%

conf              = inputVars{1};
scriptVersions    = conf.Versioning;


if(findVersion(scriptVersions,'sendData2DB') == 0)
    [outputVars] = sendData2DB_0(inputVars);%no DB distribution
elseif(findVersion(scriptVersions,'distributeAnaVars') == 1)
    
else
end
return


