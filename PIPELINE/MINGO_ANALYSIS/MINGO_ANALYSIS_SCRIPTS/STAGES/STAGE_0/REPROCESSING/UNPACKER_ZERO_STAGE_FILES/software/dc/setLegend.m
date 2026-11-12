% Purpose: Define setlegend values for the legacy Stage-0 unpacker.

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%% Set the legend
if(strcmp(interpreter,'matlab'))
    legH = get(axisH,'legend');
elseif(strcmp(interpreter,'octave'))
    try
        legH = get(axisH,'__legend_handle__');
    catch
        legH = [];
    end
end

if(length(legH) == 0)
    legH = legend(varName);
else
    if(strcmp(interpreter,'matlab'))
        S = get(legH,'String');
        S{end} = varName;
        set(legH,'String',S);
    elseif(strcmp(interpreter,'octave'))
        S = get(legH,'String');
        S = horzcat(S,varName);
        legend(S);
    end
end
set(legH,'visible','off');
if(axisLegend)
    set(legH,'visible','on');
    set(legH,'location','northwest');
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
