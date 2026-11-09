% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/setLegend.m
% Purpose: Set the legend.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%% Set the legend
if(strcmp(interpreter,'matlab'))
    legH = get(axisH,'legend');
elseif(strcmp(interpreter,'octave'))
    try
        legH = get(axisH,'__legend_handle__');
    catch
        legH = [];
    end
end

if(length(legH) == 0)
    legH = legend(varName);
else
    if(strcmp(interpreter,'matlab'))
        S = get(legH,'String');
        S{end} = varName;
        set(legH,'String',S);
    elseif(strcmp(interpreter,'octave'))
        S = get(legH,'String');
        S = horzcat(S,varName);
        legend(S);
    end
end
set(legH,'visible','off');
if(axisLegend)
    set(legH,'visible','on');
    set(legH,'location','northwest');
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%