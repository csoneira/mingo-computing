% Purpose: Draw the final reference line in a legacy plot.

function lastline(what,value)
%function lastline(what,value)
%set(max(get(gca,'children')),what,value)
if strcmp(what,'delete')
   delete(max(get(gca,'children')))
	return   
end
set(max(get(gca,'children')),what,value)
return
