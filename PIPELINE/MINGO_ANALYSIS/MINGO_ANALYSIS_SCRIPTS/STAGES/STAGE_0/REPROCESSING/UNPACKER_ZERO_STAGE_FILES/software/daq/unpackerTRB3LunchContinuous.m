% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/unpackerTRB3LunchContinuous.m
% Purpose: unpackerTRB3LunchContinuous function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function tmpFolder = unpackerTRB3LunchContinuous(inputVars)

%2024-02-27 on Generic - Change a bit the inputVars to tranport conf and therefore scriptVersions

conf              = inputVars{1};
inPath            = inputVars{2};
outPath           = inputVars{3};
fileType          = inputVars{4};
TRBs              = inputVars{5};
bufferSize        = inputVars{6};
writeTDCCal       = inputVars{7};
keepHLDs          = inputVars{8};
zipFiles          = inputVars{9};
downScale         = inputVars{10};


OS                = conf.OS;
logs              = conf.logs;
alarms            = conf.alarms;
Versioning        = conf.Versioning;

b                 = getBarOS(OS);
interpreter       = conf.INTERPRETER;


[status, result] = system(['ls -1rt ' inPath fileType]);
fileListRun = initFileHandler(Versioning,result,'HADES');

if(size(fileListRun,1) > 1)
    [status, result] = setSemaphore(inPath,logs,OS);
    if ~status
        %Semaphore is in place, creating a "private" area, both for unpacking and for raw2var
        tmpFolder  = ['tmp_' fileListRun(1).fileName];
        inPathTmp  = [inPath  tmpFolder b];
        outPathTmp = [outPath tmpFolder b];
        
        mkdirOS(inPathTmp,OS,1);
        mvOS(inPath,inPathTmp,fileListRun(1).fileNameExt,OS);
        
        mkdirOS(outPathTmp,OS,1);
        [status, result] = remSemaphore(inPath,logs,OS);
    else
        message2log = ['Semaphore in place or error during it generation skipping.'];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
        tmpFolder = 'none';
        return
    end
else
    message2log = ['No files to read. Skipping'];
    disp(message2log);
    write2log(logs,message2log,'   ','syslog',OS);
    tmpFolder = 'none';
    return
end



[status, result] = system(['ls -1rt ' inPathTmp fileType]);
fileListRun = initFileHandler(Versioning,result,'HADES');


try
    for hldFile=1
        fileName = fileListRun(hldFile).fileName;
        message2log = ['Unpacking file ' fileName];disp(message2log);write2log(logs,message2log,'   ','syslog',OS);
        
        
        errorType = unpackTRB3({inPathTmp},{outPathTmp},{fileName},TRBs,bufferSize,writeTDCCal,interpreter,OS);
        
        % Deal with the error during unpacking
        if(strcmp(errorType,'No events'))
            %Cause -> No events inside of hld file
            message2log = ['Unpacking error. No valid events inside of ' fileName];disp(message2log);write2log(logs,message2log,'   ','syslog',OS);
            message2log = ['Unpacking error. No valid events inside of ' fileName];disp(message2log);write2log(logs,message2log,'   ','criticallog',OS);
            %Solution -> File will be moved to done or deleted. No problem.
            %Send alarm
            inputvars = {alarms(locateAlarm('unpacking',alarms)),message2log};sendAlarm(inputvars);
        else
            %nothing to do
        end
        
        %%%What to do with the file in origing
        if(zipFiles)     %keep the file, move to done and zip
            %%%    Check if the folder exist
            [~, ~] = system(['mkdir -p ' inPath 'done' b]);
            [~, ~] = system(['mv ' inPathTmp fileListRun(hldFile).fileNameExt ' ' inPath 'done' b]);
            [~, ~] = system(['tar -czvf ' inPath 'done' b fileListRun(hldFile).fileName '.tar.gz ' inPath 'done' b fileListRun(hldFile).fileNameExt]);
            [~, ~] = system(['rm ' inPath 'done' b fileListRun(hldFile).fileNameExt]);
            
            message2log = ['Moving to done and zip on location: ' inPath 'done ' fileListRun(hldFile).fileNameExt];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
        elseif(keepHLDs)        %keep the file, move to done
            %%%    Check if the folder exist
            [~, ~] = system(['mkdir -p ' inPath 'done' b]);
            [~, ~] = system(['mv ' inPathTmp fileListRun(hldFile).fileNameExt ' ' inPath 'done' b]);
            
            message2log = ['Moving to done on location: ' inPath 'done ' fileListRun(hldFile).fileNameExt];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
            
        else            %delete the file
            rmOS(inPathTmp,fileListRun(hldFile).fileNameExt,OS)
            message2log = ['Deleting on  location: ' inPath 'done ' fileListRun(hldFile).fileNameExt];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
        end
        %%%%%%%%%%%%%
        
        [~, ~] = system(['rmdir ' inPathTmp]);
        
        message2log = ['Unpacking done'];disp(message2log);write2log(logs,message2log,'   ','syslog',OS);
    end
catch exception
    
    for i = 1:length(exception.stack)
        message2log = ['Error in: ' exception.stack(i).file ' line ' num2str(exception.stack(i).line)];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
        write2log(logs,message2log,'   ','criticallog',OS);
    end
    
    
    %Send alarm
    inputvars = {alarms(locateAlarm('unpacking',alarms)),message2log};sendAlarm(inputvars);
end

end
