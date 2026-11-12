% Purpose: Extract the acquisition date from a log filename.

function  matDate = logsName2Date(varargin)
%
% Convert the name of the HADES files into a matlab date
%


scriptVersions       = varargin{1};
fileName             = varargin{2};



if (findVersion(scriptVersions,'logsName2Date') ==  1)

    date     = fileName(isstrprop(fileName,'digit'));
    
    yyFromFile    = str2num(date(1:4));
    MMFromFile    = str2num(date(5:6));
    ddFromFile    = str2num(date(7:8));
    hourFromFile  = 0;
    mmFromFile    = 0;
    ssFromFile    = 0;
    
    matDate = datenum([yyFromFile MMFromFile ddFromFile hourFromFile  mmFromFile ssFromFile]);
elseif (findVersion(scriptVersions,'initFileHandler') ==  2)
end

end
