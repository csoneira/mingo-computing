% Purpose: Format the Z axis in a legacy plot.

function Z=zaxis(mini,maxi,tickstep);
%function Z=Zaxis(mini,maxi,tickstep);

if nargin==0
	Z=axis;
	Z=Z(1:2);
	return
end

a=axis;
a(5)=mini;
a(6)=maxi;
axis(a);

if nargin==3
	set(gca,'Ztick',linspace(mini,maxi,(maxi-mini)/tickstep+1))
end


return
