% Purpose: Select Files By Time.

function listedFiles = selectFilesByTime(listedFiles,time2Merge)

if time2Merge > 0
    timeFromNames = [];
    for i=1:length(listedFiles)
        timeFromNames(i) = datenum(listedFiles(i).name(1:10));
    end
    
    
    
    I = find(timeFromNames > time2Merge(1));
    
    listedFiles = listedFiles(I);
end
end
