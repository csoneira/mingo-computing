% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/plot/gx.m
% Purpose: gx function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [chisq] = gx(par)
global x;
global y;
global sigma;

% this calculates a gaussian (normal) distribution
%    x     - input value or array
%    mean  - mean of the gaussian
%    stdev - standard deviation of the gaussian
%    value - value of the the gaussian at the input value(s)
%            if input is array, output is an array

mean  = par(1);
stdev = par(2);
amp   = par(3);
fx = g(x,mean,stdev);
fx = amp * fx;

ind=find(y>0);
chisq = sum((y(ind) - fx(ind)).^2 ./ (sigma(ind)).^2);
