% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/unpackTRB3.m
% Purpose: unpackTRB3 function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function  errorType = unpackTRB3(pathIn,pathOut,filename,TRBs,numberOfBitsToRead,writeTDCCal,interpreter,OS)

% size: 0x00000020  decoding: 0x00030001  id:    0x00010002  seqNr:  0x00000000
% date: 2015-05-05  time:     14:12:44    runNr: 0x0dc243dc  expId:
%
% size: 0x000001b4  decoding: 0x00030001  id:    0x00002001  seqNr:  0x00000001
% date: 2015-05-05  time:     14:12:44    runNr: 0x0dc243dc  expId:  ub
% size: 0x00000194  decoding: 0x00020001  id:    0x00008000  trigNr: 0xd09b3a39 trigTypeTRB3: 0x1

%V1.1
%V1.2 This include two other cases. TRBs in serie.
%2023-06-11 Save the data from header always in a separate file
%2023-06-05 Include triger type on the decodification => modify TRBDecoding
%           for the moment only including 20011 => Physical and 20012 => SelfTrigger



errorType = 'none';


bSl=@(A) swapbytes(uint32(A));%%% This is defined for decimals


%%% Varsother cases. 
%pathIn              = {conf.unpacking.inputPathHLD};
%pathIn              = {'/mnt/B/pet/hlds/runTalvezSolved/'}
%pathOut             = {conf.unpacking.outputPathMAT};
%filename            = {conf.unpaother cases. cking.fileName};
%filename            = {'dabc18043092744'}
%outLogFile          = {conf.unpacking.logFile};
%TRBs                = conf.TRBs;
%numberOfBitsToRead  = conf.unpacking.bufferSize;

TRBDecoding_01 = hex2dec('00020011');%Physical trigger
TRBDecoding_02 = hex2dec('00020021');
%TRBDecoding    = hex2dec('00020001');
%%% the headers are in little-endian!!!!
headerDecoding = bSl(hex2dec('00030001'));
headerId_01       = bSl(hex2dec('00002001'));
headerId_02       = bSl(hex2dec('00002002'));
FPGAHUB        = [];%If different of 0 mean that there is a HUB


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% First readout only a portion of the file to check the configuration
fid=fopen([pathIn{1} filename{1} '.hld'],'r');
if fid == (-1)
    error(['rdf: Could not open file:' pathIn{1} filename{1}]);
end

%Remove _ in multiprocessing
if(strcmp(filename{1}(1),'_'));filename{1} = filename{1}(2:end);end

%%% Check if at least there is a full complete event.
numberOfBitsToReadInitial        = 10000;

while 1
    %Read out the data
    frewind(fid);
    
    A= fread(fid,numberOfBitsToReadInitial,'uint32','b');
    
    eventSizeId = intersect(find(A == headerDecoding)+1,find(A == headerId_01 | A == headerId_02)) -2;
    if(length(eventSizeId) == 0)%Something wrong with the file there is no header!!
        errorType = 'No events';
        return
    elseif(length(eventSizeId) == 1)%Only one haeder event detected => increase the number of bits to readout if possibel
        if(length(A) < numberOfBitsToReadInitial)%no more data availabel
            errorType = 'No events';
            return
        else%Increse the bits readout.
            numberOfBitsToReadInitial = floor(numberOfBitsToReadInitial * 10);
        end
    else%Continue at least one event has been recorded
        break
    end
end

