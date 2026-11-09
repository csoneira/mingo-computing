% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/conf/loadConfiguration.m
% Purpose: loadConfiguration function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function configuration = loadConfiguration(inputVars)

configuration       = inputVars{1};
HOSTNAME            = inputVars{2};
SYSTEMNAME          = inputVars{3};
HOME                = inputVars{4};
SYS                 = inputVars{5};
INTERPRETER         = inputVars{6};
OS                  = inputVars{7};

%%
time2Show   = 7*24;
oneHour     = datenum([0000 00 00 01 00 00]) - datenum([0000 00 00 00 00 00]);
time1       = datenum([2023 10 01 00 00 00]);time2       = datenum([2023 01 08 12 00 00]);
%time2Show = [time1 now];
time2Show = [(now - oneHour*time2Show) now];

%hours
downScaling = 1;
%% General information
configuration.SYSTEMNAME                             = SYSTEMNAME;
configuration.HOSTNAME                               = HOSTNAME;
configuration.SYSTEM                                 = SYSTEMNAME;
configuration.HOME                                   = HOME;
configuration.SYS                                    = SYS; 
configuration.OS                                     = OS;
configuration.INTERPRETER                            = INTERPRETER;
configuration.bar                                    = getBarOS(OS);b = getBarOS(OS);

%% Some general work with the paths
mkdirOS(SYS,OS,1);
mkdirOS([SYS 'devices' b],OS,1);
mkdirOS([SYS 'logs' b],OS,1);

devicePos = 1;
%%% Devices
%% HV PS      01    Device 01
dev = initDevice();

    dev.active                              =    1;
    dev.name                                = 'HV';
    dev.subName                             = '01';
    dev.type                                =   '';
    dev.subType                             =   '';
        dev.reportable.active               =    0;
        
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
            
        dev.dcs.active                      =   1;
        dev.dcs.readable                    =   1;
        dev.dcs.armed                       =   1;
         
        dev.dcs.rAccess.active              =   1;

        dev.dcs.rAccess.IP{1}               = SYSTEMNAME;
        dev.dcs.rAccess.user{1}             = 'rpcuser';
        dev.dcs.rAccess.key{1}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{1}             = '22';
        
        dev.dcs.rAccess.IP{2}               = SYSTEMNAME;
        dev.dcs.rAccess.user{2}             = 'rpcuser';
        dev.dcs.rAccess.key{2}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{2}             = '5801';
        
        dev.dcs.rAccess.fileExt             = 'hv0*.log';
        dev.dcs.rAccess.remotePath          = '/home/rpcuser/logs/';
        
        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';
        
        dev.dcs.dcData2MatScript            = 'procMINGOHV';
        dev.dcs.type                        = '';
        dev.dcs.columns                     = 17;
        dev.dcs.nameFormat                  = []; 
        
        dev.dcs.distributionLT              = 'lookUpTableHV.m';
        
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = '';                                                   %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev = dev;
devicePos = devicePos +1;

%% Sensors    01    Device 02
dev = initDevice();

    dev.active                              =    1;
    dev.name                                = 'SENSORS';
    dev.subName                             = '01';
    dev.type                                =   '';
    dev.subType                             =   '';
        dev.reportable.active               =    0;
        
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
            
        dev.dcs.active                      =   1;
        dev.dcs.readable                    =   1;
        dev.dcs.armed                       =   0;
        
        dev.dcs.rAccess.active              =   1;

        dev.dcs.rAccess.IP{1}               = SYSTEMNAME;
        dev.dcs.rAccess.user{1}             = 'rpcuser';
        dev.dcs.rAccess.key{1}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{1}             = '22';
        
        dev.dcs.rAccess.IP{2}               = SYSTEMNAME;
        dev.dcs.rAccess.user{2}             = 'rpcuser';
        dev.dcs.rAccess.key{2}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{2}             = '5801';

        dev.dcs.rAccess.fileExt             = 'sensors_bus0_*.log';
        dev.dcs.rAccess.remotePath          = '/home/rpcuser/logs/';
        
        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';
        
        dev.dcs.dcData2MatScript            = 'procGenericLog';
        dev.dcs.type                        = 'I2C';
        dev.dcs.columns                     = 7;
        dev.dcs.nameFormat                  = '*************2023-04-21****';  
        
        dev.dcs.distributionLT              = 'lookUpTableSensor0.m';
        
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = '';                                                   %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;

