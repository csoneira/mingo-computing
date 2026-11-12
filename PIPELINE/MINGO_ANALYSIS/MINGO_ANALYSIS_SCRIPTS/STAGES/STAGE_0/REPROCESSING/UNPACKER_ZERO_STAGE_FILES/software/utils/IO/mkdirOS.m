% Purpose: Create a directory using the configured operating-system command.

function mkdirOS(inputPath,OS,verbose)


if(~exist(inputPath,'dir'))
    if(verbose == 1)
        disp(['Creating folder ' inputPath]);
    end
    
    if(strcmp(OS,'windows'))
        system(['mkdir ' inputPath]);
    elseif(strcmp(OS,'linux'))
        system(['mkdir -p ' inputPath]);
    else
        disp('Operating system not defined. Stopping')
        pause;
    end
end

return
