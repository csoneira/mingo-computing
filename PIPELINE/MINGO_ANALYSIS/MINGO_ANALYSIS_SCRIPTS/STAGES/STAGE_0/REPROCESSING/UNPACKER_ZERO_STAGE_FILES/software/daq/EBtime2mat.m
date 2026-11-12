% Purpose: Convert event-builder timing records into MATLAB arrays.

function EBtime = EBtime2mat(eventDate,eventTime)
%Process Event Builder time and date extracted from hld file


DD = double(bitand(eventDate,uint32(hex2dec('000000ff'))));
MM = double(bitand(bitshift(eventDate,-8),uint32(hex2dec('000000ff')))) + 1;
YY = num2str(bitshift(eventDate,-16));YY = double(str2num([repmat('20',size(YY,1),1) YY(:,2:3)]));


ss = double(bitand(eventTime,uint32(hex2dec('000000ff'))));
mm = double(bitand(bitshift(eventTime,-8),uint32(hex2dec('000000ff'))));
hh = double(bitand(bitshift(eventTime,-16),uint32(hex2dec('000000ff'))));


EBtime = datenum(YY,MM,DD,hh,mm,ss);
return
