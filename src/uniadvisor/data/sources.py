"""Load each raw input into a uniform shape. No decisions here beyond parsing; see build.py."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from uniadvisor.data.text import fold, nfc, norm_code, parse_score, split_combos

# Columns of a cutoff observation, whatever the site.
OBS_COLUMNS = ["source_id", "school_code", "program_code", "program_name", "year", "combos", "score",
               "raw_score", "note", "url", "tuition_raw"]

THPT_METHOD_CODE = "100"   # unipilot method code of "ĐT THPT" (xét điểm thi tốt nghiệp THPT)


def _csv(path: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", **kw).map(nfc)


# ---------------------------------------------------------------- unipilot export

def load_unipilot(inputs: Path) -> dict[str, pd.DataFrame]:
    d = inputs / "unipilot"
    programs = _csv(d / "program.csv")
    programs["program_id"] = programs["id"].str.replace(r"@\d{4}$", "", regex=True)
    programs["norm_code"] = programs["program_code"].map(norm_code)
    return {
        "schools": _csv(d / "school.csv"),
        "programs": programs,
        "methods": _csv(d / "program_admission_method.csv"),
        "program_combos": _csv(d / "program_subject_combo.csv"),
        "subjects": _csv(d / "subject.csv"),
        "combo_parts": _csv(d / "subject_combo_part.csv"),
    }


def unipilot_thpt_programs(u: dict[str, pd.DataFrame]) -> set[str]:
    """Unipilot program ids (with '@year') that list the THPT exam method."""
    m = u["methods"]
    return set(m.loc[m["method_code"] == THPT_METHOD_CODE, "program_id"])


def is_combined_exam_method(label: str) -> bool:
    """A method that mixes the exam score with something else ('THPT + Học bạ', 'THPT + CCNN', 'Kết Hợp')."""
    text = fold(label)
    return ("thpt" in text and "+" in text) or text == "kết hợp"


def is_talent_method(label: str) -> bool:
    """A combined method that needs a school-run talent test ('THPT + NK')."""
    return bool(re.search(r"\bnk\b|năng khiếu", fold(label)))


def unipilot_thpt_method_label(u: dict[str, pd.DataFrame]) -> str:
    m = u["methods"]
    labels = m.loc[m["method_code"] == THPT_METHOD_CODE, "method_label"].unique()
    if len(labels) != 1:
        raise ValueError(f"Expected one label for method code {THPT_METHOD_CODE}, got {labels}")
    return labels[0]


# ---------------------------------------------------------------- MOET catalog

def load_moet(inputs: Path) -> pd.DataFrame:
    return _csv(inputs / "manual" / "moet_majors.csv")


# ---------------------------------------------------------------- cutoff sites

def _obs(df: pd.DataFrame, source_id: str, score_col: str, combos_col: str, note_col: str | None,
         tuition_col: str | None) -> pd.DataFrame:
    out = pd.DataFrame({
        "source_id": source_id,
        "school_code": df["school_code"].str.strip().str.upper(),
        "program_code": df["program_code"].map(norm_code),
        "program_name": df["program_name"].str.strip(),
        "year": df["year"].astype(int),
        "combos": df[combos_col].map(split_combos),
        "score": df[score_col].map(parse_score),
        "raw_score": df[score_col],
        "note": df[note_col] if note_col else "",
        "url": df["url"],
        "tuition_raw": df[tuition_col] if tuition_col else "",
    })
    return out[OBS_COLUMNS]


def _site_csv(inputs: Path, collected: Path | None, name: str) -> pd.DataFrame:
    """The site's CSV from the old inputs, plus the same file from our own collectors when present."""
    frames = [_csv(inputs / "collected" / name)]
    if collected is not None and (collected / name).exists():
        frames.append(_csv(collected / name))
    return pd.concat(frames, ignore_index=True)


def load_vnexpress(inputs: Path, collected: Path | None = None) -> pd.DataFrame:
    df = _site_csv(inputs, collected, "vnexpress_cutoffs.csv")
    return _obs(df, "vnexpress", "thpt_score_raw", "combos", "other_methods", "tuition_raw")


def load_tuyensinh247(inputs: Path, collected: Path | None = None) -> pd.DataFrame:
    df = _site_csv(inputs, collected, "tuyensinh247_cutoffs.csv")
    return _obs(df, "tuyensinh247", "score_raw", "combos", None, None)


def load_vietnamnet(inputs: Path, collected: Path | None = None) -> pd.DataFrame:
    df = _site_csv(inputs, collected, "vietnamnet_cutoffs.csv")
    return _obs(df, "vietnamnet", "score_raw", "combos_raw", "note", None)


# VietNamNet mixes admission methods; the method is only stated in the free-text note.
_VNN_THPT = re.compile(r"thpt", re.I)
_VNN_OTHER = re.compile(
    r"học bạ|\bhb\b|đgnl|đgtd|hsa|tsa|v-sat|\bsat\b|\bnk\b|năng khiếu|kết hợp|\+|ccqt|ccnn|chứng chỉ|"
    r"ielts|phỏng vấn|ưu tiên xét|xét tuyển thẳng|gpa|\bib\b|a-level|quy đổi|v-act|spt|h-sca", re.I
)


def vietnamnet_method(note: str) -> str:
    """'thpt' when the note says the row is the THPT exam method only; 'other' or 'unknown' otherwise."""
    text = nfc(note)
    if not text.strip():
        return "unknown"
    if _VNN_OTHER.search(text):
        return "other"
    if _VNN_THPT.search(text):
        return "thpt"
    return "unknown"


_WEIGHT_SUBJECTS = {"anh": "N1", "tiếng anh": "N1", "toán": "TO", "văn": "VA", "ngữ văn": "VA", "lý": "LI",
                    "vật lí": "LI", "vật lý": "LI", "hóa": "HO", "hoá": "HO", "sinh": "SI", "sử": "SU",
                    "địa": "DI"}
_WEIGHT_RE = re.compile(r"môn\s+([^\s()|,;]+(?:\s[^\s()|,;]+)?)\s+hệ số\s*2", re.I)


def doubled_subject(note: str) -> str | None:
    """Subject code doubled according to a note like '(điểm môn Anh hệ số 2)'."""
    m = _WEIGHT_RE.search(nfc(note))
    if not m:
        return None
    return _WEIGHT_SUBJECTS.get(fold(m.group(1)))


def stated_scale(note: str) -> int | None:
    """Scale stated in a note ('Thang điểm: 40', 'Thang điểm 100')."""
    m = re.search(r"thang điểm:?\s*(\d+)", nfc(note), flags=re.I)
    return int(m.group(1)) if m else None
