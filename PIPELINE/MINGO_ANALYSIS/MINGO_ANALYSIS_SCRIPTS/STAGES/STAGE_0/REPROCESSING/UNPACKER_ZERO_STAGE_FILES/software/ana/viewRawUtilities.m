% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/viewRawUtilities.m
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

run('../conf/initConf.m');
[status, RPCRUNMODE] = system('echo $RPCRUNMODE');

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
run([HOME 'software/conf/loadGeneralConf.m']);


%% Load configuration
conf = initSystem();
conf = loadConfiguration({conf,HOSTNAME,SYSTEMNAME,HOME,SYS,INTERPRETER,OS});

b = conf.bar;

% View vars in  anaPlaneStrips
%nPlanes = conf.ana.param.strips.planes;
nStrips = conf.ana.param.strips.strips;
nPlanes = conf.ana.param.strips.planes;
load([conf.daq.raw2var.path.lookUpTables conf.ana.calibration.QPEDParam])


load('/home/alberto/tmp/m3/dabc24240084233.mat')






%%% hist Q front / Q left
for p = 1:nPlanes
    eval(['QB = Q' num2str(p) '_B;QF = Q' num2str(p) '_F;']);
    figP(p) = figure;set(figP,'name',['Plane ' num2str(p)]);
   
    for s = 1:nStrips
        subplot(ceil(sqrt(nStrips)),ceil(sqrt(nStrips)),s);hold on
        title(['Strip ' num2str(s)]);
        I = find(QF(:,s) ~= 0);
        histf(QF(I,s),-100:500);plot(QOffSets(s,(2*p -1)),0,'.','markersize',12);
        I = find(QB(:,s) ~= 0);
        histf(QB(I,s),-100:500);plot(QOffSets(s,2*p),0,'.','markersize',12);
        grid;xaxis(10,150);%yaxis(-500,500);
    end
end



%%% Scatter plot Q front / Q left
for p = 1:nPlanes
    eval(['QB = Q' num2str(p) '_B;QF = Q' num2str(p) '_F;']);
    figP(p) = figure;set(figP,'name',['Plane ' num2str(p)]);
   
    for s = 1:nStrips
        subplot(ceil(sqrt(nStrips)),ceil(sqrt(nStrips)),s);hold on
        title(['Strip ' num2str(s)]);
        plot(QF(:,s),QB(:,s),'.');
        grid;xaxis(10,1050);yaxis(10,1050);
    end
end


return






