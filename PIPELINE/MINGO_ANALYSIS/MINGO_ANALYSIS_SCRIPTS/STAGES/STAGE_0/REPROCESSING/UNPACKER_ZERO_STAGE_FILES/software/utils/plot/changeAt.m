% Purpose: Apply a piecewise change to values at the configured boundary.

function changeAt(what,value,who)
%function changeAt(who,what,value)

if strcmp(what,'delete')
    if(nargin == 2)
        H = value;
    else
        H =  max(get(gca,'children'));
    end
    delete(H)
    return   
end


if(nargin == 2)
    H =  max(get(gca,'children'));
else
    H = who;
end


set(H,what,value)

return
