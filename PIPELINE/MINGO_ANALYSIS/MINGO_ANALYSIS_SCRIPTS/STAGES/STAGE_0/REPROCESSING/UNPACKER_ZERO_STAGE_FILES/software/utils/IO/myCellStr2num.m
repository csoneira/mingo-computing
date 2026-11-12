% Purpose: My Cell Str2num for the legacy unpacker.

function N = myCellStr2num(cellStr)


N = zeros(length(cellStr),1);
for i=1:length(cellStr)
    if (isnumeric(cellStr{i}))
        N(i) =  cellStr{i};
    else
        N(i) =  str2num(cellStr{i});
    end
end



return
