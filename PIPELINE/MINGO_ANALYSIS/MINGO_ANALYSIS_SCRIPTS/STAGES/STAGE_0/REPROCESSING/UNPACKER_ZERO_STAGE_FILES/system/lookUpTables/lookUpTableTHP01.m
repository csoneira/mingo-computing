% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/system/lookUpTables/lookUpTableTHP01.m
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
              %Alarm active, mim value for alarm
              %Alarm active, max value for alarm
distributionLookUpTable = {...
                       1,          2,         3,          4,          5,          6,          7,          8;...
                'TEMP01',   'TEMP02',  'TEMP03',   'TEMP04',     'HR01',     'HR02',  'Press01',  'Press02';...
             'SELADA1M2','SELADA1M2','SELADA1M2','SELADA1M2','SELADA1M2','SELADA1M2','SELADA1M2','SELADA1M2';...
                     '' ,        '' ,       '' ,        '' ,         '',         '',         '',         '';...
                   {0,0},      {0,0},     {0,0},      {0,0},      {0,5},      {0,5},    {0,0.5},    {0,0.5};...
                 {0,0.5},    {0,0.5},   {0,0.5},    {0,0.5},    {0,5.8},    {0,5.8},    {0,0.0},   {0,0.0}};
