% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/distributeVars.m
% Purpose: distributeVars function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function distributeVars(inputVars)
%2023-10-17 - Implementation of the inputVars
%
%


systemName    =   inputVars{1};
device        =   inputVars{2};
inPath        =   inputVars{3};
LT            =   inputVars{4};
conf          =   inputVars{5};
logs          =   inputVars{6};
interpreter  =   inputVars{7};
alarms        =   inputVars{8};
OS            =   inputVars{9};


b = getBarOS(OS);


%% distribute the information
s = dir([inPath '*.mat']);

if (length(s) > 0)
    try
        for i=1:size(s,1)
            
            fileName = s(i).name;
            dateFromFile =  fileName(1:10);
            
            load([inPath fileName]);
            
            run(LT);
                        
            for j=1:size(distributionLookUpTable,2)
                column2Index    = distributionLookUpTable{1,j};
                varName         = distributionLookUpTable{2,j};
                dev2Distribute  = [distributionLookUpTable{3,j} distributionLookUpTable{4,j}];
                devIndex        = locatedev(dev2Distribute,conf);
                outPath         = conf.dev(devIndex).dcs.path.data;
                
                timeStamp     = time;
                variable      = data(:,column2Index);
                if strcmp('matlab',interpreter)
                    save([outPath  dateFromFile '-' varName '.mat'],'timeStamp','variable');
                elseif strcmp('octave',interpreter)
                    save([outPath  dateFromFile '-' varName '.mat'],'timeStamp','variable','-mat7-binary');
                else
                end

                message2log = ['Distributing ' varName ' to ' dev2Distribute ' from file ' inPath fileName ];
                disp(message2log);
                write2log(logs,message2log,'   ','syslog',OS);
                
                if(conf.DB.active == 1 & conf.DB.DistributeDCSVars == 1)
                    connect2DB({conf});
                    try
                        remoteIP  = conf.DB.connection.remoteIP;
                        user      = conf.DB.connection.user;
                        pass      = conf.DB.connection.pass;
                        port      = conf.DB.connection.port;
                        file2Send = [conf.DB.tmpFolder dev2Distribute '_' varName '.csv'];
                        type      = 'time';
                        subType   = '';

                        
                        writeCSV4DB({conf,file2Send,timeStamp,varName,variable,type,subType});
                        sendData2DB({conf,remoteIP,user,pass,port,conf.DB.tmpFolder,systemName,dev2Distribute,varName,file2Send});

                        message2log = ['Distributing to DB ' varName ' to ' dev2Distribute ' from file ' inPath fileName ];
                        disp(message2log);
                        write2log(logs,message2log,'   ','syslog',OS);

                    catch
                        message2log = ['Error on distributing to DB ' varName ' to ' dev2Distribute ' from file ' inPath fileName ];
                        disp(message2log);
                        write2log(logs,message2log,'   ','syslog',OS);
                    end
                end


                
            end
            
            system(['mv ' inPath fileName ' ' inPath 'done' b]);
        end
    catch exception
        keyboard
        fullMessage = [];
        for j = 1:length(exception.stack)
            message2log = ['Error in: ' exception.stack(j).file ' line ' num2str(exception.stack(j).line)];
            fullMessage = [fullMessage ' ' message2log];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
            write2log(logs,message2log,'   ','criticallog',OS);
        end
        alarmType = 'unpackDCS';
        processAlarm(systemName,device,alarmType,fullMessage,alarms);
    end
else
    message2log = ['No files to distribute. Skipping'];
    disp(message2log);
    write2log(logs,message2log,'   ','syslog',OS);
end
return