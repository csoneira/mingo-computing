% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/connect2DB.m
% Purpose: connect2DB function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function connect2DB(inputVars)
%2024-01-04 - First implementation
%
%


conf            = inputVars{1};

logs            = conf.logs;
OS              = conf.OS;
systemName      = conf.SYSTEMNAME;
alarms          = conf.alarms;


    [status, result] = system('ps -ef | grep lipsql');
    if(strfind(result,'autossh -M 0 -o ServerAliveInterval 30 -o ServerAliveCountMax 3 -N    lipsql'))
        %autossh conenction alive, do nothing
    else
        %autossh conenction not present reconecting
        [status, result] = system('autossh -M 0 -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -N -f lipsql');
        
        message2log = ['Re-connecting DB'];
        disp(message2log);
        write2log(logs,message2log,'Error','netlog',OS);
        alarmType = 'netAccess';processAlarm(systemName,'DB',alarmType,message2log,alarms);
    end
return