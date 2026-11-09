% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/distributeAnaVarsDB.m
% Purpose: distributeAnaVarsDB function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function distributeAnaVarsDB(inputVars)

%2023-11-03 Creation go the function
%distributeAnaVarsDB({dateRegularFormat,                         Qmean,      '-QMean.mat',device,conf,  'time',                'none'});
                        

%% Load Variables

timeStamp         = inputVars{1};
variable          = inputVars{2};
varName           = inputVars{3};varName = varName(2:end-4);
dev2Distribute    = inputVars{4};
conf              = inputVars{5};
type              = inputVars{6};
subType           = inputVars{7};

remoteIP          = conf.DB.connection.remoteIP;
user              = conf.DB.connection.user;
pass              = conf.DB.connection.pass;
systemName        = conf.SYSTEMNAME;

if strcmp(type,'time')
    file2Send         = [conf.DB.tmpFolder dev2Distribute '_' varName '.csv'];
    writeCSV4DB({file2Send,timeStamp,varName,variable});
    sendData2DB({remoteIP,user,pass,conf.DB.tmpFolder,systemName,dev2Distribute,varName,file2Send})
end


return