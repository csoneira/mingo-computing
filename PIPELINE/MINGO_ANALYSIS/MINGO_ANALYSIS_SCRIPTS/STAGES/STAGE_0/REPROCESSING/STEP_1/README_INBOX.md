# Stage 0 reprocessing petition inbox

For MINGO01, add one petition per line to:

`MINGO01/STAGE_0/REPROCESSING/INBOX/PETITIONS.txt`

Accepted forms:

```text
dates 2026-10-20 2026-10-29
force-dates 2026-10-20 2026-10-29
name mi0126293003302
force-name mi0126293003302
```

`dates` includes both dates and skips files already present in Task 3 metadata.
`name` requests one exact file and skips it if it was already analyzed. Use
`force-dates` or `force-name` to explicitly reprocess a date range or exact file. A successful request is removed from
`PETITIONS.txt`, fetched HLDs are unpacked into the Stage 0 Step 2
`UNPROCESSED` queue, and the request plus its interpretation is appended to
`INBOX/ATTENDED.md`. A failed or malformed petition stays in the inbox for
correction or retry.

The unattended poller runs every five minutes for MINGO01. “Attended” means
the HLDs were fetched and admitted to the Stage 0 queue (or the request was
already satisfied); downstream Task 3 completion is tracked separately by the
existing pipeline metadata.

Run one poll manually with:

```bash
python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/STEP_1/process_reprocessing_inbox.py 1
```
