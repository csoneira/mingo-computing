% Purpose: Find alarm conditions in detector-control measurements.

function alarmPosition = locateAlarm(alarmToLocate,alarms)


for i = 1:length(alarms)
    if strcmp(alarmToLocate,[alarms(i).type])
        alarmPosition = i;
        return
    end
end
return
