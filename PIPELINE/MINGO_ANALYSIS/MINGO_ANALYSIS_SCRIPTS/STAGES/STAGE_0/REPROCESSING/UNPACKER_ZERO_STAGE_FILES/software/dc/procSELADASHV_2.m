% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/procSELADASHV_2.m
% Purpose: procSELADASHV function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [errorOnClose, newFilename] = procSELADASHV(fp,fileName,outPath,systemName,dev2Read,logs,alarms,interpreter,OS)



time  = [];
otherVariables = [];
data  = [];

errorOnClose = 0;

try
    while ~feof(fp)
        string = fgetl(fp);
        
        result1 = 0;result2 = 0;result3 = 0;
        [result1, lastPosition, time_] = checkTimeFormat(string,'I2C','');
        if result1 %time check format passed
            [result2, lastPosition, ID_] = checkIDFormat(string,lastPosition);
            if result2
                [result3, lastPosition, data_] = checkColFormat(string,lastPosition,16);
                if result3
                    data = [data;  data_];
                    time = [time;  time_];
                end
            end
        end
        
                
        if ~(result1 & result2 & result3)
            message2log = [dev2Read ': Skipping one line due to wrong length or missformatting.'];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
        end
        
    end
    
    %Just the date without extension 2019-11-12
    newFilename = fileName(strfind(fileName,'_')+1:end-4);
    if strcmp('matlab',interpreter)
        save([outPath newFilename '.mat'],'time','data','otherVariables');
    elseif strcmp('octave',interpreter)
        save([outPath newFilename '.mat'],'time','data','otherVariables','-mat7-binary');
    else
    end
    
    fclose(fp);
    
catch exception
    
    message2log = processException(exception);
    write2log(logs,message2log,'   ','syslog',OS);
    write2log(logs,message2log,'   ','criticallog',OS);
    
    errorOnClose = 1;
    fclose(fp);
    
    alarmType = 'unpackDCS';
    processAlarm(systemName,dev2Read,alarmType,message2log,alarms);
    
end

return