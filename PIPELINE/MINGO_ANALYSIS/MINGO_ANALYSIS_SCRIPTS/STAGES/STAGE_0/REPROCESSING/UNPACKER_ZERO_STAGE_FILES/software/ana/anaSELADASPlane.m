% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/anaSELADASPlane.m
% Purpose: anaSTRATOSPlane function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [rawEvents, events, Q, Qmean, Qmedian, ST, XY, XY_Q, XY_ST,X,Y,X_,Y_] = anaSTRATOSPlane(TF,TB,QOffSets)

rawEvents = size(TF,1);
runtime = 1;

PED_QF = repmat(QOffSets(:,1)',rawEvents,1);
PED_QB = repmat(QOffSets(:,2)',rawEvents,1);


%%% Select only events with left and right time and charge
QF_p = TF*NaN;QB_p = TF*NaN;
I = find(TF ~= 0 & TB ~= 0);
% 
% MTF = TF*0;I = find(TF);MTF(I) = 1;
% MTB = TB*0;I = find(TB);MTB(I) = 1;


QF_p(I) = (QF(I) - PED_QF(I));I_ = find(QF_p < 0);if(length(I_) > 0);QF_p(I_) = NaN;end 
QB_p(I) = (QB(I) - PED_QB(I));I_ = find(QB_p < 0);if(length(I_) > 0);QB_p(I_) = NaN;end

clear PED_QF PED_QB QF QB

[QFmax,XFmax]= max(QF_p,[],2);
[QBmax,XBmax]= max(QB_p,[],2);

Ind2Cut  = find(TF ~= 0 & TB ~= 0 & ~isnan(QF_p) & ~isnan(QB_p) & XFmax == XBmax );[row,col] = ind2sub(size(TF),Ind2Cut);rows = unique(row);
Ind2Keep = sub2ind(size(TF),rows,XFmax(rows));

%%% Do the cut here, select only above events. 
%sparse(row,XFmax,TF(row,XFmax)/2 +   TB(row,XFmax)/2;,s1,s2)]
events = rawEvents;
T = nan(events,1);Q = nan(events,1);X = nan(events,1);Y = nan(events,1);

T(rows) =    TF(Ind2Keep)/2 +   TB(Ind2Keep)/2;  
Q(rows) = (QF_p(Ind2Keep)   + QB_p(Ind2Keep))/2;
X(rows) =                        XFmax(rows);
Y(rows) =    (TF(Ind2Keep)   -   TB(Ind2Keep))/2;

% MTF = sum(MTF');MTF = MTF(rows);
% MTB = sum(MTB');MTB = MTB(rows);

Y_ = Y;%Left this variable without calibration
%%% Calibrate Y
for i=1:64
   I_ = find(X== i);
   Y_(I_) = (Y(I_) - YCenters(i));
end

%%% Change to mm
vprop=165.7;%165.7mm/ns
X_= ((X -1)+ (rand(length(X),1))) *1200/64;
Y_ = Y_*vprop;


STLevel = 100;
[XY,XY_Q,XY_ST] = STRATOS2Dplots(X_,Y_,Q,[-100:10:1300],[-800:10:800],STLevel);
XY = XY';XY_Q = XY_Q';%XY_ST = XY_ST';
%XY = 0;XY_Q = 0;XY_ST = 0;


%% Calculate the mean, median and % streamer
Qmean            = nanmean(Q);
Qmedian          = nanmedian(Q);
ST               = length(find(Q >STLevel))/length(find(~isnan(Q)));
return
