% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/plot/mySetRange.m
% Purpose: mySetRange function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function range = mySetRange(ax,axRange,var)

if(isa(axRange,'char'))
    if(strcmp(axRange,'NONE') || strcmp(axRange,'None'))
        %Do nothing
    elseif(strcmp(axRange(1:end-3),'MEDIAN') || strcmp(axRange(1:end-3),'Median'))
        range(1) = 0; 
        range(2) = median(median(var))*str2num(axRange(end-2:end));
    end
else
    if(strcmp(ax,'x') || strcmp(ax,'X'))
        %
    elseif(strcmp(ax,'y') || strcmp(ax,'Y'))
        %
    elseif(strcmp(ax,'z') || strcmp(ax,'Z'))
        range = axRange;
    else
    end
end



return