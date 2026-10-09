"""Numbers in Vietnamese messages: '8,5', '8.25', '40tr', '1tr5', 'bốn mươi triệu', 'tám phẩy hai lăm', 'tám rưỡi'.

find_numbers returns every number with its position and unit, so the extractors can pair a number with the subject or
school next to it. A number written as a single ambiguous word ('năm' is also "year", 'một' also "a", 'tư' also
"private") is marked weak; extractors accept a weak number only right after what it belongs to.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

DIGITS = {
    "không": 0, "khong": 0, "một": 1, "mot": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "bon": 4, "tư": 4, "tu": 4,
    "năm": 5, "nam": 5, "lăm": 5, "lam": 5, "nhăm": 5, "sáu": 6, "sau": 6, "bảy": 7, "bay": 7, "tám": 8, "tam": 8,
    "chín": 9, "chin": 9,
}
TEN = {"mười", "muoi"}           # 'mười' = 10, as a prefix 1x
TENS = {"mươi", "muoi"}          # 'hai mươi' = 20
HUNDRED = {"trăm", "tram"}
LINH = {"linh", "lẻ", "le"}
POINT = {"phẩy", "phay", "chấm", "cham"}
HALF = {"rưỡi", "ruoi"}
WEAK = {"năm", "nam", "một", "mot", "tư", "tu", "ba", "sáu", "sau", "bay", "tam", "lam"}
NUMBER_WORDS = set(DIGITS) | TEN | TENS | HUNDRED | LINH | POINT | HALF

UNITS = {
    "trieu": ("triệu", "tr", "trieu", "củ", "cu", "m"),
    "diem": ("điểm", "diem", "đ", "d"),
    "nghin": ("nghìn", "nghin", "ngàn", "ngan", "k"),
}


@dataclass(frozen=True)
class Number:
    value: float
    start: int                  # character offsets in the normalised text
    end: int
    unit: str | None            # 'trieu', 'diem', 'nghin' or None
    weak: bool = False


def normalise(text: str) -> str:
    """NFC, lowercase, single spaces (offsets of find_numbers refer to this)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).lower()).strip()


def _words_value(words: list[str]) -> float | None:
    """Value of a run of number words, or None when it is not a well-formed number."""
    if not words:
        return None
    if any(w in POINT for w in words):
        i = next(i for i, w in enumerate(words) if w in POINT)
        whole, tail = _int_value(words[:i]), words[i + 1:]
        if tail and all(w in DIGITS for w in tail):      # digits read one by one: 'hai lăm' -> 25, 'không năm' -> 05
            frac = "".join(str(DIGITS[w]) for w in tail)
        else:
            value = _int_value(tail)
            frac = None if value is None else str(value)
        if whole is None or frac is None:
            return None
        return float(f"{whole}.{frac}")
    half = words[-1] in HALF
    value = _int_value(words[:-1] if half else words)
    if value is None:
        return None
    return value + (0.5 if half else 0)


def _int_value(words: list[str]) -> int | None:
    if not words:
        return None
    if any(w in HUNDRED for w in words):
        i = next(i for i, w in enumerate(words) if w in HUNDRED)
        head = _int_value(words[:i]) if i else 1
        rest = words[i + 1:]
        if rest and rest[0] in LINH:
            rest = rest[1:]
            tail = _int_value(rest) if rest else 0
            if tail is None or tail > 9:
                return None
        else:
            tail = _int_value(rest) if rest else 0
        return None if head is None or tail is None or head > 9 else head * 100 + tail
    if len(words) == 1:
        w = words[0]
        if w in TEN:
            return 10
        return DIGITS.get(w) if w not in ("lăm", "lam", "nhăm", "mốt") else None
    if words[0] in TEN:                                   # mười hai, mười lăm
        if len(words) == 2 and words[1] in DIGITS and words[1] not in ("mốt",):
            return 10 + DIGITS[words[1]]
        return None
    if len(words) >= 2 and words[1] in TENS and words[0] in DIGITS and words[0] not in ("lăm", "lam", "mốt"):
        tens = DIGITS[words[0]] * 10                      # hai mươi, hai mươi mốt, hai mươi lăm
        if tens == 0:
            return None
        if len(words) == 2:
            return tens
        if len(words) == 3 and words[2] in DIGITS:
            return tens + DIGITS[words[2]]
        return None
    if all(w in DIGITS for w in words) and len(words) == 2 and words[1] in ("lăm", "lam"):
        return None
    return None


_DIGIT_RE = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![\d])")
_TR_SLANG = re.compile(r"(?<![\w.,])(\d+)\s*(tr|triệu|trieu|củ|cu)\s*(\d)(?![\d\w])")   # 1tr5 = 1.5 triệu
_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)


def _unit_after(text: str, end: int) -> tuple[str | None, int]:
    m = re.match(r"\s*([^\W\d_]+)", text[end:])
    if m:
        word = m.group(1)
        for unit, forms in UNITS.items():
            if word in forms:
                return unit, end + m.end()
    return None, end


def find_numbers(text: str) -> list[Number]:
    """Every number in normalised text (see normalise), in order of position."""
    out: list[Number] = []
    taken: list[tuple[int, int]] = []
    for m in _TR_SLANG.finditer(text):
        out.append(Number(float(f"{m.group(1)}.{m.group(3)}"), m.start(), m.end(), "trieu"))
        taken.append((m.start(), m.end()))

    def free(s, e):
        return all(e <= a or s >= b for a, b in taken)

    for m in _DIGIT_RE.finditer(text):
        if not free(m.start(), m.end()):
            continue
        value = float(m.group(1).replace(",", "."))
        # a unit glued to the number: '40tr', '8đ'
        glued = re.match(r"(tr|triệu|trieu|củ|đ|k)\b", text[m.end():])
        if glued:
            unit = {"tr": "trieu", "triệu": "trieu", "trieu": "trieu", "củ": "trieu", "đ": "diem", "k": "nghin"}[
                glued.group(1)]
            end = m.end() + glued.end()
        else:
            unit, end = _unit_after(text, m.end())
        out.append(Number(value, m.start(), end, unit))
        taken.append((m.start(), end))

    tokens = [(t.group(0), t.start(), t.end()) for t in _TOKEN.finditer(text)]
    i = 0
    while i < len(tokens):
        if tokens[i][0] not in NUMBER_WORDS or tokens[i][0] in POINT | HALF | LINH | TENS - TEN:
            i += 1
            continue
        j = i
        while j < len(tokens) and tokens[j][0] in NUMBER_WORDS and (j == i or tokens[j][1] - tokens[j - 1][2] <= 1):
            j += 1
        # longest well-formed run starting at i
        for k in range(j, i, -1):
            words = [t[0] for t in tokens[i:k]]
            value = _words_value(words)
            if value is not None and free(tokens[i][1], tokens[k - 1][2]):
                unit, end = _unit_after(text, tokens[k - 1][2])
                weak = len(words) == 1 and words[0] in WEAK
                out.append(Number(value, tokens[i][1], end, unit, weak))
                taken.append((tokens[i][1], end))
                i = k
                break
        else:
            i += 1
    return sorted(out, key=lambda n: n.start)
