% Purpose: Parse the output of the legacy directory-listing command.

function lsList = procLsOut(lsOutput)

%%% This function should be used with the output of something like 
%%% ls -1
%%% The output of the function give a cell with all file

%%% Check if there are no files
if(strfind(lsOutput,'ls: cannot access') == 1)
    lsList = [];
    return
end

index = find(isstrprop(lsOutput, 'wspace'));

lsList = cell(size(index,2),1);

index = [0, index];

for i=1:(length(index)-1)
    lsList{i} = lsOutput(index(i)+1:index(i+1)-1);
end

return
