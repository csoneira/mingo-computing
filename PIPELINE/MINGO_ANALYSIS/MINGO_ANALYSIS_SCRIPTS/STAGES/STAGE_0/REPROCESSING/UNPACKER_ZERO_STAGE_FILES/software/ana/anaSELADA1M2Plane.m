% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/anaSELADA1M2Plane.m
% Purpose: anaSELADA1M2Plane function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [rawEvents, Q_p, hits, Qmean, Qmedian, ST, hitMap, QMap, STMap] = anaSELADA1M2Plane(T,Q,QOffSets,EBtime)

strTh     = 100;
rawEvents = size(T,1);
QMap      = cell(5,6);


%Runtime in seconds
runtime = etime(datevec(EBtime(end)),datevec(EBtime(1)));

PED_Q = repmat(QOffSets(:,1)',rawEvents,1);

%%%
Q_p = T*NaN;Q_p = T*NaN;
I = find(T ~= 0);

Q_p(I) = (Q(I) - PED_Q(I));I_ = find(Q_p < 0);if(length(I_) > 0);Q_p(I_) = NaN;end 
clear PED_Q Q

%%% multiplicity
mult = zeros(size(T)); mult(I) = 1;

%%% kill outlayers
I = find(Q_p > 10000);Q_p(I) = nan;

%%%
I = find(Q_p > strTh);
str = zeros(size(T));str(I) = 1;

for i=1:30
    QMap{i} = Q_p(:,i); 
end



hits       = sum(mult)./runtime;
hitMap     = reshape(hits,5,6);
Qmean      = nanmean(Q_p);
Qmedian    = nanmedian(Q_p);
ST         = sum(str)./sum(mult);
STMap      = reshape(ST,5,6);




% [Qmax,Xmax]= max(Q_p,[],2);
% Ind2Cut  = find(T ~= 0  & ~isnan(Q_p));[row,col] = ind2sub(size(T),Ind2Cut);rows = unique(row);
% Ind2Keep = sub2ind(size(T),rows,Xmax(rows));
% 
% Q = nan(events,1);
% Q(rows) = Q_p(Ind2Keep);


return
