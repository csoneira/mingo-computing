% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/findVersion.m
% Purpose: findVersion function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function version = findVersion(scriptVersion,fun2Find)


s = strfind(scriptVersion(:,1),fun2Find);
%Position on the array of teh candidate
p = find(not(cellfun('isempty',s)));




if(isempty(p))
    disp(['No version found for ' fun2Find ' selecting by defult version 1']);
    version = 1;
else
    
    if(strcmp(scriptVersion{p,1},fun2Find))
        %Name exactly match the string
        version = scriptVersion{p,2};
    else
        disp('Name of the function does not have an exact match check');
        keyboard
    end
end
return
