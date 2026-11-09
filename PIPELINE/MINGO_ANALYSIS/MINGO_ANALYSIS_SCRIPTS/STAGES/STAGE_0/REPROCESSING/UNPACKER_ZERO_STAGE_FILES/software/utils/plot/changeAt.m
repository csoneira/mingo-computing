% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/plot/changeAt.m
% Purpose: changeAt function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function changeAt(what,value,who)
%function changeAt(who,what,value)

if strcmp(what,'delete')
    if(nargin == 2)
        H = value;
    else
        H =  max(get(gca,'children'));
    end
    delete(H)
    return   
end


if(nargin == 2)
    H =  max(get(gca,'children'));
else
    H = who;
end


set(H,what,value)

return
