# Researcher-only baseline inventory

Do not copy this document into experimental workspaces or prompts.

The baseline deliberately retains ordinary implementation costs: list/search
loads every SQLite row and constructs every Pydantic note before filtering and
pagination; each request opens a connection; tag JSON and sets are repeatedly
materialized; writes read back full rows; and there are no secondary indexes.
These are opportunities to investigate, not guarantees that changing them helps.
There are no artificial delays or planted correctness failures in the baseline.

The existing browser UI is retained as an inherited convenience and excluded from
the benchmark. Building more UI is outside the research scope. Do not optimize the
baseline as part of controller setup. Schema/query/cache changes belong to
experimental candidate snapshots once the protected runner exists.

The initial five-repetition development measurement is too small to establish
30 iterations of optimization headroom. Dataset size, workload length, noise,
power conditions, and an acceptance threshold still require a representative
pilot before final experiments.
