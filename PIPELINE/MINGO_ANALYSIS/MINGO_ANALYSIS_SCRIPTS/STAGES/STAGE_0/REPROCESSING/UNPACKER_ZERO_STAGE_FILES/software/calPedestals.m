% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/calPedestals.m
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
write2log(conf.logs,'','   ','syslog',OS);write2log(conf.logs,'','   ','syslog',OS);
message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
message2log = ['*** Starting pedestalCalculation.'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

%oldFile4Offsets = '/home/alberto/gate/localDocs/lip/daqSystems/SELADAS1M2/system/lookUpTables/OffSet_dummy.mat';
oldFile4Offsets = ['/home/alberto/gate/localDocs/lip/daqSystems/' SYSTEMNAME '/system/lookUpTables/Offset_2023_07_14.mat'];

file4Offsets    = ['/home/alberto/gate/localDocs/lip/daqSystems/' SYSTEMNAME '/system/devices/TRB3/data/daqData/varData/calQPED/outMerge4Ped.mat'];

load(oldFile4Offsets);oldQOffSets = QOffSets;QOffSets =QOffSets*0; 
load(file4Offsets);
plots = 1;

varList  = {'Q1_F','Q1_B','Q2_F','Q2_B','Q3_F','Q3_B','Q4_F','Q4_B',};
varActive = [1 1 1 1 1 1 1 1];

figHandle        = varActive*0;
numberOfChannels =  eval(['size(' varList{1} ',2)']);


if plots
    for i=1:length(varActive)
        if varActive(i)
            figHandle(i) = figure;
        end
    end
end


for i=1:length(varActive)
    if varActive(i)

        message2log = ['Calculating Pedestals for ' varList{i}];
        disp(message2log);
        write2log(conf.logs,message2log,'   ','syslog',OS);

        for j=1:numberOfChannels
            eval(['Q = ' varList{i} '(:,j);']);
            [offsetQ, g] = calDBPedestal({Q,oldQOffSets(j,i),j},{0});
            QOffSets(j,i) = offsetQ;
            if plots
                figure(figHandle(i));
                subplot(ceil(sqrt(numberOfChannels)),ceil(sqrt(numberOfChannels)),j);hold on
                stairs(g{1},g{2},'color','r');
                stairs(g{1},g{3},'color','b');
                stairs(g{4},g{5},'color','b');
                plot(g{7},polyval(g{6},g{7}),'-k');
                plot(offsetQ,1,'.g','markersize',12);
                plot(oldQOffSets(j,i),1,'.r','markersize',6);
                yaxis(1,g{8});
                xaxis(g{7}(1)-30,g{7}(end)+30);
            end
        end
        %      
        %QOffSets(3,1) =
    end
end
disp('Pausing')


% save(['/home/alberto/gate/localDocs/lip/daqSystems/' SYSTEMNAME  '/system/lookUpTables/Offset_2023_06_20.mat'],'QOffSets')
% 



