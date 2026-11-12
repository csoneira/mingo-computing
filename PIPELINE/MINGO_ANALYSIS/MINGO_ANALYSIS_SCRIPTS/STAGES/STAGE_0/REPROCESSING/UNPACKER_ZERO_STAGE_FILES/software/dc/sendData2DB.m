% Purpose: Upload detector-control measurements to the configured database.

function sendData2DB(inputVars)

%2023-11-17 Created versioning capable function
%
%
%
%
%
%

conf              = inputVars{1};
scriptVersions    = conf.Versioning;


if(findVersion(scriptVersions,'sendData2DB') == 0)
    [outputVars] = sendData2DB_0(inputVars);%no DB distribution
elseif(findVersion(scriptVersions,'distributeAnaVars') == 1)
    
else
end
return
