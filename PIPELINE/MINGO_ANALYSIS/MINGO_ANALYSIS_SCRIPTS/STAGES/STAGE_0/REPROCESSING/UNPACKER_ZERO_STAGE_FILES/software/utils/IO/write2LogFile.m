% Purpose: Write Log File.

function write2LogFile(text,issue,inPath)



file2Open = inPath;

[fp, message]=fopen(file2Open,'a');
if fp==-1
    disp(message);
    error(['Failed to open file: ' file2Open]);
    return
end

text2write = [datestr(now) ': ' issue '                  :   '    text];

fprintf(fp,'\n %s', text2write);


fclose(fp);




end
