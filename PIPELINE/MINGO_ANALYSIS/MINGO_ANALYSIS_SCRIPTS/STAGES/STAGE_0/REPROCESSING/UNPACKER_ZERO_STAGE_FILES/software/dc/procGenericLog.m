% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/procGenericLog.m
% Purpose: procGenericLog function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [errorOnClose, newFilename] = procGenericLog(inputVars)

%%
%2023-04-21 - Implementation of the inputVars and Versioning.

scriptVersions      =  inputVars{1};
fp                  =  inputVars{2};
fileName            =  inputVars{3};
outPath             =  inputVars{4};
systemName          =  inputVars{5};
dev2Read            =  inputVars{6};
type                =  inputVars{7};
columns             =  inputVars{8};
nameFormat          =  inputVars{9};
logs                = inputVars{10};
alarms              = inputVars{11};
interpreter         = inputVars{12};
OS                  = inputVars{13};


%%Versions

%1   2023-04-21 - Posibility to change the output Name dinamically through the confFile
%0 Initial Version


if(findVersion(scriptVersions,'procGenericLog') == 1)

    time  = [];
    otherVariables = [];
    data  = [];

    errorOnClose = 0;

    try
        while ~feof(fp)
            string = fgetl(fp);

            result1 = 0;result2 = 0;
            [result1, lastPosition, time_] = checkTimeFormat(string,type,'');
            if result1 %time check format passed
                [result2, lastPosition, data_] = checkColFormat(string,lastPosition,columns);
                if result2
                    data = [data;  data_];
                    time = [time;  time_];
                end
            end


            if ~(result1 & result2)
                message2log = [dev2Read ': Skipping one line due to wrong length or missformatting.'];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);
            end

        end

        %Just the date without extension 2019-11-12
        newFilename = fileName(setdiff(1:length(nameFormat),findstr('*',nameFormat)));
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

elseif(findVersion(scriptVersions,'procGenericLog') == 0)
    time  = [];
    otherVariables = [];
    data  = [];

    errorOnClose = 0;

    try
        while ~feof(fp)
            string = fgetl(fp);

            result1 = 0;result2 = 0;
            [result1, lastPosition, time_] = checkTimeFormat(string,type,'');
            if result1 %time check format passed
                [result2, lastPosition, data_] = checkColFormat(string,lastPosition,columns);
                if result2
                    data = [data;  data_];
                    time = [time;  time_];
                end
            end


            if ~(result1 & result2)
                message2log = [dev2Read ': Skipping one line due to wrong length or missformatting.'];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);
            end

        end

        %Just the date without extension 2019-11-12
        positionOF_ = strfind(fileName,'_');positionOF_ = positionOF_(end);
        newFilename = fileName(positionOF_+1:end-4);
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

end

return