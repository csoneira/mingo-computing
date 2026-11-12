% Purpose: Save Indx Data.

function saveIndxData(inputVars)

inputPath          = inputVars{1};
outputPath         = inputVars{2};
fileName           = inputVars{3};
indx               = inputVars{4};
conf               = inputVars{5};


OS                 = conf.OS;
b                  = getBarOS(OS);
interpreter        = conf.INTERPRETER;

S = load([inputPath fileName]);
    load([inputPath fileName]);

varInStruct = fieldnames(S);

for i = 1:size(varInStruct,1)
    if(~strcmp(varInStruct{i},'TRBs'))
        eval([varInStruct{i} '=' varInStruct{i} '(indx,:);']);
    end
end

mkdirOS(outputPath,OS,1);


for i = 1:size(varInStruct,1)
    if strcmp('matlab',interpreter)
        if(~exist([outputPath fileName],'file'))
            save([outputPath fileName],varInStruct{1});
        else
            save([outputPath fileName],varInStruct{i},'-append');
        end
    elseif strcmp('octave',interpreter)
        if(~exist([outputPath fileName],'file'))
            save([outputPath fileName],varInStruct{1},'-mat7-binary');
        else
            save([outputPath fileName],varInStruct{i},'-append','-mat7-binary');
        end
    else
    end
end

return
