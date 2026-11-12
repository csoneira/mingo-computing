% Purpose: Configure conf for the legacy Stage-0 unpacker.

%% Configuration

# Display the HOME variable
disp(['loadGeneralConf.m --> Current HOME used: ' HOME]);  % <-- Echo HOME to stdout/log

path(path,[HOME 'software/']);
path(path,[HOME 'software/conf/']);
path(path,[HOME 'software/utils/IO/']);
path(path,[HOME 'software/utils/plot/']);
path(path,[HOME 'software/utils/var/']);
path(path,[HOME 'software/utils/sejda-console-3.2.14/']);path4sejda = [HOME 'software/utils/sejda-console-3.2.14/'];
path(path,[HOME 'software/dc/']);
path(path,[HOME 'software/daq/']);
path(path,[HOME 'software/ana/']);
path(path,[HOME 'software/online/']);
