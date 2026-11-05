function [status, result] = sendbashEmail2(subject,to,message,attachment)
% Legacy mail helper deliberately disabled during public-repository recovery.
% It previously carried an SMTP password literal and exposed it in shell args.
% No active analysis cron job calls this helper. Use a separately configured
% notification service if this legacy function is needed again.
status = 1;
result = 'Legacy SMTP helper disabled; configure a secure notification service.';
warning('%s', result);
end
