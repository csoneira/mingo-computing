% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ana/prepareAna.m
% Purpose: prepareAna function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function prepareAna(inPath,outputPath,conf)



try
    OS                 = conf.OS;
    b                  = getBarOS(OS);
    interpreter        = conf.INTERPRETER;


    numberOfPlanes     = conf.ana.param.strips.planes;
    


    %% Lunch the standard analisys
    file2ana = dir([inPath '*.mat']);
    if (length(file2ana) > 1)
        
        %%% Loop on the file
        for i=1:length(file2ana)
            message2log = ['Starting ana on               ' file2ana(i).name];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
            dateRegularFormat = hadesData2Regular(file2ana(i).name(1:end-4));
            inPathPed = conf.daq.raw2var.path.lookUpTables;

            try
                load([inPath file2ana(i).name],'triggerType');
            catch
                message2log = ['Corrupted file found          ' file2ana(i).name ' moving to done'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',OS);
                mvOS(inPath, [inPath 'done/'],file2ana(i).name,OS);
                continue
            end

            %%%Check if there is Physics events
            indx = find(triggerType == 1);
            if(length(indx) > 100)
                message2log = ['Starting physics ana on       ' file2ana(i).name ' with ' num2str(length(indx)) ' events'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
                                
                outputVarsPlane     = doAna(inPath,inPathPed,file2ana(i).name,indx,conf);
                outPutVarsTelescope = doEffcalculation(outputVarsPlane,conf);


                for plane = 1:numberOfPlanes
                    Events = outputVarsPlane{plane}{2};
                    if (Events > 100)
                        device          = ['RPC0' num2str(plane)];
                        Qmean           = outputVarsPlane{plane}{11};
                        QmeanNoStr      = outputVarsPlane{plane}{12};
                        Qmedian         = outputVarsPlane{plane}{13};
                        QmedianNoStr    = outputVarsPlane{plane}{14};
                        Str             = outputVarsPlane{plane}{15};
                        Qhist           = outputVarsPlane{plane}{20};
                        XY              = outputVarsPlane{plane}{16};
                        XY_Qmean        = outputVarsPlane{plane}{17};
                        XY_Str          = outputVarsPlane{plane}{19};
                        
                        Eff             = outPutVarsTelescope{1}(plane);
                        XY_hit          = outPutVarsTelescope{2}(:,:,plane);
                        XY_det          = outPutVarsTelescope{3}(:,:,plane);
                        

                        message2log = ['Distribution files from       ' file2ana(i).name ' in plane ' num2str(plane)];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',OS);

                        [~] = distributeAnaVars({dateRegularFormat,                         Qmean,       '-QMean.mat',device,conf,  'time',                'none'});
                        [~] = distributeAnaVars({dateRegularFormat,                    QmeanNoStr,  '-QMeanNoStr.mat',device,conf,  'time',                'none'});
                        [~] = distributeAnaVars({dateRegularFormat,                       Qmedian,     '-QMedian.mat',device,conf,  'time',                'none'});
                        [~] = distributeAnaVars({dateRegularFormat,                  QmedianNoStr,'-QMedianNoStr.mat',device,conf,  'time',                'none'});
                        [~] = distributeAnaVars({dateRegularFormat,                           Str,         '-Str.mat',device,conf,  'time',                'none'});
                        [~] = distributeAnaVars({dateRegularFormat,                           Eff,         '-Eff.mat',device,conf,  'time',                'none'});

                        [~] = distributeAnaVars({dateRegularFormat,                         Qhist,           '-Q.mat',device,conf,'static',          'staticHist'});
                        [~] = distributeAnaVars({dateRegularFormat,                            XY,       '-xyMap.mat',device,conf,'static',        'staticHist2D'});
                        [~] = distributeAnaVars({dateRegularFormat,                 {XY_Qmean,XY},    '-QMapMean.mat',device,conf,'static','staticHist2D-average'});
                        [~] = distributeAnaVars({dateRegularFormat,                   {XY_Str,XY},      '-StrMap.mat',device,conf,'static',  'staticHist2D-ratio'});
                        [~] = distributeAnaVars({dateRegularFormat,               {XY_det,XY_hit},      '-EffMap.mat',device,conf,'static',  'staticHist2D-ratio'});
                    else
                        message2log = ['skipping                      ' file2ana(i).name ' in plane ' num2str(plane) ' due to lack of events'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
                    end
                end
                
                if(conf.ana.keepFiles.TriggerType1 == 1)
                    saveIndxData({inPath,[outputPath 'TT1' b datestr(dateRegularFormat, 'yyyy-mm-dd') b],file2ana(i).name,indx,conf})
                    message2log = ['Saving physTrigger file from  ' file2ana(i).name];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
                end
                
                if(conf.ana.keepVars.TriggerType1 == 1)
                    if strcmp('matlab',interpreter)
                        save([outputPath 'Vars' b 'TT1' b file2ana(i).name],'outputVarsPlane','outPutVarsTelescope');
                    elseif strcmp('octave',interpreter)
                        save([outputPath 'Vars' b 'TT1' b file2ana(i).name],'outputVarsPlane','outPutVarsTelescope','-mat7-binary');
                    end
                    message2log = ['Saving physTrigger data from  ' file2ana(i).name];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
                end
                
                clear outputVarsPlane outPutVarsTelescope indx                 

                message2log = ['Physics ana on                ' file2ana(i).name ' finished.'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
            else
                message2log = ['Skipping physics ana on       ' file2ana(i).name ' due to lack of events'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
            end

            %%%Check if there is ST events
            load([inPath file2ana(i).name],'triggerType');
            indx = find(triggerType == 2);
            if(length(indx) > 2000)
                message2log = ['Starting selfTrigger ana on   ' file2ana(i).name  ' with ' num2str(length(indx)) ' events'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
                load([inPath file2ana(i).name]);

                outputVarsPlane = doSTAna(inPath,inPathPed,file2ana(i).name,indx,conf);

                
                for plane = 1:numberOfPlanes
                    Events = outputVarsPlane{plane}{2};
                    if (Events > 2000)
                        device          = ['RPC0' num2str(plane)];
                        Qmean           = outputVarsPlane{plane}{11};
                        QmeanNoStr      = outputVarsPlane{plane}{12};
                        Qmedian         = outputVarsPlane{plane}{13};
                        QmedianNoStr    = outputVarsPlane{plane}{14};
                        Str             = outputVarsPlane{plane}{15};
                        Qhist           = outputVarsPlane{plane}{20};
                        XY              = outputVarsPlane{plane}{16};
                        XY_Qmean        = outputVarsPlane{plane}{17};
                        XY_Str          = outputVarsPlane{plane}{19};

                        message2log = ['Distribution files from       ' file2ana(i).name ' in plane ' num2str(plane)];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',OS);

                        [~] = distributeAnaVars({dateRegularFormat,                         Qmean,       '-QMean-ST.mat',device,conf,  'time',                'none'});
                        [~] = distributeAnaVars({dateRegularFormat,                    QmeanNoStr,  '-QMeanNoStr-ST.mat',device,conf,  'time',                'none'});
                        [~] = distributeAnaVars({dateRegularFormat,                       Qmedian,     '-QMedian-ST.mat',device,conf,  'time',                'none'});
                        [~] = distributeAnaVars({dateRegularFormat,                  QmedianNoStr,'-QMedianNoStr-ST.mat',device,conf,  'time',                'none'});
                        [~] = distributeAnaVars({dateRegularFormat,                           Str,         '-Str-ST.mat',device,conf,  'time',                'none'});

                        [~] = distributeAnaVars({dateRegularFormat,                         Qhist,          '-Q-ST.mat',device,conf,'static',          'staticHist'});
                        [~] = distributeAnaVars({dateRegularFormat,                            XY,      '-xyMap-ST.mat',device,conf,'static',        'staticHist2D'});
                        [~] = distributeAnaVars({dateRegularFormat,                 {XY_Qmean,XY},   '-QMapMean-ST.mat',device,conf,'static','staticHist2D-average'});
                        [~] = distributeAnaVars({dateRegularFormat,                   {XY_Str,XY},     '-StrMap-ST.mat',device,conf,'static',  'staticHist2D-ratio'});

                    else
                        message2log = ['skipping                        ' file2ana(i).name ' in plane ' num2str(plane) ' due to lack of events'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
                    end
                end

                if(conf.ana.keepFiles.TriggerType2 == 1)
                    saveIndxData({inPath,[outputPath 'TT2' b datestr(dateRegularFormat, 'yyyy-mm-dd') b],file2ana(i).name,indx,conf})
                    message2log = ['Saving selfTrigger file from  ' file2ana(i).name];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
                end
                
                if(conf.ana.keepVars.TriggerType2 == 1)
                    if strcmp('matlab',interpreter)
                        save([outputPath 'Vars' b 'TT2' b file2ana(i).name],'outputVarsPlane');
                    elseif strcmp('octave',interpreter)
                        save([outputPath 'Vars' b 'TT2' b file2ana(i).name],'outputVarsPlane','-mat7-binary');
                    end
                    message2log = ['Saving selfTrigger data from  ' file2ana(i).name];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
                end
                
                clear outputVarsPlane indx
                
                message2log = ['SelfTrigger ana on                ' file2ana(i).name ' finished.'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
            else
                message2log = ['Skipping selfTrigger ana on       ' file2ana(i).name ' due to lack of events'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',conf.OS);
            end

            
            if(conf.daq.raw2var.keepRawFiles == 1)
                mkdirOS([outputPath datestr(dateRegularFormat, 'yyyy-mm-dd') b],OS,1);
                mvOS(inPath,[inPath 'done' b],file2ana(i).name,OS);
            else
                system(['rm ' inPath file2ana(i).name]);
            end
        end
       
    else
        message2log = ['No files to read. Skipping'];disp(message2log);write2log(conf.logs,message2log,'   ','syslog',OS);
    end

catch exception
    message2log = ['Error identifier: ' exception.identifier '      with message     '  exception.message];
    disp(message2log);
    write2log(conf.logs,message2log,'   ','syslog',OS);
    write2log(conf.logs,message2log,'   ','criticallog',OS);
    for i = 1:length(exception.stack)
        message2log = ['Error in: ' exception.stack(i).file ' line ' num2str(exception.stack(i).line)];
        disp(message2log);
        write2log(conf.logs,message2log,'   ','syslog',OS);
        write2log(conf.logs,message2log,'   ','criticallog',OS);
    end
end
return
