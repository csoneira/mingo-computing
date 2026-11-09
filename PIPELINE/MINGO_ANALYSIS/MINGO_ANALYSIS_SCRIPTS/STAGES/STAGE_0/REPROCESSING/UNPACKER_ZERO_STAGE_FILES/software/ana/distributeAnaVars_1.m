% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/distributeAnaVars_1.m
% Purpose: distributeAnaVars_1 function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [outputVars] = distributeAnaVars_1(inputVars)

%2020-03-16 - Modified to be abel to acumulate static variables,
%2020-10-15 - Modified to delete corrupted files
%
%
%
%

%% Load Variables
dateRegularFormat = inputVars{1};
var2Distribute    = inputVars{2};
filePrefix        = inputVars{3};varName = filePrefix(2:end-4);
dev2Find          = inputVars{4};dev2Distribute = dev2Find;
conf              = inputVars{5};
type              = inputVars{6};
subType           = inputVars{7};

b                 = conf.bar;
interpreter       = conf.INTERPRETER;
dev               = locatedev(dev2Find,conf);                                   %Devide        where send the data
outPath           = conf.dev(dev).dcs.path.data;                                %Path          where send the data 
outFile           = [datestr(dateRegularFormat, 'yyyy-mm-dd') filePrefix];      %Out File name where send the data 

if(isfield(conf,'DB'))
    if(conf.DB.active)
        remoteIP          = conf.DB.connection.remoteIP;
        user              = conf.DB.connection.user;
        pass              = conf.DB.connection.pass;
        port              = conf.DB.connection.port;
        systemName        = conf.SYSTEMNAME;

    end
else
    conf.DB.active    = 0;
end

%Write to log
if(conf.DB.active)
    message2log = ['Distribution locally and to DB  ' filePrefix ' to ' dev2Find];
else
    message2log = ['Distributing locally ' filePrefix ' to ' dev2Find];
end

disp(message2log);
write2log(conf.logs,message2log,'   ','syslog',conf.OS);

%%Process the variables depending on the type
%% This is just variables and timeStamp
if strcmp(type,'time')
    % Time type, just verify that file exist and append the variable
    path_ = outPath;file_ = outFile;
    myLoad;
    if(strcmp(myLoadStatus,'good'))
        timeStamp = [timeStamp; dateRegularFormat];
        variable  = [variable; var2Distribute];
    else
        timeStamp = dateRegularFormat;
        variable  = var2Distribute;
    end
    
    if strcmp('matlab',interpreter)
        save([outPath outFile],'timeStamp','variable');
    elseif strcmp('octave',interpreter)
        save([outPath outFile],'timeStamp','variable','-mat7-binary');
    end
   
    if (conf.DB.active)
        file2Send         = [conf.DB.tmpFolder dev2Distribute '_' varName '.csv'];
        writeCSV4DB({conf,file2Send,dateRegularFormat,varName,var2Distribute,type,subType});
        sendData2DB({conf,remoteIP,user,pass,port,conf.DB.tmpFolder,systemName,dev2Distribute,varName,file2Send});
    end
    
    
elseif strcmp(type,'static')
    if strcmp(subType,'hist')
        %%% Eliminate zeros and NaN
        keyboard
