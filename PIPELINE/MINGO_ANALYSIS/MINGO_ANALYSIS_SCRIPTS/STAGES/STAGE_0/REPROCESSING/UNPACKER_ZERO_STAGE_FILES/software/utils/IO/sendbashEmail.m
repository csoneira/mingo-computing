% Purpose: Send Email.

function [status, result] = sendbashEmail(subject,to,message,attachment)
%!/bin/bash
%sudo apt-get install sendemail
%sudo apt-get install libnet-ssleay-perl
%sudo apt-get install libnet-smtp-ssl-perl
%if error change:
%/usr/bin/sendemail on line 1907: 'SSLv3 TLSv1' => 'SSLv3' 
%if persistent do:
%if (! IO::Socket::SSL->start_SSL($SERVER, SSL_version => 'SSLv23:!SSLv2', SSL_verify_mode => 0)) {


from = '-f rpc.slow.control@gmail.com';
sendTo = ['-t'];
for i=1:max(size(to)) %max(size(to)) will work with column and raw cell arrays
    sendTo = [sendTo ' '  to{i}];
end

sendAttachment = ['-a'];
for i=1:size(attachment,1)
    sendAttachment = [sendAttachment ' ' attachment{i}];
end

[status, result] = system(['sendEmail -o tls=yes ' from ' ' sendTo ' -s smtp.gmail.com:587 -xu rpc.slow.control@gmail.com -xp bgylttrezpuauuho -u "' subject '" -m "' message '" ' sendAttachment]);
