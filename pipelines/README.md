# pipelines/

Offline tools that produce what the app reads: the database (`data/uniadvisor.db`) and the two trained models in
`models/`. When the default database is absent in a local checkout, the app lazily invokes the database builder once;
otherwise these tools are run manually from the repository root.

Most raw inputs are not published (`pipelines/data/`): cached pages, the universities' documents, reviewed
corrections and the LLM-generated training data. The code is here so that every number in the app can be traced to how
it was made; the tests run the build on a small fixture in the same formats (`tests/rawfixture.py`).

## Database

| Command | What it does |
|---|---|
| `python -m pipelines.collect.run` | Collects published cutoffs for in-scope schools from public pages, through a polite cache (`--offline` rebuilds from the cache only) |
| `python -m pipelines.database.prepare` | The slow step (minutes): applies the rules to the raw inputs and the reviewed corrections and writes the final tables, one CSV per database table with exactly its columns, to `pipelines/data/tables/` (committed). Also writes `data/coverage.md` and the review lists in `data/review/`. `--check` says whether the committed tables are out of date |
| `python -m pipelines.database.build` | Loads the final tables into `data/uniadvisor.db` in seconds: schemas, programs, exam combinations, cutoffs converted to the 30-point scale, tuition, MOET ngành codes and the per-ngành facts |
| `python -m pipelines.database.compare OLD.db NEW.db` | Compares two databases table by table: values, types and row order |
| `python -m pipelines.database.export` | Writes the tables of any built database to a folder of CSVs |
| `python -m pipelines.facts.sheets check` | Checks the reviewed nhóm ngành fact sheets against the numbers in the database |
| `python -m pipelines.facts.apply_review <folder>` | Applies a review round of the occupation mapping and close ngành |

Every rule the build applies is named and recorded on the row it affects; source priority is the university's own
document, then VnExpress, Tuyensinh247 and VietNamNet. Per-ngành facts come from O*NET 31.0 through the CIP 2020 to
O*NET-SOC crosswalk (`pipelines/facts/`).

## Major suggester (`models/suggester/`)

| Command | What it does |
|---|---|
| `python -m pipelines.majors_model.make_notebook` | Writes `pipelines/notebooks/student_generation*.ipynb`: open LLMs on Kaggle write invented students who answer the questionnaire, each planned for one target nhóm ngành (attribute-conditioned generation) |
| `python -m pipelines.majors_model.prepare` | Cleans the generated students (`pipelines/data/students/`) and writes a report |
| `python -m pipelines.majors_model.train` | Fits small learned option weights on top of the O*NET data scores, tests on the LLM family held out from training, runs the behaviour checks, and writes `models/suggester/` |
| `python -m pipelines.majors_model.checks` | Behaviour checks of the data scores alone (the baseline) |

## Chat classifier (`models/message_classifier/`)

| Command | What it does |
|---|---|
| `python -m pipelines.chat_model.make_notebook` | Writes `pipelines/notebooks/chat_message_generation.ipynb`: open LLMs write Vietnamese chat messages for the 28 request types (round 3 is the nine new Part 4 types) |
| `python -m pipelines.chat_model.train` | TF-IDF and logistic regression on the generated messages, tested on the held-out LLM family, reviewed checks and the separate human-written Part 4 holdout when supplied; promotion also requires the Part 4 holdout gate, otherwise it writes only `candidate.joblib` |

## Benchmarks

| Command | What it does |
|---|---|
| `python -m pipelines.benchmarks.bench` | The list rules on 272 invented students (17 shortlists, totals 15-29, two cities) -> `data/bench.md` |
| `python -m pipelines.benchmarks.bench_lists` | The three phương án for the same students -> `data/bench_lists.md` |
| `python -m pipelines.benchmarks.samples` | A few sample students' lists, for reading -> `data/sample_lists.md` |
