% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/viewOutput.m
% Purpose: ViewOutput.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

plane = 4;

rawEvents    =  OutputVars{plane}{1};
Events       =  OutputVars{plane}{2};    
runTime      =  OutputVars{plane}{3};    
Xraw         =  OutputVars{plane}{4};   
Yraw         =  OutputVars{plane}{5};    
Q            =  OutputVars{plane}{6};    
Xmm          =  OutputVars{plane}{7};    
Ymm          =  OutputVars{plane}{8};     
T            =  OutputVars{plane}{9};    
Qmean        =  OutputVars{plane}{10};    
QmeanNoST    =  OutputVars{plane}{11};    
Qmedian      =  OutputVars{plane}{12};    
QmedianNoST  =  OutputVars{plane}{13};    
ST           =  OutputVars{plane}{14};    
XY           =  OutputVars{plane}{15};    
XY_Qmean     =  OutputVars{plane}{16};   
XY_Qmedian   =  OutputVars{plane}{17};     
XY_ST        =  OutputVars{plane}{18};    
Qhist        =  OutputVars{plane}{19};    


XRange                = [-50:10:350];
YRange                = [-200:10:200];
strTh                 = 100;
 
[XY,XY_Qmean,XY_Qmedian,XY_ST] = strips2Dplots(Xmm,Ymm,Q,XRange,YRange,strTh);




%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
Xmm = X4;Ymm = Y4;Q = Q4;
Xmm = X2(I);Ymm = Y2(I);Q = Q2(I);
[XY,XY_Qmean,XY_Qmedian,XY_ST,XY_Q] = strips2DplotsAdvance(Xmm,Ymm,Q,XRange,YRange,strTh);
XY = XY';XY_Qmean = XY_Qmean';XY_ST = XY_ST';XY_Q = XY_Q';

figH = figure;
ax1H = subplot(1,2,1);
ax2H = subplot(1,2,2);

axes(ax1H);
imagesc(XY)

while(1)
     [x,y] = ginput(1);x = floor(x);y = floor(y);
     axes(ax2H);
     [xx,nn]=histf(XY_Q{y,x},-10:500);stairs(nn,xx);logy;yaxis(1, max(xx)*1.5),xaxis(-10,500);
end


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
X1 = []; Y1 = []; Q1 = [];
X2 = []; Y2 = []; Q2 = [];
X3 = []; Y3 = []; Q3 = [];
X4 = []; Y4 = []; Q4 = [];
inPath = '/home/alberto/gate/localDocs/lip/daqSystems/sRPC/ana/Background/'
s = dir([inPath '*.mat']);
for i=1:length(s)
    load([inPath s(i).name],'OutputVars');
    Q1 = [Q1; OutputVars{1}{6}];Q2 = [Q2; OutputVars{2}{6}];Q3 = [Q3; OutputVars{3}{6}];Q4 = [Q4; OutputVars{4}{6}];
    X1 = [X1; OutputVars{1}{7}];X2 = [X2; OutputVars{2}{7}];X3 = [X3; OutputVars{3}{7}];X4 = [X4; OutputVars{4}{7}];
    Y1 = [Y1; OutputVars{1}{8}];Y2 = [Y2; OutputVars{2}{8}];Y3 = [Y3; OutputVars{3}{8}];Y4 = [Y4; OutputVars{4}{8}];
end
save([inPath 'out.mat'],'X1','X2','X3','X4','Y1','Y2','Y3','Y4','Q1','Q2','Q3','Q4');