%% Sensors    02    Device 03
dev = initDevice();

    dev.active                              =    1;
    dev.name                                = 'SENSORS';
    dev.subName                             = '02';
    dev.type                                =   '';
    dev.subType                             =   '';
        dev.reportable.active               =    0;
        
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
            
        dev.dcs.active                      =   1;
        dev.dcs.readable                    =   1;
        dev.dcs.armed                       =   1;

        dev.dcs.rAccess.active              =   1;
         
        dev.dcs.rAccess.IP{1}               = SYSTEMNAME;
        dev.dcs.rAccess.user{1}             = 'rpcuser';
        dev.dcs.rAccess.key{1}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{1}             = '22';
        
        dev.dcs.rAccess.IP{2}               = SYSTEMNAME;
        dev.dcs.rAccess.user{2}             = 'rpcuser';
        dev.dcs.rAccess.key{2}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{2}             = '5801';

        dev.dcs.rAccess.fileExt             = 'sensors_bus1_*.log';
        dev.dcs.rAccess.remotePath          = '/home/rpcuser/logs/';
        
        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';
        
        dev.dcs.dcData2MatScript            = 'procGenericLog';
        dev.dcs.type                        = 'I2C';
        dev.dcs.columns                     = 7;
        dev.dcs.nameFormat                  = '*************2023-04-21****'; 
        
        dev.dcs.distributionLT              = 'lookUpTableSensor1.m';
        
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = '';                                                   %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;

%% FlowMeter  01    Device 03
dev = initDevice();

    dev.active                              =    1;
    dev.name                                = 'FLOW';
    dev.subName                             = '01';
    dev.type                                =   '';
    dev.subType                             =   '';
        dev.reportable.active               =    0;
        
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
            
        dev.dcs.active                      =   1;
        dev.dcs.readable                    =   1;
        dev.dcs.armed                       =   1;

        dev.dcs.rAccess.active              =   1;
         
        dev.dcs.rAccess.IP{1}               = SYSTEMNAME;
        dev.dcs.rAccess.user{1}             = 'rpcuser';
        dev.dcs.rAccess.key{1}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{1}             = '22';
        
        dev.dcs.rAccess.IP{2}               = SYSTEMNAME;
        dev.dcs.rAccess.user{2}             = 'rpcuser';
        dev.dcs.rAccess.key{2}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{2}             = '5801';

        dev.dcs.rAccess.fileExt             = 'Flow0_*.log';
        dev.dcs.rAccess.remotePath          = '/home/rpcuser/logs/';
        
        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';
        
        dev.dcs.dcData2MatScript            = 'procGenericLog';
        dev.dcs.type                        = 'I2C_5';
        dev.dcs.columns                     = 4;
        dev.dcs.nameFormat                  = '******2023-04-21****';                  
        
        dev.dcs.distributionLT              = 'lookUpTableFlow.m';
        
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = '';                                                   %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;


%% RPC        01   
dev = initDevice();

    dev.active                              =    1;
    dev.name                                = 'RPC';
    dev.subName                             = '01';
    dev.type                                =   '';
    dev.subType                             =   '';
        dev.reportable.active               =    1;
        dev.reportable.LT                   = 'LookUpRPC01Report.csv';
        dev.reportable.timeElapsed          = time2Show;
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];            mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
        dev.path.reporting                  = [dev.path.base 'reporting' b];                         mkdirOS(dev.path.reporting,OS,1);
            
        dev.dcs.active                      =   0;
        dev.dcs.readable                    =   0;
        dev.dcs.armed                       =   0;
         
        dev.dcs.rAccess.active              =   0;
        dev.dcs.rAccess.IP                  = '';
        dev.dcs.rAccess.user                = '';
        dev.dcs.rAccess.key                 = '';
        dev.dcs.rAccess.port                = '';
        dev.dcs.rAccess.fileExt             = '';
        dev.dcs.rAccess.remotePath          = '';
        
        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';
        
        dev.dcs.dcData2MatScript            = '';
        dev.dcs.type                        = '';
        dev.dcs.columns                     = 0;
        dev.dcs.nameFormat                  = []; 
        
        dev.dcs.distributionLT              = '';
        
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = [dev.dcs.path.base 'data' b];                         mkdirOS(dev.dcs.path.data,OS,1);mkdirOS([dev.dcs.path.data 'merge' b],OS,1);                                                   %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;

