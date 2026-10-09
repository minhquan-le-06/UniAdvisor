"""Repository paths, resolved from the package location."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
RULES_DIR = CONFIG_DIR / "rules"
INPUTS_DIR = ROOT / "data" / "inputs"
CURATED_DIR = ROOT / "data" / "curated"
COLLECTED_DIR = ROOT / "data" / "collected"          # our own collectors' CSVs (uniadvisor.collect)
COLLECTED_CACHE_DIR = ROOT / "data" / "cache" / "http"
BUILD_DIR = ROOT / "data" / "build"
DB_PATH = BUILD_DIR / "uniadvisor.db"
