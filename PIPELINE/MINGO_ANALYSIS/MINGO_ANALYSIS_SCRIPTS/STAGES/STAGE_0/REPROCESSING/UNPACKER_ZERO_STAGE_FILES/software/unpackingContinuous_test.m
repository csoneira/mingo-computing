% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/unpackingContinuous_test.m
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

%% Check necessary files and paths
requiredFiles = {
    './conf/initConf.m', ...
    [HOME 'software/conf/loadGeneralConf.m']
};

missingFiles = {};
for i = 1:length(requiredFiles)
    if ~exist(requiredFiles{i}, 'file')
        missingFiles{end+1} = requiredFiles{i};
    end
end

if ~isempty(missingFiles)
    errorMessage = ['Missing required files or paths:\n' strjoin(missingFiles, '\n')];
    disp(errorMessage);
    write2log(conf.logs, errorMessage, '   ', 'syslog', OS);
    error('Script cannot proceed without the required files.');
else
    disp('All required files are present.');
    write2log(conf.logs, 'All required files are present.', '   ', 'syslog', OS);
end

disp(['Required files: ', strjoin(requiredFiles, ', ')]);
write2log(conf.logs, ['Required files: ', strjoin(requiredFiles, ', ')], '   ', 'syslog', OS);


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
    if  0 %% Copy files from daq

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
                    ip         = conf.daq(i).rAccess.IP;
                    user       = conf.daq(i).rAccess.user;
                    key        = conf.daq(i).rAccess.key;
                    daqPath = conf.daq(i).rAccess.remotePath;
                    localPath  = conf.daq(i).unpacking.path.rawDataDat;
                    fileExt    = conf.daq(i).rAccess.fileExt;
                    port       = conf.daq(i).rAccess.port;
                    logs       = conf.logs;
                    scpLastDoneAndMove(ip,user,key,daqPath,localPath,port,fileExt,logs,OS);
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

    if 1 %% Unpack files
        message2log = ['*** Starting the unpacking of daq files.'];
        disp(message2log);
        write2log(conf.logs,message2log,'   ','syslog',OS);

        for i=1:size(conf.daq,2)
            %Convert to mat files
            active   = conf.daq(i).active;
            readable = conf.daq(i).readable;
            %if active, readable
            if active & readable
                %Go to read
                inPath        =  conf.daq(i).unpacking.path.rawDataDat;
                outPath       =  conf.daq(i).unpacking.path.rawDataMat;
                fileType      =  conf.daq(i).unpacking.fileExt;
                TRB           =  conf.daq(i).TRB3;
                bufferSize    =  conf.daq(i).unpacking.bufferSize;
                
                writeTDCCal   = conf.daq(i).unpacking.writeTDCCal;
                keepHLDs      =  conf.daq(i).unpacking.keepHLDs;
                
                zipFiles      =  conf.daq(i).unpacking.zipFiles;
                downScale     =  conf.daq(i).unpacking.downScale;

                if conf.daq(i).active
                    tmpRaw2varPath = unpackerTRB3LunchContinuous({conf,inPath,outPath,fileType,TRB,bufferSize,writeTDCCal,keepHLDs,zipFiles,downScale});
                elseif 0
                    keyboard
                else
                    keyboard
                end
            end
        end
    end


    if ~strcmp(tmpRaw2varPath,'none') %% raw 2 var
        message2log = ['*** Starting the convertion from raw 2 var.'];
        disp(message2log);
        write2log(conf.logs,message2log,'   ','syslog',OS);

        for i=1:size(conf.daq,2)
            %Convert to mat files
            active   = conf.daq(i).active;
            readable = conf.daq(i).readable;
            %if active, readable
            if active & readable
                %Go to read
                inPath        =  [conf.daq(i).unpacking.path.rawDataMat tmpRaw2varPath b];
                outPath       =  [conf.daq(i).raw2var.path.varData tmpRaw2varPath b];mkdirOS(outPath,OS,0);
                for j=1:size(conf.daq(i).raw2var.lookUpTables,2)
                    lookUpTables{j}  =  [conf.daq(i).raw2var.path.lookUpTables conf.daq(i).raw2var.lookUpTables{j}];
                end
                keepRawFiles  =  conf.daq(i).raw2var.keepRawFiles;
                logs          =  conf.logs;

                if conf.daq(i).active
                    TRBs = conf.daq(i).TRB3;
                    raw2varContinuous(inPath,outPath,TRBs,lookUpTables,keepRawFiles,INTERPRETER,logs,OS);
                    if exist([inPath 'TDCCal/'],'dir')
                        mkdirOS([inPath '../TDCCal/'],OS,0);
                        mvOS([inPath 'TDCCal/'],[inPath '../TDCCal/'],'*.*',OS)
                    end
                    [~, ~] = system(['rm -r ' inPath]);
                elseif 0
                    keyboard
                else
                    keyboard
                end
            end
        end
    end


    if ~strcmp(tmpRaw2varPath,'none')
        for i=1:size(conf.daq,2)
            %%% Export if necessary to Asci
            if(conf.daq(i).var2cal.exportAsci == 1)
                message2log = ['Exporting data to asci.'];
                disp(message2log);write2log(conf.logs,message2log,'   ','syslog',OS);

                inPath           = [conf.daq(i).raw2var.path.varData tmpRaw2varPath b];
                outPath          =  conf.daq(i).var2cal.exportAsciPath;
                zipOutput        = conf.daq(i).var2cal.zipAsci;
                lookUpTablesPath = conf.daq(i).var2cal.path.lookUpTables;
                systemName       = conf.SYSTEM;

                exportASCIData({inPath,outPath,zipOutput,lookUpTablesPath,systemName});
            end

            %%% Just move the data to var folder folder
            inPath      =  outPath;
            mvOS([conf.daq(i).raw2var.path.varData tmpRaw2varPath b],[conf.daq(i).raw2var.path.varData tmpRaw2varPath b '../'],'*.*',OS);

            [~, ~] = system(['rm -r ' conf.daq(i).raw2var.path.varData tmpRaw2varPath]);
            message2log = ['***************************************************************'];
            disp(message2log);write2log(conf.logs,message2log,'   ','syslog',OS);
        end
    end

    if strfind(RPCRUNMODE,'oneRun')
        disp('System configured to run one. Exiting.')
        break
    end
    disp('Waiting 30 seconds for new files');
    pause(30);

end

message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

