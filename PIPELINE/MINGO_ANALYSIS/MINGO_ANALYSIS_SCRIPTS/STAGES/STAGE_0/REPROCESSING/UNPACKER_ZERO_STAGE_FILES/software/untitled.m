% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/untitled.m
% Purpose: Untitled.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

figure;
for i=1:4
    subplot(2,2,i);grid
    plot(QB(:,i),QF(:,i),'.');xaxis(-1000,1000);yaxis(-1000,1000);
end

figure;
for i=1:4
    
    subplot(2,2,i);grid
    
    plot(QB_p(:,i),QF_p(:,i),'.');xaxis(-1000,1000);yaxis(-1000,1000);
    title(['Strip ' num2str(i)])
end

figure;
for i=1:4
    subplot(2,2,i);grid
    plot(QB_(:,i),QF_(:,i),'.');xaxis(-1000,1000);yaxis(-1000,1000);
end

figure;
for i=1:4
    subplot(2,2,i);grid;hold on
    histf(QB(:,i),10:200);
    histf(QF(:,i),10:200);
end

MTF = TF*0;I = find(TF);MTF(I) = 1;sum(MTF)',sum(sum(MTF))
MTB = TB*0;I = find(TB);MTB(I) = 1;sum(MTB)',sum(sum(MTB))

figure;
for i=1:4
    subplot(2,2,i);grid;hold on
    histf(QB_p(:,i),-10:200);
    histf(QF_p(:,i),-10:200);
end


QB = [QB(:,1) QB(:,2) QB(:,3) QB(:,4)];
QF = [QF(:,4) QF(:,2) QF(:,3) QF(:,1)];
TB = [TB(:,1) TB(:,2) TB(:,3) TB(:,4)];
TF = [TF(:,4) TF(:,2) TF(:,3) TF(:,1)];


figure;hold on
histf(Ymm(Xraw == 1)-140,-4000:5:4000)
histf(Ymm(Xraw == 2)+315,-4000:5:4000)
histf(Ymm(Xraw == 3)+155,-4000:5:4000)
histf(Ymm(Xraw == 4)+550,-4000:5:4000)



figure;
for i=1:34
    hold on;
    histf(leadingFineTime(:,i),10:1000)
end

