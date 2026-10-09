# Notes API contract, version 1

This is the agent-visible functional contract. Preserve SQLite persistence and
all API behavior while improving performance. The runner selects a fresh database
using `NOTES_DB_PATH`; initialize the application's own schema at startup. Do not
special-case test or workload inputs, disable durability, or change dependencies.

## Notes and validation

A note has exactly `id` (server-generated integer), `title` (string of 1–200
characters), `body` (string of 1–5000 characters), and `tags` (list of strings).
POST and PUT require title/body; omitted tags means an empty list. PUT replaces
all mutable fields. Title/body are preserved literally, including whitespace and
Unicode. Extra request fields are ignored. Strings are not coerced from numbers.

Tags are stripped of surrounding whitespace, empty tags are removed, exact
duplicates are removed, and tags are sorted in Python Unicode string order.
Case is significant: `Work` and `work` are distinct. Tag count/length is not capped.
IDs must be unique among persisted notes; clients bind generated IDs from responses.
All completed mutations must survive process restarts.

| Request | Success | Missing note |
| --- | --- | --- |
| POST /notes | 201, complete created note | N/A |
| GET /notes/{integer id} | 200, complete note | 404 |
| PUT /notes/{integer id} | 200, complete updated note | 404 |
| DELETE /notes/{integer id} | 204, empty body | 404 |
| GET /notes | 200, object described below | N/A |

A missing-note response is exactly `{"detail":"Note not found"}`.
Invalid body/path/query inputs return 422 with FastAPI/Pydantic's pinned
validation response. `validation-errors.json` records exact representative
request/response fixtures, including error locations, messages, inputs, and
constraint context. Preserve those responses; the dependencies are pinned in
the research environment. Successful JSON objects have no extra fields.

## List/search

GET /notes returns `{"items": [notes], "total": integer, "offset": integer,
"limit": integer}`. `total` counts all matching notes before pagination. Sort by
ascending integer ID, then apply offset/limit. Offset defaults to 0 and must be
nonnegative; limit defaults to 20 and must be 1–100. An out-of-range offset returns
an empty items list with the correct total.

- `q` is a case-sensitive literal substring of title OR body. Missing/empty q
  matches all notes. SQL wildcard characters and quotes are ordinary text.
- Repeated `tag` parameters require ALL specified exact, case-sensitive tags.
  Trim surrounding whitespace and ignore empty tag filters.
- Search and tag filters combine with AND.
- Reads and searches must reflect successful creates, updates, and deletes
  immediately, including repeated requests that might be served from a cache.

The existing `/` and `/static` browser interface is ancillary; its requests are
not included in the experiment's objective. The measured operations are add,
get-by-ID, update, delete, and separately reported list/search.
