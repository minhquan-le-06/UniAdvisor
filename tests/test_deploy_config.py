"""The deployment files: what Vercel reads (pyproject.toml, vercel.json, web_api.py) and what the images install."""

import json
import tomllib

from fastapi import FastAPI

from uniadvisor.paths import ROOT


def load_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def names(specs) -> set[str]:
    return {s.split("==")[0].split("[")[0].lower() for s in specs}


def test_the_hosted_api_does_not_install_streamlit():
    project = load_pyproject()["project"]
    base = names(project["dependencies"])
    assert {"fastapi", "uvicorn", "pydantic", "slowapi", "huggingface_hub", "scikit-learn", "pandas"} <= base
    assert not {"streamlit", "altair"} & base              # a function over 500 MB does not deploy on Vercel
    assert names(project["optional-dependencies"]["ui"]) == {"streamlit", "altair"}


def test_streamlit_cloud_still_installs_the_ui():
    assert ".[ui]" in (ROOT / "requirements.txt").read_text(encoding="utf-8")


def test_vercel_finds_the_api_and_not_the_streamlit_app(monkeypatch, fake_db_path):
    entry = load_pyproject()["tool"]["vercel"]["entrypoint"]
    assert entry == "web_api:app" and (ROOT / "web_api.py").is_file()
    monkeypatch.setenv("UNIADVISOR_DB", str(fake_db_path))
    import importlib
    import sys
    sys.modules.pop("web_api", None)
    module = importlib.import_module("web_api")
    assert isinstance(module.app, FastAPI)


def test_vercel_json_builds_the_frontend_and_sets_headers():
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert "npm --prefix web run build" in cfg["buildCommand"] and "public" in cfg["buildCommand"]
    fn = cfg["functions"]["web_api.py"]
    assert "config/**" in fn["includeFiles"] and "models/**" in fn["includeFiles"] and "web/dist/**" in fn["includeFiles"]
    headers = {h["source"]: {x["key"]: x["value"] for x in h["headers"]} for h in cfg["headers"]}
    assert headers["/assets/(.*)"]["Cache-Control"] == "public, max-age=31536000, immutable"
    csp = headers["/(.*)"]["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "huggingface" not in csp


def test_vercel_ignore_names_top_level_folders_only():
    lines = [x.strip() for x in (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
             if x.strip() and not x.startswith("#")]
    # A bare name matches at any depth: `data` would drop src/uniadvisor/data and the function would fail at import.
    folders = {x for x in lines if not x.startswith(("**", "*", ".env"))}
    assert folders and all(x.startswith("/") for x in folders), folders
    assert {"/data", "/pipelines", "/docs", "/tests"} <= set(lines)
    kept = {"/config", "/models", "/src", "/web", "/web/src", "/web/package.json", "/web_api.py"}
    assert not kept & set(lines)                         # the build and the function need these


def test_the_package_folders_the_function_imports_are_not_ignored():
    import fnmatch
    ignored = [x.lstrip("/") for x in (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
               if x.startswith("/")]
    for needed in ("src/uniadvisor/data/scope.py", "src/uniadvisor/planner/lists.py", "config/list.yaml",
                   "models/message_classifier/model.joblib", "web/src/main.tsx", "web/package-lock.json"):
        assert not any(needed == i or needed.startswith(i + "/") or fnmatch.fnmatch(needed, i) for i in ignored), needed
