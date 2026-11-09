% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/conf/initConf.m
% Purpose: Check system.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

%% Check system
[status, result] = system('hostname');
result = strtrim(result);  % Remove trailing newline or whitespace

% Retrieve SYSTEMNAME from environment variable
env_system = getenv('RPCSYSTEM');
if isempty(env_system)
    env_system = 'mingo01'; % Fallback if not defined
end

if strcmp(result, 'manta')
    OS = 'linux';
    HOSTNAME    = 2;
    SYSTEMNAME  = env_system;
    % Software location
    HOME        = ['/home/alberto/gate/localDocs/lip/daqSystems/' SYSTEMNAME '/'];
    % System data structure
    SYS         = [HOME 'system/'];
    INTERPRETER = 'matlab';
else
    more off
    warning('off');
    OS = 'linux';
    HOSTNAME    = 1;
    SYSTEMNAME  = env_system;
    % Software location
    HOME        = [fileparts(fileparts(fileparts(mfilename('fullpath')))) filesep];
    % System data structure
    SYS         = [HOME 'system/'];
    INTERPRETER = 'octave';
end
