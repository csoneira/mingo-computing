% Purpose: Release the unpacker semaphore lock.

function [status, result] = remSemaphore(pathIn,logs,OS)
%
%
%Status = 1 means error 
%result is a coment about the problem



if(exist([pathIn 'semaphore'],'dir'))%create the semaphore
    try
        [status, result] = system(['rmdir ' pathIn  'semaphore/']);
        if status == 1
            message2log = ['Error when removing the Semaphore skipping.'];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
            keyboard
        end
    catch
        message2log = ['Error when removing the Semaphore skipping.'];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
        status = 1;
        result = message2log;
        keyboard
    end
else
    message2log = ['No semaphore when It is supossed to be.'];
    disp(message2log);
    write2log(logs,message2log,'   ','syslog',OS);
    status = 1;
    result = message2log;
    keyboard
end






return
