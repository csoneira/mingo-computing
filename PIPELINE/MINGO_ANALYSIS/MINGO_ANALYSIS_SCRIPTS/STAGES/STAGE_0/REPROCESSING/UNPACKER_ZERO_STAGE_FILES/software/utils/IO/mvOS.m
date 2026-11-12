% Purpose: Move a file using the configured operating-system command.

function mvOS(inputPath,outputPath,file,OS)


if(strcmp(OS,'windows'))%windows
    system(['move ' inputPath file ' ' outputPath]);
elseif(strcmp(OS,'linux'))%linux
    system(['mv ' inputPath file ' ' outputPath ]);
else
    disp('Operating system not defined. Stopping')
    pause;
end
disp(['Moving file ' file ' from ' inputPath ' to ' outputPath]);

return
