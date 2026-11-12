% Purpose: Define openfile values for the legacy Stage-0 unpacker.

[fp, message]=fopen(file2Open);
if fp==-1
    disp(message);
    error(['Failed to open file: ' file2Open]);
    return
end
