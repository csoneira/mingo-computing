% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/mkdirOS.m
% Purpose: mkdirOS function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function mkdirOS(inputPath,OS,verbose)


if(~exist(inputPath,'dir'))
    if(verbose == 1)
        disp(['Creating folder ' inputPath]);
    end
    
    if(strcmp(OS,'windows'))
        system(['mkdir ' inputPath]);
    elseif(strcmp(OS,'linux'))
        system(['mkdir -p ' inputPath]);
    else
        disp('Operating system not defined. Stopping')
        pause;
    end
end

return
