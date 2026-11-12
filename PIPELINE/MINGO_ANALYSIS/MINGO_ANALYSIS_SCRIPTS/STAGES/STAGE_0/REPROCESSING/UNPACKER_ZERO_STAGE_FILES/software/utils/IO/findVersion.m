% Purpose: Find Version for the legacy unpacker.

function version = findVersion(scriptVersion,fun2Find)


s = strfind(scriptVersion(:,1),fun2Find);
%Position on the array of teh candidate
p = find(not(cellfun('isempty',s)));




if(isempty(p))
    disp(['No version found for ' fun2Find ' selecting by defult version 1']);
    version = 1;
else
    
    if(strcmp(scriptVersion{p,1},fun2Find))
        %Name exactly match the string
        version = scriptVersion{p,2};
    else
        disp('Name of the function does not have an exact match check');
        keyboard
    end
end
return
