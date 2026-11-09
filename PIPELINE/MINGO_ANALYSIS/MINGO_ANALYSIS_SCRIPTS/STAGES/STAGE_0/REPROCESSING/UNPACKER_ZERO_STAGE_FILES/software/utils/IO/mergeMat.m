% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/mergeMat.m
% Purpose: mergeMat function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function mergeMat(varargin)

%%%  mergeMat({      1,inPath,'be21044201746*.mat',  outPath,'outMerge_be21044201746.mat','numberOfFiles',time2Merge,typeOfFiles,INTERPRETER},{'RPCTA','R'},{'Q','R'},{'EffQTh','N'},{'longBins','N'},...
%%%  merge   ({version,inPath,  'inputPatternFile','outPath',                   'fileOut','numberOfFiles',time2Merge,typeOfFiles,INTERPRETER}, .....
%%%
%%% version          => Control the version of the script
%%% inPath           => Location of the files to merge
%%% inputPatternFile => Patter of the files to merge
%%% outPath          => Output path of the merged files
%%% fileOut          => Name of the output file if none the name is selected autoamtically
%%% numberOfFiles    => Number of files to be merged, if = 0 precess time2Merge, all process all files i nthe folder
%%% time2Merge       => Select the range in time of the files to be merged
%%% typeOfFiles      => Indicated the type of files, HADES, MUTOM ...
%%% INTERPRETER
%%%
%%%
%%%  R merge in row
%%%  N do nothing
%%%  A merge doing the sum
%%%  M merge doing the average
%%%  RS merge in row for sparse. This optimize the memory
%%%  Version 1 2021-04-26





scriptVersions        = varargin{1}{1};
inputPath            = varargin{1}{2};
inputPatternFile     = varargin{1}{3};
outputPath           = varargin{1}{4};
outputFile           = varargin{1}{5};
numberOfFiles        = varargin{1}{6};
time2Merge           = varargin{1}{7};
typeOfFiles          = varargin{1}{8};
interpreter          = varargin{1}{9};




%p = findVersion(scriptVersions,'initFileStruct');

fileStruct = initFileHandler(scriptVersions,dir([inputPath inputPatternFile]),typeOfFiles);





if(isnumeric(numberOfFiles))%numberOfFiles is a number select files based on this
    numberOfFiles2Process = min([size(fileStruct,1) numberOfFiles]);
    fileStruct = fileStruct(1:numberOfFiles2Process);
    disp(['Selecting '  num2str(numberOfFiles2Process) ' files.'])
elseif(strcmp(numberOfFiles,'all') | strcmp(numberOfFiles,'All') | strcmp(numberOfFiles,'All'))%All files selected
     disp(['Selecting all available file in total '  num2str(size(fileStruct,1)) ' files.'])
else%Select the files with time
    files2Process = find([fileStruct.hadesDate] >= datenum(time2Merge{1}) & [fileStruct.hadesDate] <= datenum(time2Merge{2}));
    if(length(files2Process) == 0)
        disp('No files availables in the selected period. Aborting');
        return
    else
        fileStruct = fileStruct(files2Process);
        disp(['Selecting '  num2str(length(files2Process)) ' files.'])
    end
end    
    
    
    

if (findVersion(scriptVersions,'mergeMat') == 1)
    
    for matFile=1:size(fileStruct,1)
        %%%Load the file
        
        load([fileStruct(matFile).fullName]);
        disp(['Merging ' fileStruct(matFile).fullName]);
        
        %%%Create variables if is the first iteraion
        if matFile == 1
            for j=2:size(varargin,2)
                eval([varargin{j}{1} '_ = [];']);
            end
        end
        
        %%%Merge variables
        for j=2:size(varargin,2)
            warning off
            switch varargin{j}{2}
                %%%Merge by rows
                
                case 'R'
                    eval([varargin{j}{1} '_ = [' varargin{j}{1} '_;' varargin{j}{1} '];']);
                case 'C'
                    eval([varargin{j}{1} '_ = [' varargin{j}{1} '_ ' varargin{j}{1} '];']);
                case 'RS'
                    eval(['T = ' varargin{j}{1} ';']);I = find(T);[I1,I2] = ind2sub(size(T),I);[s1,s2]=size(T);
                    eval([varargin{j}{1} '_ = [' varargin{j}{1} '_; sparse(I1,I2,T(I),s1,s2)];']);
                case 'N'
                    eval([varargin{j}{1} '_ = [' varargin{j}{1} '];']);
                case 'A'
                    if matFile == 1
                        eval([varargin{j}{1} '_ = ' varargin{j}{1} ';']);
                    else
                        eval([varargin{j}{1} '_ = ' varargin{j}{1} ' + '  varargin{j}{1} '_;']);
                    end
                case 'M'
                    if matFile == 1
                        eval([varargin{j}{1} '_ = ' varargin{j}{1} ';']);
                    else
                        eval([varargin{j}{1} '_ = (' varargin{j}{1} ' + '  varargin{j}{1} '_)/2;']);
                    end
                    
            end
            
            
        end
    end
    
    
    %%%Rename vars and collect
    outputVars = [];
    for j=2:size(varargin,2)
        outputVars = [outputVars '''' varargin{j}{1} '''' ','];
        eval([varargin{j}{1} ' = ' varargin{j}{1} '_;']);
        eval(['clear ' varargin{j}{1} '_;' ])
    end
    
    
    
    %%%Save output
    if(strcmp(outputFile,'none'))
        outputFile = [fileStruct(1).fileName '_merge'];
    end
    
    if(~exist(outputPath,'dir')); mkdirOS(outputPath,'linux',1); end
    
    disp(['Writting merged file to ' outputPath outputFile]);
    if strcmp('matlab',interpreter)
        eval(['save(' '''' outputPath outputFile '''' ',' outputVars(1:end-1) ');']);
    elseif strcmp('octave',interpreter)
        eval(['save(' '''' outputPath outputFile '''' ',' outputVars(1:end-1) ',''-mat7-binary'');']);
    else
    end
else
    disp('Check version');
end
return