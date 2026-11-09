% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dcs.m
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
write2log(conf.logs,'','   ','syslog',OS);write2log(conf.logs,'','   ','syslog',OS);
message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
message2log = ['*** Starting dcs.'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

while 1
    %% Copy files from SC devices
    if 1
        message2log = ['*** Starting the readout of dcs files.'];
        disp(message2log);
        write2log(conf.logs,message2log,'   ','syslog',OS);

        for i=1:size(conf.dev,2)
            %Read device is it is active and readable
            active   = conf.dev(i).dcs.active;
            readable = conf.dev(i).dcs.readable;

            if active & readable
                %Go to read
                remoteAccessActive = conf.dev(i).dcs.rAccess.active;
                localAccessActive  = conf.dev(i).dcs.lAccess.active;
                if remoteAccessActive
                    systemName = conf.SYSTEM;
                    hostName   = conf.HOSTNAME;
                    device     = [conf.dev(i).name conf.dev(i).subName];
                    ip         = conf.dev(i).dcs.rAccess.IP  {hostName};
                    user       = conf.dev(i).dcs.rAccess.user{hostName};
                    key        = conf.dev(i).dcs.rAccess.key {hostName};
                    port       = conf.dev(i).dcs.rAccess.port{hostName};
                    remotePath = conf.dev(i).dcs.rAccess.remotePath;
                    fileExt    = conf.dev(i).dcs.rAccess.fileExt;
                    localPath  = conf.dev(i).dcs.path.rawDataDat;
                    logs       = conf.logs;
                    alarms     = conf.alarms;

                    scpLastAndMove(systemName,device,ip,user,key,remotePath,localPath,port,fileExt,logs,alarms,OS);
                elseif localAccessActive
                    %                 path       = conf.dev(i).dcs.lAccess.path;
                    %                 localPath  = conf.dev(i).dcs.path.rawDataDat;
                    %                 fileExt    = conf.dev(i).dcs.lAccess.fileExt;
                    %                 logs       = conf.logs;
                    %                 %Need to implement last improvements as scpLastAndMove
                    %                 cpLastAndMove(path,localPath,fileExt,logs,OS);
                else
                    disp('not implemented for the moment');
                end
            end
        end
    end

    %% Convert to mat
    if 1
        message2log = ['*** Starting the conversion of dcs files.'];
        disp(message2log);
        write2log(conf.logs,message2log,'   ','syslog',OS);

        for i=1:size(conf.dev,2)
            %Convert to mat files
            active   = conf.dev(i).dcs.active;
            readable = conf.dev(i).dcs.readable;

            %if active, readable
            if active & readable
                %Go to read
                systemName  = conf.SYSTEM;
                interpreter =  conf.INTERPRETER;
                versions    = {'dcDat2Mat',1;'procGenericLog',1};
                inPath      =  conf.dev(i).dcs.path.rawDataDat;
                outPath     =  conf.dev(i).dcs.path.rawDataMat;
                fileType    =  conf.dev(i).dcs.rAccess.fileExt;
                scriptInfo  =  {conf.dev(i).dcs.dcData2MatScript conf.dev(i).dcs.type conf.dev(i).dcs.columns conf.dev(i).dcs.nameFormat};
                dev2Read    = [conf.dev(i).name conf.dev(i).subName];
                logs        =  conf.logs;
                alarms      =  conf.alarms;

                dcDat2Mat({versions,inPath,outPath,fileType,scriptInfo,systemName,logs,alarms,dev2Read,interpreter,OS});
            end
        end
    end

    %% Distribute vars
    if 1
        message2log = ['*** Starting the distribution of dcs files.'];
        disp(message2log);
        write2log(conf.logs,message2log,'   ','syslog',OS);

        for i=1:size(conf.dev,2)
            %Convert to mat files
            active   = conf.dev(i).dcs.active;
            readable = conf.dev(i).dcs.readable;

            %if active, readable
            if active & readable
                %Go to read
                systemName  = conf.SYSTEM;
                device      = [conf.dev(i).name conf.dev(i).subName];
                inPath      = conf.dev(i).dcs.path.rawDataMat;
                lookUpTable = [conf.dev(i).dcs.path.LT  conf.dev(i).dcs.distributionLT];
                alarms      = conf.alarms;
                logs        = conf.logs;

                distributeVars({systemName,device,inPath,lookUpTable,conf,logs,INTERPRETER,alarms,OS});
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
    disp('Waiting 300 seconds for new files');
    pause(300);


end