numTRBs = size(TRBs,2);
%%% Loop  on the TRB boards to discover it and check conf. No data is stored about the data stream
for i=1:numTRBs
    numFPGAs = size(TRBs(i).FPGAs,1);
    
        %%%Find the central FPGA ID and first event
        centralFPGA_hex = TRBs(i).centralFPGA;centralFPGA_dec = hex2dec(centralFPGA_hex);confInt{1} = {};
        disp(['Central FPGA ' centralFPGA_hex ' found in the configuration file.']);
        
        %%%These are the first word on each event.
        firstEventID = intersect(find(A == TRBDecoding_01 | A == TRBDecoding_02)+1,find(A == centralFPGA_dec)) + 2;
        if(size(firstEventID,1) > 0)
            firstEventID = firstEventID(1);
            disp(['Central FPGA ' centralFPGA_hex ' found in the data stream']);
        else
            disp(['Central FPGA ' centralFPGA_hex ', found in the configuration file, is not in the data stream.']);
        end
        
        %%%Loop on the FPGAs of the data stream
        for k=1:numFPGAs
            if(strcmp(TRBs(i).FPGAs(k,2),'ADC-GBE'))
                FPGA = dec2hex(double(bitand(uint32(A(firstEventID - 2)),uint32(hex2dec('0000ffff')))));
                blockSize = double(uint32(A(firstEventID - 4)));blockSize = blockSize/4; blockSize = blockSize - 3 - 3;
            else
                FPGA = dec2hex(double(bitand(uint32(A(firstEventID)),uint32(hex2dec('0000ffff')))));
                blockSize = double(bitshift(bitand(uint32(A(firstEventID)),uint32(hex2dec('ffff0000'))),-16));
            end
            
            %%Look for the correct FPGA on the configurtion var
            index = find(strcmp(TRBs(i).FPGAs(:,1),FPGA));
            if(length(index == 1))
                if(strcmp(TRBs(i).FPGAs{index,3},'TRUE'))
                    disp(['FPGA ' TRBs(i).FPGAs{index,1} ' with ' TRBs(i).FPGAs{index,2} ' design found on data stream. In use']);
                    %%%Configuration information of the FPGAs
                    confInt{index} = inspectFPGA(A(firstEventID:firstEventID+blockSize),TRBs(i).FPGAs(index,:));
                else
                    disp(['FPGA ' TRBs(i).FPGAs{index,1} ' with ' TRBs(i).FPGAs{index,2} ' design found on data stream. Not in use']);
                end
            else
                disp('Something wrong while looking for the FPGAS')
                return
            end
            
            if( strcmp(TRBs(i).FPGAs(index,2),'HUB'))
                firstEventID = firstEventID + 1;
            else
                %Warning this line was not check for ADC-GE .. it is not used actually because it is suposed to be ALWAYS alone in the FPG
                firstEventID = firstEventID + blockSize + 1;
            end
        end
        TRBs(i).conf = confInt;
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Rewind file and read events.
frewind(fid);
t = clock;
done = 1;
counterFile = 1;
previusA = [];%This is for the remaining events after processing


