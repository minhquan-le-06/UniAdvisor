# data/

The app reads one SQLite database, `data/uniadvisor.db` (about 29 MB). It is not part of this repository: it holds
cutoff scores, tuition and programme data collected from third-party pages and schools' documents.

- On the first local app launch, this default database is built here from the final tables in
  `pipelines/data/tables/`. Or point `UNIADVISOR_DB` at an already built database; a missing explicitly configured
  path is reported and never created.
- The hosted web version never builds it: it downloads this file from a private Hugging Face dataset at startup
  (`tools/upload_db.py` uploads it; `docs/design/web.md`).
- `python -m pipelines.database.build` writes it here in seconds from those final tables (development repository only;
  `pipelines/README.md`).
- `python -m pipelines.database.prepare` is slow and is run by whoever changes the source data; it writes the final
  tables, `coverage.md` and the review files in `review/`.
