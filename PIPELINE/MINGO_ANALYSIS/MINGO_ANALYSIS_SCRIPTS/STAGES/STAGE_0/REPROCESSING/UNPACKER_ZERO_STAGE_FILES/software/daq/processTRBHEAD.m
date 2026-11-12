% Purpose: Process TRBHEAD for the legacy unpacker.

function [triggerType, filePosition,fileNames,EBtime] = processTRBHEAD(fileName,inputPath)

load([inputPath fileName]);
eventsFromTime = size(eventTime,1);
disp(['Loading ' fileName ' with ' num2str(eventsFromTime) ' events.']);

filePosition = (1:eventsFromTime)';
fileNames = repmat(fileName,eventsFromTime,1);
EBtime = EBtime2mat(eventDate,eventTime);

if(~exist('triggerType','var'))%In case triggerType does not exist create a dummy
    triggerType = eventTime*0;
end

return
