% Purpose: Open the configured database connection.

function connect2DB(inputVars)
%2024-01-04 - First implementation
%
%


conf            = inputVars{1};

logs            = conf.logs;
OS              = conf.OS;
systemName      = conf.SYSTEMNAME;
alarms          = conf.alarms;


    [status, result] = system('ps -ef | grep lipsql');
    if(strfind(result,'autossh -M 0 -o ServerAliveInterval 30 -o ServerAliveCountMax 3 -N    lipsql'))
        %autossh conenction alive, do nothing
    else
        %autossh conenction not present reconecting
        [status, result] = system('autossh -M 0 -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -N -f lipsql');
        
        message2log = ['Re-connecting DB'];
        disp(message2log);
        write2log(logs,message2log,'Error','netlog',OS);
        alarmType = 'netAccess';processAlarm(systemName,'DB',alarmType,message2log,alarms);
    end
return
