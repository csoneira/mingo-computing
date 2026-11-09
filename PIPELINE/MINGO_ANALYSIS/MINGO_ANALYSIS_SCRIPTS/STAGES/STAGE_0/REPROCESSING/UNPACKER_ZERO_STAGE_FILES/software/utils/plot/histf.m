% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/plot/histf.m
% Purpose: histf function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [N,X]=histf(y,x)
%HISTF Plot histograms with equally spaced bins.
%	Functionaly similar to HIST, but the performance is independent of the
%	number of bins. Generally faster anyway.
%	If a vector X is specified the binwidth will be (max(X)-min(X))/length(X).
%
%	y = matrix not implemented yet.
%
%	Paulo Fonte 15-10-98
%	Instituto Superior de Engenharia de Coimbra, 3000 Coimbra, Portugal.

if nargin == 0
	error('Requires one or two input arguments.')
end

if nargin == 1
    x = 10;
end

if isstr(x) | isstr(y)
	error('Input arguments must be numeric.')
end

if min(size(y))==1, 
	y = y(:); 
else
   	error('y=matrix Not implemented');
end

[m,n] = size(y);

miny = min(min(y));
maxy = max(max(y));

if max(size(x)) == 1
    maxx=maxy;
    minx=miny;
    nbins=x;
    binwidth = (maxy - miny) ./ nbins;
    X_=linspace(minx+binwidth/2,maxx-binwidth/2,nbins)';
else
    nbins=length(x);
    binwidth = (max(x)-min(x))/(nbins-1);
    maxx=max(x)+binwidth/2;
    minx=min(x)-binwidth/2;
    X_=x(:);
    y=y(find(y>=minx & y<=maxx));  % force maxx=maxy and minx=miny
end

% map y from -0.4999 to nbins-.4999 and project into the integers
y=(y-minx)/(maxx-minx)*(nbins-.4999)-.4999;

y=[y;(-1:nbins)'*ones(1,n)]; % make sure that we have at least one count per bin

y=sort(y); % do now most of the job;
N_=diff(find(diff(round(y))))-1;  % now do the rest of the job

% find doesn't work columnwise, so y=matrix must be implemented column by column

if nargout == 0
    stairs(X_,N_);
else
  if min(size(y))==1, % Return row vectors if possible.
    N=N_';
    X=X_';
  else
   	error('y=matrix Not implemented');
  end
end
