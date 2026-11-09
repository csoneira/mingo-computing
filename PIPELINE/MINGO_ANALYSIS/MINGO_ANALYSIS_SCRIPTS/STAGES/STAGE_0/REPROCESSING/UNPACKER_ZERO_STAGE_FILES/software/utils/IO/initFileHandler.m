% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/initFileHandler.m
% Purpose: initFileHandler function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function myFiles = initFileHandler(varargin)
%two possibilities for imputs: an array of cells or the output of dir
%
% 2024-05-15: Possibility to use this with log files
% 2022-02-25: Just coment each of the options
% 2021-06-15: Add a method to retrieve MUTOM Dat. Do it in all versions
% 2021-06-15: Just create another fiel with name Date, to replace the HADESDate. Do it in all versions
% 2020-05-05: Version 2: Just ussing version 2 of hadesName2Date
% 2020-05-05: Version 3. Acept an ls output as input.
% [status, result] = system(['ls ~/tmp/log/*.log -1t']); => we can use any parameter of ls
% initFileHandler(3,result,'HADES')

scriptVersions                 = varargin{1};

%Process the output of a dir comand
if(findVersion(scriptVersions,'initFileHandler') == 1) %two possibilities for inputs: an array of cells or the output of dir 
    
    inputFiles              = varargin{2};
    type                    = varargin{3};
    
    
    %%Init myfiles structure
    
    
    myFiles = struct('active'       ,{}        , ...
        'fullName'      ,{}        , ...%path + fileName + ext
        'inPath'        ,{}        , ...%path
        'fileName'      ,{}        , ...%file name without ext
        'fileNameExt'   ,{}        , ...%file name with ext
        'ext'           ,{}        , ...
        'hadesDate'     ,{}        , ...
        'Date'          ,{}        , ...
        'convert'       ,{}       );
    %myfile.hades2mat = @mytest; => myfile.hades2mat()
    
    
    
    if isstruct(inputFiles) &  size(inputFiles,1)   %Process the output of a dir comand
        for i=1:size(inputFiles,1)
            myFiles(i).fullName         = inputFiles(i).name;
            myFiles(i).inPath           = inputFiles(i).folder;
            
            I = strfind(inputFiles(i).name,'.');
            myFiles(i).fileName         = inputFiles(i).name(1:I(1)-1);
            myFiles(i).fileNameExt      = inputFiles(i).name;
            myFiles(i).ext              = inputFiles(i).name(I(1)+1:end);
            if (strcmp(type,'HADES'))
                myFiles(i).hadesDate = hadesName2Date(scriptVersions,inputFiles(i).name);
                myFiles(i).Date      = hadesName2Date(scriptVersions,inputFiles(i).name);
            elseif(strcmp(type,'MUTOM'))
                myFiles(i).Date      = mutomName2Date(scriptVersions,inputFiles(i).name);
            elseif(strcmp(type,'LOGS'))
                myFiles(i).Date      = logsName2Date(scriptVersions,inputFiles(i).name);
            end
        end
    end
    
    
    myFiles =   myFiles';

%Process the output of a dir comand
elseif(findVersion(scriptVersions,'initFileHandler') == 2)
    inputFiles              = varargin{2};
    type                    = varargin{3};
    
    
    %%Init myfiles structure
    
    
    myFiles = struct('active'       ,{}        , ...
        'inPath'        ,{}        , ...%path
        'fullName'      ,{}        , ...%path + fileName + ext
        'fileName'      ,{}        , ...%       fileName - ext
        'fileNameExt'   ,{}        , ...%       fileName + ext
        'ext'           ,{}        , ...
        'hadesDate'     ,{}        , ...
        'Date'          ,{}        , ...
        'convert'       ,{}       );
    %myfile.hades2mat = @mytest; => myfile.hades2mat()
    
    
    
    if isstruct(inputFiles) &  size(inputFiles,1)   %Process the output of a dir comand
        for i=1:size(inputFiles,1)
            myFiles(i).inPath           = [inputFiles(i).folder '/'];
            myFiles(i).fullName         = [myFiles(i).inPath  inputFiles(i).name];
                   
            I = strfind(inputFiles(i).name,'.');
            myFiles(i).fileName         = inputFiles(i).name(1:I(1)-1);
            myFiles(i).fileNameExt      = inputFiles(i).name;
            myFiles(i).ext              = inputFiles(i).name(I(1)+1:end);
            if (strcmp(type,'HADES'))
                myFiles(i).hadesDate = hadesName2Date(scriptVersions,inputFiles(i).name);
                myFiles(i).Date      = hadesName2Date(scriptVersions,inputFiles(i).name);
            elseif(strcmp(type,'MUTOM'))
                myFiles(i).Date      = mutomName2Date(scriptVersions,inputFiles(i).name);
            elseif(strcmp(type,'LOGS'))
                myFiles(i).Date      = logsName2Date(scriptVersions,inputFiles(i).name);
            end
        end
    end
    
    
    myFiles =   myFiles';
elseif(findVersion(scriptVersions,'initFileHandler') == 3)
     inputFiles              = varargin{2};
     type                    = varargin{3};
    
    
    %%Init myfiles structure
    
    
    myFiles = struct('active'       ,{}        , ...
        'fullName'      ,{}        , ...%path + fileName + ext
        'inPath'        ,{}        , ...%path
        'fileName'      ,{}        , ...%file name without ext
        'fileNameExt'   ,{}        , ...%file name with ext
        'ext'           ,{}        , ...
        'hadesDate'     ,{}        , ...
        'Date'          ,{}        , ...
        'convert'       ,{}       );
    %myfile.hades2mat = @mytest; => myfile.hades2mat()
    
    %Locate the carriage return
    index = [0 find(ismember(inputFiles, char([10 13])))];
    
    for i=1:length(index)-1
        inputFiles_     = inputFiles((index(i)+1):(index(i+1)-1));
        index2          = strfind(inputFiles_,'/');
        inputFiles__    = inputFiles_((index2(end)+1):end);
        index3          = strfind(inputFiles__,'.');
        
        myFiles(i).fullName         = inputFiles_;
        myFiles(i).inPath           = inputFiles_(1:index2(end));
        myFiles(i).fileName         = inputFiles__(1:(index3-1));
        myFiles(i).fileNameExt      = inputFiles__;
        myFiles(i).ext              = inputFiles__((index3+1):end);
        if (strcmp(type,'HADES'))
                myFiles(i).hadesDate = hadesName2Date(scriptVersions,myFiles(i).fileNameExt);
                myFiles(i).Date      = hadesName2Date(scriptVersions,myFiles(i).fileNameExt);
        elseif(strcmp(type,'MUTOM'))
                myFiles(i).Date      = mutomName2Date(scriptVersions,inputFiles(i).name);
        elseif(strcmp(type,'LOGS'))
                myFiles(i).Date      = logsName2Date(scriptVersions,inputFiles(i).name);
        end
    end
        
    
    myFiles =   myFiles';
else
    keyboard
end