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
%
message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

%% Send the report
message2log = ['Try to send the daily report.'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

subject     = [SYSTEMNAME ' report'];
to          = conf.ana.report.address4Email;
message     = ['Here is the '  SYSTEMNAME ' report']; 
telNumber = locatedev(SYSTEMNAME,conf);
attachment  = {[conf.dev(telNumber).path.reporting   'report_' SYSTEMNAME '.pdf']};
[status, result] = sendbashEmail(subject,to,message,attachment);


message2log = result;
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
