"""Per-ngành facts for step 1 (spec 3.1, 3.4): jobs, main knowledge areas, Holland interest types and close ngành, from
the step 6 tables (src/uniadvisor/facts/build.py). A nhóm ngành combines its ngành, weighted by their program counts.
Loaded once into memory; empty when the database has no step 6 data."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from uniadvisor.app.catalog import Catalog

MIN_IMPORTANCE = 3.0      # O*NET knowledge importance (1-5) a knowledge area needs to be listed for a ngành
# A nhóm ngành gets facts only when its ngành with facts hold at least this share of its programs: otherwise a minor
# ngành speaks for the whole group (Quân sự: Chỉ huy kỹ thuật công binh's civil engineers). Defaults,
# 2026-10-07, after an LLM review of the fact sheets.
MIN_GROUP_COVERAGE = 0.5

ONET_CREDIT = ("Việc làm, kiến thức và sở thích nghề nghiệp lấy từ cơ sở dữ liệu O*NET 31.0 của Bộ Lao động Hoa Kỳ "
               "(USDOL/ETA, giấy phép CC BY 4.0), đã được UniAdvisor chọn lọc, tổng hợp theo ngành và dịch sang "
               "tiếng Việt; USDOL/ETA không kiểm duyệt các thay đổi này. Đây là dữ liệu về nghề nghiệp ở Mỹ, chỉ để "
               "tham khảo.")


@dataclass
class Facts:
    jobs: list[str] = field(default_factory=list)                 # Vietnamese occupation names, most typical first
    knowledge: list[str] = field(default_factory=list)            # main knowledge areas (Vietnamese)
    interests: list[tuple[str, str]] = field(default_factory=list)  # (Holland type, what it means)
    close: list[str] = field(default_factory=list)                # closest ngành codes, best first
    draft: bool = True                                             # names or mapping not yet reviewed

    @property
    def empty(self) -> bool:
        return not (self.jobs or self.knowledge or self.interests)


class FactsIndex:
    def __init__(self, by_code: dict[str, Facts]):
        self.by_code = by_code

    def get(self, code: str) -> Facts:
        return self.by_code.get(code, Facts())

    def proposed_close(self, code: str, n: int = 2, exclude: set[str] = frozenset()) -> list[str]:
        return [c for c in self.get(code).close if c not in exclude][:n]

    @classmethod
    def load(cls, conn: sqlite3.Connection, catalog: Catalog, top_jobs: int = 6, top_knowledge: int = 5,
             top_interests: int = 3) -> "FactsIndex":
        tables = {t for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "nganh_occupation" not in tables:
            return cls({})
        names = defaultdict(dict)
        desc = {}
        for kind, key, name, d in conn.execute("SELECT kind, key, name_vi, description FROM name_vi"):
            names[kind][key] = name
            if d:
                desc[key] = d
        statuses = {s for (s,) in conn.execute("SELECT DISTINCT status FROM name_vi")} | \
                   {s for (s,) in conn.execute("SELECT DISTINCT status FROM nganh_cip")}
        draft = statuses != {"reviewed"}

        jobs = defaultdict(list)                                 # ngành -> [(share, rank, occupation)]
        for n, o, share, rank in conn.execute(
                "SELECT nganh_code, occupation_code, share, display_rank FROM nganh_occupation "
                "WHERE display_rank IS NOT NULL ORDER BY nganh_code, display_rank"):
            jobs[n].append((share, rank, o))
        knowledge = defaultdict(dict)
        for n, e, v in conn.execute("SELECT nganh_code, element, importance FROM nganh_knowledge"):
            knowledge[n][e] = v
        interest = defaultdict(dict)
        for n, r, v in conn.execute("SELECT nganh_code, riasec, score FROM nganh_interest"):
            interest[n][r] = v
        close = defaultdict(list)
        for n, o in conn.execute("SELECT nganh_code, other_code FROM nganh_close ORDER BY nganh_code, rank"):
            if o in catalog.majors:
                close[n].append(o)

        # Knowledge areas are ranked by how distinctive they are for the ngành (z-score across ngành) among those that
        # matter for its jobs (importance >= MIN_IMPORTANCE): nearly every job rates its own language highly, which
        # would otherwise top every list.
        stats = {}
        for e in {e for k in knowledge.values() for e in k}:
            vals = [k[e] for k in knowledge.values() if e in k]
            mean = sum(vals) / len(vals)
            sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
            stats[e] = (mean, sd)

        def distinctive(know: dict[str, float]) -> list[str]:
            ranked = sorted(((e, (v - stats[e][0]) / stats[e][1]) for e, v in know.items()
                             if v >= MIN_IMPORTANCE and e in stats), key=lambda x: (-x[1], x[0]))
            return [e for e, _ in ranked]

        def make(job_weights: dict[str, float], know: dict[str, float], inter: dict[str, float], near: list[str],
                 first: list[str] = ()):
            occ_names = names["occupation"]
            ordered_jobs = [occ_names[o] for o in first if o in occ_names] + [
                occ_names[o] for o, _ in sorted(job_weights.items(), key=lambda x: (-x[1], x[0])) if o in occ_names]
            top_k = [names["knowledge"].get(e, e) for e in distinctive(know)]
            top_i = [(names["riasec"].get(r, r), desc.get(r, "")) for r, _ in
                     sorted(inter.items(), key=lambda x: (-x[1], x[0]))]
            return Facts(list(dict.fromkeys(ordered_jobs))[:top_jobs], top_k[:top_knowledge],
                         top_i[:top_interests], near, draft)

        by_code: dict[str, Facts] = {}
        for code, m in catalog.majors.items():
            if m.level == "nganh" and code in knowledge:
                weights = {o: (len(jobs[code]) - rank + 1) for _, rank, o in jobs[code]}   # display order
                by_code[code] = make(weights, knowledge[code], interest[code], close[code])
        for code, m in catalog.majors.items():
            if m.level != "nhom_nganh":
                continue
            kids = [c for c in m.children if c in by_code]
            if not kids or sum(catalog.majors[c].n_programs for c in kids) < MIN_GROUP_COVERAGE * m.n_programs:
                continue
            w = {c: catalog.majors[c].n_programs for c in kids}
            total = sum(w.values()) or 1
            job_w: dict[str, float] = defaultdict(float)
            know_w: dict[str, float] = defaultdict(float)
            int_w: dict[str, float] = defaultdict(float)
            near: list[str] = []
            for c in kids:
                n_jobs = len(jobs[c])
                for _, rank, o in jobs[c]:
                    job_w[o] += w[c] / total * (n_jobs - rank + 1) / n_jobs
                for e, v in knowledge[c].items():
                    know_w[e] += w[c] / total * v
                for r, v in interest[c].items():
                    int_w[r] += w[c] / total * v
            for c in sorted(kids, key=lambda c: -w[c]):              # closest ngành outside the group
                near += [o for o in close[c][:3] if catalog.majors[o].parent != code and o not in near]
            # Each ngành's main job first (most programs first), so a small ngành is not hidden by a big one (no
            # journalist under Báo chí, Truyền thông...); then the rest by weight.
            first = list(dict.fromkeys(jobs[c][0][2] for c in sorted(kids, key=lambda c: (-w[c], c)) if jobs[c]))
            by_code[code] = make(job_w, know_w, int_w, near, first[:top_jobs])
        return cls(by_code)
