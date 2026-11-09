% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/cpLastCloseAndMove.m
% Purpose: cpLastCloseAndMove function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function cpLastCloseAndMove(pathIn,pathOut,fileExt,zip,logs,OS)
%%

b = getBarOS(OS);

try %Try the copy
    %%%List the files
    [status, result] = system(['ls -1rt ' pathIn fileExt]);
    
    if status == 0
        hld2Copy = initFileHandler({'initFileHandler',3;'hadesName2Date',1},result,'HADES');
    else
        message2log = ['Error while copying from local location: ' result];
        disp(message2log);
        write2log(logs,message2log,'Error','netlog',OS);
        
        message2log = ['Error while copying from local location: ' result];
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
        %Place Semaphore if possible
        [status, result] = setSemaphore(pathIn,logs,OS);
        if ~status
            %Just copy one file
            for i=1
                file     = hld2Copy(i).fullName;
                fileName = hld2Copy(i).fileName;
                
                %%%    Check if the folder exist
                mkdirOS(pathOut,OS,1);mkdirOS([pathOut 'done' b],OS,1);
                
                %%%Copy files
                [status, result] = system(['cp ' file ' ' pathOut]);
                
                message2log = ['Copying from local location: ' file];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);
                
                %%%Move to the local \ done folder
                if(zip == 1)
                    message2log = ['Compressing and moving to done on local location: ' file];
                    disp(message2log);
                    write2log(logs,message2log,'   ','syslog',OS);
                    mkdirOS([pathIn 'done' b],OS,0);
                    [status, result] = system(['tar -czvf ' pathIn 'done' b fileName '.gz.tar ' file]);
                    [status, result] = system(['rm ' file]);
                else
                    message2log = ['Moving to done on local location: ' file];
                    disp(message2log);
                    write2log(logs,message2log,'   ','syslog',OS);
                    mkdirOS([pathIn 'done' b],OS,0);
                    [status, result] = system(['mv ' file ' ' pathIn 'done' b]);
                end
            end
            [status, result] = remSemaphore(pathIn,logs,OS);
        else
            message2log = ['Semaphore in place or error during it generation skipping.'];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
        end
    end
catch%if error report the error
    
    message2log = ['Error while copying from local location: '];
    disp(message2log);
    write2log(logs,message2log,'Error','netlog',OS);
    
    message2log = ['Error while copying from local location: '];
    disp(message2log);
    write2log(logs,message2log,'Error','criticallog',OS);
end

return