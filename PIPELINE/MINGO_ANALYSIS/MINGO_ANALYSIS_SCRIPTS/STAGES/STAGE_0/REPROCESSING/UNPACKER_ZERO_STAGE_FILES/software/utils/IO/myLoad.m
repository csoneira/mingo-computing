% Purpose: Define myload values for the legacy Stage-0 unpacker.

myLoadStatus = 'good';
try
    load([path_ file_]);
catch exception
    %Damaged file or unable to load it because do not exist
    if(strfind(exception.message,'Unable to read file') | strfind(exception.message,'unable to determine file format') | strfind(exception.message,'unable to find file'))
        myLoadStatus = 'noGood';
    else
        myLoadStatus = 'notDefined';
    end
end
