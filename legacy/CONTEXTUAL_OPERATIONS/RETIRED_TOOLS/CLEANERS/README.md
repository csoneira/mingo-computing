# Retired cleanup helpers

`rank_parquet_lake_candidates.py` emitted a NUL-delimited ranking of Parquet
lake files, placing files outside configured date-interest ranges before files
inside those ranges and sorting each group oldest-first. It was read-only, had
no active in-repository caller, and was not used by `clean_dataflow.py`.
Preserved here for reference; it does not perform cleanup itself.
