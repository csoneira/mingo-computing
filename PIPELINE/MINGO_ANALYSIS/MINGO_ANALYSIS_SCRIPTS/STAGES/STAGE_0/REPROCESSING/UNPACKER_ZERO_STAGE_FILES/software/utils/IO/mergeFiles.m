% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/mergeFiles.m
% Purpose: mergeFiles function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function mergeFiles(varargin)

%%%  merge({'d:\tmp\','*.mat','d:\tmp\','outFile.mat'},{'RPCTA','R'},{'Q','R'},{'EffQTh','N'},{'longBins','N'},...
%%%  merge({'parthIn','file','psthOut','fileOut' .....
%%%
%%%  R merge in row
%%%  N do nothing
%%%  A merge doing the sum
%%%  M merge doing the average
%%%  RS merge in row for sparse. This optimize the memory


inputPath        = varargin{1}{1};
inputPatternFile = varargin{1}{2};
outputPath       = varargin{1}{3};
outputFile       = varargin{1}{4};
if size(varargin{1},2) > 4
   time2Merge       = varargin{1}{5};
end
if size(varargin{1},2) > 5
    interpreter       = varargin{1}{6};
end

warning off
listedFiles_ = dir([inputPath inputPatternFile]);

if exist('time2Merge','var')
     listedFiles_ = selectFilesByTime(listedFiles_,time2Merge);
else
    %Do nothing
end

if(size(listedFiles_,1) == 0)
    disp(['No files of type ' inputPatternFile ' on ' inputPath] );
    return
end



for i_=1:size(listedFiles_,1)
    %%%Load the file
    
    load([inputPath listedFiles_(i_).name]);
    disp(['Merging ' inputPath listedFiles_(i_).name]);
    
    %%%Create variables if is the first iteraion
    if i_ == 1
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
                if i_ == 1
                    eval([varargin{j}{1} '_ = ' varargin{j}{1} ';']);
                else
                    eval([varargin{j}{1} '_ = ' varargin{j}{1} ' + '  varargin{j}{1} '_;']);
                end
            case 'M'
                if i_ == 1
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
    outputFile = [listedFiles_(1).name(1:end-4) '_merge'];
end

if(~exist(outputPath,'dir')); mkdirOS(outputPath,'linux',1); end;

if strcmp('matlab',interpreter)
    eval(['save(' '''' outputPath outputFile '''' ',' outputVars(1:end-1) ');']);
elseif strcmp('octave',interpreter)
    eval(['save(' '''' outputPath outputFile '''' ',' outputVars(1:end-1) ',''-mat7-binary'');']);
else
end

return