% Purpose: Set the displayed data range for a legacy plot.

function range = mySetRange(ax,axRange,var)

if(isa(axRange,'char'))
    if(strcmp(axRange,'NONE') || strcmp(axRange,'None'))
        %Do nothing
    elseif(strcmp(axRange(1:end-3),'MEDIAN') || strcmp(axRange(1:end-3),'Median'))
        range(1) = 0; 
        range(2) = median(median(var))*str2num(axRange(end-2:end));
    end
else
    if(strcmp(ax,'x') || strcmp(ax,'X'))
        %
    elseif(strcmp(ax,'y') || strcmp(ax,'Y'))
        %
    elseif(strcmp(ax,'z') || strcmp(ax,'Z'))
        range = axRange;
    else
    end
end



return
