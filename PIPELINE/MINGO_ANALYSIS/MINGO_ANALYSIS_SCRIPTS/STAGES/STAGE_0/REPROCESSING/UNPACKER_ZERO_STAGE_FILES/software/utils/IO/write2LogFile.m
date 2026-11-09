% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/write2LogFile.m
% Purpose: write2LogFile function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

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

