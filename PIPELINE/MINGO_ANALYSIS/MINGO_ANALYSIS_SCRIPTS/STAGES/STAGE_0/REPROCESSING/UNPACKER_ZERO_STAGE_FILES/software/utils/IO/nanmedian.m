% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/nanmedian.m
% Purpose: nanmedian function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function y = nanmedian(x,dim)
%NANMEDIAN Median value, ignoring NaNs.
%   M = NANMEDIAN(X) returns the sample median of X, treating NaNs as
%   missing values.  For vector input, M is the median value of the non-NaN
%   elements in X.  For matrix input, M is a row vector containing the
%   median value of non-NaN elements in each column.  For N-D arrays,
%   NANMEDIAN operates along the first non-singleton dimension.
%
%   NANMEDIAN(X,DIM) takes the median along the dimension DIM of X.
%
%   See also MEDIAN, NANMEAN, NANSTD, NANVAR, NANMIN, NANMAX, NANSUM.

%   Copyright 1993-2004 The MathWorks, Inc.
%   $Revision: 1.1.8.1 $  $Date: 2010/03/16 00:15:51 $

if nargin == 1
    y = prctile(x, 50);
else
    y = prctile(x, 50,dim);
end
