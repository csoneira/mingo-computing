% Purpose: Save Editor Status.

function saveEditorStatus(name)
list = matlab.desktop.editor.getAll;


fileNames = cell(size(list,2),1);
for i=1:size(list,2)
    fileNames{i} = list(i).Filename;
end

save(['~/.matlab/EditorStatus_' name '.mat'],'fileNames');

return