%% RPC        02   
dev = initDevice();

    dev.active                              =    1;
    dev.name                                = 'RPC';
    dev.subName                             = '02';
    dev.type                                =   '';
    dev.subType                             =   '';
        dev.reportable.active               =    1;
        dev.reportable.LT                   = 'LookUpRPC02Report.csv';
        dev.reportable.timeElapsed          = time2Show;
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];            mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
        dev.path.reporting                  = [dev.path.base 'reporting' b];                         mkdirOS(dev.path.reporting,OS,1);
            
        dev.dcs.active                      =   0;
        dev.dcs.readable                    =   0;
        dev.dcs.armed                       =   0;
         
        dev.dcs.rAccess.active              =   0;
        dev.dcs.rAccess.IP                  = '';
        dev.dcs.rAccess.user                = '';
        dev.dcs.rAccess.key                 = '';
        dev.dcs.rAccess.port                = '';
        dev.dcs.rAccess.fileExt             = '';
        dev.dcs.rAccess.remotePath          = '';
        
        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';
        
        dev.dcs.dcData2MatScript            = '';
        dev.dcs.type                        = '';
        dev.dcs.columns                     = 0;
        dev.dcs.nameFormat                  = []; 
        
        dev.dcs.distributionLT              = '';
        
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = [dev.dcs.path.base 'data' b];                         mkdirOS(dev.dcs.path.data,OS,1);mkdirOS([dev.dcs.path.data 'merge' b],OS,1);                                                  %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;

%% RPC        03   
dev = initDevice();

    dev.active                              =    1;
    dev.name                                = 'RPC';
    dev.subName                             = '03';
    dev.type                                =   '';
    dev.subType                             =   '';
        dev.reportable.active               =    1;
        dev.reportable.LT                   = 'LookUpRPC03Report.csv';
        dev.reportable.timeElapsed          = time2Show;
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];            mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
        dev.path.reporting                  = [dev.path.base 'reporting' b];                         mkdirOS(dev.path.reporting,OS,1);
            
        dev.dcs.active                      =   0;
        dev.dcs.readable                    =   0;
        dev.dcs.armed                       =   0;
         
        dev.dcs.rAccess.active              =   0;
        dev.dcs.rAccess.IP                  = '';
        dev.dcs.rAccess.user                = '';
        dev.dcs.rAccess.key                 = '';
        dev.dcs.rAccess.port                = '';
        dev.dcs.rAccess.fileExt             = '';
        dev.dcs.rAccess.remotePath          = '';
        
        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';
        
        dev.dcs.dcData2MatScript            = '';
        dev.dcs.type                        = '';
        dev.dcs.columns                     = 0;
        dev.dcs.nameFormat                  = []; 
        
        dev.dcs.distributionLT              = '';
        
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = [dev.dcs.path.base 'data' b];                         mkdirOS(dev.dcs.path.data,OS,1);mkdirOS([dev.dcs.path.data 'merge' b],OS,1);                                                   %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;

%% RPC        04   
dev = initDevice();

    dev.active                              =    1;
    dev.name                                = 'RPC';
    dev.subName                             = '04';
    dev.type                                =   '';
    dev.subType                             =   '';
        dev.reportable.active               =    1;
        dev.reportable.LT                   = 'LookUpRPC04Report.csv';
        dev.reportable.timeElapsed          = time2Show;
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];            mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
        dev.path.reporting                  = [dev.path.base 'reporting' b];                         mkdirOS(dev.path.reporting,OS,1);
            
        dev.dcs.active                      =   0;
        dev.dcs.readable                    =   0;
        dev.dcs.armed                       =   0;
         
        dev.dcs.rAccess.active              =   0;
        dev.dcs.rAccess.IP                  = '';
        dev.dcs.rAccess.user                = '';
        dev.dcs.rAccess.key                 = '';
        dev.dcs.rAccess.port                = '';
        dev.dcs.rAccess.fileExt             = '';
        dev.dcs.rAccess.remotePath          = '';
        
        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';
        
        dev.dcs.dcData2MatScript            = '';
        dev.dcs.type                        = '';
        dev.dcs.columns                     = 0;
        
        
        dev.dcs.distributionLT              = '';
        
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = [dev.dcs.path.base 'data' b];                         mkdirOS(dev.dcs.path.data,OS,1);mkdirOS([dev.dcs.path.data 'merge' b],OS,1);                                                   %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;

