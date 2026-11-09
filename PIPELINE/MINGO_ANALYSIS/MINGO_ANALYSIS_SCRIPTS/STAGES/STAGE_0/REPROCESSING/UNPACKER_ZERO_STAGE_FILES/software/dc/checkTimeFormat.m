% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/checkTimeFormat.m
% Purpose: checkTimeFormat function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [result, lastPosition, time] = checkTimeFormat(varargin)
%Check the format of the time from sc files
%Check if the time of the sc files is right formated
%result         => 1 if ok, = 0 if not ok
%LastPosition   => position of the string with the last character from  time, Nan if result = 0
%time           => time in matlab format , Nan if result = 0


string              =  varargin{1};
version             =  varargin{2};



%             I2C        - 2020-11-26T00:21:04
%             I2C_2      - 2020-11-26T00:21:04.171121
%2021-08-18   I2C_3      - 2021-08-18T09:09:01 1.9 21.2 21.1 1019           Implementing a space in the begining  . This is found in the STRATOS GAS DISTRIBUTOR 
%2023-04-20   I2C_4      - 2023-04-20T18:28:03; 80:1F:12:59:D4:A9           Implementing a space after date and before the MAC in HV 
%2023-04-20   I2C_5      - 2023-04-21 00:00:04 493 524 505 520              Implementing a time without T
%2023-06-06   I2C_6      - Outro .... 


try
    
    if strcmp(version,'I2C')
        result = string(5) == '-' & string(8) == '-' & string(11) == 'T' & string(14) == ':' & string(17) == ':';
        
        if result
            time   = datenum([str2num(string(1:4)) str2num(string(6:7)) str2num(string(9:10)) str2num(string(12:13)) str2num(string(15:16)) str2num(string(18:20))]);
            lastPosition = 20;
        else
            result       = 0;
            lastPosition = nan;
            time         = nan;
        end
    elseif strcmp(version,'I2C_2')
        result = string(5) == '-' & string(8) == '-' & string(11) == 'T' & string(14) == ':' & string(17) == ':' & string(20) == '.';
        
        if result
            time   = datenum([str2num(string(1:4)) str2num(string(6:7)) str2num(string(9:10)) str2num(string(12:13)) str2num(string(15:16)) str2num(string(18:20))]);
            lastPosition = 20 + 6;
        else
            result       = 0;
            lastPosition = nan;
            time         = nan;
        end    
    elseif strcmp(version,'I2C_3')% There is a space in the begining  2021-08-18T09:09:01 1.9 21.2 21.1 1019. This is found in the STRATOS GAS DISTRIBUTOR 
        string = string(2:end);
        result = string(5) == '-' & string(8) == '-' & string(11) == 'T' & string(14) == ':' & string(17) == ':';
        
        if result
            time   = datenum([str2num(string(1:4)) str2num(string(6:7)) str2num(string(9:10)) str2num(string(12:13)) str2num(string(15:16)) str2num(string(18:20))]);
            lastPosition = 20 +1;
        else
            result       = 0;
            lastPosition = nan;
            time         = nan;
        end        
    elseif strcmp(version,'I2C_4')
        result = string(5) == '-' & string(8) == '-' & string(11) == 'T' & string(14) == ':' & string(17) == ':';

        if result
            time   = datenum([str2num(string(1:4)) str2num(string(6:7)) str2num(string(9:10)) str2num(string(12:13)) str2num(string(15:16)) str2num(string(18:20))]);
            lastPosition = 21;
        else
            result       = 0;
            lastPosition = nan;
            time         = nan;
        end
    elseif strcmp(version,'I2C_5')
        result = string(5) == '-' & string(8) == '-'  & string(14) == ':' & string(17) == ':';

        if result
            time   = datenum([str2num(string(1:4)) str2num(string(6:7)) str2num(string(9:10)) str2num(string(12:13)) str2num(string(15:16)) str2num(string(18:20))]);
            lastPosition = 19;
        else
            result       = 0;
            lastPosition = nan;
            time         = nan;
        end
    elseif strcmp(version,'I2C_6')
        result = string(5) == '-' & string(8) == '-'  & string(14) == ':' & string(17) == ':';

        if result
            time   = datenum([str2num(string(1:4)) str2num(string(6:7)) str2num(string(9:10)) str2num(string(12:13)) str2num(string(15:16)) str2num(string(18:20))]);
            lastPosition = 20;
        else
            result       = 0;
            lastPosition = nan;
            time         = nan;
        end
    elseif strcmp(version,'FPGA')
        fileName = varargin{3};
        result = string(3) == ':' & string(6) == ':';
        if result
            time   = datenum([str2num(fileName(1:4)) str2num(fileName(6:7)) str2num(fileName(9:10)) str2num(string(1:2)) str2num(string(4:5)) str2num(string(7:8))]);
            lastPosition = 8;
        else
            result       = 0;
            lastPosition = nan;
            time         = nan;
        end
    else
        
        
    end
    
catch
    result       = 0;
    lastPosition = nan;
    time         = nan;
end

return