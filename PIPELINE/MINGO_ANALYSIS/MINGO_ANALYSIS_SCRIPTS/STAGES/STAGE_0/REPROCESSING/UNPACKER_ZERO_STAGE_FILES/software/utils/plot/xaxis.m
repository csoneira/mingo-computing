% Purpose: Format the X axis in a legacy plot.

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
