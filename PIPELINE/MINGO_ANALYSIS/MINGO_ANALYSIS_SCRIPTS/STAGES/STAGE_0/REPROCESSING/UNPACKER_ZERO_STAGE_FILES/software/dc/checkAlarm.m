% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/checkAlarm.m
% Purpose: checkAlarm function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function checkAlarm(varargin)

device       = varargin{1};
lookUpTable  = varargin{2};
logs         = varargin{3};
alarms       = varargin{4};
SYSTEMNAME   = varargin{5};
conf         = varargin{6};


N = sprintf('\n');

run(lookUpTable);


for j=1:size(distributionLookUpTable,2)
                column2Index    = distributionLookUpTable{1,j};
                varName         = distributionLookUpTable{2,j};
                dev2Distribute  = [distributionLookUpTable{3,j} distributionLookUpTable{4,j}];
                devIndex        = locatedev(dev2Distribute,conf);
                path            = conf.dev(devIndex).dcs.path.data;
                
                minAlarmActive  = distributionLookUpTable{5,j}{1};
                minAlarmValue   = distributionLookUpTable{5,j}{2};
                    if size(distributionLookUpTable{5,j},2) > 2 
                        minAlarmRep   = distributionLookUpTable{5,j}{3};
                    else
                        minAlarmRep   = 1;
                    end
                                
                maxAlarmActive  = distributionLookUpTable{6,j}{1};
                maxAlarmValue   = distributionLookUpTable{6,j}{2};
                    if size(distributionLookUpTable{6,j},2) > 2 
                        maxAlarmRep   = distributionLookUpTable{6,j}{3};
                    else
                        maxAlarmRep   = 1;
                    end
                
                
                %Check the  size of the distributionlookUpTable if it is > 6 => actions are included
                if (size(distributionLookUpTable,1) > 6)
                    minActionActive = distributionLookUpTable{7,j}{1};
                    minActionValue  = distributionLookUpTable{7,j}{2};
                    minActionRep    = distributionLookUpTable{7,j}{3};
                    minAction       = distributionLookUpTable{7,j}{4};
                    
                    maxActionActive = distributionLookUpTable{8,j}{1};
                    maxActionValue  = distributionLookUpTable{8,j}{2};
                    maxActionRep    = distributionLookUpTable{8,j}{3};
                    maxAction       = distributionLookUpTable{8,j}{4};
                else
                    minActionActive = 0;
                    minActionValue  = 0;
                    minAction       = 0;
                    
                    maxActionActive = 0;
                    maxActionValue  = 0;
                    maxAction       = 0;
                end
                
                
                s = dir([path '*' varName '*']);
                
                if(length(s) == 0)%Alarm if there is no file
                          message2log = ['The log file of variable ' varName ' from device ' dev2Distribute  ' is not present but Alarm is armed. Please check'];   
                          inputvars = {alarms(locateAlarm('Online Monitoring',alarms)),message2log,SYSTEMNAME};sendAlarm(inputvars);
                else              %Check the variable and alarm if needed
                          %Just load the last file but could be better. 
                          load([path s(end).name]);
                          %Find the values of last hour
                          I = find(-etime(datevec(timeStamp),datevec(repmat(now,length(timeStamp),1))) < 60*60*0.9);
                                                    
                          if minAlarmActive
                              J = find(variable(I) < minAlarmValue);
                              if length(J) >= minAlarmRep
                                  message2log = ['Variable ' varName ' on ' dev2Distribute ' with value lower than minimum ' num2str(minAlarmValue) '  ' N 'See values below:' N N];
                                  for i=1:length(J)
                                      message2log = [message2log datestr(timeStamp(I(J(i))),0) ' ==> ' num2str(variable(I(J(i)))) N];
                                  end
                                  
                                  disp(message2log);
                                  inputvars = {alarms(locateAlarm('Online Monitoring',alarms)),message2log,SYSTEMNAME};sendAlarm(inputvars);      
                                  
                                  if minActionActive
                                      J = find(variable(I) < minActionValue);
                                      if length(J) > minActionRep
                                          message2log = ['Variable ' varName ' on ' dev2Distribute ' with value lower than minimum ' num2str(minAlarmValue) ' found more than ' num2str(minActionRep) ' times => ' N ...
                                                        'Executing  ' maxAction N ...
                                                        'See values below:' N N];    
                                          for i=1:length(J)
                                                message2log = [message2log datestr(timeStamp(I(J(i))),0) ' ==> ' num2str(variable(I(J(i)))) N];
                                          end
                                                    
                                          disp(message2log);
                                          inputvars = {alarms(locateAlarm('Online Monitoring',alarms)),message2log,SYSTEMNAME};sendAlarm(inputvars);  
                                          
                                          %%Execute and check if it was ok.
                                      end
                                  end
                                  
                              end
                          end
                          
                          if maxAlarmActive
                              J = find(variable(I) > maxAlarmValue);
                              if length(J) >= maxAlarmRep
                                  message2log = ['Variable ' varName ' on ' dev2Distribute ' with value higher than maximum ' num2str(maxAlarmValue) '  ' N 'See values below:' N N];
                                  for i=1:length(J)
                                      message2log = [message2log datestr(timeStamp(I(J(i))),0) ' ==> ' num2str(variable(I(J(i)))) N];
                                  end
                                  
                                  disp(message2log);
                                  inputvars = {alarms(locateAlarm('Online Monitoring',alarms)),message2log,SYSTEMNAME};sendAlarm(inputvars);            
                                  
                                  if maxActionActive
                                      J = find(variable(I) > maxActionValue);
                                      if length(J) > maxActionRep
                                          message2log = ['Variable ' varName ' on ' dev2Distribute ' with value higher than maximum ' num2str(minAlarmValue)  ' found more than ' num2str(maxActionRep) ' times => ' N ...
                                                        'Executing  ' maxAction N ...
                                                        'See values below:' N N];              
                                          for i=1:length(J)
                                                message2log = [message2log datestr(timeStamp(I(J(i))),0) ' ==> ' num2str(variable(I(J(i)))) N];
                                          end
                                                           
                                          disp(message2log);
                                          inputvars = {alarms(locateAlarm('Online Monitoring',alarms)),message2log,SYSTEMNAME};sendAlarm(inputvars);  
                                          
                                          %%Execute and check if it was ok.
                                          [status, result] = system([maxAction]);
                                           message2log = ['Variable ' varName ' on ' dev2Distribute ' with value higher than maximum ' num2str(minAlarmValue)  ' found more than ' num2str(maxActionRep) ' times => ' N ...
                                                          'the output of executing  ' maxAction ' is below:' N ...
                                                          result ];
                                          
                                          disp(message2log);
                                          inputvars = {alarms(locateAlarm('Online Monitoring',alarms)),message2log,SYSTEMNAME};sendAlarm(inputvars);                                          
                                      end
                                  end
                              end
                          end
                                               
                end
                
end

return