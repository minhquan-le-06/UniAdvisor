"""Values of one request, by its type (spec 5, step 3): rules and name matching, never the model.

extract(text, type, ctx) -> Items. What is unclear stays open on the Item with the options to choose from; the change
card asks for it.
"""

from __future__ import annotations

import re

from uniadvisor.app.state import AREAS, CATEGORIES
from uniadvisor.app.texts import CATEGORY_VI
from uniadvisor.chat.changes import Item
from uniadvisor.chat.context import ChatContext
from uniadvisor.chat.mentions import (
    Mention, find_area, find_category, find_levels, find_nv, find_subjects, prefer_nganh,
)
from uniadvisor.chat.numbers import Number, find_numbers, normalise
from uniadvisor.data.scope import strip_accents

# Words that may sit between a subject and its score: "toán được 8", "văn thi dự kiến khoảng 7,5", "toán: 8".
FILLER = {"duoc", "la", "thi", "du", "kien", "khoang", "tam", "chac", "diem", "con", "mon", "em", "minh", "co", "dat",
          "se", "thanh", "len", "xuong", "sua", "doi", "lai", "nua", "toi", "tui", "chi"}
NO_LIMIT = re.compile(r"\b(khong (gioi han|lo|quan trong|can tinh)|bo (gioi han|ngan sach)|thoai mai|bao nhieu cung "
                      r"duoc|khong co ngan sach|xoa ngan sach)\b")
NEG = r"(?:khong|chang|cha|ko|k)"
NEAR_ON = re.compile(rf"\b{NEG} (?:muon|thich|can|nen) (?:phai )?(?:di )?(?:hoc )?xa\b")   # "không muốn đi xa"
NEAR_OFF = re.compile(
    rf"\b{NEG} (?:can|muon|thich|bat buoc|nhat thiet|quan trong)? ?(?:phai )?(?:hoc )?(?:o )?gan(?: nha)?\b"
    r"|\bgan nha (?:khong|cha|ko) (?:quan trong|can|sao)\b"
    r"|\bxa(?: nha)? (?:cung|van) (?:duoc|ok|on|khong sao)\b"
    r"|\b(?:tat|bo) (?:che do |yeu cau |dieu kien )?(?:hoc )?gan nha\b"
    r"|\b(?:muon|thich|di) (?:hoc )?xa\b")          # negated forms are caught by NEAR_ON first


def near_home_value(key: str) -> bool:
    """Turn "học gần nhà" on (True) or off (False) from an accent-free message."""
    if NEAR_ON.search(key):
        return True
    return not NEAR_OFF.search(key)


CLOSE_WORDS = re.compile(r"\b(nganh gan|gan nhau|nganh phu|nganh lien quan)\b")


def _gap_is_filler(text: str, a: int, b: int) -> bool:
    words = re.findall(r"[a-z0-9]+", strip_accents(text[a:b]))
    return all(w in FILLER for w in words)


def _score_for(mention: Mention, nxt: Mention | None, numbers: list[Number], norm: str) -> Number | None:
    limit = nxt.start if nxt else len(norm)
    after = [n for n in numbers if mention.end <= n.start < limit and 0 <= n.value <= 10 and n.unit != "trieu"]
    for n in after:
        if not n.weak or _gap_is_filler(norm, mention.end, n.start):
            return n
    before = [n for n in numbers if n.end <= mention.start and 0 <= n.value <= 10 and n.unit in (None, "diem")]
    if before and _gap_is_filler(norm, before[-1].end, mention.start) and not before[-1].weak:
        return before[-1]                                 # "8 điểm toán"
    return None


def _school_item(kind: str, m: Mention, ctx: ChatContext, text: str, allowed: list[str] | None = None) -> Item:
    values = [v for v in m.values if allowed is None or v in allowed] or list(m.values)
    item = Item(kind, {"school": values[0] if len(values) == 1 else None}, text=text)
    if len(values) > 1:
        item.open = ["school"]
        item.options["school"] = [(v, ctx.school_label(v)) for v in values]
    return item


