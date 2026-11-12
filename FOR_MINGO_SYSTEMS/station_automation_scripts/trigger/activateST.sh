#!/bin/bash
# Purpose: Enable self-trigger acquisition temporarily, then restore the previous DAQ mode.

# Enable the existing self-trigger + M3 configuration for one minute, then
# return to the existing M3 configuration. A lock prevents overlapping runs.
export PATH="$PATH:$HOME/trbsoft/trbnettools/bin:$HOME/trbsoft/daqdata/bin"
. /home/rpcuser/trbsoft/trb3/dabc/dabclogin
export DAQOPSERVER=localhost:1

exec 9>/tmp/activateST.lock
flock -n 9 || exit 0

TRIGGER_DIR=/home/rpcuser/trbsoft/userscripts/trb/trigger
restore_trigger() {
    "$TRIGGER_DIR/setTrigger2M3.sh"
}
trap restore_trigger EXIT

"$TRIGGER_DIR/setTrigger2ST+M3.sh"
sleep 60
