"""Repository paths, resolved from the package location."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
RULES_DIR = CONFIG_DIR / "rules"

# The app reads one SQLite database; the pipelines write it, and their reports, next to it.
BUILD_DIR = ROOT / "data"
DB_PATH = BUILD_DIR / "uniadvisor.db"

# What the offline pipelines read (pipelines/README.md).
PIPELINE_DATA = ROOT / "pipelines" / "data"
INPUTS_DIR = PIPELINE_DATA / "inputs"
CURATED_DIR = PIPELINE_DATA / "curated"              # reviewed corrections: the only files people edit
TABLES_DIR = PIPELINE_DATA / "tables"                # the final tables, one CSV per table, written by prepare
COLLECTED_DIR = PIPELINE_DATA / "collected"          # our own collectors' CSVs (pipelines.collect)
COLLECTED_CACHE_DIR = PIPELINE_DATA / "cache" / "http"
