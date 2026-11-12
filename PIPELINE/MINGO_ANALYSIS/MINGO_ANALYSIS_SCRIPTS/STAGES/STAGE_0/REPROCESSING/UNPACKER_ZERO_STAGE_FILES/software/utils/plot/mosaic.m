% Purpose: Arrange legacy plots in a tiled figure.

function mosaic(nwin,last)

windows=sort(get(0,'children'));
%screen=get(0,'screenSize');
%set(0,'screenSize',[1 0 1920 1080]);
screen = [1 -1564 1920 100];

% square mosaic
% lower corner maybe changed in the future.

if ~nargin
   rows=ceil(sqrt(length(windows)));
   else
   rows=ceil(sqrt(nwin));
end

Xsize=(screen(3)-screen(1))/rows;
%Ysize=(screen(4)-screen(2)-40*rows)/rows
Ysize=(screen(4)-screen(2)-70)/rows;

for i=(rows-1):-1:0
   for j=(rows-1):-1:0
      Iwindow=j+i*rows+1;
      if Iwindow <=length(windows)
%	  p=[screen(1)+j*Xsize, screen(4)-(i+1)*(Ysize+40), Xsize, Ysize]
	 p=[screen(1)+j*Xsize, screen(4)-70-(i+1)*(Ysize), Xsize, Ysize];
	 if nargin<2
				set(windows(Iwindow),'visible','off')
	    set(windows(Iwindow),'position', p);
				set(windows(Iwindow),'visible','on')
	 else
	    if Iwindow==length(windows);
					set(windows(Iwindow),'visible','off')
		 set(windows(Iwindow),'position', p);
	       set(windows(Iwindow),'visible','on')
	    end

	 end
      end

   end
end
