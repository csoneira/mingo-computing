% Purpose: Configure software for the legacy Stage-0 unpacker.

%% Configuration
clear all;close all;

run('./conf/initConf.m');
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
run([HOME 'software/conf/loadGeneralConf.m']);


%% Load configuration
conf = initSystem();
conf = loadConfiguration({conf,HOSTNAME,SYSTEMNAME,HOME,SYS,INTERPRETER,OS});    
b = conf.bar;


%
message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
message2log = ['*** Starting calTDCPar.'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

inPath = conf.daq.unpacking.path.rawDataMat;
doCalTDCs(inPath,conf)
