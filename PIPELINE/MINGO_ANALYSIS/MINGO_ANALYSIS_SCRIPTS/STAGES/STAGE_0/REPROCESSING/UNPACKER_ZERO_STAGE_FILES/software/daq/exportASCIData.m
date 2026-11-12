% Purpose: Export ASCI Data for the legacy unpacker.

function exportASCIData(inputvars)



inPath        = inputvars{1};
outPath       = inputvars{2};
zipOutput     = inputvars{3};
lookUpTables  = inputvars{4};
systemName    = inputvars{5};

if ~isempty(lookUpTables)
    if lookUpTables(end) ~= filesep
        lookUpTables = [lookUpTables filesep];
    end
end

s = dir([inPath '*.mat']);
load([inPath s(1).name]);


name2Open  = [s(1).name(1:end-4) '.dat'];
file2Open = [outPath name2Open];
openFile;

exportScript = [lookUpTables systemName 'export2asic.m'];
if exist(exportScript,'file') ~= 2
    fallbackScript = [lookUpTables 'mingo01export2asic.m'];
    warning(['exportASCIData: missing script ' exportScript '.']);
    if exist(fallbackScript,'file') == 2
        warning(['exportASCIData: falling back to ' fallbackScript '.']);
        exportScript = fallbackScript;
    else
        error(['exportASCIData: unable to locate export2asic script for ' systemName '.']);
    end
end

run(exportScript);

fclose(fp);

if zipOutput
    [~, ~] = system(['cd ' outPath '; tar -czvf ./'  name2Open '.tar.gz ./' name2Open ';cd -']);
    [~, ~] = system(['rm -r ' file2Open]);
end

return
