% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/system/lookUpTables/lookUpTableTRB.m
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
              %Operation to be performed
distributionLookUpTable = {...
                       1,          2,             3,         4,          4,          5,          5,          6,          6,          7,          7,          8,          9,         10,         11;...
          'RateAsserted','RateEdges','RateAccepted',    'Rate','RateRPC04',     'Rate','RateRPC03',     'Rate','RateRPC02',     'Rate','RateRPC01',   'Rate01',   'Rate02',   'Rate03',   'Rate04';...
                 'mingo',    'mingo',       'mingo',     'RPC',    'mingo',      'RPC',    'mingo',      'RPC',    'mingo',      'RPC',    'mingo',    'mingo',    'mingo',    'mingo',    'mingo';...
                   '01' ,      '01' ,         '01' ,     '04' ,      '01' ,       '03',       '01',       '02',       '01',       '01',       '01',       '01',       '01',       '01',       '01';...
               {0,0,1  },  {0,0,1  },     {1,4,1  }, {0,0,1  },  {0,0,1  },  {0,0,1  },  {0,0,1  },  {0,0,1  },  {0,0,1  },  {0,0,1  },  {0,0,1  },  {0,0,1  },  {0,0,1  },  {0,0,1  },  {0,0,1  };...
              {0,90,1  }, {0,90,1  },    {0,90,1  },{0,90,1  }, {0,90,1  }, {0,90,1  }, {0,90,1  }, {0,90,1  }, {0,90,1  }, {0,90,1  }, {0,90,1  }, {0,90,1  }, {0,90,1  }, {0,90,1  }, {0,90,1  };...
              {0,0,0,''}, {0,0,0,''},    {0,0,0,''},{0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''};...
              {0,0,0,''}, {0,0,0,''},    {0,0,0,''},{0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''}, {0,0,0,''};...
                      };



