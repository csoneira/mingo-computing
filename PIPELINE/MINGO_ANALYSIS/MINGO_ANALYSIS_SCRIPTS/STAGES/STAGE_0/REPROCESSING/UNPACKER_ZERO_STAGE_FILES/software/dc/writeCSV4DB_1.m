% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/writeCSV4DB_1.m
% Purpose: writeCSV4DB_1 function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [outputVars] = writeCSV4DB_1(inputVars)

conf            =   inputVars{1};
file2Send       =   inputVars{2};
timeStamp       =   inputVars{3};
varName         =   inputVars{4};
variable        =   inputVars{5};
typeOfVar       =   inputVars{6};
subTypeOfVar    =   inputVars{7};



%%%Build the script
fid = fopen(file2Send,'w');
if fid == (-1)
    error('rdf: Could not open file:');
end

count = fprintf(fid,['timestamps, ' varName '\n']);

if strcmp(typeOfVar ,'time')
    M = [datevec(timeStamp) variable];
    for i= 1:size(M,1)
        count = fprintf(fid,['%04d-%02d-%02d %02d:%02d:%02d, %012.4f\n'],M(i,:));
    end
elseif strcmp(typeOfVar,'static')
    if strcmp(subTypeOfVar,'staticHist')
        variable(isnan(variable)) = 0;
        M = [datevec(timeStamp) variable];
        str = ['%04d-%02d-%02d %02d:%02d:%02d, "{'];
        for i=1:size(variable,2)
            str = [str '%012.4f, '];
        end
        str = str(1:end-2);
        str = [str '}"'];
        count = fprintf(fid,str,M);
    elseif (strcmp(subTypeOfVar,'staticHist2D') | strcmp(subTypeOfVar,'staticHist2D-average') |  strcmp(subTypeOfVar,'staticHist2D-ratio'))
        %Replace NaN for Zeros
        variable(isnan(variable)) = 0;
        M = [datevec(timeStamp) reshape(variable,1,size(variable,1)*size(variable,2))];
        str = ['%04d-%02d-%02d %02d:%02d:%02d, "{'];
        for i=1:size(variable,2)
            str = [str '{'];
            for j=1:size(variable,2)
                str = [str '%012.4f, '];
            end
            str = str(1:end-2);
            str = [str '},'];
        end
        str = str(1:end-1);
        str = [str '}"'];
        count = fprintf(fid,str,M);
    else
    end
else
end

fclose(fid);
outputVars = 0;
return