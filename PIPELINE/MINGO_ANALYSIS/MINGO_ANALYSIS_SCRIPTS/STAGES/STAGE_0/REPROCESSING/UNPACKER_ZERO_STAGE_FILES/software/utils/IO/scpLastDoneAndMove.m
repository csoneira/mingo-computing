% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/scpLastDoneAndMove.m
% Purpose: scpLastDoneAndMove function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function scpLastDoneAndMove(inputVars)

%2024-04-26 on sRPC    - Do the code compatible with no entries on config
%2023-01-10 on Seladas - Add the possibility to downscale, keepFile or zipit
%2023-01-10 on Seladas - Modified to be abel to acumulate static variables

%%% Load Variables

conf      = inputVars{1};
remoteIP  = inputVars{2};
user      = inputVars{3};
key       = inputVars{4};
pathIn    = inputVars{5};
pathOut   = inputVars{6};
port      = inputVars{7};
fileExt   = inputVars{8};
keepHLDs  = inputVars{9};
zipFiles  = inputVars{10};
downScale = inputVars{11};

logs      = conf.logs;
OS        = conf.OS;

b = getBarOS(OS);

if (length(key) > 0);     keyString = ['-i '  key ' '];else;    keyString = '';end
if (length(port) > 0);sshPortString = ['-p ' port ' '];else;sshPortString = '';end
if (length(port) > 0);scpPortString = ['-P ' port ' '];else;scpPortString = '';end
if (length(user) > 0);   userString =       [user '@'];else;   userString = '';end

try %Try the copy
    %%% List the files
    [status, result] = system(['ssh ' keyString sshPortString userString remoteIP ' ls -1rt ' pathIn fileExt]);
    
    if status == 0
        %%% resultProc = procLsOut(result);
        hld2Copy = initFileHandler(conf.Versioning,result,'HADES');
    else
        message2log = ['Error while copying from remote location: ' remoteIP ' ' result];
        disp(message2log);
        write2log(logs,message2log,'Error','syslog',OS);
        
        message2log = ['Error while copying from remote location: ' remoteIP ' ' result];
        disp(message2log);
        write2log(logs,message2log,'Error','netlog',OS);
        
        message2log = ['Error while copying from remote location: ' remoteIP '' result];
        disp(message2log);
        write2log(logs,message2log,'Error','criticallog',OS);
        return
    end
    
    if(size(hld2Copy,1) == 0 )
        message2log = ['No files on location'];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
    elseif(size(hld2Copy,1) == 1)
        message2log = ['Just one file => skipping it.'];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
    else
        for i=1:size(hld2Copy,1)-1
            file        = hld2Copy(i).fullName;
            fileNameExt = hld2Copy(i).fileNameExt;
            
            %%Verify if the file is been written if so continue
            %%If the file is not been written proced normaly
            %[status, result] = system(['ssh -i ' key ' -p ' port ' ' user '@' remoteIP ' lsof | grep ' pathIn fileExt]);

            %%% Check if the folder exist
            mkdirOS(pathOut,OS,1);mkdirOS([pathOut 'done' b],OS,1);
            [status, result] = system(['ssh ' keyString sshPortString userString remoteIP ' mkdir -p ' pathIn 'done' b]);
            
            if(~mod(i-1,downScale))%%% Just skip to copy one file 
                %%% Copy files
                message2log = ['Copying from remote location: ' remoteIP ' ' file];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);
                [status, result] = system(['scp ' keyString scpPortString userString remoteIP ':' file ' ' pathOut]);
            else
                message2log = ['Skiping from remote location: ' remoteIP ' ' file ' due to downscale factor ' downScale];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);
            end
            
            if (keepHLDs == 1 && zipFiles == 0)%%% Just copy the files to done
                %%% Move to the remote \ done folder
                [status, result] = system(['ssh ' keyString sshPortString userString remoteIP ' mv ' file ' ' pathIn 'done' b]);

                message2log = ['Moving to done on remote location: ' remoteIP ' ' file];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);
            elseif(keepHLDs == 1 && zipFiles == 1)
                message2log = ['Compressing and moving to done on remote location: ' remoteIP ' ' file];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);
                [status, result] = system(['ssh ' keyString sshPortString userString remoteIP ' "tar -czvf ' pathIn 'done' b fileNameExt '.tar.gz ' file '"']);
                [status, result] = system(['ssh ' keyString sshPortString userString remoteIP ' rm ' file ]);
            elseif(keepHLDs == 0 && zipFiles == 0)%%% Just delete the file
                [status, result] = system(['ssh ' keyString sshPortString userString remoteIP ' rm ' file ]);

                message2log = ['Deleting on remote location: ' remoteIP ' ' file];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);
            else
                keyboard
            end
        end
    end
catch%if error report the error
    message2log = ['Error while copying from remote location: ' remoteIP ' '];
    disp(message2log);
    write2log(logs,message2log,'Error','syslog',OS);
    
    message2log = ['Error while copying from remote location: ' remoteIP ' '];
    disp(message2log);
    write2log(logs,message2log,'Error','netlog',OS);
    
    message2log = ['Error while copying from remote location: ' remoteIP ' '];
    disp(message2log);
    write2log(logs,message2log,'Error','criticallog',OS);
end

return
