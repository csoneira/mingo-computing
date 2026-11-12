% Purpose: Write detector-control values in the database import CSV format.

function [outputVars] = writeCSV4DB(inputVars)

%2023-11-17 Created versioning capable function
%
%
%
%
%
%

conf              = inputVars{1};
scriptVersions    = conf.Versioning;


if(findVersion(scriptVersions,'writeCSV4DB') == 0)
    [outputVars] = writeCSV4DB_0(inputVars);%no DB distribution
elseif(findVersion(scriptVersions,'distributeAnaVars') == 1)
    [outputVars] = writeCSV4DB_1(inputVars);%With DB distribution capability
else
end
return
