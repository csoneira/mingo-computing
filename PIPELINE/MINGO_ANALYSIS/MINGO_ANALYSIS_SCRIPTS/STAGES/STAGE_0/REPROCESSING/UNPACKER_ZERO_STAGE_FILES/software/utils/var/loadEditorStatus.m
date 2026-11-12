% Purpose: Load Editor Status.

function loadEditorStatus(name)

load(['~/.matlab/EditorStatus_' name '.mat'],'fileNames');

for i=1:size(fileNames,1)
    edit(fileNames{i});
end
return
