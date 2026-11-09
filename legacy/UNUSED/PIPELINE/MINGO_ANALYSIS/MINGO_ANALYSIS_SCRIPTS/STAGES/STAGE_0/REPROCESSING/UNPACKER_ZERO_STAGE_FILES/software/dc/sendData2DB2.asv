function sendData2DB2(inputVars)


remoteIP        =   inputVars{1};
user            =   inputVars{2};
port            =   inputVars{3};
tmpPathOut      =   inputVars{4};
systemName      =   inputVars{5};
dev2Distribute  =   inputVars{6};
varName         =   inputVars{7};
file2Send       =   inputVars{8};

%%%Build the script
fid = fopen([tmpPathOut 'sendData2DB.sh'],'w');
if fid == (-1)
    error('rdf: Could not open file:');
end


count = fprintf(fid,['PGPASSWORD=rpc@1234 psql -U ' user ' -p ' port ' -h ' remoteIP '  -d "' systemName '" -f - <<EOF\n']); % nova notacao ... -d "sRPC"
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

return


