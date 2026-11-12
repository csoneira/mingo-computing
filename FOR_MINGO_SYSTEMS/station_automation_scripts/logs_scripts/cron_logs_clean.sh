#!/bin/bash
# Purpose: Clean station cron logs according to the configured retention policy.

cd /home/rpcuser/logs/

pwd

cat Flow0* > clean_Flow0.txt
echo "Flow file done"

cat hv0* > clean_hv0.txt
sed -i 's/T/ /' clean_hv0.txt
echo "HV file done"

# CAEN logs use hv_YYYY-MM-DD.log and remain separate from LIP's hv0_* logs.
caen_log="hv_$(date +%F).log"
: > clean_hv_caen.txt
if [[ -f "$caen_log" ]]; then
    cat "$caen_log" > clean_hv_caen.txt
fi
sed -i 's/T/ /' clean_hv_caen.txt
echo "CAEN HV file done"

cat sensors_bus0* > clean_sensors_bus0.txt
cat sensors_bus1* > clean_sensors_bus1.txt

sed -i 's/T/ /' clean_sensors_bus*
sed -i 's/;//' clean_sensors_bus*
sed -i 's/nan nan nan nan //' clean_sensors_bus*
echo "Environment files done"

cat rates* > clean_rates.txt
sed -i 's/T/ /' clean_rates*
sed -i 's/;//' clean_rates*
echo "TRB rate file done"
