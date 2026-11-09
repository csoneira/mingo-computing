% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/plot/yaxis.m
% Purpose: yaxis function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function Y=yaxis(min,max,nticks);

if nargin==0
	Y=axis;
	Y=Y(3:4);
	return
end

a=axis;
a(3)=min;
a(4)=max;
axis(a);

if nargin==3
	set(gca,'Ytick',linspace(min,max,nticks+2))
end


return