def _open_school(kind: str, ctx: ChatContext, text: str, pool: list[str]) -> Item:
    return Item(kind, {"school": None}, {"school": [(c, ctx.school_label(c)) for c in pool]}, ["school"], text)


def extract(text: str, rtype: str, ctx: ChatContext) -> list[Item]:
    norm = normalise(text)
    key = strip_accents(norm)
    numbers = find_numbers(norm)
    fn = _EXTRACTORS.get(rtype)
    return fn(text, norm, key, numbers, ctx) if fn else [Item(rtype, text=text)]


def _scores(text, norm, key, numbers, ctx):
    mentions = find_subjects(text, set(ctx.subjects))
    items = []
    for i, m in enumerate(mentions):
        n = _score_for(m, mentions[i + 1] if i + 1 < len(mentions) else None, numbers, norm)
        item = Item("set_score", {"subject": m.values[0], "value": n.value if n else None}, text=text)
        if n is None:
            item.open = ["value"]
        items.append(item)
    if not mentions:
        scores = [n for n in numbers if 0 <= n.value <= 10 and not n.weak]
        item = Item("set_score", {"subject": None, "value": scores[0].value if scores else None},
                    {"subject": list(ctx.subjects.items())}, ["subject"] + ([] if scores else ["value"]), text)
        items.append(item)
    return items


def _priority(text, norm, key, numbers, ctx):
    items = [Item("set_area", {"value": m.values[0]}, text=text) for m in find_area(text)[:1]]
    items += [Item("set_category", {"value": m.values[0]}, text=text) for m in find_category(text)[:1]]
    if not items:
        items.append(Item("set_area", {"value": None}, {"value": [(a, a) for a in AREAS]}, ["value"], text))
        items.append(Item("set_category", {"value": None}, {"value": [(c, CATEGORY_VI[c]) for c in CATEGORIES]},
                          ["value"], text))
    return items


def _budget(text, norm, key, numbers, ctx):
    if NO_LIMIT.search(key):
        return [Item("set_budget", {"value": None}, text=text)]
    value = None
    for unit in ("trieu", "nghin", None):
        found = [n for n in numbers if n.unit == unit and not n.weak]
        if found:
            v = found[0].value
            value = v / 1000 if unit == "nghin" else (v / 1_000_000 if v >= 100_000 else v)
            break
    item = Item("set_budget", {"value": value}, text=text)
    if value is None or not 0 < value <= 1000:
        item.params["value"], item.open = None, ["value"]
    return [item]


def _near_home(text, norm, key, numbers, ctx):
    return [Item("set_near_home", {"value": near_home_value(key)}, text=text)]


def _extra(text, norm, key, numbers, ctx):
    schools = ctx.indexes.schools.find(text)
    spans = [(m.start, m.end) for m in schools]
    points = [n for n in numbers if 0 <= n.value <= 10 and not n.weak
              and not any(a <= n.start < b for a, b in spans)]
    items = []
    for i, m in enumerate(schools):
        nxt = schools[i + 1].start if i + 1 < len(schools) else len(norm)
        prev = schools[i - 1].end if i else 0
        mine = [n for n in points if m.end <= n.start < nxt] or [n for n in points if prev <= n.start < m.start]
        if not mine and len(points) == 1:
            mine = points
        item = _school_item("set_extra", m, ctx, text, ctx.school_names and list(ctx.school_names))
        item.params["value"] = mine[0].value if mine else None
        if not mine:
            item.open.append("value")
        items.append(item)
    if not schools:
        item = _open_school("set_extra", ctx, text, ctx.schools_on_list or list(ctx.school_names))
        item.params["value"] = points[0].value if points else None
        if not points:
            item.open.append("value")
        items.append(item)
    return items


NO_FAVORITE = re.compile(r"\b(bo|xoa|khong con|khong co|het) (chon )?(truong )?(yeu thich|thich nhat)\b"
                         r"|\b(khong|chua) (co )?truong (nao )?(yeu thich|thich nhat)\b")
