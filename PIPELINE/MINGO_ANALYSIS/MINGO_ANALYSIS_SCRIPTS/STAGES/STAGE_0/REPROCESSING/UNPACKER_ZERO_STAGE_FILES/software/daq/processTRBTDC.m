% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/processTRBTDC.m
% Purpose: processTRBTDC function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [T] = processTRBTDC(fileName,timeCalPar,inputPath)



load([inputPath fileName]);


eventsFromTime = size(leadingEpochCounter,1);
disp(['Loading ' fileName ' with ' num2str(eventsFromTime) ' events.']);

disp('Debug: Data being processed:');
disp(timeCalPar); % Replace 'data' with the actual variable being processed

load(timeCalPar);

timeCalPar_1 = repmat(tCalPar(:,2)',eventsFromTime,1);
timeCalPar_2 = repmat((5./(tCalPar(:,3)-tCalPar(:,2)))',eventsFromTime,1);


leadingTime_  = leadingCoarseTime*0; leadingTime  = leadingCoarseTime*0;Il  = find(leadingFineTime);
trailingTime_ = trailingCoarseTime*0;trailingTime = trailingCoarseTime*0;It = find(trailingFineTime);


leadingTime_(Il)  =  leadingEpochCounter(Il)*10240  + leadingCoarseTime(Il)*5   - ((leadingFineTime(Il) -timeCalPar_1(Il)).*timeCalPar_2(Il));
trailingTime_(It) = trailingEpochCounter(It)*10240  + trailingCoarseTime(It)*5  - ((trailingFineTime(It)-timeCalPar_1(It)).*timeCalPar_2(It));

Tref_leading                 = leadingTime_(:,1);
Tl                           = leadingTime_(:,2:end);
I = find(Tl); Tref_leading_  = repmat(Tref_leading,1,size(Tl,2));
leadingTime(I)               = Tl(I) - Tref_leading_(I);
clear Tl I Tref_leading_ leadingTime_


Tref_trailing                = trailingTime_(:,1);
Tt                           = trailingTime_(:,2:end);
I = find(Tt); Tref_trailing_ = repmat(Tref_leading,1,size(Tt,2));%We use here Tref_leading
trailingTime(I)              = Tt(I) - Tref_trailing_(I);
clear Tr I Tref_trailing_ trailingTime_
T = [Tref_leading Tref_trailing leadingTime trailingTime];

return
