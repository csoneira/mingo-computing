% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/logsName2Date.m
% Purpose: logsName2Date function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function  matDate = logsName2Date(varargin)
%
% Convert the name of the HADES files into a matlab date
%


scriptVersions       = varargin{1};
fileName             = varargin{2};



if (findVersion(scriptVersions,'logsName2Date') ==  1)

    date     = fileName(isstrprop(fileName,'digit'));
    
    yyFromFile    = str2num(date(1:4));
    MMFromFile    = str2num(date(5:6));
    ddFromFile    = str2num(date(7:8));
    hourFromFile  = 0;
    mmFromFile    = 0;
    ssFromFile    = 0;
    
    matDate = datenum([yyFromFile MMFromFile ddFromFile hourFromFile  mmFromFile ssFromFile]);
elseif (findVersion(scriptVersions,'initFileHandler') ==  2)
end

end