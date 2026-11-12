% Purpose: Write output data.

function write2log(logs,message2log,issue,logType,OS)

for i=1:size(logs,2)
    active    = logs(i).active;
    type      = logs(i).type;
    logPath   = logs(i).localPath;
    if(active && strcmp(logType,type))
        write2LogFile(message2log,issue,logPath);
    end
end
return
