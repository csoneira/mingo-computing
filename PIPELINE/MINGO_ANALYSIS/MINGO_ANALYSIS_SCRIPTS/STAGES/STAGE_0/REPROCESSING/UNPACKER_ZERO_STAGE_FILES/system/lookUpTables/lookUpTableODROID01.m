% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/system/lookUpTables/lookUpTableODROID01.m
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
         %Alarm active, min value for alarm, needed amout of repetitions needed to trigger
         %Alarm active, max value for alarm, needed amout of repetitions needed to trigger
         %Action active, min value for action, needed amout of repetitions needed to trigger, action
         %Action active, max value for action, needed amout of repetitions needed to trigger, action
distributionLookUpTable = {...
                       1,          2,          3;...
                'Disk01',   'Disk02',     'File';...
                 'DAQ01',    'DAQ01',    'DAQ01';...
                     '' ,         '',         '';...
                 {0,0,0},    {0,0,0}, {1,1000,1};...
                {1,80,1},   {1,80,1},   {0,90,0};...
              {0,0,0,''}, {0,0,0,''}, {0,0,0,''};...
              {0,0,0,''}, {0,0,0,''}, {0,0,0,''}};
