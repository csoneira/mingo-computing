#!/bin/bash
# Purpose: Join station cron logs into the configured summary.

cd /home/rpcuser/logs/'done'

shopt -s nullglob
log_dir=/home/rpcuser/logs
today=$(date +%F)

# Archive completed CAEN daily files without touching LIP's hv0_* files.
for caen_log in "$log_dir"/hv_????-??-??.log; do
    log_date=${caen_log##*/hv_}
    log_date=${log_date%.log}
    if [[ "$log_date" < "$today" ]]; then
        mv -n -- "$caen_log" .
    fi
done

pwd

rm -f merged_Flow0.txt merged_hv0.txt merged_sensors_bus0.txt merged_sensors_bus1.txt merged_rates.txt merged_hv_caen.txt
: > merged_Flow0.txt
: > merged_hv0.txt
: > merged_sensors_bus0.txt
: > merged_sensors_bus1.txt
: > merged_rates.txt
: > merged_hv_caen.txt

echo 'Starting Flow merge'

flow_logs=(Flow0*)
((${#flow_logs[@]})) && cat "${flow_logs[@]}" >> merged_Flow0.txt

echo 'Flow done'

echo 'Starting HV merge'

lip_hv_logs=(hv0*)
((${#lip_hv_logs[@]})) && cat "${lip_hv_logs[@]}" >> merged_hv0.txt
sed -i 's/T/ /' merged_hv0.txt

echo 'HV done'

echo 'Starting environmental sensors merge'

sensors_bus0_logs=(sensors_bus0*)
sensors_bus1_logs=(sensors_bus1*)
((${#sensors_bus0_logs[@]})) && cat "${sensors_bus0_logs[@]}" >> merged_sensors_bus0.txt
((${#sensors_bus1_logs[@]})) && cat "${sensors_bus1_logs[@]}" >> merged_sensors_bus1.txt

sed -i 's/T/ /' merged_sensors_bus*
sed -i 's/;//' merged_sensors_bus*
sed -i 's/nan nan nan nan //' merged_sensors_bus*

echo 'Done'

echo 'Starting TRB rate merge'

rate_logs=(rates*)
((${#rate_logs[@]})) && cat "${rate_logs[@]}" >> merged_rates.txt
sed -i 's/T/ /' merged_rates*
sed -i 's/;//' merged_rates*

echo 'TRB rate merge done'

echo 'Starting CAEN HV merge'
caen_logs=(hv_????-??-??.log)
((${#caen_logs[@]})) && cat "${caen_logs[@]}" >> merged_hv_caen.txt
sed -i 's/T/ /' merged_hv_caen.txt
echo 'CAEN HV merge done'
