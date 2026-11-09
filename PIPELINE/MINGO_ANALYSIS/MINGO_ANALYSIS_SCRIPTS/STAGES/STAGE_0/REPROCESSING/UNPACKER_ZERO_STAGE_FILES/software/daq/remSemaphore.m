% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/remSemaphore.m
% Purpose: remSemaphore function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [status, result] = remSemaphore(pathIn,logs,OS)
%
%
%Status = 1 means error 
%result is a coment about the problem



if(exist([pathIn 'semaphore'],'dir'))%create the semaphore
    try
        [status, result] = system(['rmdir ' pathIn  'semaphore/']);
        if status == 1
            message2log = ['Error when removing the Semaphore skipping.'];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
            keyboard
        end
    catch
        message2log = ['Error when removing the Semaphore skipping.'];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
        status = 1;
        result = message2log;
        keyboard
    end
else
    message2log = ['No semaphore when It is supossed to be.'];
    disp(message2log);
    write2log(logs,message2log,'   ','syslog',OS);
    status = 1;
    result = message2log;
    keyboard
end






return

