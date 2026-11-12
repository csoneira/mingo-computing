% Purpose: Set Semaphore for the legacy unpacker.

function [status, result] = setSemaphore(pathIn,logs,OS)
%
%
%Status = 1 means error 
%result is a coment about the problem



if(~exist([pathIn 'semaphore'],'dir'))%create the semaphore
    try
        [status, result] = system(['mkdir -p ' pathIn  'semaphore/']);
        if status == 1
            message2log = ['Error in the generation of the Semaphore skipping. '];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
        end
    catch
        message2log = ['Error in the generation of the Semaphore skipping. (Inside try)'];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
        status = 1;
        result = message2log;
    end
else
    message2log = ['Semaphore in place skipping.'];
    disp(message2log);
    write2log(logs,message2log,'   ','syslog',OS);
    status = 1;
    result = message2log;
end






return
