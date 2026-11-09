% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/doSTAna.m
% Purpose: doSTAna function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function OutputVars = doSTAna(inPath,inPathPed,file2ana,indx,conf)

%% Select the right pedestal file
%% Load files
load([inPathPed conf.ana.calibration.QPEDParam]);
load([inPathPed conf.ana.calibration.LonYParam]);
load([inPath file2ana])


 
numberOfPlanes = conf.ana.param.strips.planes;
for plane = 1:numberOfPlanes
      eval(['TF = T' num2str(plane) '_F(indx,:);']);eval(['TB = T' num2str(plane) '_B(indx,:);']);eval(['QF = Q' num2str(plane) '_F(indx,:);']);eval(['QB = Q' num2str(plane) '_B(indx,:);']);  
      OutputVars{plane} = anaPlaneStrips(TF,TB,QF,QB,QOffSets(:,(1:2)+(2*plane-2)),YCenters(:,plane),EBtime,conf);
end


% OutputVars{1}{4} OutputVars{1}{5}]
% %%%
% LI_Qsc_M2_Qsc_High       = Qsc(:,21) > 500 & Qsc(:,24) > 500;
% indx                     = find(LI_Qsc_M2_Qsc_High);
% eff_hits                 = length(indx);
% eff_det                  = length(find(Q1_(indx) > 0));
% eff_Q                    = nanmean(Q1_(indx));
% eff_x                    = nanmean(X1_(indx));
% eff_y                    = nanmean(Y1_(indx));
% eff                      = [eff_hits eff_det eff_Q eff_x eff_y];

if(conf.ana.calibration.longitudinalY.active  == 1)
    XY = [];
    for plane = 1:numberOfPlanes
        XY = [XY  OutputVars{plane}{5} OutputVars{plane}{6}];
    end
    
    %%% For Calibration X1, Y1 is uncalibrated position
    if strcmp('matlab',conf.INTERPRETER)
        save([conf.ana.calibration.longitudinalY.path file2ana],'XY');
    elseif strcmp('octave',conf.INTERPRETER)
        save([conf.ana.calibration.longitudinalY.path file2ana],'XY')
    end
end

if(conf.ana.scintAna.active == 1)
    I = find(Qsc(:,21) > 0 | Qsc(:,24) > 0);                         %RPC Calibrated vars                                    %RPC Raw                                           %Scint
    saveIndexedVars(conf.INTERPRETER,conf.ana.scintAna.path,file2ana,T_(I,:),'T',Q1_(I,:),'Q',X1_(I),'X',Y1_(I),'Y',T_F(I,:),'T_F',T_B(I,:),'T_B',Q_F(I,:),'Q_F',Q_B(I,:),'Q_B',Tsc(I,:),'Tsc',Qsc(I,:),'Qsc',EBtime(I),'EBtime');
end    

if(conf.ana.backgroundAna.active == 1)                           
    saveIndexedVars(conf.INTERPRETER,conf.ana.backgroundAna.path,file2ana,OutputVars,'OutputVars',EBtime,'EBtime');
end

return
