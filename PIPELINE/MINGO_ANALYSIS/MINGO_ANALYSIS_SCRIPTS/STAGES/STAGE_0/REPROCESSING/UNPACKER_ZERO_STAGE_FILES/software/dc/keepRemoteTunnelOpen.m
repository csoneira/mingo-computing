% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/keepRemoteTunnelOpen.m
% Purpose: KeepRemoteTunnelOpen.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

[status, result] = system('ps -ef | grep lipana');
if(strfind(result,'autossh -M 0 -o ServerAliveInterval 30 -o ServerAliveCountMax 3 -N    lipana'))
    %autossh conenction alive, do nothing
 else
    %autossh conenction not present reconecting
    [status, result] = system('autossh -M 0 -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -N -f lipana');
 end
