function fixMingoData(inputvars)

inPath      = inputvars{1};
outPath     = inputvars{2};
outPath2     = inputvars{3};
exportAsci  = inputvars{4};

s = dir([inPath '*.mat']);
load([inPath s(1).name]);

for plane = 1:4
    eval(['QF = Q' num2str(plane) '_F;']);eval(['QB = Q' num2str(plane) '_B;']);
    eval(['TF = T' num2str(plane) '_F;']);eval(['TB = T' num2str(plane) '_B;']);
    for ch = 1:4
        indx = find(QF(:,ch) < 0);
        if(length(indx) > 0)
            leadingOld  = TF(:,ch);
            trailingOld = QF(:,ch) + TF(:,ch);

            leadingNew  =  leadingOld;leadingNew(indx)  = trailingOld(indx);
            trailingNew = trailingOld;trailingNew(indx) =  leadingOld(indx);

            TF(:,ch) = leadingNew;
            QF(:,ch) = trailingNew - leadingNew;
        end
        clear leadingNew leadingOld trailingNew trailingOld

        indx = find(QB(:,ch) < 0);
        if(length(indx) > 0)
            leadingOld  = TB(:,ch);
            trailingOld = QB(:,ch) + TB(:,ch);

            leadingNew  =  leadingOld;leadingNew(indx)  = trailingOld(indx);
            trailingNew = trailingOld;trailingNew(indx) =  leadingOld(indx);

            TB(:,ch) = leadingNew;
            QB(:,ch) = trailingNew - leadingNew;
        end
        clear leadingNew leadingOld trailingNew trailingOld
    end
    eval(['Q' num2str(plane) '_F = QF;']);eval(['Q' num2str(plane) '_B = QB;']);
    eval(['T' num2str(plane) '_F = TF;']);eval(['T' num2str(plane) '_B = TB;']);
    clear QB QF TB TF
end

save([outPath s(1).name],'EBtime','Q1_B','Q1_F','Q2_B','Q2_F','Q3_B','Q3_F','Q4_B','Q4_F','T1_B','T1_F','T2_B','T2_F','T3_B','T3_F','T4_B','T4_F','TRBs','triggerType');
[~, ~] = system(['rm -r ' inPath]);


if(exportAsci)
    M = full([T1_F T1_B Q1_F Q1_B    T2_F T2_B Q2_F Q2_B   T3_F T3_B Q3_F Q3_B      T4_F T4_B Q4_F Q4_B]);
    fileName = s(1).name;fileName = fileName(1:end-4);
    mkdirOS([outPath2 'asci/'],'linux',1);file2Open = [outPath2 'asci/' fileName '.dat'];
    openFile;
    fprintf(fp, ['%010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f    %010.4f %010.4f %010.4f %010.4f \n'],M');

    fclose(fp);
end

return