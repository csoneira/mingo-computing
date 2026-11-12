% Purpose: function [mHist, binx, biny] = histf2d (vX, vY, vW, vXEdge, vYEdge, titulo).

%function [mHist, binx, biny] = histf2d (vX, vY, vW, vXEdge, vYEdge, titulo)
%2 Dimensional Histogram
%Counts vW times the number of points of coordinates vX, vY in the bins defined by vYEdge, vXEdge.
%size(mHist) == [length(vYEdge)-1, length(vXEdge)-1]
%ver HISTC para binx, biny. Values outside Edges go to bin=0.
%
% PLOT WITH
% pcolor(vXEdge(1:end-1)+diff(vXEdge)/2, vYEdge(1:end-1)+diff(vYEdge)/2, mHist);
% if 'titulo' is defined this is executed.
%
% %% EXAMPLE
% X=linspace(0,10,10000);
% Y=X*2+linspace(0,1,10000);
% EdgeX=0:10;
% EdgeY=0:2:20;
%
% [mHist, binX, binY] = histf2d(X, Y, sqrt(Y), EdgeX, EdgeY, 'test');
%
% I=find(binX==1 & binY==1);
% [min(X(I)) max(X(I))]
% [min(Y(I)) max(Y(I))]

function [mHist, binX, binY] = histf2d (vX, vY, vW, vXEdge, vYEdge,titulo)

if length(vX)~=length(vY), error('length(vX)~=length(vY)'); end

nY = length (vYEdge)-1; nX = length (vXEdge)-1;

vY = vY(:); vX = vX(:);

if ~length(vW), vW=ones(size(vX)); end % empty weights
if length(vW)==1, vW=ones(size(vX))*vW; end % single weight

% ignore NaNs
I=find(~isnan(vX)&~isnan(vY)&~isnan(vW));
if(length(I)>0)
vX=vX(I); vY=vY(I); vW=vW(I); 
end
mHist = zeros(nY,nX);
binY=vY*0; binX=vX*0;

for iRow = 1:nY
    rRowLB = vYEdge(iRow);
    rRowUB = vYEdge(iRow+1);

    [mIdxRow] = find (vY > rRowLB & vY <= rRowUB);
    vXFound = vX(mIdxRow);
    vWFound = vW(mIdxRow);
    binY(mIdxRow)=mIdxRow*0+iRow;

    if (~isempty(vXFound))
        [vFound, bins] = histc (vXFound, vXEdge);
        binX(mIdxRow)=bins;

        % process weights 
        for i=1:length(vFound), vFound(i)=sum(vWFound(bins==i)); end
        
        nFound = (length(vFound)-1);
        if (nFound ~= nX)
            [nFound nX]
            error ('hist2d error: Size Error')
        end

        [nYFound, nXFound] = size (vFound);

        nYFound = nYFound - 1;
        nXFound = nXFound - 1;

        if nYFound == nX
            mHist(iRow, :)= vFound(1:nFound)';
        elseif nXFound == nX
            mHist(iRow, :)= vFound(1:nFound);
        else
            error ('hist2d error: Size Error')
        end
    end

end


if exist('titulo')
%     pcolor(vXEdge(1:end)+diff(vXEdge)/2,...
%         vYEdge(1:end)+diff(vYEdge)/2, ...
%         cat(1,cat(2,mHist,zeros(size(mHist,1),1)),zeros(1,size(mHist,2)+1)));
    pcolor(vXEdge(1:end), vYEdge(1:end), ...
        cat(1,cat(2,mHist,zeros(size(mHist,1),1)),zeros(1,size(mHist,2)+1)));
    colorbar
    title(titulo)
    shading flat
end


end



%%
function test()

X=linspace(0,10,10000);
Y=X*2+linspace(0,1,10000); % slightly skewed
EdgeX=0:0.1:10;
EdgeY=0:0.2:20;

[mHist, binX, binY] = histf2d(X, Y, abs(X-5) ,EdgeX, EdgeY, 'test');
shading flat

I=find(binX==1 & binY==1);
[min(X(I)) max(X(I))]
[min(Y(I)) max(Y(I))]

end
