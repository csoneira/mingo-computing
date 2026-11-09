# CAEN monitor

`monitor.py` is the newer MINGO01 CAEN high-voltage monitor/controller, copied
from `/home/rpcuser/CAEN/monitor.py` on 2026-09-30. Its SHA-256 at retrieval was
`b29778c15661d5abd90e21c115461d69d688c01c65e259e3f6e7b7ea663c427a`.

This supersedes the older MINGO01 copy at `/home/rpcuser/CAENOLD/monitor.py`.
Compared with that copy, it adds comma-separated and all-channel selection,
detects the connected supply's channel count, uses a non-interactive five
second lock timeout, resolves `variables.txt` beside the program, and supports
relative log directories.

The station's `variables.txt` contains local connection settings and is not
stored here. Use `variables.example.txt` as the template. The existing station
automation sync deploys `station_automation_scripts/` only; it does not deploy
this CAEN directory.
