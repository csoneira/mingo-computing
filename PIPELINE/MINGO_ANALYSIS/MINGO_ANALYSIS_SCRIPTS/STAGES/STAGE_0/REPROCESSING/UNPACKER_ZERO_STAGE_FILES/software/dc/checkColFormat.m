% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/checkColFormat.m
% Purpose: checkColFormat function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [result, lastPosition, data] = checkColFormat(varargin)
%Check the number of columns from sc files
%Check if the number of columns is the right one 
%result         => 1 if ok, = 0 if not ok
%LastPosition   => position of the string with the last character from  time, Nan if result = 0
%time           => time in matlab format , Nan if result = 0


string              =  varargin{1};
firstPosition       =  varargin{2};
nCol                =  varargin{3};


f = firstPosition  + 1;


try
    data = str2num(string(f:end));
    
    if size(data,2) == nCol
        result = 1;
        lastPosition = 0;
    else
        disp('Number of columns found on the file is not equal to the number of columns on the configuration');
        result = 0;
        lastPosition = nan;
        data = nan;
    end
    
catch
    disp('Something wrong on the checkColFormat try loop');
    result = 0;
    lastPosition = nan;
    data = nan;
end

return