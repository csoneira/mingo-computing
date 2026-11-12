% Purpose: Extract the acquisition date from a HADES filename.

function  matDate = hadesName2Date(varargin)
%
% Convert the name of the HADES files into a matlab date
%
% 2024-02-27: Version 3: Assume that we do not have more than EB => just data
% 2020-05-05: Version 2: The data is stracted from the filename removing 4 first digits and not ussing isstrprop, to accomodate numbers on the prefix necessary for stratos 
%             Version 1: Init version
%

scriptVersions              = varargin{1};
fileName                    = varargin{2};
   


if (findVersion(scriptVersions,'hadesName2Date') == 1)
    
    hadesDate     = fileName(isstrprop(fileName,'digit'));
    
    yyFromFile    = str2num(hadesDate(1:2));
    ddFromFile    = str2num(hadesDate(3:5));
    hourFromFile  = str2num(hadesDate(6:7));
    mmFromFile    = str2num(hadesDate(8:9));
    ssFromFile    = str2num(hadesDate(10:11));
    
    [dayOfTheMonth,month] = HADESDate2Date(yyFromFile,ddFromFile);
    matDate = datenum([str2num(['20' num2str(yyFromFile)]) month dayOfTheMonth  hourFromFile  mmFromFile ssFromFile]);
elseif(findVersion(scriptVersions,'hadesName2Date') == 2)
    hadesDate     = fileName(5:end-4);
    
    yyFromFile    = str2num(hadesDate(1:2));
    ddFromFile    = str2num(hadesDate(3:5));
    hourFromFile  = str2num(hadesDate(6:7));
    mmFromFile    = str2num(hadesDate(8:9));
    ssFromFile    = str2num(hadesDate(10:11));
    
    [dayOfTheMonth,month] = HADESDate2Date(yyFromFile,ddFromFile);
    matDate = datenum([str2num(['20' num2str(yyFromFile)]) month dayOfTheMonth  hourFromFile  mmFromFile ssFromFile]);
elseif(findVersion(scriptVersions,'hadesName2Date') == 3)
    hadesDate     = fileName(end-14:end-4);
    
    yyFromFile    = str2num(hadesDate(1:2));
    ddFromFile    = str2num(hadesDate(3:5));
    hourFromFile  = str2num(hadesDate(6:7));
    mmFromFile    = str2num(hadesDate(8:9));
    ssFromFile    = str2num(hadesDate(10:11));
    
    [dayOfTheMonth,month] = HADESDate2Date(yyFromFile,ddFromFile);
    matDate = datenum([str2num(['20' num2str(yyFromFile)]) month dayOfTheMonth  hourFromFile  mmFromFile ssFromFile]);

else
    keyboard
end
