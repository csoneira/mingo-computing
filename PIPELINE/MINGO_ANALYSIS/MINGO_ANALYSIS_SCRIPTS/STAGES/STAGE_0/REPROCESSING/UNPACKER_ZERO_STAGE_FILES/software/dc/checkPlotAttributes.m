% Purpose: Set and validate default attributes for detector plots.

%First the default values

yLogActivated      = 0;
colorType          = 'k';
xaxisLabel         = '';
yaxisLabel         = '';
xZoom              = 'NONE';
yZoom              = 'MM';
zZoom              = 'NONE';
xyMAP_zRange       = 'NONE';
dateFormat         = 0;
axisTitle          = '';
fontSize           = 6;
axisLegend         = 0;
gridActive         = 'NONE';
LineStyleType      = 'NONE';
MarkerType         = 'NONE';
MarkerSIZE         = 6;



for indx =1:size(attributes,1)
    if strcmp(attributes{indx,1},'Ylog')
            yLogActivated   = 1;         
    elseif (strcmp(attributes{indx,1},'Color') | strcmp(attributes{indx,1},'color'))
            colorType       =  attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Xlabel')
            xaxisLabel      =  attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Ylabel')
            yaxisLabel      =  attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Xaxis')
            xZoom           =  attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Yaxis')
            yZoom           =  attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Zaxis')
            zZoom           =  attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Zrange')
            xyMAP_zRange    =  attributes{indx,2};     
    elseif strcmp(attributes{indx,1},'DataFormat')
            dateFormat      =  attributes{indx,2};
    elseif (strcmp(attributes{indx,1},'Title') | strcmp(attributes{indx,1},'title')) 
            axisTitle       = attributes{indx,2};
    elseif strcmp(attributes{indx,1},'FontSize')
            fontSize       = attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Legend')
            axisLegend      = attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Grid')
            gridActive      = attributes{indx,2};
    elseif strcmp(attributes{indx,1},'LineStyle')
            LineStyleType   = attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Marker')
            MarkerType      = attributes{indx,2};
    elseif strcmp(attributes{indx,1},'Markersize')
            MarkerSIZE      = attributes{indx,2};
    else
    end
end
