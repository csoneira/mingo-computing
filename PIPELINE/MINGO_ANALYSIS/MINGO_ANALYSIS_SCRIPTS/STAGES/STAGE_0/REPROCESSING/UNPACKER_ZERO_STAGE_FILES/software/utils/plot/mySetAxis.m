% Purpose: Set axis limits and formatting for legacy plots.

function mySetAxis(ax,axZoom,var)

if(isa(axZoom,'char'))
    if(strcmp(axZoom,'NONE') || strcmp(axZoom,'None'))
        %Do nothing
    elseif(strcmp(axZoom,'MM') || strcmp(axZoom,'mm'))%Set 1.2 0.8 around the max
        yaxisMM(var);
    end
else
    if(strcmp(ax,'x') || strcmp(ax,'X'))
        xaxis(axZoom(1),axZoom(2));
    elseif(strcmp(ax,'y') || strcmp(ax,'Y'))
        yaxis(axZoom(1),axZoom(2));
    elseif(strcmp(ax,'z') || strcmp(ax,'Z'))
        zaxis(axZoom(1),axZoom(2));
    else
    end
end
end
