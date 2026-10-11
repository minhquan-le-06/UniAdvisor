"""The plan file: "Tải kế hoạch" downloads everything the student entered as JSON with a schema version;
loading it restores the session. The file goes straight to the student's browser and back; nothing is kept on our
side.

Loading is strict about types and ranges and lenient about content that changed since the file was saved (a ngành no
longer offered, a removed province name): such values are dropped with a warning, the rest is restored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from uniadvisor.ui.state import (AREAS, CATEGORIES, COMPULSORY, LIST_CHOICES, MAX_CLOSE, MAX_CUTOFF_SHIFT,
                                  MAX_ELECTIVES, MAX_ITEMS, SCALES, SCORE_KINDS, PlanState, ShortlistEntry)

FORMAT = "uniadvisor-plan"
SCHEMA_VERSION = 2            # 2: questionnaire answers and the three recommended lists
MAX_BYTES = 200_000


class PlanFileError(ValueError):
    """The file cannot be loaded. The message is Vietnamese, for the student."""


@dataclass(frozen=True)
class Known:
    """What the current app knows, to check a loaded file against."""
    subjects: frozenset[str]
    provinces: frozenset[str]
    codes: frozenset[str]                   # ngành and nhóm ngành the app offers
    schools: frozenset[str]
    programs: frozenset[str]
    province_aliases: dict[str, str] = field(default_factory=dict)   # former province or other name -> current name


def dump(state: PlanState, admission_year: int) -> str:
    data = {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "admission_year": admission_year,
        "profile": {
            "scores": dict(sorted(state.scores.items())),
            "score_kind": state.score_kind,
            "home_province": state.home_province,
            "area": state.area,
            "category": state.category,
            "graduation_year": state.graduation_year,
            "budget_trieu": state.budget_trieu,
            "near_home": state.near_home,
            "favorite_school": state.favorite_school,
        },
        "majors": {
            "picks": list(state.picks),
            "shortlist": [{"main": e.main, "close": list(e.close)} for e in state.shortlist],
            "answers": dict(state.answers),
        },
        "lists": {
            "chosen": state.list_choice,
            "recommended": list(state.recommended),
        },
        "adjustments": {
            "extra_points": dict(sorted(state.extra_points.items())),
            "own_scores": {s: {"score": v, "scale": k} for s, (v, k) in sorted(state.own_scores.items())},
            "cutoff_shifts": dict(sorted(state.cutoff_shifts.items())),
            "removed_schools": sorted(state.removed_schools),
            "removed_programs": sorted(state.removed_programs),
        },
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _number(value, lo: float, hi: float, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise PlanFileError(f"Tệp kế hoạch có {what} không hợp lệ.")
    return float(value)


def _int_or_none(value, lo: int, hi: int, what: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise PlanFileError(f"Tệp kế hoạch có {what} không hợp lệ.")
    return value


def _str_list(value, what: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise PlanFileError(f"Tệp kế hoạch có {what} không hợp lệ.")
    return value


def _answers(value) -> dict:
    if not isinstance(value, dict):
        raise PlanFileError("Tệp kế hoạch có câu trả lời không hợp lệ.")
    out = {}
    for qid, v in value.items():
        if not (v is None or isinstance(v, str) or (isinstance(v, list) and all(isinstance(x, str) for x in v))):
            raise PlanFileError("Tệp kế hoạch có câu trả lời không hợp lệ.")
        out[qid] = v
    return out


def _recommended(value, known: Known) -> list[dict]:
    """The three recommended lists as saved: priority, program ids, pentagon values, chance of no admission."""
    if not isinstance(value, list) or len(value) > 3:
        raise PlanFileError("Tệp kế hoạch có danh sách gợi ý không hợp lệ.")
    out = []
    for r in value:
        if not isinstance(r, dict) or r.get("priority") not in LIST_CHOICES:
            raise PlanFileError("Tệp kế hoạch có danh sách gợi ý không hợp lệ.")
        values = r.get("values", {})
        if not isinstance(values, dict) or not all(v is None or (isinstance(v, (int, float)) and 0 <= v <= 1)
                                                   for v in values.values()):
            raise PlanFileError("Tệp kế hoạch có danh sách gợi ý không hợp lệ.")
        out.append({"priority": r["priority"],
                    "programs": [p for p in _str_list(r.get("programs", []), "danh sách gợi ý") if p in known.programs],
                    "values": values,
                    "no_admission": _number(r.get("no_admission", 0.0), 0, 1, "danh sách gợi ý")})
    return out


def load(raw: bytes | str, known: Known) -> tuple[PlanState, list[str]]:
    """(state, warnings). Raises PlanFileError when the file is not a plan file or is damaged."""
    if isinstance(raw, bytes):
        if len(raw) > MAX_BYTES:
            raise PlanFileError("Tệp quá lớn, không phải tệp kế hoạch của UniAdvisor.")
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise PlanFileError("Không đọc được tệp. Hãy chọn tệp .json đã tải từ UniAdvisor.") from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise PlanFileError("Không đọc được tệp. Hãy chọn tệp .json đã tải từ UniAdvisor.") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise PlanFileError("Đây không phải tệp kế hoạch của UniAdvisor.")
    version = data.get("schema_version")
    if not isinstance(version, int) or version > SCHEMA_VERSION or version < 1:
        raise PlanFileError("Tệp kế hoạch được tạo bởi phiên bản khác của ứng dụng, chưa đọc được.")

    try:
        profile, majors, adj = data["profile"], data["majors"], data["adjustments"]
        if not all(isinstance(x, dict) for x in (profile, majors, adj)):
            raise KeyError
        warnings: list[str] = []
        state = PlanState()

        scores = profile["scores"]
        if not isinstance(scores, dict):
            raise PlanFileError("Tệp kế hoạch có điểm các môn không hợp lệ.")
        for subject, score in scores.items():
            value = _number(score, 0, 10, "điểm môn học")
            if subject not in known.subjects:
                warnings.append(f"Bỏ điểm môn không còn trong danh sách môn thi: {subject}.")
            elif subject not in COMPULSORY and sum(s not in COMPULSORY for s in state.scores) >= MAX_ELECTIVES:
                warnings.append(f"Chỉ giữ {MAX_ELECTIVES} môn tự chọn; bỏ điểm môn {subject}.")
            else:
                state.scores[subject] = value

        kind = profile["score_kind"]
        if kind not in SCORE_KINDS:
            raise PlanFileError("Tệp kế hoạch có loại điểm không hợp lệ.")
        state.score_kind = kind

        province = profile["home_province"]
        if province is not None and not isinstance(province, str):
            raise PlanFileError("Tệp kế hoạch có tỉnh/thành không hợp lệ.")
        if province is not None and province not in known.provinces and province in known.province_aliases:
            province = known.province_aliases[province]          # a former province (2025 merger) -> its new unit
        if province is not None and province not in known.provinces:
            warnings.append(f"Không còn tỉnh/thành “{province}” trong danh sách; em chọn lại nhé.")
            province = None
        state.home_province = province

        if profile["area"] not in AREAS or profile["category"] not in CATEGORIES:
            raise PlanFileError("Tệp kế hoạch có khu vực hoặc đối tượng ưu tiên không hợp lệ.")
        state.area, state.category = profile["area"], profile["category"]
        state.graduation_year = _int_or_none(profile["graduation_year"], 2000, 2100, "năm tốt nghiệp")
        budget = profile["budget_trieu"]
        state.budget_trieu = None if budget is None else _number(budget, 0, 10_000, "ngân sách học phí")
        if not isinstance(profile["near_home"], bool):
            raise PlanFileError("Tệp kế hoạch có lựa chọn “học gần nhà” không hợp lệ.")
        state.near_home = profile["near_home"]
        favorite = profile.get("favorite_school")          # optional: files saved before 2026-10-08 have none
        if favorite is not None and not isinstance(favorite, str):
            raise PlanFileError("Tệp kế hoạch có trường yêu thích không hợp lệ.")
        if favorite is not None and favorite not in known.schools:
            warnings.append(f"Trường yêu thích mã {favorite} không còn trong danh sách trường; em chọn lại nhé.")
            favorite = None
        state.favorite_school = favorite

        for code in _str_list(majors["picks"], "danh sách ngành đã chọn"):
            if code in known.codes:
                if code not in state.picks:
                    state.picks.append(code)
            else:
                warnings.append(f"Ngành/nhóm ngành mã {code} hiện không còn chương trình nào ở Hà Nội, TP.HCM; "
                                "đã bỏ khỏi lựa chọn.")
        shortlist = majors["shortlist"]
        if not isinstance(shortlist, list) or len(shortlist) > MAX_ITEMS:
            raise PlanFileError("Tệp kế hoạch có danh sách ưu tiên ngành không hợp lệ.")
        for entry in shortlist:
            if not isinstance(entry, dict) or not isinstance(entry.get("main"), str):
                raise PlanFileError("Tệp kế hoạch có danh sách ưu tiên ngành không hợp lệ.")
            close = _str_list(entry.get("close", []), "ngành gần")
            if entry["main"] not in known.codes:
                warnings.append(f"Ngành/nhóm ngành mã {entry['main']} hiện không còn chương trình nào ở Hà Nội, "
                                "TP.HCM; đã bỏ khỏi danh sách ưu tiên.")
                continue
            kept = [c for c in close if c in known.codes][:MAX_CLOSE]
            if len(kept) < len(close):
                warnings.append("Đã bỏ một số ngành gần không còn chương trình nào.")
            state.shortlist.append(ShortlistEntry(entry["main"], kept))

        extra = adj["extra_points"]
        if not isinstance(extra, dict):
            raise PlanFileError("Tệp kế hoạch có điểm cộng không hợp lệ.")
        for school, points in extra.items():
            value = _number(points, 0, 10, "điểm cộng")
            if school in known.schools:
                state.extra_points[school] = value
        own = adj.get("own_scores", {})                    # optional: files saved before 2026-10-08 have none
        if not isinstance(own, dict):
            raise PlanFileError("Tệp kế hoạch có điểm xét tuyển tự tính không hợp lệ.")
        for school, entry in own.items():
            if not isinstance(entry, dict) or entry.get("scale") not in SCALES:
                raise PlanFileError("Tệp kế hoạch có điểm xét tuyển tự tính không hợp lệ.")
            value = _number(entry.get("score"), 0, entry["scale"], "điểm xét tuyển tự tính")
            if school in known.schools:
                state.own_scores[school] = (value, entry["scale"])
        shifts = adj.get("cutoff_shifts", {})
        if not isinstance(shifts, dict):
            raise PlanFileError("Tệp kế hoạch có điều chỉnh điểm chuẩn không hợp lệ.")
        for school, points in shifts.items():
            value = _number(points, -MAX_CUTOFF_SHIFT, MAX_CUTOFF_SHIFT, "điều chỉnh điểm chuẩn")
            if school in known.schools and value:
                state.cutoff_shifts[school] = value
        state.removed_schools = [s for s in _str_list(adj["removed_schools"], "trường đã bỏ") if s in known.schools]
        state.removed_programs = [p for p in _str_list(adj["removed_programs"], "nguyện vọng đã bỏ")
                                  if p in known.programs]
        state.answers = _answers(majors.get("answers", {}))              # optional: schema 1 files have none
        lists = data.get("lists", {})
        if not isinstance(lists, dict):
            raise PlanFileError("Tệp kế hoạch có danh sách gợi ý không hợp lệ.")
        chosen = lists.get("chosen")
        if chosen is not None and chosen not in LIST_CHOICES:
            raise PlanFileError("Tệp kế hoạch có danh sách đã chọn không hợp lệ.")
        state.list_choice = chosen
        state.recommended = _recommended(lists.get("recommended", []), known)
    except (KeyError, TypeError):
        raise PlanFileError("Tệp kế hoạch bị thiếu hoặc hỏng một phần, chưa đọc được.") from None
    return state, warnings
