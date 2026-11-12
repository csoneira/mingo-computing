% Purpose: Get Bar OS for the legacy unpacker.

function b = getBarOS(OS)


    if(strcmp(OS,'windows'))%windows
        b = '\';
    elseif(strcmp(OS,'linux'))%linux
        b = '/';
    else
        disp('Operating system not defined. Stopping')
        pause;
    end
        

return
