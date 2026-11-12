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


%% Select here waht to merge
%mergeSelector = 'QPedestals';
%mergeSelector = 'YOffsets';
%mergeSelector = 'QPedestals';runNumber = '054';

mergeSelector = 'cernLumi';
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%



versions        = {'mergeMat',1;'initFileHandler',2;'hadesName2Date',2,;'logsName2Date',1}; 
typeOfFiles     = 'HADES';

if(strcmp(mergeSelector,'QPedestals'))
        inPath          =  ['/home/alberto/gate/localDocs/lip/daqSystems/' SYSTEMNAME '/system/devices/TRB3/data/daqData/varData/'];
        outPath         =  [inPath 'calQPED/'];mkdirOS(outPath,OS,1);
        numberOfFiles   = 'all';
        numberOfFiles   = 40;
        time2Merge      = 0;
        
        mergeMat({versions,inPath,'*.mat',  outPath,'outMerge4Ped.mat',numberOfFiles,time2Merge,typeOfFiles,INTERPRETER},{'Q1_F','RS'},{'Q1_B','RS'},{'Q2_F','RS'},{'Q2_B','RS'},{'Q3_F','RS'},{'Q3_B','RS'},{'Q4_F','RS'},{'Q4_B','RS'});
elseif(strcmp(mergeSelector,'YOffsets'))
        inPath          =  conf.ana.calibration.longitudinalY.path;
        outPath         =  inPath; 
        numberOfFiles   = 40;
        time2Merge      = 0;
        mergeMat({versions,inPath,'*.mat',  outPath,'outMerge4LongitudinalOffset.mat',numberOfFiles,time2Merge,typeOfFiles,INTERPRETER},{'XY','R'});
elseif(strcmp(mergeSelector,'scintAna'))
    inPath          =  [conf.ana.scintAna.path 'run' runNumber '/'];
    outPath         =  inPath;
    numberOfFiles   = 'all';
    time2Merge      = 0;
    %mergeMat({versions,inPath,'sest23*.mat',  outPath,'outScint.mat',numberOfFiles,time2Merge,typeOfFiles,INTERPRETER},{'X','R'},{'Y','R'},{'Q','R'},{'Qsc','R'},{'Tsc','R'});
    mergeMat({versions,inPath,'sest23*.mat',  outPath,'outScint.mat',numberOfFiles,time2Merge,typeOfFiles,INTERPRETER},{'T','R'},{'X','R'},{'Y','R'},{'Q','R'},{'T_F','R'},{'T_B','R'},{'Q_F','R'},{'Q_B','R'},{'Qsc','R'},{'Tsc','R'},{'EBtime','R'});
elseif(strcmp(mergeSelector,'cernAna'))
    inPath          =  '/home/alberto/gate/localDocs/lip/daqSystems/sRPC/ana/CERN/run01/'
    outPath         =  inPath;
    numberOfFiles   = 'all';
    time2Merge      = 0;
    %mergeMat({versions,inPath,'sest23*.mat',  outPath,'outScint.mat',numberOfFiles,time2Merge,typeOfFiles,INTERPRETER},{'X','R'},{'Y','R'},{'Q','R'},{'Qsc','R'},{'Tsc','R'});
    mergeMat({versions,inPath,'*.mat',  outPath,'outScint.mat',numberOfFiles,time2Merge,typeOfFiles,INTERPRETER},{'T1_F','R'},{'T1_B','R'},{'T2_F','R'},{'T2_B','R'},{'T3_F','R'},{'T3_B','R'},{'T4_F','R'},{'T4_B','R'},{'Q1_F','R'},{'Q1_B','R'},{'Q2_F','R'},{'Q2_B','R'},{'Q3_F','R'},{'Q3_B','R'},{'Q4_F','R'},{'Q4_B','R'},{'EBtime','R'},{'triggerType','R'});
elseif(strcmp(mergeSelector,'cernLumi'))
    inPath          =  '/home/alberto/gate/localDocs/lip/daqSystems/sRPCDev/system/devices/LHC/data/dcData/data/'
    outPath         =  [inPath 'merge/'];
    numberOfFiles   = 'all';
    time2Merge      = 0;
    %mergeMat({versions,inPath,'sest23*.mat',  outPath,'outScint.mat',numberOfFiles,time2Merge,typeOfFiles,INTERPRETER},{'X','R'},{'Y','R'},{'Q','R'},{'Qsc','R'},{'Tsc','R'});
    mergeMat({versions,inPath,'*lum.mat',outPath,'lumiMerge.mat',numberOfFiles,time2Merge,'LOGS',INTERPRETER},{'variable','R'},{'timeStamp','R'});
    
    inPath          =  '/home/alberto/gate/localDocs/lip/daqSystems/sRPCDev/system/devices/sRPC/data/dcData/data/'
    outPath         =  [inPath 'merge/'];
    numberOfFiles   = 'all';
    time2Merge      = 0;
    %mergeMat({versions,inPath,'sest23*.mat',  outPath,'outScint.mat',numberOfFiles,time2Merge,typeOfFiles,INTERPRETER},{'X','R'},{'Y','R'},{'Q','R'},{'Qsc','R'},{'Tsc','R'});
    mergeMat({versions,inPath,'*RateAccepted*.mat',outPath,'RateAcceptedMerge.mat',numberOfFiles,time2Merge,'LOGS',INTERPRETER},{'variable','R'},{'timeStamp','R'});
else
end
