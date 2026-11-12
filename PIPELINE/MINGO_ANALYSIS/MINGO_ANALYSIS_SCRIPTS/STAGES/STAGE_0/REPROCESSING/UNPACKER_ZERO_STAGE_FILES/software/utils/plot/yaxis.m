% Purpose: Format the Y axis in a legacy plot.

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
