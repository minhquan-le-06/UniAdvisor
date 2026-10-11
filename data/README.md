# data/

The app reads one SQLite database, `data/uniadvisor.db` (about 29 MB). It is not part of this repository: it holds
cutoff scores, tuition and programme data collected from third-party pages and schools' documents.

- To run the app locally, put a built database here, or point `UNIADVISOR_DB` at one.
- `python -m pipelines.database.build` writes it here when the raw inputs are present (`pipelines/README.md`),
  together with `coverage.md` and the review files in `review/`.
