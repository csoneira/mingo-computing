% Purpose: Save Indexed Vars.

function saveIndexedVars(INTERPRETER,outPath,outFile, varargin)

%%First cahnge the varName
outputVars = [];
for ind = 1:2:size(varargin,2)-1
    eval([eval(['varargin{' num2str(ind + 1) '}']) ' =  varargin{' num2str(ind) '};']);
    outputVars = [outputVars '''' eval(['varargin{' num2str(ind + 1) '}']) '''' ','];
end

outputVars = outputVars(1:end-1);

if strcmp('matlab',INTERPRETER)
    eval(['save([' '''' outPath outFile '''' '],' outputVars ');']);
elseif strcmp('octave',INTERPRETER)
    eval(['save([' '''' outPath outFile '''' '],' outputVars ',''-mat7-binary'');']);
end



return
