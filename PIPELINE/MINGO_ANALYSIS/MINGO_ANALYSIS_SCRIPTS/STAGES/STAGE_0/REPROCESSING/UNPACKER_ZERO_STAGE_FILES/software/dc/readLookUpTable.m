% Purpose: Read Look Up Table.

function lookUpTable=readLookUpTable(file2Read)


%Read the lookUpTable
%L = readcell(file2Read);
L = csv2Cell(file2Read,'%');

%Check the number of active columns and loop On It
indx = strfind([L{1,:}],'1');

%Export lookUpTable
lookUpTable = L(:,indx);


return
