% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/strips2Dplots.m
% Purpose: strips2Dplots function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [XY,XY_Qmean,XY_Qmedian,XY_ST] = strips2Dplots(X,Y,Q,binsX,binsY,STLevel)

XY         = zeros(length(binsX)-1,length(binsY)-1);
XY_Qmean   = zeros(length(binsX)-1,length(binsY)-1);
XY_Qmedian = zeros(length(binsX)-1,length(binsY)-1);
XY_ST      = zeros(length(binsX)-1,length(binsY)-1);

for i=1:length(binsX)-1
    for j= 1:length(binsY)-1
        I = find(X > binsX(i) & X <= binsX(i+1) & Y > binsY(j) & Y <= binsY(j+1));
        XY(i,j)        = length(I);
        XY_Qmean(i,j)  = nanmean(Q(I));
        %XY_Qmedian(i,j)= nanmedian(Q(I));
        XY_Qmedian(i,j) = 0;
        XY_ST(i,j)     = length(find(Q(I) > STLevel));
    end
end

I = isnan(XY_Qmean);XY_Qmean(I) = 0;
%I = isnan(XY_Qmedian);XY_Qmedian(I) = 0;