% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/doCalTDCs.m
% Purpose: doCalTDCs function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function doCalTDCs(inPath,conf)


daq = conf.daq;
OS = conf.OS;
b = getBarOS(OS);

for i=1:size(daq.TRB3.FPGAs,1)
    FPGA = daq.TRB3.FPGAs{i,1};
    if((strcmp(daq.TRB3.FPGAs{i,2},'TDC') | strcmp(daq.TRB3.FPGAs{i,2},'TDC-CTS')) & strcmp(daq.TRB3.FPGAs{i,3},'TRUE') & strcmp(daq.TRB3.FPGAs{i,3},'TRUE')) 
       message2log = ['Extracting TDC cal par from ' FPGA];disp(message2log);%write2log(conf.logs,message2log,'   ','syslog',OS); 
       
       files2Read = dir([inPath 'TDCCal' b '*' FPGA '*']);
       leadingTDCParMin   = [];leadingTDCParMax   = []; leadingEvents = [];
       trailingTDCParMin  = [];trailingTDCParMax  = [];trailingEvents = [];
       
       
       for j=1:length(files2Read)
           load([inPath 'TDCCal' b files2Read(j).name]);
           %Patch to avoid 1023 time
           I = find(leadingFineTime > 1000);leadingFineTime(I) = 0;
           I = find(trailingFineTime > 1000);trailingFineTime(I) = 0;
           %
           message2log = ['Extracting TDC cal par from ' FPGA];disp(message2log);%write2log(conf.logs,message2log,'   ','syslog',OS); 
           leadingTDCParMax = max([leadingTDCParMax; full(max(leadingFineTime))],[],1);
           trailingTDCParMax = max([trailingTDCParMax; full(max(trailingFineTime))],[],1);
           %Trick to calculate properly the min value.
           I = (leadingFineTime > 0); leadingFineTime_ =  leadingFineTime*0+1000; leadingFineTime_(I) =  leadingFineTime(I); leadingFineTime = leadingFineTime_;
           leadingEvents = sum([leadingEvents; sum(I)],1);
           I = (trailingFineTime > 0);trailingFineTime_ = trailingFineTime*0+1000;trailingFineTime_(I) = trailingFineTime(I);trailingFineTime = trailingFineTime_;
           trailingEvents = sum([trailingEvents; sum(I)],1);
           leadingTDCParMin = min([leadingTDCParMin; full(min(leadingFineTime))],[],1);
           trailingTDCParMin = min([trailingTDCParMin; full(min(trailingFineTime))],[],1);
       end
       %Eliminate the 1000 values added before
       I = find(leadingTDCParMin == 1000);leadingTDCParMin(I) = 0;
       leadingTDCPar = [leadingTDCParMin; leadingTDCParMax];
       I = find(trailingTDCParMin == 1000);trailingTDCParMin(I) = 0;
       trailingTDCPar = [trailingTDCParMin; trailingTDCParMax];
       mkdirOS([inPath 'TDCCal' b 'calPar' b],OS,1);
       tCalPar = [(1:64)' leadingTDCPar'];
       %Best guess to calcualte the spam of channel one.
       I = find(leadingTDCPar(1,:));tCalPar(1,2) = floor(mean(leadingTDCPar(1,I(2:end))));
       I = find(leadingTDCPar(2,:));tCalPar(1,3) = floor(mean(leadingTDCPar(2,I(2:end))));
       
       save([inPath 'TDCCal' b 'calPar' b 'timeCalibrationParameters' FPGA '.mat'],'leadingTDCPar','trailingTDCPar','leadingEvents','trailingEvents','tCalPar');
    end
    
end
return