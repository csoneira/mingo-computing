% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/plot/chisqmin.m
% Purpose: chisq_min function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [parout,chisq]=chisq_min(par, xin, yin, sigmain)

global x;
global y;
global sigma;
global ndf;

clear parout;

x = xin;
y = yin;
if nargin == 4
  sigma = sigmain;
else
%  sigma = ones(size(x));
%  sigma = max(ones(size(x)), sqrt(y));
  sigma = sqrt(y);
end;

ndf=length(find (sigma > 0));
parout=fminsearch('gx',par);
chisq = gx(parout);
