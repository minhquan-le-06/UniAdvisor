"""The web API's entry point for Vercel (and for `uvicorn web_api:app`).

app.py in this folder is the Streamlit app, so the API has its own file; pyproject.toml ([tool.vercel] entrypoint)
points Vercel here. The package lives in src/, which is put on the path first. The database is loaded when the
function starts: UNIADVISOR_DB if set, else downloaded from the private dataset UNIADVISOR_DB_REPO with HF_TOKEN into
the temporary folder (src/uniadvisor/api/dbfetch.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from uniadvisor.api.app import create_app  # noqa: E402

app = create_app()
