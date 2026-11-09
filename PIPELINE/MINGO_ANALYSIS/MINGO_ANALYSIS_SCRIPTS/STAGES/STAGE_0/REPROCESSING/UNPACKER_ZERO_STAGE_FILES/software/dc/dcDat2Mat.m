% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/dcDat2Mat.m
% Purpose: dcDat2Mat function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function dcDat2Mat(inputVars)

%%
%2023-04-21 - Implementation of the inputVars and Versioning.





scriptVersions      =  inputVars{1};
inPath              =  inputVars{2};
outPath             =  inputVars{3};
fileType            =  inputVars{4};
scriptInfo          =  inputVars{5};
systemName          =  inputVars{6};
logs                =  inputVars{7};
alarms              =  inputVars{8};
dev2Read            =  inputVars{9};
interpreter         = inputVars{10};
OS                  = inputVars{11};


script2Run         = scriptInfo{1};
type               = scriptInfo{2};
columns            = scriptInfo{3};
nameFormat         = scriptInfo{4};

message2log = ['Reading files from ' dev2Read];
disp(message2log);
write2log(logs,message2log,'   ','syslog',OS);

%%Versions

%1   2023-04-21 Modification of procGenericLog to admit variable number of input vars. This was done on MINGOS
%0 Initial Version



%% Version Control
if(findVersion(scriptVersions,'dcDat2Mat') == 1)


    s = dir([inPath fileType]);
    if (length(s) > 0)
        try
            for i=1:size(s,1)
                fileName = s(i).name;
                file2Open = [inPath fileName];
                openFile;

                message2log = ['Reading file                                             : ' num2str(i) ' ' fileName];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);

                if strcmp(script2Run,'procGenericLog')
                    %New implementation of generic readout
                    eval(['[errorBack, newFileName] = ' script2Run '({scriptVersions,' num2str(fp) ',' '''' fileName '''' ',' '''' outPath '''' ',systemName,dev2Read,type,columns,nameFormat,logs,alarms,interpreter,OS});']);
                else
                    %Old implementation
                    eval(['[errorBack, newFileName] = ' script2Run '(' num2str(fp) ',' '''' fileName '''' ',' '''' outPath '''' ',systemName,dev2Read,logs,alarms,interpreter,OS);']);
                end

                if(~errorBack)
                    [status, result] = system(['mv ' file2Open ' ' inPath 'done' getBarOS(OS)]);
                    message2log = ['Moving file                                              : ' num2str(i) ' ' fileName];
                    disp(message2log);
                    write2log(logs,message2log,'   ','syslog',OS);
                end
            end
        catch exception

            message2log = processException(exception);

            disp(message2log);
            write2log(logs,message2log,'Error','syslog',OS);
            write2log(logs,message2log,'Error','criticallog',OS);
        end
    else
        message2log = ['No files to read. Skipping                               :'];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
    end


elseif(findVersion(scriptVersions,'dcDat2Mat') == 0)

    s = dir([inPath fileType]);
    if (length(s) > 0)
        try
            for i=1:size(s,1)
                fileName = s(i).name;
                file2Open = [inPath fileName];
                openFile;

                message2log = ['Reading file                                             : ' num2str(i) ' ' fileName];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);

                if strcmp(script2Run,'procGenericLog')
                    %New implementation of generic readout
                    eval(['[errorBack, newFileName] = ' script2Run '(' num2str(fp) ',' '''' fileName '''' ',' '''' outPath '''' ',systemName,dev2Read,type,columns,logs,alarms,interpreter,OS);']);
                else
                    %Old implementation
                    eval(['[errorBack, newFileName] = ' script2Run '(' num2str(fp) ',' '''' fileName '''' ',' '''' outPath '''' ',systemName,dev2Read,logs,alarms,interpreter,OS);']);
                end

                if(~errorBack)
                    [status, result] = system(['mv ' file2Open ' ' inPath 'done' getBarOS(OS)]);
                    message2log = ['Moving file                                              : ' num2str(i) ' ' fileName];
                    disp(message2log);
                    write2log(logs,message2log,'   ','syslog',OS);
                end
            end
        catch exception

            message2log = processException(exception);

            disp(message2log);
            write2log(logs,message2log,'Error','syslog',OS);
            write2log(logs,message2log,'Error','criticallog',OS);
        end
    else
        message2log = ['No files to read. Skipping                               :'];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
    end

end


return