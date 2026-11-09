% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/plot/xaxis.m
% Purpose: xaxis function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function X=xaxis(mini,maxi,tickstep);
%function X=xaxis(mini,maxi,tickstep);

if nargin==0
	X=axis;
	X=X(1:2);
	return
end

a=axis;
a(1)=mini;
a(2)=maxi;
axis(a);

if nargin==3
	set(gca,'Xtick',linspace(mini,maxi,(maxi-mini)/tickstep+1))
end


return

