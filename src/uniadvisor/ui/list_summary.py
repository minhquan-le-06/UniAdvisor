"""What the three recommended lists give and cost, in words (docs/design/lists.md, "Explaining the three lists").

Everything is counted from the 15 wishes of each list, not from the simulation behind the pentagon, so a student can
check a sentence against the list underneath.  Three measures: how many wishes are the chosen ngành, the usual fee
(median of the known fees) and how ambitious the first three wishes are.  A list gets a "Được" line where it is best
at a measure and an "Đổi lại" line where it is worst, only when the difference is big enough to matter; two lists
that share most programs are said to be nearly the same instead.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from uniadvisor.data.school_docs import combo_label
from uniadvisor.planner.lists import Priority, Recommended, overlap
from uniadvisor.planner.models import Level
from uniadvisor.ui.texts import LEVEL_VI, chance_pct, num

LIST_VI = {Priority.NGANH: "Đúng ngành nhất", Priority.CAREER: "Hợp sở thích nhất", Priority.MON: "Hợp môn học nhất",
           Priority.COST: "Tiết kiệm nhất"}
FIT = {
    Priority.NGANH: "em muốn học đúng ngành đã chọn, ở các trường mạnh nhất về ngành đó",
    Priority.CAREER: "em chưa chắc chỉ một ngành, muốn ngành hợp sở thích và tính cách qua 12 câu hỏi",
    Priority.MON: "em học rất mạnh vài môn và muốn tận dụng tổ hợp đó",
    Priority.COST: "học phí là điều quan trọng nhất với em",
}
INTRO = ("Ba phương án xếp nguyện vọng theo cùng một luật, chỉ khác nhau ở một điều: khi có nhiều trường để chọn thì "
         "**ưu tiên cái gì**.")

MAX_WISHES = 15
MIN_FEES = 5                 # a usual fee needs at least this many known fees on both lists compared
FEE_DIFF = (3.0, 0.10)       # triệu, share: the difference must reach the larger
NGANH_DIFF = 2               # wishes
AIM_DIFF = 1.0               # points on 30, mean cutoff of the first three wishes
UNKNOWN_SHARE = 1 / 3        # of the wishes without a known fee before a non-cost list says so


@dataclass(frozen=True)
class Metrics:
    n: int
    in_group: int                          # wishes of the chosen ngành or nhóm ngành
    near: tuple[str, ...]                  # the two commonest other ngành (codes)
    near_count: int
    fee_median: float | None               # triệu/năm, of the known fees (free ones apart)
    fee_known: int
    fee_unknown: int
    fee_free: int
    aim_low: float                         # cutoffs of the first three wishes
    aim_high: float
    aim_mean: float
    reach: float                           # the student's score at the first wish
    first_gap: float
    mo_uoc: int


@dataclass
class Card:
    priority: Priority
    name: str
    fit: str
    good: list[str] = field(default_factory=list)
    bad: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warning: str | None = None
    same_as: str | None = None             # a sentence replacing good and bad when the list nearly repeats another
    blocked: str | None = None             # a sentence replacing the card when no wish fits (choose button off)


@dataclass(frozen=True)
class Pick:
    """The list the three pentagons favour for this student, with one sentence saying why."""
    priority: Priority
    name: str
    reason: str
    scores: dict[Priority, float]


@dataclass
class Summary:
    intro: str
    safe_line: str | None
    cards: list[Card]
    notes: list[str]
    pick: Pick | None = None


def _trieu(x: float) -> str:
    return num(x, 1).removesuffix(",0")


def _is_free(c) -> bool:
    return c.program.tuition_basis == "free"


def metrics(rec: Recommended) -> Metrics | None:
    wishes = rec.result.wishes
    if not wishes:
        return None
    cands = [w.candidate for w in wishes]
    fees = [c.program.tuition_max_vnd for c in cands]
    known = [f / 1_000_000 for c, f in zip(cands, fees) if f is not None and not _is_free(c)]
    other = Counter(c.program.moet_code for c in cands if c.relation not in ("main", "group") and c.program.moet_code)
    top = [c.latest_cutoff for c in cands[:3]]
    return Metrics(
        n=len(cands), in_group=sum(c.relation in ("main", "group") for c in cands),
        near=tuple(code for code, _ in other.most_common(2)), near_count=sum(other.values()),
        fee_median=statistics.median(known) if known else None, fee_known=len(known),
        fee_unknown=sum(f is None for f in fees), fee_free=sum(_is_free(c) for c in cands),
        aim_low=min(top), aim_high=max(top), aim_mean=sum(top) / len(top), reach=cands[0].student.score,
        first_gap=cands[0].gap, mo_uoc=sum(c.level.value == "mo_uoc" for c in cands))


def unknown_fees_text(rec: Recommended) -> str | None:
    """Fees the list could not compare: any for Tiết kiệm nhất, a third or more for the other lists."""
    m = metrics(rec)
    if m is None or not m.fee_unknown:
        return None
    if rec.priority is not Priority.COST and m.fee_unknown < m.n * UNKNOWN_SHARE:
        return None
    return (f"{m.fee_unknown}/{m.n} nguyện vọng chưa rõ học phí nên chưa so được; ứng dụng xếp chúng sau các "
            "chương trình đã biết học phí.")


def _fee_threshold(a: float, b: float) -> float:
    return max(FEE_DIFF[0], FEE_DIFF[1] * max(a, b))


def _names(codes: tuple[str, ...], label: Callable[[str], str]) -> str:
    return ", ".join(label(c) for c in codes)


def _highlights(rec_ms: list[tuple[Recommended, Metrics]], label: Callable[[str], str]) -> dict[Priority, tuple[list, list]]:
    """Per list: (good lines, bad lines) from the measures where the three lists differ enough."""
    out = {rec.priority: ([], []) for rec, _ in rec_ms}
    ms = {rec.priority: m for rec, m in rec_ms}
    if len(rec_ms) < 2:
        return out

    # Own point of the list.
    for rec, m in rec_ms:
        if rec.priority is Priority.CAREER and m.near_count:
            names = f" ({_names(m.near, label)})" if m.near else ""
            out[rec.priority][0].append(f"Có thêm ngành gần hợp câu trả lời của em{names}.")
        if rec.priority is Priority.MON:
            combo = combo_label(rec.result.wishes[0].candidate.student.combo)
            out[rec.priority][0].append(f"Ưu tiên chương trình xét tổ hợp {combo} em mạnh nhất.")

    # The chosen ngành.
    counts = {p: m.in_group for p, m in ms.items()}
    best, worst = max(counts.values()), min(counts.values())
    if best - worst >= NGANH_DIFF:
        for p, m in ms.items():
            if m.in_group == best:
                out[p][0].append(f"{m.in_group}/{m.n} nguyện vọng đúng ngành em chọn.")
            elif m.in_group == worst:
                out[p][1].append(f"Chỉ {m.in_group}/{m.n} nguyện vọng đúng ngành em chọn; còn lại là ngành gần.")

    # The usual fee.
    fees = {p: m.fee_median for p, m in ms.items() if m.fee_median is not None and m.fee_known >= MIN_FEES}
    if len(fees) >= 2:
        lo, hi = min(fees.values()), max(fees.values())
        if hi - lo >= _fee_threshold(lo, hi):
            for p, v in fees.items():
                if v == lo:
                    out[p][0].append(f"Học phí thường ~{_trieu(v)} triệu/năm, thấp hơn ~{_trieu(hi - v)} triệu so với phương án đắt nhất.")
                elif v == hi:
                    out[p][1].append(f"Học phí thường ~{_trieu(v)} triệu/năm, cao hơn ~{_trieu(v - lo)} triệu so với phương án rẻ nhất.")

    # How high the first wishes aim.
    means = {p: m.aim_mean for p, m in ms.items()}
    top, bottom = max(means.values()), min(means.values())
    if top - bottom >= AIM_DIFF:
        for p, m in ms.items():
            if m.aim_mean == top:
                out[p][0].append(f"Nhắm cao hơn: 3 nguyện vọng đầu có điểm chuẩn {num(m.aim_low)}–{num(m.aim_high)}"
                                 f"{f'; cả danh sách có {m.mo_uoc} nguyện vọng mơ ước' if m.mo_uoc else ''}.")
            elif m.aim_mean == bottom:
                out[p][1].append(f"Nhắm thấp hơn: 3 nguyện vọng đầu có điểm chuẩn {num(m.aim_low)}–{num(m.aim_high)}.")
    return out


def _pair_difference(a: Metrics, b: Metrics, label: Callable[[str], str]) -> str:
    """What differs between a list and the one it nearly repeats: fee first, then the ngành, else 'specific programs'."""
    if a.fee_median is not None and b.fee_median is not None and a.fee_known >= MIN_FEES and b.fee_known >= MIN_FEES:
        d = b.fee_median - a.fee_median
        if abs(d) >= _fee_threshold(a.fee_median, b.fee_median):
            return (f"thay trường đắt bằng trường rẻ hơn ~{_trieu(-d)} triệu/năm" if d < 0 else
                    f"học phí thường cao hơn ~{_trieu(d)} triệu/năm")
    if abs(a.in_group - b.in_group) >= 1:
        return f"{abs(a.in_group - b.in_group)} nguyện vọng đổi sang ngành khác"
    return "chỉ khác ở các chương trình cụ thể"


# ---------------------------------------------------------------- the list the pentagons favour

# "Nguyện vọng cao" is how often the admission lands on a mơ ước or thử sức wish: it says how ambitious the outcome
# is, not that it is better, so it does not count towards the pick (owner, 2026-10-15: 1 -> 0.25 -> 0).
CORNER_WEIGHT = {"hop_mon": 1.0, "nguyen_vong_cao": 0.0, "dung_nganh": 1.0}
# The fee corner is about affordability, so it counts only when a budget was given (without one it has no value);
# the career corner counts double when the 12 questions were answered.
BUDGET_WEIGHT, CAREER_WEIGHT = 2.0, 2.0
LEAD = 0.05                  # a corner is named in the sentence when the pick leads the others by this much
ORDER = {Priority.NGANH: 0, Priority.CAREER: 1, Priority.MON: 1, Priority.COST: 2}
EDGE = {
    "hop_mon": "hợp tổ hợp môn mạnh nhất của em hơn",
    "dung_nganh": "đúng ngành em chọn hơn",
    "hoc_phi": "học phí thấp hơn",
    "nghe_nghiep": "hợp câu trả lời của em hơn",
}


def corner_weights(budget_trieu: float | None, career: bool) -> dict[str, float]:
    return {**CORNER_WEIGHT, "hoc_phi": BUDGET_WEIGHT if budget_trieu is not None else 0.0,
            "nghe_nghiep": CAREER_WEIGHT if career else 1.0}


def _score(rec: Recommended, weights: dict[str, float]) -> float:
    pairs = [(weights[c], v) for c, v in rec.pentagon.values.items() if v is not None and weights.get(c, 0.0) > 0]
    total = sum(w for w, _ in pairs)
    return sum(w * v for w, v in pairs) / total if total else 0.0


def choose_best(recs: list[Recommended], *, budget_trieu: float | None, tie_margin: float = 0.02) -> Pick | None:
    """The list with the best weighted mean of its pentagon's corners; lists within `tie_margin` of the best are
    tied and the first in the fixed order (Đúng ngành, then Hợp sở thích / Hợp môn, then Tiết kiệm) wins.  A list with
    no wishes, no pentagon or below the safety floor is passed over while another list is fit to choose."""
    usable = [r for r in recs if r.result.wishes and r.pentagon]
    fit = [r for r in usable if r.floor_met] or usable
    if not fit:
        return None
    weights = corner_weights(budget_trieu, any(r.priority is Priority.CAREER for r in recs))
    scores = {r.priority: _score(r, weights) for r in fit}
    best = max(scores.values())
    tied = [r for r in fit if scores[r.priority] >= best - tie_margin]
    top = min(tied, key=lambda r: ORDER[r.priority])
    return Pick(top.priority, LIST_VI[top.priority], _reason(top, fit, weights, budget_trieu, len(tied) > 1), scores)


def _reason(top: Recommended, fit: list[Recommended], weights: dict[str, float], budget_trieu: float | None,
            tied: bool) -> str:
    others = [r for r in fit if r is not top]
    if not others:
        return "Đây là phương án duy nhất đủ nguyện vọng an toàn."
    leads = []
    for corner, w in weights.items():
        mine = top.pentagon.values.get(corner)
        theirs = [r.pentagon.values.get(corner) for r in others if r.pentagon.values.get(corner) is not None]
        if w > 0 and mine is not None and theirs and mine - max(theirs) >= LEAD:
            leads.append((w * (mine - max(theirs)), corner))
    names = [EDGE[c] + (f" (trong ngân sách {_trieu(budget_trieu)} triệu)" if c == "hoc_phi" and budget_trieu is not None
                        else "") for _, c in sorted(leads, reverse=True)[:2]]
    if not names and tied:
        return "Các phương án gần như ngang nhau, nên ưu tiên phương án bám sát ngành em chọn nhất."
    if not names:
        return "Phương án có điểm tổng hợp cao nhất trên ba biểu đồ, dù chênh lệch với các phương án khác không lớn."
    text = " và ".join(names) + " so với các phương án còn lại."
    return text[0].upper() + text[1:]


def build_summary(recs: list[Recommended], *, budget_trieu: float | None, floor: float, cap: float,
                  similar: float, label: Callable[[str], str], favorite: str | None = None,
                  item_labels: tuple[str, ...] = (), tie_margin: float = 0.02) -> Summary:
    ms = [(rec, metrics(rec)) for rec in recs]
    built = [(rec, m) for rec, m in ms if m is not None]
    high = _highlights(built, label)
    by_metric = {rec.priority: m for rec, m in built}

    cards: list[Card] = []
    for rec, m in ms:
        card = Card(rec.priority, LIST_VI[rec.priority], FIT[rec.priority])
        if m is None:
            card.blocked = _blocked(rec, budget_trieu)
            cards.append(card)
            continue
        card.good, card.bad = [s for s in high[rec.priority][0][:2]], [s for s in high[rec.priority][1][:2]]
        card.notes = _notes(rec, m, budget_trieu, favorite, item_labels)
        card.warning = _warning(rec, floor, cap)
        cards.append(card)

    # Lists that nearly repeat an earlier one.
    pairs = {}
    for j in range(len(recs)):
        for i in range(j):
            if recs[i].result.wishes and recs[j].result.wishes and overlap(recs[i].result, recs[j].result) >= similar:
                pairs.setdefault(j, i)
    notes: list[str] = []
    for j, i in pairs.items():
        o = overlap(recs[i].result, recs[j].result)
        k = round((1 - o) * len(recs[j].result.wishes))
        cards[j].same_as = (f"Giống “{cards[i].name}”: cùng các chương trình." if k == 0 else
                            f"Gần giống “{cards[i].name}” (trùng {round(o * 100)}%): khác {k} nguyện vọng, "
                            f"{_pair_difference(by_metric[recs[i].priority], by_metric[recs[j].priority], label)}.")
    if len(pairs) >= 2 and all(overlap(recs[a].result, recs[b].result) >= similar
                               for a in range(len(recs)) for b in range(a + 1, len(recs))
                               if recs[a].result.wishes and recs[b].result.wishes):
        notes.append("Với điểm và ngành của em, 3 phương án gần như giống nhau; xem từng danh sách để thấy chỗ khác.")

    safe = None
    live = [rec for rec in recs if rec.result.wishes]
    if live and all(r.chances is not None and r.floor_met for r in live):
        safe = (f"Cả {'3' if len(live) == 3 else len(live)} phương án đều đủ nguyện vọng an toàn (khả năng đỗ ít nhất "
                f"1 nguyện vọng ≥ {round((1 - floor) * 100)}%).")
    return Summary(INTRO, safe, cards, notes, choose_best(recs, budget_trieu=budget_trieu, tie_margin=tie_margin))


def _blocked(rec: Recommended, budget_trieu: float | None) -> str:
    if rec.priority is Priority.COST and budget_trieu is not None:
        return (f"Không có chương trình nào trong ngân sách {_trieu(budget_trieu)} triệu/năm. Em thử tăng ngân sách "
                "ở phần Về em.")
    return "Chưa có nguyện vọng nào phù hợp với phương án này."


def _warning(rec: Recommended, floor: float, cap: float) -> str | None:
    if rec.chances is None or rec.floor_met:
        return None
    return (f"Khả năng đỗ ít nhất 1 nguyện vọng chỉ {chance_pct(1 - rec.chances.none, cap)}, dưới mức an toàn "
            f"{round((1 - floor) * 100)}%: không còn chương trình an toàn nào để thêm.")


def _notes(rec: Recommended, m: Metrics, budget_trieu: float | None, favorite: str | None,
           item_labels: tuple[str, ...]) -> list[str]:
    notes: list[str] = []
    if m.n < MAX_WISHES:
        notes.append(f"Chỉ có {m.n}/{MAX_WISHES} nguyện vọng.")
    if m.n < MAX_WISHES and rec.priority is Priority.COST and budget_trieu is not None:
        notes.append(f"Chỉ tìm được {m.n} nguyện vọng trong ngân sách {_trieu(budget_trieu)} triệu/năm. Em có thể "
                     "tăng ngân sách hoặc thêm ngành gần.")
    if m.n <= 5:
        notes.append("Ít lựa chọn nên danh sách chưa đủ rộng.")
    if rec.priority is Priority.COST:
        if budget_trieu is None:
            notes.append("Em chưa đặt ngân sách nên ứng dụng xếp theo học phí thấp nhất trong từng mức. Đặt ngân sách "
                         "ở phần Về em để loại bớt chương trình vượt mức.")
        else:
            dropped = sum(e.reason == "over_budget" for e in rec.result.excluded)
            if dropped:
                notes.append(f"Đã bỏ {dropped} chương trình có học phí cao hơn ngân sách {_trieu(budget_trieu)} "
                             "triệu/năm.")
    elif budget_trieu is not None:
        over = sum(w.candidate.over_budget for w in rec.result.wishes)
        if over:
            notes.append(f"{over} nguyện vọng có học phí cao hơn ngân sách {_trieu(budget_trieu)} triệu/năm.")
    if text := unknown_fees_text(rec):
        notes.append(text)
    if m.fee_free:
        notes.append(f"{m.fee_free} nguyện vọng miễn học phí (trường tuyển riêng, điều kiện xét khác); không tính "
                     "vào mức học phí thường.")
    if any(w.candidate.relation == "wider" for w in rec.result.wishes) or any(
            n.startswith("topped_up:") for n in rec.result.notes):
        notes.append("Đã thêm nguyện vọng an toàn của ngành gần hoặc cùng nhóm ngành, vì ngành em chọn không còn đủ "
                     "chương trình an toàn.")
    shifted = [n.split(":")[2:] for n in rec.result.notes if n.startswith("shifted_down:")]
    if shifted:
        levels = list(dict.fromkeys(LEVEL_VI[Level(level)] for level, _ in shifted))
        notes.append(f"Thiếu chương trình ở mức {' và '.join(levels)} nên {sum(int(c) for _, c in shifted)} chỗ được "
                     "chuyển xuống mức an toàn hơn.")
    for note in rec.result.notes:
        if note.startswith("teacher_training_first:"):
            notes.append(f"Ngành sư phạm chỉ được xét ở 5 nguyện vọng đầu nên {note.split(':')[1]} nguyện vọng sư "
                         "phạm đặt đầu danh sách.")
    if len(item_labels) == 2:
        notes.append(f"Đúng ngành tính cả hai hướng: {item_labels[0]} và {item_labels[1]}.")
    if favorite:
        notes.append(f"Trường {favorite} đứng đầu mỗi mức vì em chọn là trường yêu thích.")
    if m.aim_high <= m.reach:
        notes.append(f"Em đạt điểm chuẩn cả 3 nguyện vọng đầu ({num(m.aim_low)}–{num(m.aim_high)}; em có "
                     f"{num(m.reach)}).")
    return notes
