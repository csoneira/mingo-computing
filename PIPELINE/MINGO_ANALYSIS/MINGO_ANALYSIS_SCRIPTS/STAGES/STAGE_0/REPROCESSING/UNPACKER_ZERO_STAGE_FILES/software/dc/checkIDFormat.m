% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/checkIDFormat.m
% Purpose: checkIDFormat function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [result, lastPosition, ID] = checkIDFormat(varargin)
%Check the format of the ID from sc files
%Check if the ID of the sc files is right formated
%result         => 1 if ok, = 0 if not ok
%LastPosition   => position of the string with the last character from  ID, Nan if result = 0
%time           => time in matlab format , Nan if result = 0


string              =  varargin{1};
firstPosition       =  varargin{2};



f = firstPosition  + 1;


try 
    ID  = [string(f:f+1) string(f+3:f+4) string(f+6:f+7) string(f+9:f+10) string(f+12:f+13) string(f+15:f+16)];
    ID_ = hex2dec(ID);
    lastPosition = f + 16 + 1;
    result = 1;
catch
    result = 0;
    lastPosition = nan;
    ID = nan; 
end


return