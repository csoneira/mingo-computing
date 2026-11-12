% Purpose: Define tmp values for the legacy Stage-0 unpacker.

for i=1:32
    
   evt = 1:100;ch=1+i;full([(evt)' leadingEpochCounter(evt,ch) leadingCoarseTime(evt,ch)  trailingCoarseTime(evt,ch) (trailingCoarseTime(evt,ch)-leadingCoarseTime(evt,ch))*5])
    i  
    pause
end