%% TRBsc  
dev = initDevice();

    dev.active                              = 1;
    dev.name                                = 'TRB';
    dev.subName                             = '';
    dev.type                                = 'all';
    dev.subType                             = '';
        dev.reportable.active               = 0;
        dev.reportable.LT                   = '';
        dev.reportable.timeElapsed          = time2Show;
        %dev.reportable.downScaling          = downScaling;
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];            mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
        dev.path.reporting                  = [dev.path.base 'reporting' b];                         mkdirOS(dev.path.reporting,OS,1);
            
        dev.dcs.active                      = 1;
        dev.dcs.readable                    = 1;
        dev.dcs.armed                       = 1;
        
        dev.dcs.rAccess.active              = 1;
        dev.dcs.rAccess.IP{1}               = SYSTEMNAME;
        dev.dcs.rAccess.user{1}             = 'rpcuser';
        dev.dcs.rAccess.key{1}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{1}             = '22';
        
        dev.dcs.rAccess.IP{2}               = SYSTEMNAME;
        dev.dcs.rAccess.user{2}             = 'rpcuser';
        dev.dcs.rAccess.key{2}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{2}             = '5801';
        
        dev.dcs.rAccess.fileExt             = 'rates*.*';
        dev.dcs.rAccess.remotePath          = '/home/rpcuser/logs/';

        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';

        
        dev.dcs.dcData2MatScript            = 'procGenericLog';
        dev.dcs.type                        = 'I2C';
        dev.dcs.columns                     = 11;
        dev.dcs.nameFormat                  = '******2023-05-26'; 
        
        dev.dcs.distributionLT              = 'lookUpTableTRB.m';

        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = '';                                                   %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;


