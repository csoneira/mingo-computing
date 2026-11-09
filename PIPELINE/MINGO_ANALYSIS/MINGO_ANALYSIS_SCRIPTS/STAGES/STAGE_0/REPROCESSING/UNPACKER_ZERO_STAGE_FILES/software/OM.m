% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/OM.m
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
try
write2log(conf.logs,'','   ','syslog',OS);write2log(conf.logs,'','   ','syslog',OS);
message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
message2log = ['*** Starting om.'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
catch
end

%% Online Monitoring
message2log = ['*** Starting the online monitoring.'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
    
    for i=1:size(conf.dev,2)
        
        active   = conf.dev(i).dcs.active;
        readable = conf.dev(i).dcs.readable;
        armed    = conf.dev(i).dcs.armed;
        
         if active & readable & armed
            
            device      = [conf.dev(i).name conf.dev(i).subName]
            lookUpTable = [conf.dev(i).dcs.path.LT  conf.dev(i).dcs.distributionLT];
            logs        =  conf.logs;
            alarms     = conf.alarms;
            systemName  = conf.SYSTEM;
             
            checkAlarm(device,lookUpTable,logs,alarms,systemName,conf);
         end
    end
