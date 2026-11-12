% Purpose: Process Alarm for the legacy unpacker.

function processAlarm(systemName,device,alarmType,message2log,alarms)


for i=1:size(alarms,2)
    active      =    alarms(i).active;
    type        =    alarms(i).type;
    TO          =    alarms(i).TO;
    
    if active & strcmp(type,alarmType)
            [status, result] = sendbashEmail([systemName '   : ' device ],TO,message2log,'');
    end
end
