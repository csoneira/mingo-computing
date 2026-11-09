% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/saveIndexedVars.m
% Purpose: saveIndexedVars function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function saveIndexedVars(INTERPRETER,outPath,outFile, varargin)

%%First cahnge the varName
outputVars = [];
for ind = 1:2:size(varargin,2)-1
    eval([eval(['varargin{' num2str(ind + 1) '}']) ' =  varargin{' num2str(ind) '};']);
    outputVars = [outputVars '''' eval(['varargin{' num2str(ind + 1) '}']) '''' ','];
end

outputVars = outputVars(1:end-1);

if strcmp('matlab',INTERPRETER)
    eval(['save([' '''' outPath outFile '''' '],' outputVars ');']);
elseif strcmp('octave',INTERPRETER)
    eval(['save([' '''' outPath outFile '''' '],' outputVars ',''-mat7-binary'');']);
end



return