LOWER = re.compile(r"\b(thap hon|giam|ao|lam phat|nhieu (muc )?diem cong|khong cao (bang|nhu)|de hon)\b")
REVERT = re.compile(r"\b(bo|xoa|huy) (dieu chinh|chinh|diem tu tinh|diem xet tuyen)\b|\bnhu (cu|cong bo)\b")


def _schools_or_open(kind: str, text: str, ctx: ChatContext) -> list[Item]:
    found = ctx.indexes.schools.find(text)
    if found:
        return [_school_item(kind, found[0], ctx, text, list(ctx.school_names))]
    return [_open_school(kind, ctx, text, ctx.schools_on_list or list(ctx.school_names))]


def _favorite(text, norm, key, numbers, ctx):
    if NO_FAVORITE.search(key):
        return [Item("set_favorite", {"school": None}, text=text)]
    return _schools_or_open("set_favorite", text, ctx)


def _own_score(text, norm, key, numbers, ctx):
    item = _schools_or_open("set_own_score", text, ctx)[0]
    if REVERT.search(key):
        item.params["value"] = None
        return [item]
    found = [n for n in numbers if 0 < n.value <= 100 and not n.weak and n.unit != "trieu"
             and not strip_accents(norm[max(0, n.start - 7):n.start]).rstrip().endswith("thang")]   # "thang 100"
    item.params["value"] = found[-1].value if found else None      # "điểm xét tuyển ... của em là 82"
    if not found:
        item.open.append("value")
    return [item]


def _cutoff_shift(text, norm, key, numbers, ctx):
    """'Điểm chuẩn UIT thực ra thấp hơn 1 điểm' -> UIT -1. Numbers above 5 are cutoffs, not the shift ("30 điểm
    của UIT không cao bằng 29 của HCMUS"): the amount is then asked on the card, with the sign from the words."""
    item = _schools_or_open("set_cutoff_shift", text, ctx)[0]
    if REVERT.search(key):
        item.params["value"] = 0.0
        return [item]
    sign = -1.0 if LOWER.search(key) else 1.0
    cutoffs = [n.value for n in numbers if n.value > 5 and not n.weak and n.unit != "trieu"]
    if len(cutoffs) == 2 and sign < 0 and 0 < cutoffs[0] - cutoffs[1] <= 5:
        item.params["value"] = round(cutoffs[1] - cutoffs[0], 2)    # "30 của A không cao bằng 29 của B": A -1
        return [item]
    found = [n for n in numbers if 0 < n.value <= 5 and not n.weak and n.unit != "trieu"]
    item.params["value"] = sign * found[0].value if found else None
    if not found:
        item.open.append("value")
    return [item]


def _remove(text, norm, key, numbers, ctx):
    items = []
    for m in find_nv(text):
        w = ctx.wishes_by_nv.get(int(m.values[0]))
        if w:
            items.append(Item("remove_program", {"program": w.candidate.program.id}, text=text))
    for m in ctx.indexes.schools.find(text):
        items.append(_school_item("remove_school", m, ctx, text, ctx.schools_on_list or None))
    if not items:
        items.append(_open_school("remove_school", ctx, text, ctx.schools_on_list))
    return items


def _restore(text, norm, key, numbers, ctx):
    removed_s, removed_p = ctx.state.removed_schools, ctx.state.removed_programs
    items = []
    for m in ctx.indexes.schools.find(text):
        hits = [v for v in m.values if v in removed_s]
        progs = [p for p in removed_p if ctx.programs.get(p) and ctx.programs[p].school_code in m.values]
        if hits:
            items.append(_school_item("restore_school", Mention("school", tuple(hits), m.start, m.end, m.text), ctx,
                                      text))
        items += [Item("restore_program", {"program": p}, text=text) for p in progs]
    if not items:
        targets = [(("school", s), ctx.school_label(s)) for s in removed_s] + \
                  [(("program", p), ctx.program_label(p)) for p in removed_p]
        if len(targets) == 1:
            kind, value = targets[0][0]
            items.append(Item(f"restore_{kind}", {kind: value}, text=text))
        else:
            items.append(Item("restore_any", {"target": None}, {"target": targets}, ["target"], text))
    return items


