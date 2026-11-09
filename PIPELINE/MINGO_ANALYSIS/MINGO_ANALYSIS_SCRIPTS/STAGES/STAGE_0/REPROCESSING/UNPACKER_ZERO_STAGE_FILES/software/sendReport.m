% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/sendReport.m
% Purpose: Configuration.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

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
