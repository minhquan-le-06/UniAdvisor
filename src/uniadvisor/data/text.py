"""Small text helpers shared by the build steps."""

from __future__ import annotations

import re
import unicodedata


def nfc(text) -> str:
    return unicodedata.normalize("NFC", str(text)) if text is not None else ""


def fold(text) -> str:
    """Lowercase, NFC, single spaces: for matching Vietnamese names."""
    return re.sub(r"\s+", " ", nfc(text).lower()).strip()


def norm_code(code) -> str:
    """Normalise a school's program code: uppercase, no whitespace."""
    return re.sub(r"\s+", "", nfc(code)).upper()


# Old-style tone placement -> the new style, so "Hoá học" and "Hóa học" are the same name.
_TONES = {"oá": "óa", "oà": "òa", "oả": "ỏa", "oã": "õa", "oạ": "ọa", "oé": "óe", "oè": "òe", "oẻ": "ỏe",
          "oẽ": "õe", "oẹ": "ọe", "uý": "úy", "uỳ": "ùy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy"}
# Abbreviations and misspellings the sites use in program names.
_ABBREVIATIONS = {"sp": "sư phạm", "gd": "giáo dục", "cnkt": "công nghệ kỹ thuật", "kh": "khoa học",
                  "cn": "công nghệ", "cntt": "công nghệ thông tin", "ttdl": "truyền thông dữ liệu",
                  "qtkd": "quản trị kinh doanh", "xnk": "xuất nhập khẩu", "kỷ": "kỹ", "lich": "lịch",
                  "tri": "trị"}
# Words that only structure a name ("Ngành X, chương trình đào tạo Y").
_STRUCTURE = re.compile(r"chương trình đào tạo|chuyên ngành|nhóm ngành|\bngành\b")
# Phrases that say how or where a program is taught, not what it is (matched on the folded words).
_HOW_TAUGHT = re.compile(
    r"chương trình|ctđt|\bct\b|\bclc\b|chất lượng cao|tiên tiến|tài năng|liên kết|song bằng|"
    r"đơn bằng|định hướng|dự kiến|đại học|dự bị|"
    r"(giảng dạy|dạy|học)( bằng)? tiếng anh|bằng tiếng anh|tiếng anh toàn phần|toàn phần tiếng anh|"
    r"ngoại ngữ tiếng (anh|nhật|hàn|trung)( (anh|nhật|hàn|trung))*|"
    r"(cơ sở|phân hiệu)( tại)? (hà nội|tp hcm|hcm|thành phố hồ chí minh|tp hồ chí minh)|"
    r"kỹ sư|cử nhân|\bhệ\b|\bchuẩn\b")
_GENERIC_WORDS = {"và", "các", "với", "trong", "học", "the", "of", "and", "in"}


def name_words(name, keep_variant: bool = False) -> set[str]:
    """The words that say what a program is: tone placement unified, abbreviations spelt out, words in brackets kept
    (a specialisation is often only there), structure words ('ngành', 'chương trình đào tạo') dropped. Phrases about
    how it is taught ('chất lượng cao', 'bằng tiếng Anh', 'cơ sở Hà Nội') are dropped too, unless `keep_variant`:
    across years they drift, but within one year they tell a school's variants apart (CLC and standard)."""
    text = fold(name)
    for old, new in _TONES.items():
        text = text.replace(old, new)
    words: list[str] = []
    for w in re.findall(r"[^\W\d_]+", text):
        words += _ABBREVIATIONS.get(w, w).split()
    text = _STRUCTURE.sub(" ", " ".join(words))
    if not keep_variant:
        text = _HOW_TAUGHT.sub(" ", text)
    return {w for w in text.split() if w not in _GENERIC_WORDS}


def same_program_name(a, b, min_overlap: float = 0.5) -> bool:
    """Whether two names can be the same program: at least `min_overlap` of the shorter name's specific words are in
    the other. A name with no specific words counts as the same. Lenient on purpose (site names carry typos and
    long specialisations); names that are two different official ngành ("Đông phương học", "Đông Nam Á học") are
    told apart with the MOET catalog (build.reused_code)."""
    wa, wb = name_words(a), name_words(b)
    if not wa or not wb:
        return True
    return len(wa & wb) / min(len(wa), len(wb)) >= min_overlap


def parse_score(raw) -> float | None:
    if raw is None:
        return None
    text = nfc(raw).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def split_combos(raw) -> list[str]:
    """'A00; A01,D01' -> ['A00', 'A01', 'D01'] (order kept, duplicates removed)."""
    if raw is None or (isinstance(raw, float)):
        return []
    seen: list[str] = []
    for part in re.split(r"[;,\s]+", nfc(raw).upper()):
        if part and part not in seen:
            seen.append(part)
    return seen


def combo_key(combos) -> str:
    return ";".join(sorted(set(combos)))
