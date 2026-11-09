% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/system/lookUpTables/lookUpTableFlow.m
% Purpose: Column.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

              %Column
              %varName
              %devName
              %devsubNam
              %Alarm active
              %Alarm active, min value for alarm, needed amout of repetitions needed to trigger
              %Alarm active, max value for alarm, needed amout of repetitions needed to trigger
              %Action active, min value for action, needed amout of repetitions needed to trigger, action
              %Action active, max value for action, needed amout of repetitions needed to trigger, action

distributionLookUpTable = {...
                       1,          2,          3,          4;...
                'Flow01',   'Flow02',   'Flow03',   'Flow04';... 
                 'mingo',    'mingo',    'mingo',    'mingo';...
                    '01',       '01',       '01',       '01';...
                 {0,0,1},    {0,0,1},    {0,5,1},    {0,5,1};...
               {0,0.5,1},  {0,0.5,1},  {0,6.4,1},  {0,6.4,1};...
             {0,20,0,''},{0,20,0,''},{0,20,0,''},{0,20,0,''};...
             {0,20,0,''},{0,46,5,''},{0,20,0,''},{0,20,0,''}...
                   };
