% Purpose: Run the legacy Stage-0 event-analysis workflow.

%% Configuration
clear all;close all;

run('./conf/initConf.m');
[status, RPCRUNMODE] = system('echo $RPCRUNMODE');

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
run([HOME 'software/conf/loadGeneralConf.m']);


%% Load configuration
conf = initSystem();
conf = loadConfiguration({conf,HOSTNAME,SYSTEMNAME,HOME,SYS,INTERPRETER,OS});

b = conf.bar;

write2log(conf.logs,'','   ','syslog',OS);write2log(conf.logs,'','   ','syslog',OS);
message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
message2log = ['*** Starting Analysis.'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

while 1
    %% Go 2 ANA
    message2log = ['*** Prepare ana.'];
    disp(message2log);
    write2log(conf.logs,message2log,'   ','syslog',OS);

    inPath      =  conf.daq(1).raw2var.path.varData;
    outPath     =  conf.dev(locatedev(conf.SYSTEM,conf)).ana.path.base;

    prepareAna(inPath,outPath,conf);

    message2log = ['***************************************************************'];
    disp(message2log);
    write2log(conf.logs,message2log,'   ','syslog',OS);


    if strfind(RPCRUNMODE,'oneRun')
        disp('System configured to run one. Exiting.')
        break
    end
    disp('Waiting 30 seconds for new files');
    pause(30);

end
