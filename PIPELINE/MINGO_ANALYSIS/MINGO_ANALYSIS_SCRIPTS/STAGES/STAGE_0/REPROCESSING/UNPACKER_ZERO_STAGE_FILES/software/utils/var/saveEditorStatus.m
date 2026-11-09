% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/var/saveEditorStatus.m
% Purpose: saveEditorStatus function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function saveEditorStatus(name)
list = matlab.desktop.editor.getAll;


fileNames = cell(size(list,2),1);
for i=1:size(list,2)
    fileNames{i} = list(i).Filename;
end

save(['~/.matlab/EditorStatus_' name '.mat'],'fileNames');

return
