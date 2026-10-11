"""Splitting one message into requests: "Toán 8,5 rồi bỏ trường Bách khoa" -> two requests.

Strong breaks (sentence ends, 'rồi', 'sau đó', 'ngoài ra', 'với lại') always split. Weak breaks (',', 'và', 'còn')
split only when the pieces are different change requests: "toán 8, văn 7" stays one request (both scores), "ngân
sách 40 triệu và bỏ trường Bách khoa" becomes two. Questions are never split at weak breaks ("CNTT và KHMT khác gì").
"""

from __future__ import annotations

import re

from uniadvisor.chat.classify import Classifier
from uniadvisor.chat.types import OTHER, QUESTION_TYPES

_STRONG = re.compile(r"(?<=[!?;])\s*|(?<=\.)\s+(?!\d)|\n+|\s+(?=(?:rồi|roi|sau đó|sau do|ngoài ra|ngoai ra|với lại|"
                     r"voi lai|thêm nữa|them nua|xong)\s)", re.IGNORECASE)
_STRONG_WORDS = re.compile(r"^(?:rồi|roi|sau đó|sau do|ngoài ra|ngoai ra|với lại|voi lai|thêm nữa|them nua|xong)\s+",
                           re.IGNORECASE)
_WEAK = re.compile(r"\s*,\s*|\s+(?:và|còn|cùng với)\s+", re.IGNORECASE)


def split_requests(text: str, classifier: Classifier) -> list[tuple[str, str]]:
    """[(request text, type)] in message order."""
    out: list[tuple[str, str]] = []
    for piece in _STRONG.split(text or ""):
        piece = _STRONG_WORDS.sub("", piece.strip()).strip(" .,;")
        if not piece:
            continue
        whole_type, _ = classifier.classify(piece)
        if whole_type in QUESTION_TYPES:
            out.append((piece, whole_type))
            continue
        parts: list[list] = []                        # [text, type]
        for part in _WEAK.split(piece):
            part = part.strip(" .,;")
            if not part:
                continue
            ptype, _ = classifier.classify(part)
            if parts and (ptype == OTHER or ptype == parts[-1][1]):
                parts[-1][0] += ", " + part
            else:
                parts.append([part, ptype])
        if len(parts) > 1 and parts[0][1] == OTHER:  # a leading fragment without a type joins the next request
            parts[1][0] = parts[0][0] + ", " + parts[1][0]
            parts.pop(0)
        if len(parts) <= 1:
            out.append((piece, whole_type))
        else:
            out += [(t, ty) for t, ty in parts]
    return out
