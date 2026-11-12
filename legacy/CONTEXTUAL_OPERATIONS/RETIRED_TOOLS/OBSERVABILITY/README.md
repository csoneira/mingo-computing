# Retired observability utility

`vscode_server_audit.sh` inspected the live process table for VS Code remote
server process topology, age, CPU, and memory use. It was read-only by default;
its optional kill-plan output was not executed automatically. No active cron
entry or tracked caller was found. Preserved here as an operator diagnostic.
