% Purpose: Process Exception for the legacy unpacker.

function message2log = processException(exception)
                        

fullMessage = [];
fullMessage = [fullMessage exception.message];

for j = 1:length(exception.stack)
    message_ = ['Error in: ' exception.stack(j).file ' line ' num2str(exception.stack(j).line)];
    fullMessage = [fullMessage ' ' message_];
end

message2log = fullMessage;
 
return
