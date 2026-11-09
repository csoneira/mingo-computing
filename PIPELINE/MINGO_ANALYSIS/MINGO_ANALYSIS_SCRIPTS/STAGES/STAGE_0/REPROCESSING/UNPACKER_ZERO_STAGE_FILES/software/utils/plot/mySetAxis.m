% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/plot/mySetAxis.m
% Purpose: mySetAxis function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function mySetAxis(ax,axZoom,var)

if(isa(axZoom,'char'))
    if(strcmp(axZoom,'NONE') || strcmp(axZoom,'None'))
        %Do nothing
    elseif(strcmp(axZoom,'MM') || strcmp(axZoom,'mm'))%Set 1.2 0.8 around the max
        yaxisMM(var);
    end
else
    if(strcmp(ax,'x') || strcmp(ax,'X'))
        xaxis(axZoom(1),axZoom(2));
    elseif(strcmp(ax,'y') || strcmp(ax,'Y'))
        yaxis(axZoom(1),axZoom(2));
    elseif(strcmp(ax,'z') || strcmp(ax,'Z'))
        zaxis(axZoom(1),axZoom(2));
    else
    end
end
end