% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/sendData2DB_0.m
% Purpose: sendData2DB_0 function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [outputVars] = sendData2DB_0(inputVars)


conf            =   inputVars{1};
remoteIP        =   inputVars{2};
user            =   inputVars{3};
pass            =   inputVars{4};
port            =   inputVars{5};
tmpPathOut      =   inputVars{6};
systemName      =   inputVars{7};
dev2Distribute  =   inputVars{8};
varName         =   inputVars{9};
file2Send       =   inputVars{10};

%%%Build the script
fid = fopen([tmpPathOut 'sendData2DB.sh'],'w');
if fid == (-1)
    error('rdf: Could not open file:');
end
count = fprintf(fid,['PGPASSWORD=' pass ' psql -U ' user ' -p ' port ' -h ' remoteIP '  -d "' systemName '" -f - <<EOF\n']);
count = fprintf(fid,['\n']);
count = fprintf(fid,['CREATE TEMPORARY TABLE "tmp_table_' varName '" AS\n']);
count = fprintf(fid,['SELECT *\n']);
count = fprintf(fid,['FROM "' dev2Distribute '"."'  varName '"\n']);
count = fprintf(fid,['WITH NO DATA;\n']);
count = fprintf(fid,['\n']);
count = fprintf(fid,['ALTER TABLE "tmp_table_' varName '" ADD COLUMN idx SERIAL;\n']);
count = fprintf(fid,['%scopy "tmp_table_' varName '"(timestamps,values) FROM ''' file2Send ''' WITH ( FORMAT CSV, HEADER);\n'],'\');
count = fprintf(fid,['DELETE FROM "tmp_table_' varName '" a\n']);
count = fprintf(fid,['USING "tmp_table_' varName '" b\n']);
count = fprintf(fid,['WHERE\n']);
count = fprintf(fid,['a.timestamps=b.timestamps and a.idx>b.idx;\n']);
count = fprintf(fid,['ALTER TABLE "tmp_table_' varName '" DROP COLUMN idx;\n']);
count = fprintf(fid,['\n']);
count = fprintf(fid,['INSERT INTO "' dev2Distribute '"."'  varName '"\n']);
count = fprintf(fid,['SELECT *\n']);
count = fprintf(fid,['FROM "tmp_table_' varName '"\n']);
count = fprintf(fid,['ON CONFLICT (timestamps)\n']);
count = fprintf(fid,['DO UPDATE\n']);
count = fprintf(fid,['SET\n']);
count = fprintf(fid,['values=EXCLUDED.values;\n']);
count = fprintf(fid,['DROP TABLE "tmp_table_' varName '";\n']);
count = fprintf(fid,['\n']);
count = fprintf(fid,['EOF\n']);
fclose(fid);

[~, ~] = system(['chmod u+x ' tmpPathOut 'sendData2DB.sh']);
[~, ~] = system([tmpPathOut 'sendData2DB.sh']);

outputVars = 0;
return


