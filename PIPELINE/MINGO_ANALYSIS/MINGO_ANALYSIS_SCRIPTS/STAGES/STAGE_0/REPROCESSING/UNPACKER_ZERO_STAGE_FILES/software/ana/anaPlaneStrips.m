% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/anaPlaneStrips.m
% Purpose: anaPlaneStrips function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function OutputVars = anaPlaneStrips(TF,TB,QF,QB,QOffSets,YCenters,EBtime,conf)

%01-  EBTime                  => EB time
%02-  rawEvents        num    => Initial number of Events
%03-  Events           num    => Final events after pedestal and left, right cuts
%04-  runTime          num    => Time of the hld in seconds
%05-  Xraw             1D     => X raw in strips
%06-  Yraw             1D     => Y raw
%07-  Q                1D     => Final charge
%08-  Xmm              1D     => Final X (across the strip)
%09 - Ymm              1D     => Final Y (along the strip)
%10 - T                1D     => Final T
%11 - Qmean            num    => Mean of the Q
%12 - QmeanNoST        num    => Mean of the Q without Streamers
%13 - Qmedian          num    => Median of the Q
%14 - QmedianNoST      num    => Median of the Q without Streamers
%15 - ST               num    => % of Streamers
%16 - XY               2D     => Hit map
%17 - XY_Qmean         2D     => Q mean map
%18 - XY_Qmedian       2D     => Q mean map
%19 - XY_ST            2D     => Hists avobe streamer level
%20 - Qhist            2D     => Charge histogram

%%%Extract parameters
vprop       = conf.ana.param.strips.vprop;  
pitch       = conf.ana.param.strips.pitch; 
strTh       = conf.ana.param.strips.strTh; 
strips      = conf.ana.param.strips.strips;
QRange      = conf.ana.param.strips.QRange;
XRange      = conf.ana.param.strips.XRange;
YRange      = conf.ana.param.strips.YRange;


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Runtime in seconds
runTime = etime(datevec(EBtime(end)),datevec(EBtime(1)));
rawEvents = size(TF,1);

% I = find(TF);MF = TF*0;MF(I) = 1;
% I = find(TB);MB = TB*0;MB(I) = 1;

% figure;hold on;stairs(sum(MF));stairs(sum(MB));
% figure;hold on;histf(sum(MF'),1:strips);histf(sum(MB'),1:strips);

%%% Select only events with left and right time and charge
QF_p = TF*NaN;QB_p = TF*NaN;
for ind = 1:strips
I = find(TF(:,ind) ~= 0 & TB(:,ind) ~= 0);
    QF_p(I,ind) = (QF(I,ind) - QOffSets(ind,1));I_ = find(QF_p(:,ind) < 0);if(length(I_) > 0);QF_p(I_,ind) = NaN;end 
    QB_p(I,ind) = (QB(I,ind) - QOffSets(ind,2));I_ = find(QB_p(:,ind) < 0);if(length(I_) > 0);QB_p(I_,ind) = NaN;end   
end


clear PED_QF PED_QB QF QB

QFmax_ = nan(rawEvents,strips);
 [QFmax,XFmax]= max(QF_p,[],2);Ind = sub2ind([rawEvents strips],(1:rawEvents)',XFmax);QFmax_(Ind) = XFmax;
QBmax_ = nan(rawEvents,strips);
 [QBmax,XBmax]= max(QB_p,[],2);Ind = sub2ind([rawEvents strips],(1:rawEvents)',XBmax);QBmax_(Ind) = XBmax;

%Ind2Keep  = find(TF ~= 0 & TB ~= 0 & ~isnan(QF_p) & ~isnan(QB_p) & QFmax_ == QBmax_ & ~isnan(QFmax_) & ~isnan(QBmax_));[row,col] = ind2sub(size(TF),Ind2Keep);rows = unique(row);
Ind2Keep  = find((TF ~= 0) .* (TB ~= 0) .* (~isnan(QF_p)) .* (~isnan(QB_p)) .* (QFmax_ == QBmax_) .* (~isnan(QFmax_)) .* (~isnan(QBmax_)));[row,col] = ind2sub(size(TF),Ind2Keep);rows = unique(row);
Ind2Keep = sub2ind(size(TF),rows,XFmax(rows));

%%% Do the cut here, select only above events. 
%sparse(row,XFmax,TF(row,XFmax)/2 +   TB(row,XFmax)/2;,s1,s2)]

T = nan(rawEvents,1);Q = nan(rawEvents,1);Xraw = nan(rawEvents,1);Yraw = nan(rawEvents,1);

T(rows) =    TF(Ind2Keep)/2 +   TB(Ind2Keep)/2;  
Q(rows) = (QF_p(Ind2Keep)   + QB_p(Ind2Keep))/2;
Xraw(rows) =                        XFmax(rows);
Yraw(rows) =   (TF(Ind2Keep)   -   TB(Ind2Keep))/2;

Events = length(find(Q > 0));

% MTF = sum(MTF');MTF = MTF(rows);
% MTB = sum(MTB');MTB = MTB(rows);

Ycal = Yraw;%Left this variable without calibration
%%% Calibrate Y
for i = 1:strips
   indx = find(Xraw == i);
   Ycal(indx) = (Yraw(indx) - YCenters(i));
end


%%% Change to mm

Xmm = ((Xraw)*(pitch) - (pitch/2)) + ((rand(length(Xraw),1)*pitch) - pitch/2);
%X_= ((X -1)+ (rand(length(X),1))) *1000/strips;
Ymm = Ycal*vprop;



[XY,XY_Qmean,XY_Qmedian,XY_ST] = strips2Dplots(Xmm,Ymm,Q,XRange,YRange,strTh);
XY = XY';XY_Qmean = XY_Qmean';XY_Qmedian = XY_Qmedian';XY_ST = XY_ST';
%XY = 0;XY_Q = 0;XY_ST = 0;

%% Calculate the mean, median and % streamer
try;Qmean            = nanmean  (Q(Q < 10000));                        catch;Qmean       = NaN;end;%Mean withou outliers
try;Qmedian          = nanmedian(Q(Q < 10000));                        catch;Qmedian     = NaN;end;
try;QmeanNoST        = nanmean  (Q((Q < strTh)));                      catch;QmeanNoST   = NaN;end;
try;QmedianNoST      = nanmedian(Q((Q < strTh)));                      catch;QmedianNoST = NaN;end;
try;ST               = length(find(Q > strTh))/length(find(~isnan(Q)));catch;ST          = NaN;end;

[N,X] = histf(Q,QRange);
Qhist = {X,N};

OutputVars = {EBtime,rawEvents,Events,runTime,Xraw,Yraw,Q,Xmm,Ymm,T,Qmean,QmeanNoST,Qmedian,QmedianNoST,ST,XY,XY_Qmean,XY_Qmedian,XY_ST,Qhist};

return
