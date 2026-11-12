% Purpose: Convert HADES records to the standard timestamp and data format.

function  dateRegular = hadesData2Regular(fileName)

yyFromFile    = str2num(fileName(end-10:end-9));
ddFromFile    = str2num(fileName(end-8:end-6));
hourFromFile  = str2num(fileName(end-5:end-4));
mmFromFile    = str2num(fileName(end-3:end-2));
ssFromFile    = str2num(fileName(end-1:end));

[dayOfTheMonth,month] = HADESDate2Date(yyFromFile,ddFromFile);
dateRegular = datenum([str2num(['20' num2str(yyFromFile)]) month dayOfTheMonth  hourFromFile  mmFromFile ssFromFile]);    

end