%         I = find(var2Distribute ~= 0 & ~isnan(var2Distribute));
%         
%         path_ = outPath;file_ = outFile;
%         myLoad;
% 
%         %%% Update the file
%         if(strcmp(myLoadStatus,'good'))
%             variable  = [variable; var2Distribute(I)];
%         else
%             variable  = var2Distribute(I);
%         end
%         
%         if strcmp('matlab',interpreter)
%             save([outPath outFile],'variable','dateRegularFormat');
%         elseif strcmp('octave',interpreter)
%             save([outPath outFile],'variable','dateRegularFormat','-mat7-binary');
%         end
    elseif strcmp(subType,'staticHist')
        path_ = outPath;file_ = outFile;
        myLoad;

        %%% Update the file
        if(strcmp(myLoadStatus,'good'))
            variableN  = var2Distribute{1};
            variableX  = variableX  + var2Distribute{2};
        else
            variableN  = var2Distribute{1};
            variableX  = var2Distribute{2};
        end
        
        if strcmp('matlab',interpreter)
            save([outPath outFile],'variableN','variableX','dateRegularFormat');
        elseif strcmp('octave',interpreter)
            save([outPath outFile],'variableN','variableX','dateRegularFormat','-mat7-binary');
        end 
        
        if (conf.DB.active)
            file2Send         = [conf.DB.tmpFolder dev2Distribute '_' varName '.csv'];
            writeCSV4DB({conf,file2Send,dateRegularFormat,varName,var2Distribute{2},type,subType});
            sendData2DB({conf,remoteIP,user,pass,port,conf.DB.tmpFolder,systemName,dev2Distribute,varName,file2Send});
        end
        
        
    elseif strcmp(subType,'staticHist2D')
        path_ = outPath;file_ = outFile;
        myLoad;

        %%% Update the file
        if(strcmp(myLoadStatus,'good'))
            variable1  = variable1  + squeeze(var2Distribute);
        else
            
            variable1  = squeeze(var2Distribute);
        end
        
        if strcmp('matlab',interpreter)
            save([outPath outFile],'variable1','dateRegularFormat');
        elseif strcmp('octave',interpreter)
            save([outPath outFile],'variable1','dateRegularFormat','-mat7-binary');
        end

        if (conf.DB.active)
            file2Send         = [conf.DB.tmpFolder dev2Distribute '_' varName '.csv'];
            writeCSV4DB({conf,file2Send,dateRegularFormat,varName,variable1,type,subType});
            sendData2DB({conf,remoteIP,user,pass,port,conf.DB.tmpFolder,systemName,dev2Distribute,varName,file2Send});
        end
    
    elseif strcmp(subType,'staticHist2D-ratio')
        path_ = outPath;file_ = outFile;
        myLoad;

        %%% Update the file
        if(strcmp(myLoadStatus,'good'))
            variable2 = variable2 + squeeze(var2Distribute{1}); 
            variable3 = variable3 + squeeze(var2Distribute{2}); 
            variable1 =                   variable2./variable3;%Ratio 
        else
            
            variable1 = squeeze(var2Distribute{1})./squeeze(var2Distribute{2});%Ratio 
            variable2 = squeeze(var2Distribute{1});                            %Var1 
            variable3 = squeeze(var2Distribute{2});                            %Var2 number of entries.  
        end
        
        if strcmp('matlab',interpreter)
            save([outPath outFile],'variable1','variable2','variable3','dateRegularFormat');
        elseif strcmp('octave',interpreter)
            save([outPath outFile],'variable1','variable2','variable3','dateRegularFormat','-mat7-binary');
        end 

        if (conf.DB.active)
            file2Send         = [conf.DB.tmpFolder dev2Distribute '_' varName '.csv'];
            writeCSV4DB({conf,file2Send,dateRegularFormat,varName,variable1,type,subType});
            sendData2DB({conf,remoteIP,user,pass,port,conf.DB.tmpFolder,systemName,dev2Distribute,varName,file2Send});
        end

    elseif strcmp(subType,'staticHist2D-average')
        path_ = outPath;file_ = outFile;
        myLoad;
        
        %%% Update the file
        if(strcmp(myLoadStatus,'good'))
            variable1 = (variable1.*variable2 +  squeeze(var2Distribute{1}).*squeeze(var2Distribute{2}))./(variable2 + var2Distribute{2});%Update the average
            variable2 = variable2 + squeeze(var2Distribute{2});%This are the number of entries in each bin just sum it
            I = isnan(variable1);variable1(I) = 0;
        else
            variable1 = squeeze(var2Distribute{1});
            variable2 = squeeze(var2Distribute{2});%This are the number of entries in each bin
            
        end
        
        if strcmp('matlab',interpreter)
            save([outPath outFile],'variable1','variable2','dateRegularFormat');
        elseif strcmp('octave',interpreter)
            save([outPath outFile],'variable1','variable2','dateRegularFormat','-mat7-binary');
        end

        if (conf.DB.active)
            file2Send         = [conf.DB.tmpFolder dev2Distribute '_' varName '.csv'];
            writeCSV4DB({conf,file2Send,dateRegularFormat,varName,variable1,type,subType});
            sendData2DB({conf,remoteIP,user,pass,port,conf.DB.tmpFolder,systemName,dev2Distribute,varName,file2Send});
        end

    
    elseif strcmp(subType,'XYmap')
        keyboard
%         path_ = outPath;file_ = outFile;
%         myLoad;
%         
%         %%% Update the file
%         if(strcmp(myLoadStatus,'good'))
%             variable  = variable + var2Distribute;
%         else
%             variable  = var2Distribute;
%         end
%         
%         if strcmp('matlab',interpreter)
%             save([outPath outFile],'variable','dateRegularFormat');
%         elseif strcmp('octave',interpreter)
%             save([outPath outFile],'variable','dateRegularFormat','-mat7-binary');
%         end
    elseif strcmp(subType,'Qmap')
        keyboard
%         path_ = outPath;file_ = outFile;
%         myLoad;
%         if(strcmp(myLoadStatus,'good'))
%             try
%             for i =1:size(var2Distribute,1)*size(var2Distribute,2)
%                 variable{i} = [variable{i}; var2Distribute{i}];
%             end
%             catch
%                 keyboard
%             end
%         else
%             variable  = var2Distribute;
%         end
%         
%         if strcmp('matlab',interpreter)
%             save([outPath outFile],'variable','dateRegularFormat');
%         elseif strcmp('octave',interpreter)
%             save([outPath outFile],'variable','dateRegularFormat','-mat7-binary');
%         end
    elseif strcmp(subType,'QmapDS')
        keyboard
%         dowScaling     = var2Distribute{2};
%         var2Distribute = var2Distribute{1};
%         path_ = outPath;file_ = outFile;
%         myLoad;
%         if(strcmp(myLoadStatus,'good'))
%             for i =1:size(var2Distribute,1)*size(var2Distribute,2)
%                 variable{i} = [variable{i}; var2Distribute{i}(1:dowScaling:end)];
%             end
% 
%         else
%             variable = cell(size(var2Distribute));
%             for i =1:size(var2Distribute,1)*size(var2Distribute,2)
%                     variable{i} = var2Distribute{i}(1:dowScaling:end);
%             end
%         end
% 
%         if strcmp('matlab',interpreter)
%             save([outPath outFile],'variable','dateRegularFormat');
%         elseif strcmp('octave',interpreter)
%             save([outPath outFile],'variable','dateRegularFormat','-mat7-binary');
%         end
     elseif strcmp(subType,'STmap')
         keyboard
%          path_ = outPath;file_ = outFile;
%          myLoad;
%          if(strcmp(myLoadStatus,'good'))
%             variable1  = variable1 + var2Distribute{1};%ST hits
%             variable2  = variable2 + var2Distribute{2};%hits
%         else
%             variable1  = var2Distribute{1};
%             variable2  = var2Distribute{2};
%         end
%         
%         if strcmp('matlab',interpreter)
%             save([outPath outFile],'variable1','variable2','dateRegularFormat');
%         elseif strcmp('octave',interpreter)
%             save([outPath outFile],'variable1','variable2','dateRegularFormat','-mat7-binary');
%         end
    end 
else
end

outputVars = 0;
return