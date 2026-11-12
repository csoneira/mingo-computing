% Purpose: Define keepremotetunnelopen values for the legacy Stage-0 unpacker.

[status, result] = system('ps -ef | grep lipana');
if(strfind(result,'autossh -M 0 -o ServerAliveInterval 30 -o ServerAliveCountMax 3 -N    lipana'))
    %autossh conenction alive, do nothing
 else
    %autossh conenction not present reconecting
    [status, result] = system('autossh -M 0 -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -N -f lipana');
 end