def _rerank(text, norm, key, numbers, ctx):
    return [Item("swap_items", text=text)]


def _replace(text, norm, key, numbers, ctx):
    cat = ctx.catalog
    mentions = [prefer_nganh(m.values, cat) for m in ctx.indexes.nganh.find(text)]
    current = [(i, e.main, list(e.close)) for i, e in enumerate(ctx.state.shortlist)]
    old = new = None
    for values in mentions:
        owner = next(((i, v, v in close) for i, main, close in current for v in values
                      if v == main or v in close), None)
        if owner and old is None:
            old = owner
        elif new is None:
            new = values
    wants_close = bool(CLOSE_WORDS.search(key)) or (old is not None and old[2])
    item_options = [(i, f"Hướng học {i + 1}: {cat.label(main)}") for i, main, _ in current]

    def new_params(item):
        if new is None:
            item.open.append("new" if item.kind == "set_close" else "code")
        elif len(new) > 1:
            name = "new" if item.kind == "set_close" else "code"
            item.open.append(name)
            item.options[name] = [(c, cat.label(c)) for c in new]
        return item

    if wants_close:
        item = Item("set_close", {"index": old[0] if old else None, "old": old[1] if old else None,
                                  "new": new[0] if new and len(new) == 1 else None}, text=text)
        if old is None:
            if len(current) == 1:
                item.params["index"] = 0
            else:
                item.open.append("index")
                item.options["index"] = item_options
        return [new_params(item)]
    item = Item("replace_item", {"index": old[0] if old else None, "code": new[0] if new and len(new) == 1 else None},
                text=text)
    if old is None:
        options = item_options + ([(len(current), "Thêm làm hướng học 2")] if len(current) == 1 else [])
        item.open.append("index")
        item.options["index"] = options
    return [new_params(item)]


def _undo(text, norm, key, numbers, ctx):
    return [Item("undo", text=text)]


def _why_nv(text, norm, key, numbers, ctx):
    nv = [int(m.values[0]) for m in find_nv(text)]
    if not nv:
        nv = [int(n.value) for n in numbers if n.value == int(n.value) and 1 <= n.value <= 15 and not n.weak]
    return [Item("ask_why_nv", {"nv": nv}, text=text)]


def _why_not(text, norm, key, numbers, ctx):
    schools = [m.values for m in ctx.indexes.schools.find(text)]
    return [Item("ask_why_not", {"schools": schools}, text=text)]


def _compare(text, norm, key, numbers, ctx):
    codes = [prefer_nganh(m.values, ctx.catalog)[0] for m in ctx.indexes.nganh.find(text)]
    return [Item("ask_compare", {"codes": list(dict.fromkeys(codes))}, text=text)]


def _what_is(text, norm, key, numbers, ctx):
    codes = [prefer_nganh(m.values, ctx.catalog)[0] for m in ctx.indexes.nganh.find(text)]
    return [Item("ask_what_is", {"codes": list(dict.fromkeys(codes))}, text=text)]


def _level(text, norm, key, numbers, ctx):
    return [Item("ask_level", {"levels": [m.values[0] for m in find_levels(text)]}, text=text)]


_EXTRACTORS = {
    "change_score": _scores, "change_priority": _priority, "change_budget": _budget,
    "change_near_home": _near_home, "extra_points": _extra, "favorite_school": _favorite, "own_score": _own_score,
    "cutoff_shift": _cutoff_shift, "remove": _remove, "restore": _restore,
    "rerank": _rerank, "replace_nganh": _replace, "undo": _undo, "ask_why_nv": _why_nv, "ask_why_not": _why_not,
    "ask_compare": _compare, "ask_what_is": _what_is, "ask_level": _level,
}
