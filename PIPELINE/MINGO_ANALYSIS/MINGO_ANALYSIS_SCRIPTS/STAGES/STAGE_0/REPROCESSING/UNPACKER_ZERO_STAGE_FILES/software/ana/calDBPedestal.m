% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/calDBPedestal.m
% Purpose: calDBPedestal function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [Qoffset, g] = calDBPedestal(varargin)
%
%calDBPedestal({Q,oldQoffset,ch},{verbosity})
%
Q              = varargin{1}{1};%                = Charge
oldQoffset     = varargin{1}{2};%                = old Q offset
ch             = varargin{1}{3};%                = corresponding channel
verbosity      = varargin{2}{1};%                = verbosity level

%verbosity                   = level of verbosity
%verbosity = 1;              %= some info


if(~ischar(ch));ch = num2str(ch);end

%Pedestal calcualtion for DBs signals
%
%
%Logic
%
%Frist clea up a little the data => date <= zero and date > 3000. All data in ns
lowerQAllowed  = 0;higerQAllowed = 3000;
lowerQ4Display = 0;higerQ4Display = 500;
searchWindow = 10;

%%% 

%%% Default values
smoothFactor            = 0.5;
slotNegativeSloope      =   5; %Remove all the slopes in the diff(q) smaller than slotNegativeSloope

g = cell(10,1);

%%% 
highStatisticAndWellBehabedQ = 'true'; %This is the case of sealedRPCs
if highStatisticAndWellBehabedQ
    smoothFactor            = 0.98;
    slotNegativeSloope      =  200;       %filter out all small even positive slopes
    cutAboveMax             = true;       %Cut all the Bind above the maximum od the Q spectra
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
events = length(Q);


ID_Qzero       = Q == 0;
ID_Qnonsense   = Q < lowerQAllowed | Q > higerQAllowed;


if verbosity >= 1
    disp(['Channel ' ch ' with '  num2str(length(find(ID_Qzero))/events)      ' of events equal to zero and with '  num2str(length(find(ID_Qnonsense))/length(find(ID_Qzero == 0)))  ' of events with values lower than '  num2str(lowerQAllowed)  ' and higer than ' num2str(higerQAllowed) ' excluding zeros'] )
end



Q = Q(find(ID_Qzero == 0 & ID_Qnonsense == 0));

binSize = 0;
if(length(Q) < 10000)
    binSize = 2;
elseif(length(Q) > 10000 & length(Q) < 50000)
    binSize = 1;
elseif(length(Q) > 50000 & length(Q) < 100000)
    binSize = 0.5;
elseif(length(Q) > 100000 & length(Q) < 1000000)
    binSize = 0.1;
elseif(length(Q) > 1000000)
    binSize = 0.05;
else
end


[qn,qx]=histf(Q,0:binSize:500);g{2} = qn;g{1} = qx;
verticalRange = max(qn)*1.2;   g{8} = verticalRange; 

if verbosity == 2
    PHS1=figure;
    stairs(qx,qn,'color','r');logy;
        yaxis(1,verticalRange);
        xaxis(lowerQ4Display,higerQ4Display);
    PHS2=figure;
    stairs(qx,qn,'color','r');
        yaxis(0,verticalRange);
        xaxis(lowerQ4Display,higerQ4Display);
end

%%% Smooth the charge spectra
scs = csaps(qx,qn,smoothFactor);%This factor here could need some adjustment!!! 
qns  = fnval(scs,qx);g{3} = qns;

%%% Deect dinalmycally the edge. This is the max of the slope
Qoffset = qx(find(diff(qns) == max(diff(qns)))) - 1; 

if verbosity == 2
    figure(PHS1);hold on;
        stairs(qx,qns,'color','b');
        plot(oldQoffset,1,'.r','markersize',12);
            yaxis(1,verticalRange);
            xaxis(lowerQ4Display,higerQ4Display);
    figure(PHS2);hold on;
        stairs(qx,qns,'color','b');
        plot(oldQoffset,0,'.r','markersize',12);
            yaxis(0,verticalRange);xaxis(lowerQ4Display,higerQ4Display);
end


%%% Use the previous pedestal as a starting point.It will be open a window
cutIndex = find(  qx > Qoffset-searchWindow & qx < Qoffset+searchWindow);
qx_c = qx(cutIndex);g{4} = qx_c;
qns_c = qns(cutIndex);g{5} = qns_c;

%%% Some Cuts
%%%Delete small oscilations with diff  < 1. It also eliminats the descent part
I = find(diff(qns_c) < slotNegativeSloope); %This factor here could need some adjustment!!!
I = [1 I+1];
qns_c(I) = 0;

%% Cut the Q bins whih chrge above the peak of the Q spectra.
if(cutAboveMax)
    qx_cMax = qx_c(find (qns_c == max(qns_c)));
    Icut = find(qx_c > qx_cMax);
    qns_c(Icut) = 0;
end
 
if verbosity == 2
    figure(PHS1);hold on;
        line([Qoffset-searchWindow Qoffset-searchWindow],[1 verticalRange]);
        line([Qoffset+searchWindow Qoffset+searchWindow],[1 verticalRange]);
        plot(qx_c,qns_c,'.b','markersize',12)
    figure(PHS2);hold on;
        line([Qoffset-searchWindow Qoffset-searchWindow],[0 verticalRange]);
        line([Qoffset+searchWindow Qoffset+searchWindow],[0 verticalRange]);
        plot(qx_c,qns_c,'.b','markersize',12)
end

%%Select only no zero point for the fit
I = find(qns_c ~= 0);
p = polyfit(qx_c(I),qns_c(I),1);g{6} = p;




evalRange = [oldQoffset-searchWindow:oldQoffset+searchWindow];g{7} = evalRange;
if verbosity == 2
   figure(PHS1);hold on; 
        plot(evalRange,polyval(p,evalRange),'-k'); 
            yaxis(1,verticalRange);
            xaxis(evalRange(1)-30,evalRange(end)+30);
   figure(PHS2);hold on; 
        plot(evalRange,polyval(p,evalRange),'-k'); 
            yaxis(1,verticalRange);
            xaxis(evalRange(1)-30,evalRange(end)+30);
end

Qoffset = -p(2)/p(1);

if verbosity == 2
    figure(PHS1);hold on;
        plot(Qoffset,1,'.g','markersize',24);
            yaxis(1,verticalRange);
            xaxis(evalRange(1)-30,evalRange(end)+30);
    figure(PHS2);hold on;
        plot(Qoffset,1,'.g','markersize',24);
        xaxis(evalRange(1)-30,evalRange(end)+30);

    keyboard
    
    close(PHS1);close(PHS2)

end



return