%%% Start the readout.
while done
    %Initialize some variables.
    %This is the matrix used to mark events with wrong size on the ADC
    %subevent. Initially it was a matrix with a column for each FPGA, but
    %it is much better to just delete the complete event.
    wrongSizeADCEvents = [];
    
    A= fread(fid,numberOfBitsToRead,'uint32','b');
    
    %%% Check if the readout is finished
    if(length(A) < numberOfBitsToRead);done = 0;end
    
    %%% Concatenate the previous events
    A= [previusA; A];
    
    %   Calculate the ids for the begining of each event, in this case size: 0x000001b4
    %   size: 0x000001b4  decoding: 0x00030001  id:    0x00002001  seqNr:  0x00000001
    %   date: 2015-05-05  time:     14:12:44    runNr: 0x0dc243dc  expId:  ub
    %   size: 0x00000194  decoding: 0x00020001  id:    0x00008000  trigNr: 0xd09b3a39 trigTypeTRB3: 0x1
    %   !! Note that the header is in little-endian!!!!!!!!!!!
    %   size: 0x000001b4 in
    %   size: 0x000001b4  decoding: 0x00030001  id:    0x00002001  seqNr:  0x00000001
    
    eventSizeId = intersect(find(A == headerDecoding)+1,find(A == headerId_01 | A == headerId_02)) -2;
    eventSize   = bSl(A(eventSizeId))/4;
    
    %%Patch to remove empty events
    %I = find(eventSize < 100);if(length(I) > 0);keyboard;end
    I = find(eventSize > 32);eventSizeId = eventSizeId(I); eventSize = eventSize(I);
    
    
    %%% Cat the data and leave the not complete data
    previusA = A(eventSizeId(end):length(A));
    A = A(1:eventSizeId(end)-1);
    %%% Recalculate the eventSizeId
    eventSizeId = eventSizeId(1:end-1);
    eventSize   = eventSize(1:end-1);
    numberOfEvents = length(eventSizeId);
    
    %%% Verification
    %%% It is check if the first 4 bits of id is zero
    %%% size: 0x000008ac  decoding: 0x00030001  id:    0x00002001  seqNr:  0x00000001
    %%% the headers are in little-endian!!!!
    if(sum(bitand(uint32((A(eventSizeId + 2))),uint32(hex2dec('0000ffff')))))
        disp('Something is wrong with the indexing');
        keyboard
    end
    
    %%% Stract the triggerType eventTime
    triggerType = dec2hex(A(eventSizeId + 2));triggerType = str2num(triggerType(:,1));
    eventDate  = bSl(A(eventSizeId + 4));
    eventTime  = bSl(A(eventSizeId + 5));
    
    %%% Delete no useful information to preven missCoincidences.
    %%% This
    %%% size: 0x00000020  decoding: 0x00030001  id:    0x00010002  seqNr:  0x00000000
    %%% date: 2015-05-05  time:     14:12:44    runNr: 0x0dc243dc  expId:
    
    if(counterFile == 1)
        A(1:8) = 0;
    end
    
    
    %%%And this
    %   size: 0x000001b4  decoding: 0x00030001  id:    0x00002001  seqNr:  0x00000001
    %   date: 2015-05-05  time:     14:12:44    runNr: 0x0dc243dc  expId:  ub
    A(eventSizeId +1) = 0;A(eventSizeId +2) = 0;A(eventSizeId +3) = 0;A(eventSizeId +4) = 0;
    A(eventSizeId +5) = 0;A(eventSizeId +6) = 0;A(eventSizeId +7) = 0;
    
    
    numFPGAsMax = 0;
    for i=1:numTRBs
        numFPGAsMax = max([numFPGAsMax size(TRBs(i).FPGAs,1)]);
    end
    
    TRBSizeId  = zeros(numberOfEvents,numTRBs);
    TRBSize    = zeros(numberOfEvents,numTRBs);
    FPGASizeId = zeros(numberOfEvents,numTRBs,numFPGAsMax);
    FPGASize   = zeros(numberOfEvents,numTRBs,numFPGAsMax);
     
    for i=1:numTRBs
        
        numFPGAs = size(TRBs(i).FPGAs,1);
        
        %%% This is the size of each TRB date block
        %%% size: 0x00000194 in
        %%% size: 0x00000194  decoding: 0x00020001  id:    0x00008000  trigNr: 0xd09b3a39 trigTypeTRB3: 0x1
        
        
            TRBId = hex2dec(TRBs(i).centralFPGA);
            TRBSizeId(:,i) = intersect(find(A == TRBDecoding_01 | A == TRBDecoding_02)+1,find(A == TRBId)) - 2;
            TRBSize(:,i)    =  A(TRBSizeId(:,i))/4;%this is the size in words
            %%Verification
            if(diff(A(TRBSizeId(:,i) + 1)))
                disp('Something is wrong with the indexing');
                keyboard
            end
                       
            
            
            %This is first FPGA (outSide loop).
            k = 1;
            if(strcmp(TRBs(i).FPGAs(k,2),'ADC-GBE'))
                FPGASizeId(:,i,k) = TRBSizeId(:,i);% In this case the size is inside the TRB size
                FPGASize  (:,i,k) = double(uint32(A(FPGASizeId(:,i,k))))/4 - 3 - 3;
            else
                FPGASizeId(:,i,k) = TRBSizeId(:,i) + 4;%Id of 0x0150a001
                FPGASize  (:,i,k) = double(bitshift(uint32(A(FPGASizeId(:,i,k))),-16));%0150
            end
            
            
            for k=2:numFPGAs%First FPGA is already done
                %Detect if the FPGA is a HUB
                isHUB = 0;
                if(strcmp(TRBs(i).FPGAs(k,2),'HUB'))
                    isHUB = 1;
                end
                
                if(isHUB)
                    FPGASizeId(:,i,k) = FPGASizeId(:,i,k-1) + FPGASize(:,i,k-1) + 1;
                    FPGASize  (:,i,k) = 0;
                else
                    FPGASizeId(:,i,k) = FPGASizeId(:,i,k-1) + FPGASize(:,i,k-1) + 1;
                    FPGASize  (:,i,k) = double(bitshift(uint32(A(FPGASizeId(:,i,k))),-16));
                end
            end
            
            
            
            %Check if the FPGA with an ADC addon has always the same size,
            %if not mark the event in wrongSizeADCEvents.
            for k=1:numFPGAs
                if(strcmp(TRBs(i).FPGAs(k,3),'TRUE') & (strcmp(TRBs(i).FPGAs(k,2),'ADC-GBE')))
                    rightSize = TRBs(i).conf{k}{1}*length(TRBs(i).conf{k}{2});
                    index_wrongEvents = find(FPGASize(:,i,k) ~= rightSize);
                    if(~isempty(index_wrongEvents))
                        wrongSizeADCEvents = unique([wrongSizeADCEvents; index_wrongEvents]);
                        disp(['================> Wrong number of events in ADC event number ' num2str(index_wrongEvents')]);
                    end
                end
            end
            
            
        
        %         if(OTHER SYSTEMS)
        %         end
    end
    
    
    %%% Delete no useful information to preven missCoincidences.
    for i=1:numTRBs
        %%%This
        %   size:        decoding: 0x00020001  id:    0x00008000  trigNr:   0xd09b3a39 trigTypeTRB3: 0x1
        
        A(TRBSizeId(:,i) + 1) = 0;A(TRBSizeId(:,i) + 2) = 0;A(TRBSizeId(:,i) + 3) = 0;
    end
    
    
    %%% Create the eventIndex, TRBIndex and FPGAIndex
    eventIndex = zeros(length(A),1);%Store the number of Event
    TRBIndex   = zeros(length(A),1);%Store the number of TRB
    FPGAIndex  = zeros(length(A),1);%Store the number of FPGA. The number is the order on the data stream
    for j=1:numberOfEvents
        eventIndex(eventSizeId(j):(eventSizeId(j) + eventSize(j) -1)) = j;
        for i=1:numTRBs
                numFPGAs = size(TRBs(i).FPGAs,1);    
                TRBIndex(TRBSizeId(j,i):(TRBSizeId(j,i) + TRBSize(j,i) -1)) = i;%Checked with ADC-GE on TRB3sc
                
                for k=1:numFPGAs
                    %%% Not taking into account the first word. For instance 0x0007c000
                    if(find(j == wrongSizeADCEvents))%FPGAIndex is left = 0 for wrongSizeADCEvents => they are not processed
                        if(strcmp(TRBs(i).FPGAs(k,2),'TDC-CTS'))
                            CTS_Offset = TRBs(i).FPGAs{k,6};%Add the offset that eleminates other words different than TDCs
                            FPGAIndex((FPGASizeId(j,i,k) + 1 + CTS_Offset): (FPGASizeId(j,i,k) + FPGASize(j,i,k))) = -1;
                        elseif(strcmp(TRBs(i).FPGAs(k,2),'ADC-GBE'))
                            FPGAIndex((FPGASizeId(j,i,k) + 4):(FPGASizeId(j,i,k) + 3 + FPGASize(j,i,k))) = -1;%In this case it should be only the ADC words
                        else%This line works with the hub by miracle!!!!
                            FPGAIndex((FPGASizeId(j,i,k) + 1):(FPGASizeId(j,i,k) + FPGASize(j,i,k))) = -1;
                        end
                    else
                        if(strcmp(TRBs(i).FPGAs(k,2),'TDC-CTS'))
                             CTS_Offset = TRBs(i).FPGAs{k,6};%Add the offset that eleminates other words different than TDCs
                             FPGAIndex((FPGASizeId(j,i,k) + 1 + CTS_Offset): (FPGASizeId(j,i,k) + FPGASize(j,i,k))) = k;
                        elseif(strcmp(TRBs(i).FPGAs(k,2),'ADC-GBE'))
                            FPGAIndex((FPGASizeId(j,i,k) + 4):(FPGASizeId(j,i,k) + 3 + FPGASize(j,i,k))) = k;%In this case it should be only the ADC words
                        else%This line works with the hub by miracle!!!!
                            FPGAIndex((FPGASizeId(j,i,k) + 1):(FPGASizeId(j,i,k) + FPGASize(j,i,k))) = k;
                        end
                    end
                end
                
            
        end
        
    end
    
    
    disp(['=== Number of events ' sprintf('%08d' ,numberOfEvents) ' with ' sprintf('%08d' ,length(wrongSizeADCEvents)) ' events with wrong number of ADC samples']);
    efectiveNumberOfEvents = numberOfEvents - length(wrongSizeADCEvents);
    disp(['=== Number of events ' sprintf('%08d' ,efectiveNumberOfEvents)]);
    
    %%% From here, data straction
    for i=1:numTRBs
        %if(strcmp(TRBs(i).type,'TRB3'))
            for k=1:size(TRBs(i).FPGAs,1)
                if(strcmp(TRBs(i).FPGAs(k,3),'TRUE') & (strcmp(TRBs(i).FPGAs(k,2),'TDC') | strcmp(TRBs(i).FPGAs(k,2),'TDC-CTS')))%Check if it is active
                    I = find(FPGAIndex == k & TRBIndex == i);
                    type          = double(bitshift(uint32(A(I)),-29));
                    epochCounter  = double(         bitand(uint32(A(I)),uint32(hex2dec('0fffffff'))));
                    coarseTime    = double(         bitand(uint32(A(I)),uint32(hex2dec('000007ff'))));
                    edge          = double(bitshift(bitand(uint32(A(I)),uint32(hex2dec('00000800'))),-11));
                    fineTime      = double(bitshift(bitand(uint32(A(I)),uint32(hex2dec('003FF000'))),-12));
                    channelNumber = double(bitshift(bitand(uint32(A(I)),uint32(hex2dec('1FC00000'))),-22));
                    
                    
                    
                    %%Reconstruction of the epoch counter in order to give a epoch couter to each meassurment
                    %%this will loop a maximum number of iterations equal to the maximum number of hits on a channel
                    
                    type_ = type;
                    I_ = 1:size(type,1)-1;%last type can not be a type 3
                    while 1
                        J = find(         type_(I_) == 3 & (type_(I_+1) == 4 | type_(I_+1) == 7)        );
                        if(~isempty(J))
                            epochCounter(J+1) = epochCounter(J);
                            type_(J+1) = 3;
                        else
                            break
                        end
                    end
                    clear type_ I_ 
                    
                                     
                    %Process leading time
                    index4Time               = find(type == 4 & edge == 1);
                    %The code is tolerant to the fact to have idex4Tim = []
                    fineTimeTRBIndex         = TRBIndex(I(index4Time));
                    fineTimeEventIndex       = eventIndex(I(index4Time));
                    fineTimeCh               = channelNumber(index4Time)+1;
                    
                    leadingEpochCounter       = epochCounter(index4Time);
                    leadingCoarseTime         = coarseTime(index4Time);
                    leadingFineTime           = fineTime(index4Time);
                    
                    %Read only first time to appear in each channel
                    [~,n,~] = unique([fineTimeEventIndex fineTimeCh],'rows','first');
                    leadingEpochCounter = sparse(fineTimeEventIndex(n), fineTimeCh(n),leadingEpochCounter(n),numberOfEvents,64);
                    leadingCoarseTime   = sparse(fineTimeEventIndex(n), fineTimeCh(n),leadingCoarseTime(n),numberOfEvents,64);
                    leadingFineTime     = sparse(fineTimeEventIndex(n), fineTimeCh(n),leadingFineTime(n),numberOfEvents,64);
                    clear index4Time fineTimeTRBIndex fineTimeEventIndex fineTimeCh
                    
                    
                    %Process  trailing time
                    index4Time                = find(type == 4 & edge == 0);
                    fineTimeTRBIndex          = TRBIndex(I(index4Time));
                    fineTimeEventIndex        = eventIndex(I(index4Time));
                    fineTimeCh                = channelNumber(index4Time)+1;
                    %%Always save the data from CTS HEADER
            I = setdiff(1:numberOfEvents,wrongSizeADCEvents);
            eventDate  = eventDate(I);
            eventTime  = eventTime(I);
            triggerType = triggerType(I);
            if strcmp('matlab',interpreter)
                save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_HEAD'  '_part' sprintf('%04d',counterFile) '.mat'],'triggerType','eventDate','eventTime');
            elseif strcmp('octave',interpreter)
                save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_HEAD'  '_part' sprintf('%04d',counterFile) '.mat'],'triggerType','eventDate','eventTime','-mat7-binary');
            end
                    trailingEpochCounter      = epochCounter(index4Time);
                    trailingCoarseTime        = coarseTime(index4Time);
                    trailingFineTime          = fineTime(index4Time);
                    
                    %Read only first time to appear in each channel
                    [~,n,~] = unique([fineTimeEventIndex fineTimeCh],'rows','first');
                    trailingEpochCounter = sparse(fineTimeEventIndex(n), fineTimeCh(n),trailingEpochCounter(n),numberOfEvents,64);
                    trailingCoarseTime   = sparse(fineTimeEventIndex(n), fineTimeCh(n),trailingCoarseTime(n),numberOfEvents,64);
                    trailingFineTime     = sparse(fineTimeEventIndex(n), fineTimeCh(n),trailingFineTime(n),numberOfEvents,64);
                    clear index4Time fineTimeTRBIndex fineTimeEventIndex fineTimeCh
                    
                    
                    if(strcmp(TRBs(i).FPGAs(k,4),'TRUE'))%Write data
                        %Eliminate the events with incorrect ADC samples.
                        I = setdiff(1:numberOfEvents,wrongSizeADCEvents);
                        leadingEpochCounter  = leadingEpochCounter(I,:); trailingEpochCounter  = trailingEpochCounter(I,:);
                        leadingCoarseTime = leadingCoarseTime(I,:);trailingCoarseTime = trailingCoarseTime(I,:);
                        leadingFineTime   = leadingFineTime(I,:);  trailingFineTime   = trailingFineTime(I,:);
                        if strcmp('matlab',interpreter)
                            save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_' num2str(TRBs(i).FPGAs{k,1}) '_part' sprintf('%04d',counterFile) '.mat'],'trailingEpochCounter','leadingEpochCounter','leadingCoarseTime','leadingFineTime','trailingCoarseTime','trailingFineTime');
                            if writeTDCCal
                                b = getBarOS(OS);
                                mkdirOS([pathOut{1} 'TDCCal' b],OS,1);
                                save([pathOut{1} 'TDCCal' b filename{1} '_' num2str(TRBs(i).centralFPGA) '_' num2str(TRBs(i).FPGAs{k,1}) '_part' sprintf('%04d',counterFile) '.mat'],'leadingFineTime','trailingFineTime');
                            end
                        elseif strcmp('octave',interpreter)
                            save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_' num2str(TRBs(i).FPGAs{k,1}) '_part' sprintf('%04d',counterFile) '.mat'],'trailingEpochCounter','leadingEpochCounter','leadingCoarseTime','leadingFineTime','trailingCoarseTime','trailingFineTime','-mat7-binary');
                            if writeTDCCal
                                b = getBarOS(OS);
                                mkdirOS([pathOut{1} 'TDCCal' b],OS,1);
                                save([pathOut{1} 'TDCCal' b filename{1} '_' num2str(TRBs(i).centralFPGA) '_' num2str(TRBs(i).FPGAs{k,1}) '_part' sprintf('%04d',counterFile) '.mat'],'leadingFineTime','trailingCoarseTime','trailingFineTime','-mat7-binary');
                            end
                        end
                    end
                    
                end
                
                if(strcmp(TRBs(i).FPGAs(k,3),'TRUE') && (strcmp(TRBs(i).FPGAs(k,2),'ADC') ||  strcmp(TRBs(i).FPGAs(k,2),'ADC-GBE')))%Check if it is active
                    I = find(FPGAIndex == k & TRBIndex == i);
                    %%% Extract the ADC, channel and value
                    value     = double(         bitand(uint32(A(I)),uint32(hex2dec('0000ffff'))));
                    %channel   = double(bitshift(bitand(uint32(A(I)),uint32(hex2dec('000f0000'))),-16));
                    %ADC       = double(bitshift(bitand(uint32(A(I)),uint32(hex2dec('00f00000'))),-20));
                    
                    %channels = (ADC*4+channel)+1;
                    numberOfSamples  = TRBs(i).conf{k}{1};
                    numberOfChannles = size(TRBs(i).conf{k}{2},1);
                    activeChannels   = TRBs(i).conf{k}{2};
                    %
                    %%%This only works if the data is sent sequentialy one
                    %%%channel after the other.
                    
                    %TDCEventIndex= eventIndex(I);
                    %linInd = sub2ind([numberOfSamples,numberOfChannles,numberOfEvents], TDCEventIndex, channels);
                    
                    try
                        %The numbre of event are substracted by the amount of events with wrong size. After that it is inserted in
                        %the proper site
                        data = reshape(value,numberOfSamples,numberOfChannles,efectiveNumberOfEvents);
                        %sparse(TDCEventIndex,channels,value_,numberOfEvents,64);
                    catch exception
                        if (strcmp(exception.identifier,'MATLAB:getReshapeDims:notSameNumel'))
                            fclose(fid);
                            errorType = 'reshape';
                            return
                        else
                            keyboard
                        end
                        
                    end
                    
                    
                    if(strcmp(TRBs(i).FPGAs(k,4),'TRUE'))%Write data
                        if strcmp('matlab',interpreter)
                            save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_' num2str(TRBs(i).FPGAs{k,1}) '_part' sprintf('%04d',counterFile) '.mat'],'data','activeChannels');
                        elseif strcmp('octave',interpreter)
                            save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_' num2str(TRBs(i).FPGAs{k,1}) '_part' sprintf('%04d',counterFile) '.mat'],'data','activeChannels','-mat7-binary');
                        end
                   
                    end
                end
                
                if(strcmp(TRBs(i).FPGAs(k,3),'TRUE') & strcmp(TRBs(i).FPGAs(k,2),'CTS'))%Check if it is active
                    %Just select the events with right size
                    I = setdiff(1:numberOfEvents,wrongSizeADCEvents);
                    
                    if(~isempty(find(diff(FPGASize(I,i,k)))))
                        disp('CTS has no constant number of words => Counters are probably wrong');
                    end
                    %double(         bitand(uint32(A(I)),uint32(hex2dec('0000ffff'))));
                    CTSCounters = [bitand(uint32(A(FPGASizeId(I,i,k) + FPGASize(I,i,k)-2)),uint32(hex2dec('00ffffff'))) ...
                        bitand(uint32(A(FPGASizeId(I,i,k) + FPGASize(I,i,k)-1)),uint32(hex2dec('00ffffff'))) ...
                        bitand(uint32(A(FPGASizeId(I,i,k) + FPGASize(I,i,k)-0)),uint32(hex2dec('00ffffff')))];
                    
                    
                    if(strcmp(TRBs(i).FPGAs(k,4),'TRUE'))%Write data
                        if strcmp('matlab',interpreter)
                            save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_' num2str(TRBs(i).FPGAs{k,1}) '_part' sprintf('%04d',counterFile) '.mat'],'CTSCounters');
                        elseif strcmp('octave',interpreter)
                            save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_' num2str(TRBs(i).FPGAs{k,1}) '_part' sprintf('%04d',counterFile) '.mat'],'CTSCounters');
                        end

                    end
                end
            end
    end

    %%Always save the data from CTS HEADER
    I = setdiff(1:numberOfEvents,wrongSizeADCEvents);
    eventDate  = eventDate(I);
    eventTime  = eventTime(I);
    triggerType = triggerType(I);
    if strcmp('matlab',interpreter)
        save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_HEAD'  '_part' sprintf('%04d',counterFile) '.mat'],'triggerType','eventDate','eventTime');
    elseif strcmp('octave',interpreter)
        save([pathOut{1} filename{1} '_' num2str(TRBs(i).centralFPGA) '_HEAD'  '_part' sprintf('%04d',counterFile) '.mat'],'triggerType','eventDate','eventTime','-mat7-binary');
    end


    l=etime(clock,t);
    disp(['=== Ellapsed Time ' sprintf('%5.1f' ,l) ' seconds'])
    disp(['=== file ', filename{1}, ' with ', num2str(numberOfEvents), ' events ']);
    disp(['=== read in ', pathIn{1} ,' and written in ', pathOut{1}]);
    
    counterFile = counterFile + 1;
end
fclose(fid);
return



function FPGAconf =  inspectFPGA(data,FPGA)


if(strcmp(FPGA{2},'TDC'))
    %Do nothing
    FPGAconf = [];

elseif(strcmp(FPGA{2},'TDC-CTS')) 
    FPGAconf = [];

elseif(strcmp(FPGA{2},'ADC'))
    channel  = double(bitshift(bitand(uint32(data(2:end)),uint32(hex2dec('000F0000'))),-16));
    ADC      = double(bitshift(bitand(uint32(data(2:end)),uint32(hex2dec('00F00000'))),-20));
    channels = (ADC*4+channel)+1;
    
    samples  = length(find(channels == channels(1)));%I assume same number of samples in all channels of the same FPGA.
    channels = unique(channels);
    disp(['     Active channels : ' num2str(channels')]);
    disp(['     with ' num2str(samples) ' samples']);
    
    %Last zero will be latter used to store the wrongADC events
    FPGAconf = {samples,channels,0};

elseif(strcmp(FPGA{2},'ADC-GBE'))
    channel  = double(bitshift(bitand(uint32(data(1:end-1)),uint32(hex2dec('000F0000'))),-16));
    ADC      = double(bitshift(bitand(uint32(data(1:end-1)),uint32(hex2dec('00F00000'))),-20));
    channels = (ADC*4+channel)+1;
    
    samples  = length(find(channels == channels(1)));%I assume same number of samples in all channels of the same FPGA.
    channels = unique(channels);
    disp(['     Active channels : ' num2str(channels')]);
    disp(['     with ' num2str(samples) ' samples']);
    
    %Last zero will be latter used to store the wrongADC events
    FPGAconf = {samples,channels,0};

    
elseif(strcmp(FPGA{2},'CTS'))
    %Do nothing
    FPGAconf = [];
elseif(strcmp(FPGA{2},'R3B'))
    FPGAconf = [];
end




return
