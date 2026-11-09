% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/checkPlotAttributes.m
% Purpose: First the default values.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

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

