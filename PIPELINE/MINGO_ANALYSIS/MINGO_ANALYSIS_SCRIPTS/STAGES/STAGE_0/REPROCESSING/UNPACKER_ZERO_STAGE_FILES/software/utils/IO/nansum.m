% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/nansum.m
% Purpose: nansum function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function y = nansum(x,dim)
%NANSUM Sum, ignoring NaNs.
%   Y = NANSUM(X) returns the sum of X, treating NaNs as missing values.
%   For vector input, Y is the sum of the non-NaN elements in X.  For
%   matrix input, Y is a row vector containing the sum of non-NaN elements
%   in each column.  For N-D arrays, NANSUM operates along the first
%   non-singleton dimension.
%
%   Y = NANSUM(X,DIM) takes the sum along dimension DIM of X.
%
%   See also SUM, NANMEAN, NANVAR, NANSTD, NANMIN, NANMAX, NANMEDIAN.

%   Copyright 1993-2004 The MathWorks, Inc.
%   $Revision: 1.1.8.1 $  $Date: 2010/03/16 00:15:54 $

% Find NaNs and set them to zero.  Then sum up non-NaNs.  Cols of all NaNs
% will return zero.
x(isnan(x)) = 0;
if nargin == 1 % let sum figure out which dimension to work along
    y = sum(x);
else           % work along the explicitly given dimension
    y = sum(x,dim);
end