%% Telescope 
 dev = initDevice();

    dev.active                              = 1;
    dev.name                                = 'mingo';
    dev.subName                             = '01';
    dev.type                                = 'all';
    dev.subType                             = '';
        dev.reportable.active               = 1;
        dev.reportable.LT                   = 'lookUpMINGOReport.csv';
        dev.reportable.timeElapsed          = time2Show;
        %dev.reportable.downScaling          = downScaling;
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];            mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
        dev.path.reporting                  = [dev.path.base 'reporting' b];                         mkdirOS(dev.path.reporting,OS,1);
            
        dev.dcs.active                      = 0;
        dev.dcs.readable                    = 0;
        dev.dcs.armed                       = 0;
        
        dev.dcs.rAccess.active              = 0;
        dev.dcs.rAccess.IP                  = '';
        dev.dcs.rAccess.user                = '';
        dev.dcs.rAccess.key                 = '';
        dev.dcs.rAccess.port                = '';
        dev.dcs.rAccess.fileExt             = '';
        dev.dcs.rAccess.remotePath          = '';
        dev.dcs.lAccess.active              = 0;
        dev.dcs.dcData2MatScript            = '';
        dev.dcs.distributionLT              = '';
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                            mkdirOS(dev.dcs.path.base,OS,1);                           
        dev.dcs.path.rawData                = '';%                           
        dev.dcs.path.rawDataDat             = '';%                           
        dev.dcs.path.rawDataMat             = '';%                           
        dev.dcs.path.data                   = [dev.dcs.path.base 'data' b];                          mkdirOS(dev.dcs.path.data,OS,1);mkdirOS([dev.dcs.path.data 'merge' b],OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                                mkdirOS(dev.dcs.path.LT,OS,1);
    
        dev.ana.active                      = 0;
        dev.ana.path.base                   = [dev.path.data 'ana' b];                               mkdirOS(dev.ana.path.base,OS,1);
        telescopePath                       =  dev.ana.path.base; 

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;        
        

%% Odroid
dev = initDevice();

    dev.active                              =    1;
    dev.name                                = 'ODROID';
    dev.subName                             = '01';
    dev.type                                =   '';
    dev.subType                             =   '';
        dev.reportable.active               =    0;
        
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
            
        dev.dcs.active                      =   1;
        dev.dcs.readable                    =   1;
        dev.dcs.armed                       =   1;
         
        dev.dcs.rAccess.active              =   1;

        dev.dcs.rAccess.IP{1}               = SYSTEMNAME;
        dev.dcs.rAccess.user{1}             = 'rpcuser';
        dev.dcs.rAccess.key{1}              = '~/.ssh/id_rsa';
        dev.dcs.rAccess.port{1}             = '22';

        dev.dcs.rAccess.fileExt             = 'Odroid_*.log';
        dev.dcs.rAccess.remotePath          = '/home/rpcuser/logs/';
        
        dev.dcs.lAccess.active              = 0;
        dev.dcs.lAccess.fileExt             = '';
        dev.dcs.lAccess.path                = '';
        
        dev.dcs.dcData2MatScript            = 'procGenericLog';
        dev.dcs.type                        = 'I2C';
        dev.dcs.columns                     = 3;
        dev.dcs.nameFormat                  = '*******2023-05-26****';
        
        dev.dcs.distributionLT              = 'lookUpTableODROID01.m';
        
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                           mkdirOS(dev.dcs.path.base,OS,1);
        dev.dcs.path.rawData                = [dev.dcs.path.base 'rawData' b];                      mkdirOS(dev.dcs.path.rawData,OS,1);
        dev.dcs.path.rawDataDat             = [dev.dcs.path.rawData 'rawDataDat' b];                mkdirOS([dev.dcs.path.rawDataDat],OS,1);mkdirOS([dev.dcs.path.rawDataDat 'done' b],OS,1);
        dev.dcs.path.rawDataMat             = [dev.dcs.path.rawData 'rawDataMat' b];                mkdirOS([dev.dcs.path.rawDataMat],OS,1);mkdirOS([dev.dcs.path.rawDataMat 'done' b],OS,1);
        dev.dcs.path.data                   = [dev.dcs.path.base 'data' b];                         mkdirOS(dev.dcs.path.data,OS,1);mkdirOS([dev.dcs.path.data 'merge' b],OS,1);                                                   %mkdirOS(dev.dcs.path.data,OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                               mkdirOS(dev.dcs.path.LT,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;

%% DAQ 
 dev = initDevice();

    dev.active                              = 1;
    dev.name                                = 'DAQ';
    dev.subName                             = '01';
    dev.type                                = 'all';
    dev.subType                             = '';
        dev.reportable.active               = 1;
        dev.reportable.LT                   = 'lookUpDAQReport.csv';
        dev.reportable.timeElapsed          = time2Show;
        %dev.reportable.downScaling          = downScaling;
        dev.path.base                       = [SYS 'devices' b  dev.name  dev.subName b];            mkdirOS(dev.path.base,OS,1);    
        dev.path.data                       = [dev.path.base 'data' b];                              mkdirOS(dev.path.data,OS,1);
        dev.path.reporting                  = [dev.path.base 'reporting' b];                         mkdirOS(dev.path.reporting,OS,1);
            
        dev.dcs.active                      = 0;
        dev.dcs.readable                    = 0;
        dev.dcs.armed                       = 0;
        
        dev.dcs.rAccess.active              = 0;
        dev.dcs.rAccess.IP                  = '';
        dev.dcs.rAccess.user                = '';
        dev.dcs.rAccess.key                 = '';
        dev.dcs.rAccess.port                = '';
        dev.dcs.rAccess.fileExt             = '';
        dev.dcs.rAccess.remotePath          = '';
        dev.dcs.lAccess.active              = 0;
        dev.dcs.dcData2MatScript            = '';
        dev.dcs.distributionLT              = '';
        dev.dcs.path.base                   = [dev.path.data 'dcData' b];                            mkdirOS(dev.dcs.path.base,OS,1);                           
        dev.dcs.path.rawData                = '';%                           
        dev.dcs.path.rawDataDat             = '';%                           
        dev.dcs.path.rawDataMat             = '';%                           
        dev.dcs.path.data                   = [dev.dcs.path.base 'data' b];                          mkdirOS(dev.dcs.path.data,OS,1);mkdirOS([dev.dcs.path.data 'merge' b],OS,1);
        dev.dcs.path.LT                     = [SYS 'lookUpTables' b];                                mkdirOS(dev.dcs.path.LT,OS,1);
    
        dev.ana.active                      = 0;
        dev.ana.path.base                   = [dev.path.data 'ana' b];                               mkdirOS(dev.ana.path.base,OS,1);

configuration.dev(devicePos) = dev;
devicePos = devicePos +1;      



%% TRB    
daq = initDAQ(); 

daq.active                              = 1;
daq.name                                = 'TRB';
daq.subName                             = '3';
    stationPathSuffix                   = [SYSTEMNAME b];
    daq.path.base                       = [SYS 'devices' b  daq.name  daq.subName b stationPathSuffix];mkdirOS(daq.path.base,OS,1);    
    daq.path.data                       = [daq.path.base 'data' b];                              mkdirOS(daq.path.data,OS,1);                              mkdirOS(daq.path.data,OS,1);
    daq.readable                        = 1;
    
    daq.rAccess.active                  = 1;
    daq.rAccess.IP{1}                   = 'localhost';
    daq.rAccess.user{1}                 = 'rpcuser';
    daq.rAccess.key{1}                  = '~/.ssh/id_rsa';
    daq.rAccess.port{1}                 = '22';

    daq.rAccess.IP{2}                   = SYSTEMNAME;
    daq.rAccess.user{2}                 = 'rpcuser';
    daq.rAccess.key{2}                  = '~/.ssh/id_rsa';
    daq.rAccess.port{2}                 = '5801';

    daq.rAccess.fileExt                 = '*.hld';
    daq.rAccess.remotePath              = ['/media/externalDisk/hlds/'];
    daq.rAccess.keepHLDs                = 1;
    daq.rAccess.zipFiles                = 1;
    daq.rAccess.downScale               = 1;                               %1 is no downScale
    
    daq.lAccess.active                  = 0;
    daq.lAccess.fileExt                 = '*.hld';
    daq.lAccess.path                    = ['/home/alberto/gate/localDocs/lip/daqSystems/SELADAS1M2/hlds/'];
    daq.lAccess.zip                     = 0;
    
    daq.unpacking.path.base             = [daq.path.data 'daqData' b];                           mkdirOS([daq.unpacking.path.base],OS,1);
    daq.unpacking.path.rawData          = [daq.unpacking.path.base 'rawData' b];                 mkdirOS([daq.unpacking.path.rawData],OS,1);
    daq.unpacking.path.rawDataDat       = [daq.unpacking.path.rawData 'dat' b];                  mkdirOS([daq.unpacking.path.rawDataDat],OS,1);mkdirOS([daq.unpacking.path.rawDataDat 'done' b],OS,1);
    daq.unpacking.path.rawDataMat       = [daq.unpacking.path.rawData 'mat' b];                  mkdirOS([daq.unpacking.path.rawDataMat],OS,1);mkdirOS([daq.unpacking.path.rawDataMat 'done' b],OS,1);
    daq.unpacking.fileExt               = '*.hld';
    daq.unpacking.bufferSize            =  60000000;%Confortable number for Manta III
    daq.unpacking.type                  = 'TRB3';
    daq.unpacking.keepHLDs              = 1;
    daq.unpacking.zipFiles              = 0;                               %keep data on origing and compress
    daq.unpacking.writeTDCCal           = 0;
    daq.unpacking.downScale             = 1;                               %1 is no downScale
    
    daq.raw2var.path.base               = [daq.path.data 'daqData' b];                           mkdirOS([daq.raw2var.path.base],OS,1);
    daq.raw2var.path.varData            = [daq.unpacking.path.base 'varData' b];                 mkdirOS([daq.raw2var.path.varData],OS,1);mkdirOS([daq.raw2var.path.varData 'done' b],OS,1);
    daq.raw2var.path.lookUpTables       = [SYS 'lookUpTables' b];                                         mkdirOS([daq.raw2var.path.lookUpTables],OS,1);
    %daq.raw2var.lookUpTables            = {'lookupTables_R3BCTS.m','lookupTables_RPC.m'};
    daq.raw2var.lookUpTables            = {'lookUpTables_RPC.m'};
    daq.raw2var.keepRawFiles            = 0;
    
    daq.var2cal.path.base               = [daq.path.data 'daqData' b];                           mkdirOS([daq.var2cal.path.base],OS,1);
    daq.var2cal.path.calData            = [daq.unpacking.path.base 'calData' b];                 mkdirOS([daq.var2cal.path.calData],OS,1);mkdirOS([daq.var2cal.path.calData 'done' b],OS,1);
    daq.var2cal.path.lookUpTables       = [SYS 'lookUpTables' b];                                         mkdirOS([daq.var2cal.path.lookUpTables],OS,1);
    daq.var2cal.lookUpTables            = '';
    daq.var2cal.keepVarFiles            = 0;
    daq.var2cal.exportAsci              = 1;
    daq.var2cal.exportAsciPath          = [daq.var2cal.path.base 'asci' b];                     mkdirOS([daq.var2cal.exportAsciPath],OS,1); 
    daq.var2cal.zipAsci                 = 0;
     
    daq(1).active                       = 1;
    daq(1).type                         = 'TRB3';
    daq.TRB3(1).centralFPGA             = 'C001';%This are the FPGA corresponding to a subEvent
    %conf.TRBs(1).lookupTables  = [conf.software.basePath 'wvf2var/lookupTables.m'];
    %The order of he FPGAs is the order on the Network MAP
    %%%%                                       ID          type   active   writeOutput                            timeCalPar                                                             lookupTables
    daq(1).TRB3(1).FPGAs                 = {'C001',            'TDC-CTS',   'TRUE',   'TRUE',        [daq.raw2var.path.lookUpTables 'timeCalibrationParametersC001.mat'],14;...
                                                                                    };  


%{11} is the offset in the TDC-CTS that jump all the words that are not TDCs 
%it is the number of words in betwwen 0x0010c001 and the first TDC word 0x60b9bd70. I assume that this is constant!!!

%size: 0x00000060  decoding: 0x00020001  id:    0x0000c001  trigNr: 0x0608e3a6 trigTypeTRB3: 0x1

%00000000:  0x0000c002  0x0010c001  0x100403e4  0xe6f5c14a
%00000010:  0x00000000  0xe6f5c14a  0x00000000  0xd3784d9d
%00000020:  0x0006e130  0x872aca87  0x00029994  0x80000000
%00000030:  0x20009500  0x60b9bd70  0x800faa96  0x80522a85
%00000040:  0x804aa30b  0x01a60000  0x00015555  0x00000001                                       
                                        
 
    
configuration.daq = daq;   


%% Ana parametres
ana.active                                  = 1;
ana.path                                    = [HOME 'ana' b];mkdirOS(ana.path,OS,1);
    
    ana.calibration.QPEDParam               = 'Offset_2023_07_14.mat';
    ana.calibration.LonYParam               = 'YOffSet_2023_07_14.mat';

    ana.keepFiles.TriggerType1              = 1;if(ana.keepFiles.TriggerType1);mkdirOS([telescopePath 'TT1' b],OS,1);end
    ana.keepFiles.TriggerType2              = 1;if(ana.keepFiles.TriggerType2);mkdirOS([telescopePath 'TT2' b],OS,1);end
    ana.keepVars.TriggerType1               = 1;if(ana.keepVars.TriggerType1);mkdirOS([telescopePath 'Vars' b],OS,1);mkdirOS([telescopePath 'Vars' b 'TT1' b],OS,1);end
    ana.keepVars.TriggerType2               = 1;if(ana.keepVars.TriggerType1);mkdirOS([telescopePath 'Vars' b],OS,1);mkdirOS([telescopePath 'Vars' b 'TT2' b],OS,1);end

    %ana.calibration.QPED.active             = 0;          
    ana.calibration.longitudinalY.active    = 0;                
    ana.calibration.longitudinalY.path      = [daq.raw2var.path.varData 'calYOff' b];mkdirOS(ana.calibration.longitudinalY.path,OS,1);

    ana.scintAna.active                     = 0;
    ana.scintAna.path                       = [ana.path 'ScintEff' b];mkdirOS(ana.scintAna.path,OS,1);

    ana.backgroundAna.active                = 0;
    ana.backgroundAna.path                  = [ana.path 'Background' b];mkdirOS(ana.backgroundAna.path,OS,1);
    
    ana.param.strips.vprop                  = 202.7;%165.7mm/ns
    ana.param.strips.strips                 = 4;
    ana.param.strips.pitch                  = 60;%mm
    ana.param.strips.planes                 = 4; 
    ana.param.strips.planesZPos             = [0 200 300 400];
    ana.param.strips.ActivePlanes           = [1 1 1 1];
    
    ana.param.strips.strTh                  = 100;
    ana.param.strips.QRange                 = [-100:0.1:500];%For Q histogram
    ana.param.strips.XRange                 = [-50:10:350];
    ana.param.strips.YRange                 = [-200:10:200];
    ana.report.address4Email                = {'alberto@coimbra.lip.pt';'csoneira@ucm.es';'vmnouvilas@ucm.es'};
   
configuration.ana                       = ana;         
            
%% Logs
log = initLog(); log.active        = 1; log.type          = 'criticallog'; log.localPath     = [SYS 'logs' b 'criticallog.log'];system(['touch ' log.localPath]);
configuration.logs = log;

log = initLog(); log.active        = 1; log.type          = 'syslog'; log.localPath     = [SYS 'logs' b 'syslog.log'];system(['touch ' log.localPath]);
configuration.logs(2) = log;

log = initLog(); log.active        = 1; log.type          = 'netlog'; log.localPath     = [SYS 'logs' b 'netlog.log'];system(['touch ' log.localPath]);
configuration.logs(3) = log;
        
%% Alarms
alarm = initAlarm(); alarm.system = SYSTEMNAME;alarm.active        = 0; alarm.type          = 'netAccess'; alarm.TO     = {'alberto@coimbra.lip.pt';'alberto.blanco.abc@gmail.com';'csoneira.alarms@gmail.com'};
configuration.alarms = alarm;        

alarm = initAlarm(); alarm.system = SYSTEMNAME;alarm.active        = 0; alarm.type          = 'unpacking'; alarm.TO     = {'rpc.slow.control@gmail.com';'csoneira.alarms@gmail.com'};
configuration.alarms(2) = alarm;  

alarm = initAlarm(); alarm.system = SYSTEMNAME;alarm.active        = 0; alarm.type          = 'unpackDCS'; alarm.TO     = {'alberto@coimbra.lip.pt'};
configuration.alarms(3) = alarm; 

alarm = initAlarm(); alarm.system = SYSTEMNAME;alarm.active        = 0; alarm.type          = 'IDs no active'; alarm.TO     = {'rpc.slow.control@gmail.com'};
configuration.alarms(4) = alarm; 

alarm = initAlarm(); alarm.system = SYSTEMNAME;alarm.active        = 0; alarm.type          = 'Online Monitoring'; alarm.TO     = {'rpc.slow.control@gmail.com';'csoneira.alarms@gmail.com'};
configuration.alarms(5) = alarm; 

% Legacy database publishing is opt-in; the analysis unpacker does not use it.
DB.active = 0; % Legacy DB publishing needs a new credential and secure transport design.

DB.connection.remoteIP  =                 'localhost';
DB.connection.port      =                     '15432';
DB.connection.user      =                   'mingo01';
DB.connection.pass = ''; % No password in public source or shell command arguments.
DB.connection.key       = '/home/alberto/.ssh/id_rsa';

DB.tmpFolder            = ['/tmp/'];                                                                                     %mkdirOS([DB.tmpFolder],OS,1);
DB.DistributeDCSVars    = 1;
DB.DistributeAnaVars    = 1;

configuration.DB        = DB;


configuration.Versioning = {'distributeAnaVars',1;'sendData2DB',0;'writeCSV4DB',1;'hadesName2Date',3;'initFileHandler',3};



%% Write the conf file once per day.
mkdirOS([HOME 'software/conf/data/'],OS,1);
save([HOME 'software/conf/data/configuration-' date '.mat'],'configuration');
return
