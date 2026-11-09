% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/sendAlarm.m
% Purpose: sendAlarm function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function sendAlarm(inputVars)
%
%2020-03-16 - Possibility to modifiy the number of inputs dinamically.
%2020-03-16 - System variable introduced
%
%sendAlarm(alarm, message, system)
%alarm      => flag if 1 alarm is send
%message    => message of the alarm
%system     => system name

alarm      = inputVars{1};
message    = inputVars{2};
                            if (size(inputVars,2) == 3); 
system     = inputVars{3};
                            else system = 'System'; end


if(alarm.active == 1)
subject     = [system ' alarm: ' alarm.type];

to          = alarm.TO;
message     = message; 
attachment  = {''};
sendbashEmail(subject,to,message,attachment);   

    
end
return