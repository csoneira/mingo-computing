% Purpose: Calculate the coordinate transformation used by the legacy plotting utilities.

function f=g(x,mean,stdev)

f=exp(-(x-mean).^2/2/stdev^2);
