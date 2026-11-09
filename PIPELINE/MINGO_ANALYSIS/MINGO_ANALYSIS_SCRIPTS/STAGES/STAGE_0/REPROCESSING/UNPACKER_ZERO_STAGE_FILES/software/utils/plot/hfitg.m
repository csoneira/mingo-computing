% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/plot/hfitg.m
% Purpose: hfitg function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [parout,chisq]=hfitg(x,n,plotit,miny,maxy)
%function [parout,chisq]=hfitg(x,n,plotit,miny,maxy)
%hfitg(array,num_of_bins)
%you can also use
%hfitg(array,num_of_bins,plot_flag,min_value,max_value)
%Where min_value and max_value will be the min/max limits of the histogram.

global ndf;

if all(size(x)==size(n))
	HistIsGiven=1;
else
	HistIsGiven=0;
end

if (nargin == 2)
	plotit=0;
end

if (nargin == 5)  % trim x
  x=x(find(x>=miny & x<=maxy ));
else
	miny=min(min(x));
	maxy=max(max(x));
end

if plotit==1,figure,end

if HistIsGiven
	nx=x; ny=n;
	if plotit
		stairs(nx,ny);
	end
else % calculate histogram
	if plotit
		[ny,nx]=hpl(x,n,miny,maxy);
	else
		[ny,nx]=hist2(x,n,miny,maxy);
	end
end
%par=[1,1,1000];
par(1)=mean(x);
par(2)=std(x);
par(3)=max(ny);
[parout,chisq]=chisqmin(par,nx,ny);
if plotit
	hold on
	X=linspace(miny,maxy,100);
%	plot(X+(X(2)-X(1)),parout(3)*g(X,parout(1),parout(2)),'b')
	plot(X,parout(3)*g(X,parout(1),parout(2)),'b')
	hold off
	v=axis;
	mean_value=['Mean: ',num2str(parout(1))];
	std_value=['Sigma: ',num2str(parout(2))];
	max_value=['Max: ',num2str(parout(3))];
	chi2_value=['Chi2/ndf: ',num2str(chisq),'/',int2str(ndf-3)];

%	xper=.27;yper=.05;
%	text(v(1)*xper+v(2)*(1-xper),v(3)*yper+v(4)*(1-yper),mean_value)
%	yper=yper+.05;
%	text(v(1)*xper+v(2)*(1-xper),v(3)*yper+v(4)*(1-yper),std_value)
%	yper=yper+.05;
%	text(v(1)*xper+v(2)*(1-xper),v(3)*yper+v(4)*(1-yper),max_value)
%	yper=yper+.05;
%	text(v(1)*xper+v(2)*(1-xper),v(3)*yper+v(4)*(1-yper),chi2_value)

	text(min(xaxis),max(yaxis),std_value);
	text(min(xaxis),max(yaxis)/5,chi2_value);


%	xline=v(1)*(xper-.1)+v(2)*(.9-xper);
%	yline=v(3)*(yper-.05)+v(4)*(.95-yper);

	hold off
end
