% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/createReport.m
% Purpose: Configuration.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

%% Configuration
clear all;close all;

run('./conf/initConf.m');
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
run([HOME 'software/conf/loadGeneralConf.m']);



%% Load configuration
conf = initSystem();
conf = loadConfiguration({conf,HOSTNAME,SYSTEMNAME,HOME,SYS,INTERPRETER,OS});

b = conf.bar;
%
%
write2log(conf.logs,'','   ','syslog',OS);write2log(conf.logs,'','   ','syslog',OS);
message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
message2log = ['*** Starting the report.'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

%% Merge info
message2log = ['*** Merging files'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);
numberOfDevices = size(conf.dev,2);
for i=1:numberOfDevices
    reportable  = conf.dev(i).reportable.active;
    
    if reportable
        inPath               = conf.dev(i).dcs.path.data;
        outPath              = [conf.dev(i).dcs.path.data 'merge' b];
        lookUpTable          = [conf.dev(i).dcs.path.LT conf.dev(i).reportable.LT];
        time2Merge           = conf.dev(i).reportable.timeElapsed;
        lookUpTable = readLookUpTable(lookUpTable);
        
        numberOfVar2Report   = size(lookUpTable,2);
        for j = 1:numberOfVar2Report
            varName   =               lookUpTable{5,j};
            mergeable = myCellStr2num(lookUpTable(6,j));
            
            if      mergeable == 1 % This are the time like variables. Var + time stamp
                    mergeFiles({inPath,['*-' varName '.mat'],outPath,[varName '.mat'],time2Merge,INTERPRETER},{'timeStamp','R'},{'variable','R'})
            elseif  mergeable == 0
                files2Transport = dir([inPath '*' varName '.mat']);
                if (size(files2Transport,1) > 0)
                    system(['cp ' inPath b  files2Transport(end).name ' ' outPath files2Transport(end).name(12:end)]);
                    message2log = ['Copying last file ' files2Transport(end).name ' to merge folder'];
                    disp(message2log);
                    %write2log(conf.logs,message2log,'   ','syslog',OS);
                end
            end
        end
    end
end

%% Generate plot

message2log = ['*** Generating plots'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

numberOfDevices = size(conf.dev,2);
for i=1:numberOfDevices
    reportable  = conf.dev(i).reportable.active;
    if reportable
        inPath         = [conf.dev(i).dcs.path.data 'merge' b];
        outPath        = conf.dev(i).path.reporting;
        timeElapsed    = conf.dev(i).reportable.timeElapsed;
        device         = [conf.dev(i).name conf.dev(i).subName];
        lookUpTable    = [conf.dev(i).dcs.path.LT conf.dev(i).reportable.LT];
        interpreter    = conf.INTERPRETER;
        lookUpTable = readLookUpTable(lookUpTable);
        generatePlot({inPath,outPath,lookUpTable,timeElapsed,device,interpreter,OS});
    end
end

%% concat the pdfs and send the report
message2log = ['*** Concatening PDFs'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

files2Cat = [' -f'];
numberOfDevices = size(conf.dev,2);
for i=1:numberOfDevices
    reportable  = conf.dev(i).reportable.active;
    if reportable
        outPath        = conf.dev(i).path.reporting;
        device         = [conf.dev(i).name conf.dev(i).subName];
        files = dir([outPath device '*.pdf']);
        for j=1:length(files)
            files2Cat      = [files2Cat [' ' outPath files(j).name]];
        end
    end
end

telNumber = locatedev(SYSTEMNAME,conf);
system([path4sejda '/bin/sejda-console merge ' files2Cat '   -o ' [conf.dev(telNumber).path.reporting  date '-' conf.dev(telNumber).name '.pdf'] '  --overwrite']);
system(['cp ' conf.dev(telNumber).path.reporting  date '-' conf.dev(telNumber).name '.pdf ' conf.dev(telNumber).path.reporting  'report_' SYSTEMNAME '.pdf']);

message2log = ['***************************************************************'];
disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',OS);

