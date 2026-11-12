% Purpose: Calculate the configured grid index for legacy detector variables.

function index = gri(N,limit)
%
% Generate random index.
%
% index = gri(N,limit)
% gri generates N random index from 0 to limit


I = randperm(limit);
index = I(1:N);

return
