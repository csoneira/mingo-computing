% Purpose: Format the Y axis in millimetres.

function yaxisMM(X)

MiN = min(X)*0.95;
MaX = max(X)*1.05;
if(MiN < MaX )
     yaxis(MiN*0.95,MaX*1.05);
end

return
