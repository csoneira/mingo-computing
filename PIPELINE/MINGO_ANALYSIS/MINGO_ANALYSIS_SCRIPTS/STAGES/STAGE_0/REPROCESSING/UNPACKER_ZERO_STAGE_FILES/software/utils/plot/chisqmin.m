% Purpose: Find the minimum chi-square in the plotted fit data.

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
