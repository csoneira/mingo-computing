% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/HADESDate2Date.m
% Purpose: HADESDate2Date function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [dayOfTheMonth,month] = HADESDate2Date(year,day)



if(year == 13)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 14)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 15)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 16)
   day2Index = [1:31 1:29 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,29)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 17)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 18)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 19)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 20)
   day2Index = [1:31 1:29 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,29)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 21)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 22)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 23)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 24)
   day2Index = [1:31 1:29 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,29)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 25)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 26)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 27)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 28)
   day2Index = [1:31 1:29 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,29)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 29)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
elseif(year == 30)
   day2Index = [1:31 1:28 1:31 1:30 1:31 1:30 1:31 1:31 1:30 1:31 1:30 1:31];
   month2Index = [zeros(1,31)+1 zeros(1,28)+2 zeros(1,31)+3 zeros(1,30)+4 zeros(1,31)+5 zeros(1,30)+ 6 zeros(1,31)+7 zeros(1,31)+8 zeros(1,30)+9 zeros(1,31)+10 zeros(1,30)+11 zeros(1,31)+12];
   dayOfTheMonth = day2Index(day);
   month         = month2Index(day);
else
    disp('Year not defined');
end




return



