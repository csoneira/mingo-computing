% Purpose: Process TRBADC 2 for the legacy unpacker.

function Q = processTRBADC_2(fileName,inputPath)



load([inputPath fileName]);
eventsFromTime = size(data,3);
disp(['Loading ' fileName ' with ' num2str(eventsFromTime) ' events.']);


%downSampling  blockSize    Xincr    polarity                      samples4BaseLine  samples4Maximum
%infoADC = {         10,        8,   25e-9,   [ones(48,1)],                 1:3,              7:10};
% infoADC = {         10,        8,   25e-9,   [ones(1,48)],            1:(floor(size(data,1)*(1/3))+1), size(data,1)-(floor(size(data,1)*(1/3))+1):size(data,1)}; plotIt = 0;
%     
%          [Baseline, Q, Qlast, TQ, Pileup1] ...
%              = MM(data,infoADC,plotIt);
Q = data;
return
