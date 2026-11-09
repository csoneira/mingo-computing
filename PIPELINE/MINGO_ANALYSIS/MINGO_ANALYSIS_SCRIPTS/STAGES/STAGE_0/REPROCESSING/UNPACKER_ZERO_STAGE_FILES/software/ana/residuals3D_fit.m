% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/residuals3D_fit.m
% Purpose: residuals3D_fit function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [R1, R2, R3, R4] = residuals3D_fit(points)

% points  are athe 3d point in the form X_,Y_,Z_ as many as I want X_ = points(:,1), Y_ = points(:,2), Z_ = points(:,3)
% Z0 is the coordiante in the Z_
%
%

N = size(points,1);


X_ave=mean(points,1);            % mean; line of best fit will pass through this point  
dX=bsxfun(@minus,points,X_ave);  % residuals
C=(dX'*dX)/(N-1);           % variance-covariance matrix of X
[R,D]=svd(C,0);             % singular value decomposition of C; C=R*D*R'
% NOTES:
% 1) Direction of best fit line corresponds to R(:,1)
% 2) R(:,1) is the direction of maximum variances of dX 
% 3) D(1,1) is the variance of dX after projection on R(:,1)
% 4) Parametric equation of best fit line: L(t)=X_ave+t*R(:,1)', where t is a real number
% 5) Total variance of X = trace(D)
% Coefficient of determineation; R^2 = (explained variance)/(total variance)
% Parametric equation of best fit line: L(t)=X_ave+t*R(:,1)', where t is a real number
% x = x0 + t*a; y = y0 + t*b; z = z0 + t*c; R(:,1) = (a, b, c); X_ave =(x0, y0, c0);
%

t = (points(1,3) - X_ave(3))/R(3,1);
X = X_ave(1) + t*R(1,1); 
Y = X_ave(2) + t*R(2,1);
Z = X_ave(3) + t*R(3,1);

R1 = [points(1,1)-X points(1,2)-Y];



t = (points(2,3) - X_ave(3))/R(3,1);
X = X_ave(1) + t*R(1,1); 
Y = X_ave(2) + t*R(2,1);
Z = X_ave(3) + t*R(3,1);

R2 = [points(2,1)-X points(2,2)-Y];

t = (points(3,3) - X_ave(3))/R(3,1);
X = X_ave(1) + t*R(1,1); 
Y = X_ave(2) + t*R(2,1);
Z = X_ave(3) + t*R(3,1);

R3 = [points(3,1)-X points(3,2)-Y];

t = (points(4,3) - X_ave(3))/R(3,1);
X = X_ave(1) + t*R(1,1); 
Y = X_ave(2) + t*R(2,1);
Z = X_ave(3) + t*R(3,1);

R4 = [points(4,1)-X points(4,2)-Y];

return
