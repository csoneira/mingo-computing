% Purpose: Send an alarm notification for the detected condition.

function sendAlarm(inputVars)
%
%2020-03-16 - Possibility to modifiy the number of inputs dinamically.
%2020-03-16 - System variable introduced
%
%sendAlarm(alarm, message, system)
%alarm      => flag if 1 alarm is send
%message    => message of the alarm
%system     => system name

alarm      = inputVars{1};
message    = inputVars{2};
                            if (size(inputVars,2) == 3); 
system     = inputVars{3};
                            else system = 'System'; end


if(alarm.active == 1)
subject     = [system ' alarm: ' alarm.type];

to          = alarm.TO;
message     = message; 
attachment  = {''};
sendbashEmail(subject,to,message,attachment);   

    
end
return
