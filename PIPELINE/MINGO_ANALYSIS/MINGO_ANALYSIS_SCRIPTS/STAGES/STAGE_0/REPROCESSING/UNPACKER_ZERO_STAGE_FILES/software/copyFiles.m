% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/copyFiles.m
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
[status, RPCRUNMODE] = system('echo $RPCRUNMODE');

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
message2log = ['*** Starting unpacking'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

while 1
    if  1 %% Copy files from daq

        message2log = ['*** Starting the copy of daq files.'];
        disp(message2log);
        write2log(conf.logs,message2log,'   ','syslog',OS);

        for i=1:size(conf.daq,2)
            %Read device is it is active and readable
            active   = conf.daq(i).active;
            readable = conf.daq(i).readable;

            %if active, readable
            if active & readable
                %Go to read
                remoteAccessActive = conf.daq(i).rAccess.active;
                localAccessActive  = conf.daq(i).lAccess.active;
                if remoteAccessActive
                    systemName = conf.SYSTEM;
                    hostName   = conf.HOSTNAME;
                    ip         = conf.daq(i).rAccess.IP{hostName};
                    user       = conf.daq(i).rAccess.user{hostName};
                    key        = conf.daq(i).rAccess.key{hostName};
                    daqPath    = conf.daq(i).rAccess.remotePath;
                    localPath  = conf.daq(i).unpacking.path.rawDataDat;
                    port       = conf.daq(i).rAccess.port{hostName};
                    fileExt    = conf.daq(i).rAccess.fileExt;
                    keepHLDs   = conf.daq(i).rAccess.keepHLDs;
                    zipFiles   = conf.daq(i).rAccess.zipFiles;
                    downScale  = conf.daq(i).rAccess.downScale;
                    scpLastDoneAndMove({conf,ip,user,key,daqPath,localPath,port,fileExt,keepHLDs,zipFiles,downScale});
                elseif localAccessActive
                    daqPath       = conf.daq(i).lAccess.path;
                    localPath  = conf.daq(i).unpacking.path.rawDataDat;
                    fileExt    = conf.daq(i).lAccess.fileExt;
                    zip        = conf.daq(i).lAccess.zip;
                    logs       = conf.logs;
                    cpLastCloseAndMove(daqPath,localPath,fileExt,zip,logs,OS);
                else
                    disp('not implemented for the moment');
                end
            end
        end
    end

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



