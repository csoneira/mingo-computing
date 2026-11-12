% Purpose: Route analysis variables to their output structures.

function [outputVars] = distributeAnaVars(inputVars)

%2023-11-17 Created versioning capable function
%
%
%
%
%
%

conf              = inputVars{5};
scriptVersions    = conf.Versioning;


if(findVersion(scriptVersions,'distributeAnaVars') == 0)
    [outputVars] = distributeAnaVars_0(inputVars);%no DB distribution
elseif(findVersion(scriptVersions,'distributeAnaVars') == 1)
    [outputVars] = distributeAnaVars_1(inputVars);%With DB distribution capability
else
end

return
