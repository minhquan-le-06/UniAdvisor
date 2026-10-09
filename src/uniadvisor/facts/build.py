"""Step 6: occupations, knowledge areas, interests and closeness per ngành.

Sources: O*NET 31.0 (occupations, Knowledge importance, Career Interest Types, Related Occupations; CC BY 4.0,
USDOL/ETA) and the O*NET Resource Center crosswalk CIP 2020 -> O*NET-SOC 2019; the ngành -> CIP mapping in
data/curated/nganh_cip.csv (drafted with an LLM, reviewed by people).

Method:
- ngành -> occupations: each ngành -> CIP link has a weight (rank x match quality, config/facts.yaml); a CIP's weight is
  shared equally by its occupations in the crosswalk, each multiplied by the occupation's inverse document frequency
  over all CIP codes (ln(CIP codes / CIP codes listing it): generic occupations such as "Managers, All Other" or
  postsecondary teachers count less); weights are normalised per ngành.
- the crosswalk links a CIP to whole residual SOC families, so geological engineering reaches photonics and robotics
  engineers: a detailed occupation of such a family is kept only when its title shares a word with the CIP title
  (match_residual_families). For knowledge, interests and closeness, the residual occupations themselves ("Engineers,
  All Other") are left out, and postsecondary teachers count `postsecondary_factor` (few graduates do that job; the
  app does not show it). Defaults of 2026-10-07, chosen against the LLM review
  review of the close ngành (data/reviews/, round step6_llm_2026-10-07).
- knowledge: the weighted mean of its occupations' O*NET Knowledge importance (1-5) per knowledge area.
- interests: the weighted mean of its occupations' RIASEC occupational interest scores (1-7), Holland 1997.
- work context: the weighted mean of its occupations' O*NET Work Context values (1-5 means; a few category shares),
  for step 7's questions (design decision 2026-10-08).
- closeness of two ngành = w x shared occupations + (1 - w) x shared knowledge, where shared occupations is the cosine of
  their occupation-weight vectors after spreading each occupation's weight to its O*NET "Related Occupations"
  (Primary-Short tier), and shared knowledge is the cosine of their knowledge profiles, each knowledge area standardised
  across ngành so that knowledge every job needs does not dominate (the angular-separation idea of Gathmann and
  Schönberg 2010, applied to standardised profiles). A pair whose shared-occupations part is below
  `min_occupation_part` is not close ("ngành gần" means similar jobs, not only similar knowledge), unless a reviewer
  judged it 'ok'.
- a reviewer's verdict on a pair (data/curated/nganh_close_verdicts.csv): 'wrong' removes it, 'weak' ranks it after
  the pairs not judged weak. `closeness.limit` cuts a ngành's list short when the next candidates are only generic.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
import yaml

from uniadvisor.paths import CONFIG_DIR

ONET_DIR = "onet_31_0"
RIASEC = ["Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"]
# Vietnamese names of occupations, knowledge areas and Holland types: one row per name, `kind` = occupation | knowledge |
# riasec; `key` = what the name_vi table uses (occupation code, knowledge area, Holland type).
NAMES_FILE = "names_vi.csv"


def load_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "facts.yaml").read_text(encoding="utf-8"))


def _tsv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, encoding="utf-8")


def load_onet(inputs: Path, cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    d = inputs / ONET_DIR
    occ = _tsv(d / "Occupation_Data.txt").rename(columns={"O*NET-SOC Code": "code", "Title": "title",
                                                          "Description": "description"})
    know = _tsv(d / "Knowledge.txt")
    know = know[know["Scale ID"] == "IM"].rename(columns={"O*NET-SOC Code": "code", "Element ID": "element_id",
                                                          "Element Name": "element", "Data Value": "importance"})
    know["importance"] = know["importance"].astype(float)
    inter = _tsv(d / "Career_Interest_Types.txt")
    inter = inter[(inter["Scale ID"] == "OI") & inter["Element Name"].isin(RIASEC)].rename(
        columns={"O*NET-SOC Code": "code", "Element Name": "riasec", "Data Value": "score"})
    inter["score"] = inter["score"].astype(float)
    zones = _tsv(d / "Job_Zones.txt").rename(columns={"O*NET-SOC Code": "code", "Job Zone": "job_zone"})
    related = _tsv(d / "Related_Occupations.txt").rename(columns={
        "O*NET-SOC Code": "code", "Related O*NET-SOC Code": "related", "Relatedness Tier": "tier", "Index": "idx"})
    cross = pd.read_csv(inputs / "cip" / "cip2020_to_onetsoc2019.csv", dtype=str, keep_default_na=False)
    return {"occupation": occ, "knowledge": know[["code", "element_id", "element", "importance"]],
            "interest": inter[["code", "riasec", "score"]], "zones": zones[["code", "job_zone"]],
            "related": related[["code", "related", "tier", "idx"]], "crosswalk": cross,
            "work_context": load_work_context(d, cfg)}


def load_work_context(d: Path, cfg: dict | None) -> pd.DataFrame:
    """O*NET Work Context per occupation: each element's 1-5 mean (CX), and for the elements in
    `work_context.category_shares` the % of workers in that category (CTP). Rows O*NET recommends suppressing (low
    precision) are left out. Columns: code, element_id, element, scale, value."""
    cols = ["code", "element_id", "element", "scale", "value"]
    if not (d / "Work_Context.txt").exists():
        return pd.DataFrame(columns=cols)
    wc = _tsv(d / "Work_Context.txt").rename(columns={"O*NET-SOC Code": "code", "Element ID": "element_id",
                                                      "Element Name": "element", "Scale ID": "scale",
                                                      "Data Value": "value"})
    wc = wc[wc["Recommend Suppress"] != "Y"]
    cx = wc[wc["scale"] == "CX"][cols]
    shares = (cfg or {}).get("work_context", {}).get("category_shares", {})
    names = {}
    if shares and (d / "Work_Context_Categories.txt").exists():
        cats = _tsv(d / "Work_Context_Categories.txt")
        names = {(e, c): t for e, s, c, t in zip(cats["Element ID"], cats["Scale ID"], cats["Category"],
                                                  cats["Category Description"]) if s == "CTP"}
    parts = [cx]
    for element_id, category in shares.items():
        rows = wc[(wc["scale"] == "CTP") & (wc["element_id"] == element_id) & (wc["Category"] == str(category))]
        label = names.get((element_id, str(category)), f"category {category}")
        parts.append(rows.assign(element_id=f"{element_id}:{category}", element=rows["element"] + ": " + label)[cols])
    out = pd.concat(parts, ignore_index=True)
    out["value"] = out["value"].astype(float)
    return out


def nganh_occupations(mapping: pd.DataFrame, crosswalk: pd.DataFrame, cfg: dict) -> dict[str, dict[str, float]]:
    """ngành -> {occupation: weight}, weights summing to 1."""
    m = cfg["mapping"]
    occ_of = crosswalk.groupby("cip_code")["onet_soc_code"].apply(lambda s: sorted(set(s))).to_dict()
    # An occupation reached from many fields of study ("Managers, All Other", postsecondary teachers) says little
    # about any one of them: weight it by its inverse document frequency over all CIP codes (TF-IDF).
    n_cip = len(occ_of)
    df = crosswalk.drop_duplicates(["cip_code", "onet_soc_code"]).groupby("onet_soc_code").size()
    idf = {o: math.log(n_cip / k) for o, k in df.items()} if m.get("idf", True) else {}
    out: dict[str, dict[str, float]] = {}
    for code, rows in mapping[mapping["status"].isin(m["use_status"])].groupby("nganh_code"):
        weights: dict[str, float] = defaultdict(float)
        for r in rows.itertuples():
            occs = occ_of.get(r.cip_code, [])
            w = m["rank_weight"].get(int(r.rank), 0.2) * m["match_weight"].get(r.match, 0.5)
            for o in occs:
                weights[o] += w / len(occs) * idf.get(o, 1.0)
        total = sum(weights.values())
        if total:
            out[code] = {o: w / total for o, w in sorted(weights.items())}
    return out


def is_residual(code: str, titles: dict[str, str]) -> bool:
    """A residual occupation ("Managers, All Other") or one of O*NET's detailed occupations under a residual SOC code
    (11-9199.xx: Compliance Managers, Wind Energy Development Managers...)."""
    base = code.split(".")[0]
    return "All Other" in titles.get(code, "") or "All Other" in titles.get(base + ".00", "")


# Words in occupation titles that name a kind of job, not a field (ignored when matching titles to CIP titles).
_JOB_WORDS = {"engineers", "managers", "specialists", "technicians", "technologists", "workers", "operators",
              "coordinators", "planners", "analysts", "officers", "except", "other", "systems", "site", "and", "all",
              "development", "operations", "including", "management", "general", "services", "service",
              "science", "sciences", "technology", "studies", "affairs", "assistant", "assistants", "medicine", "engineering",
              "physicians"}


def _stems(text: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4 and w not in _JOB_WORDS}


def match_residual_families(cross: pd.DataFrame, titles: dict[str, str]) -> pd.DataFrame:
    """The crosswalk links a CIP to whole SOC families: the SOC occupation (O*NET code .00) and all of O*NET's detailed
    occupations under it (.01, .02...). So 17-2199 "Engineers, All Other" brings mechatronics, photonics, wind energy
    engineers to every engineering CIP, and 11-9041 "Architectural and Engineering Managers" brings biofuels
    development managers. When a CIP lists a family's .00 occupation, keep its detailed occupations only when their
    title shares a word with the CIP title (Mechatronics Engineers under "Mechatronics, Robotics, and Automation
    Engineering"); the .00 occupation itself is kept."""
    linked = set(zip(cross["cip_code"], cross["onet_soc_code"]))
    keep = []
    for cip, cip_title, o in zip(cross["cip_code"], cross["cip_title"], cross["onet_soc_code"]):
        base = o.split(".")[0] + ".00"
        family_member = o != base and (cip, base) in linked
        keep.append(not family_member or bool(_stems(titles.get(o, "")) & _stems(cip_title)))
    return cross[keep]


def is_postsecondary_teacher(code: str) -> bool:
    return code.startswith("25-1")


def is_catch_all(code: str, titles: dict[str, str]) -> bool:
    """Not shown on a fact sheet: a residual occupation ("Managers, All Other") or a postsecondary teacher (25-1xxx).
    Detailed occupations of a residual family that survive match_residual_families are specific and shown."""
    return "All Other" in titles.get(code, "") or is_postsecondary_teacher(code)


def profile_weights(occ: dict[str, dict[str, float]], titles: dict[str, str], cfg: dict) -> dict[str, dict[str, float]]:
    """The weights used for knowledge, interests and closeness: residual occupations left out, postsecondary teachers
    scaled by postsecondary_factor, renormalised. A ngành reached only through such occupations keeps its weights."""
    m = cfg["mapping"]
    factor = m.get("postsecondary_factor", 1.0)
    out = {}
    for n, ws in occ.items():
        kept = {o: w * (factor if is_postsecondary_teacher(o) else 1.0) for o, w in ws.items()
                if not (m.get("drop_residual", False) and "All Other" in titles.get(o, ""))}
        total = sum(kept.values())
        out[n] = {o: w / total for o, w in kept.items()} if total else ws
    return out


def named_after_field(mapping: pd.DataFrame, crosswalk: pd.DataFrame, titles: dict[str, str], cfg: dict
                      ) -> dict[str, set[str]]:
    """ngành -> its occupations whose title shares a word with the title of a CIP it reaches them through
    (Journalism -> News Analysts, Reporters, and Journalists; Statistics -> Statisticians)."""
    used = mapping[mapping["status"].isin(cfg["mapping"]["use_status"])]
    by_cip: dict[str, set[str]] = defaultdict(set)
    for cip, cip_title, o in zip(crosswalk["cip_code"], crosswalk["cip_title"], crosswalk["onet_soc_code"]):
        if _stems(titles.get(o, "")) & _stems(cip_title):
            by_cip[cip].add(o)
    out: dict[str, set[str]] = defaultdict(set)
    for n, cip in zip(used["nganh_code"], used["cip_code"]):
        out[n] |= by_cip.get(cip, set())
    return out


def display_ranks(share: dict[str, dict[str, float]], n_cips: dict[str, int], titles: dict[str, str],
                  weight: dict[str, dict[str, float]] | None = None, named: dict[str, set[str]] | None = None
                  ) -> dict[str, dict[str, int]]:
    """Order in which a ngành's occupations are shown: catch-alls are not shown (is_catch_all); first the jobs named
    after the ngành's fields of study (named_after_field), then by IDF weight (specific jobs before generic ones such as
    "Architectural and Engineering Managers"; LLM review review of the fact sheets, 2026-10-07), then share, then
    code."""
    out: dict[str, dict[str, int]] = {}
    for n, s in share.items():
        w = (weight or {}).get(n, {})
        first = (named or {}).get(n, set())
        shown = [o for o in s if not is_catch_all(o, titles)]
        shown.sort(key=lambda o: (o not in first, -round(w.get(o, 0.0), 9), -round(s[o], 9), -n_cips.get(o, 0), o))
        out[n] = {o: i for i, o in enumerate(shown, start=1)}
    return out


def weighted_profile(occ_weights: dict[str, float], table: pd.DataFrame, key: str, value: str) -> dict[str, float]:
    """Weighted mean of `value` per `key` over the occupations (occupations without data are left out)."""
    sub = table[table["code"].isin(occ_weights)]
    sums: dict[str, float] = defaultdict(float)
    weights: dict[str, float] = defaultdict(float)
    for code, k, v in zip(sub["code"], sub[key], sub[value]):
        sums[k] += occ_weights[code] * v
        weights[k] += occ_weights[code]
    return {k: sums[k] / weights[k] for k in sorted(sums) if weights[k]}


def spread(occ_weights: dict[str, float], related: dict[str, list[str]], share: float) -> dict[str, float]:
    """Give each occupation's related occupations `share` of its weight (split equally), keeping the original."""
    out = defaultdict(float, occ_weights)
    for o, w in occ_weights.items():
        rel = related.get(o, [])
        for r in rel:
            out[r] += w * share / len(rel)
    return dict(out)


def standardise(profiles: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """z-score each knowledge area across ngành."""
    keys = sorted({k for p in profiles.values() for k in p})
    stats = {}
    for k in keys:
        vals = [p[k] for p in profiles.values() if k in p]
        mean = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) or 1.0
        stats[k] = (mean, sd)
    return {c: {k: (v - stats[k][0]) / stats[k][1] for k, v in p.items()} for c, p in profiles.items()}


def closeness(occ: dict[str, dict[str, float]], knowledge: dict[str, dict[str, float]], related: pd.DataFrame,
              cfg: dict) -> list[tuple[str, str, float, float, float]]:
    """[(ngành, other ngành, score, occupation part, knowledge part)] for every ordered pair with any similarity."""
    import numpy as np
    c = cfg["closeness"]
    rel: dict[str, list[str]] = defaultdict(list)
    shares = c["related_tiers"]
    tier_share = max(shares.values()) if shares else 0.0
    for code, r, tier in zip(related["code"], related["related"], related["tier"]):
        if tier in shares:
            rel[code].append(r)
    codes = sorted(occ)
    spread_occ = [spread(occ[n], rel, tier_share) for n in codes]
    occ_index = {o: i for i, o in enumerate(sorted({o for s in spread_occ for o in s}))}
    A = np.zeros((len(codes), len(occ_index)))
    for i, s in enumerate(spread_occ):
        for o, w in s.items():
            A[i, occ_index[o]] = w
    z = standardise(knowledge)
    keys = sorted({k for p in z.values() for k in p})
    K = np.array([[z.get(n, {}).get(k, 0.0) for k in keys] for n in codes])

    def cos(M):
        norms = np.linalg.norm(M, axis=1)
        norms[norms == 0] = 1.0
        U = M / norms[:, None]
        return U @ U.T

    O = cos(A)
    S = np.clip(cos(K), 0.0, None) if keys else np.zeros_like(O)
    w = c["occupation_weight"]
    total = w * O + (1 - w) * S
    out = []
    for i, a in enumerate(codes):
        for j, b in enumerate(codes):
            if i != j and total[i, j] > 0:
                out.append((a, b, round(float(total[i, j]), 6), round(float(O[i, j]), 6), round(float(S[i, j]), 6)))
    return out


def build_facts(conn, inputs: Path, curated: Path, review, cfg: dict | None = None) -> dict:
    """Load O*NET, the crosswalk and the mapping; derive and store per-ngành facts and closeness."""
    cfg = cfg or load_config()
    onet = load_onet(inputs, cfg)
    zones = dict(zip(onet["zones"]["code"], onet["zones"]["job_zone"]))
    conn.executemany("INSERT INTO occupation VALUES (?,?,?,?, 'onet_31_0')",
                     [(r.code, r.title, r.description, int(zones[r.code]) if zones.get(r.code) else None)
                      for r in onet["occupation"].itertuples()])
    known_occ = set(onet["occupation"]["code"])
    conn.executemany("INSERT INTO occupation_knowledge VALUES (?,?,?,?)",
                     onet["knowledge"][onet["knowledge"]["code"].isin(known_occ)].itertuples(index=False))
    conn.executemany("INSERT INTO occupation_interest VALUES (?,?,?)",
                     onet["interest"][onet["interest"]["code"].isin(known_occ)].itertuples(index=False))
    wc = onet["work_context"][onet["work_context"]["code"].isin(known_occ)]
    conn.executemany("INSERT INTO occupation_work_context VALUES (?,?,?,?,?)", wc.itertuples(index=False))
    rel = onet["related"][onet["related"]["code"].isin(known_occ) & onet["related"]["related"].isin(known_occ)]
    conn.executemany("INSERT INTO occupation_related VALUES (?,?,?,?)",
                     [(r.code, r.related, r.tier, int(r.idx)) for r in rel.itertuples()])
    cross = onet["crosswalk"]
    cips = cross.groupby("cip_code")["cip_title"].first()
    conn.executemany("INSERT INTO cip VALUES (?,?, 'cip_crosswalk')", list(cips.items()))
    conn.executemany("INSERT INTO cip_occupation VALUES (?,?)",
                     cross[cross["onet_soc_code"].isin(known_occ)][["cip_code", "onet_soc_code"]]
                     .drop_duplicates().itertuples(index=False))

    path = curated / "nganh_cip.csv"
    mapping = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame(
        columns=["nganh_code", "rank", "cip_code", "match", "confidence", "retrieved", "note", "status", "origin"])
    catalog = {c for (c,) in conn.execute("SELECT code FROM moet_major WHERE level = 'nganh'")}
    ok = mapping["nganh_code"].isin(catalog) & mapping["cip_code"].isin(set(cips.index))
    for r in mapping[~ok].itertuples():
        review.add("nganh_cip_invalid", nganh_code=r.nganh_code, cip_code=r.cip_code,
                   issue="nganh_not_in_catalog" if r.nganh_code not in catalog else "cip_not_in_crosswalk")
    mapping = mapping[ok]
    conn.executemany("INSERT INTO nganh_cip VALUES (?,?,?,?,?,?,?,?,?, 'curated')",
                     [(r.nganh_code, int(r.rank), r.cip_code, r.match, r.confidence, r.retrieved, r.note or None,
                       r.status, r.origin) for r in mapping.itertuples()])

    titles = dict(zip(onet["occupation"]["code"], onet["occupation"]["title"]))
    cross_known = match_residual_families(cross[cross["onet_soc_code"].isin(known_occ)], titles)
    occ = nganh_occupations(mapping, cross_known, cfg)
    plain_cfg = {**cfg, "mapping": {**cfg["mapping"], "idf": False}}
    share = nganh_occupations(mapping, cross_known, plain_cfg)
    n_cips = cross_known.drop_duplicates(["cip_code", "onet_soc_code"]).groupby("onet_soc_code").size().to_dict()
    rank = display_ranks(share, n_cips, titles, occ, named_after_field(mapping, cross_known, titles, cfg))
    hide_occupations(rank, conn, curated)
    occ = profile_weights(occ, titles, cfg)
    conn.executemany("INSERT INTO nganh_occupation VALUES (?,?,?,?,?)",
                     [(n, o, round(occ[n].get(o, 0.0), 6), round(s, 6), rank[n].get(o))
                      for n, ss in share.items() for o, s in ss.items()])
    knowledge = {n: weighted_profile(w, onet["knowledge"], "element", "importance") for n, w in occ.items()}
    interests = {n: weighted_profile(w, onet["interest"], "riasec", "score") for n, w in occ.items()}
    conn.executemany("INSERT INTO nganh_knowledge VALUES (?,?,?)",
                     [(n, k, round(v, 4)) for n, p in knowledge.items() for k, v in p.items()])
    conn.executemany("INSERT INTO nganh_interest VALUES (?,?,?)",
                     [(n, k, round(v, 4)) for n, p in interests.items() for k, v in p.items()])
    wc_meta = {e: (name, scale) for e, name, scale in zip(wc["element_id"], wc["element"], wc["scale"])}
    context = {n: weighted_profile(w, wc, "element_id", "value") for n, w in occ.items()}
    conn.executemany("INSERT INTO nganh_work_context VALUES (?,?,?,?,?)",
                     [(n, e, *wc_meta[e], round(v, 4)) for n, p in context.items() for e, v in p.items()])

    _review_mapping(conn, mapping, curated, review)
    _load_names(conn, curated)
    pairs = closeness(occ, knowledge, rel, cfg)
    verdicts = load_close_verdicts(curated)
    floor = cfg["closeness"].get("min_occupation_part", 0.0)
    min_score = cfg["closeness"].get("min_score", 0.0)
    teacher = TeacherTraining(cfg.get("teacher_training", {}))
    by_a: dict[str, list] = defaultdict(list)
    for a, b, s, o, k in pairs:
        v = verdicts.get((a, b))
        if v == "wrong" or separate_tracks(a, b):
            continue
        if teacher.is_subject(a, b):
            by_a[a].append((s, b, o, k))
        # Unrelated subjects are not close, whatever an earlier review said (design decision 2026-10-08).
        elif teacher.unrelated(a, b):
            continue
        # A pair sharing (almost) no jobs, or with a low score, is not close, unless a reviewer judged it 'ok'.
        elif (o >= floor and s >= min_score) or v == "ok":
            by_a[a].append((s, b, o, k))
    for a, subjects in teacher.subject_nganh.items():          # a subject ngành with no similarity at all
        for b in subjects:
            if a in occ and b in occ and b not in {x[1] for x in by_a[a]}:
                by_a[a].append((0.0, b, 0.0, 0.0))
    rows = []
    keep = cfg["closeness"]["proposed"] + cfg["closeness"]["further"]
    limit = {str(a): n for a, n in (cfg["closeness"].get("limit") or {}).items()}
    for a, lst in by_a.items():
        lst.sort(key=lambda x: (not teacher.is_subject(a, x[1]), verdicts.get((a, x[1])) == "weak", -x[0], x[1]))
        rows += [(a, b, rank, s, o, k) for rank, (s, b, o, k) in enumerate(lst[:limit.get(a, keep)], start=1)]
    conn.executemany("INSERT INTO nganh_close VALUES (?,?,?,?,?,?)", rows)
    names = dict(conn.execute("SELECT code, name FROM moet_major"))
    for a, b, rank, s, o, k in rows:
        # Subject pairs are close by rule (groups approved 2026-10-08), so nobody needs to judge them.
        if rank <= 3 and (a, b) not in verdicts and not teacher.is_subject(a, b):
            review.add("nganh_close_review", nganh_code=a, nganh_name=names.get(a, ""), rank=rank, other_code=b,
                       other_name=names.get(b, ""), score=round(s, 3), shared_occupations=round(o, 3),
                       shared_knowledge=round(k, 3), verdict="", comment="")
    return {"nganh_mapped": len(occ), "links": len(mapping), "occupations_used": len({o for w in occ.values()
                                                                                       for o in w}),
            "close_rows": len(rows)}


def hide_occupations(rank: dict[str, dict[str, int]], conn, curated: Path) -> None:
    """data/curated/occupation_hidden.csv: jobs a reviewer found misleading for a ngành or a nhóm ngành (scope) are not
    shown there (display only; closeness and profiles keep them). A nhóm ngành scope covers its ngành."""
    path = curated / "occupation_hidden.csv"
    if not path.exists():
        return
    hidden = pd.read_csv(path, dtype=str, keep_default_na=False)
    parent = dict(conn.execute("SELECT code, parent_code FROM moet_major WHERE level = 'nganh'"))
    for n, ranks in rank.items():
        drop = set(hidden.loc[hidden["scope"].isin([n, parent.get(n, "")]), "occupation_code"])
        if drop & set(ranks):
            kept = sorted((r, o) for o, r in ranks.items() if o not in drop)
            rank[n] = {o: i for i, (_, o) in enumerate(kept, start=1)}


class TeacherTraining:
    """Closeness among Sư phạm ngành (config/facts.yaml teacher_training, design decision 2026-10-08)."""

    EDUCATION = "7140"           # every education ngành (Giáo dục học, Quản lý giáo dục, the Sư phạm ngành...)

    def __init__(self, cfg: dict):
        self.group = {code: g for g, codes in (cfg.get("subject_groups") or {}).items() for code in codes}
        self.subject_nganh = {a: list(bs) for a, bs in (cfg.get("subject_nganh") or {}).items()}
        self.group_subjects: dict[str, set[str]] = defaultdict(set)
        for a, bs in self.subject_nganh.items():
            if a in self.group:
                self.group_subjects[self.group[a]].update(bs)

    def unrelated(self, a: str, b: str) -> bool:
        """Two Sư phạm ngành of different subject groups, or a Sư phạm ngành and a ngành that is neither another
        education ngành nor a subject ngành of its group (the language ngành share the teacher occupations with every
        Sư phạm ngành, so Sư phạm Mỹ thuật would otherwise be close to Ngôn ngữ Nga)."""
        if a in self.group and b in self.group:
            return self.group[a] != self.group[b]
        if a in self.group or b in self.group:
            teacher, other = (a, b) if a in self.group else (b, a)
            return not other.startswith(self.EDUCATION) and other not in self.group_subjects[self.group[teacher]]
        return False

    def is_subject(self, a: str, b: str) -> bool:
        return b in self.subject_nganh.get(a, ())


def separate_tracks(a: str, b: str) -> bool:
    """Military and police ngành (786xx) have their own admission: never close to a civilian ngành, or the reverse."""
    return a.startswith("786") != b.startswith("786")


def load_close_verdicts(curated: Path) -> dict[tuple[str, str], str]:
    """(ngành, other ngành) -> 'ok' / 'weak' / 'wrong', from a reviewer (data/curated/nganh_close_verdicts.csv)."""
    path = curated / "nganh_close_verdicts.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return {(a, b): v.strip() for a, b, v in zip(df["nganh_code"], df["other_code"], df["verdict"])}


def _review_mapping(conn, mapping: pd.DataFrame, curated: Path, review) -> None:
    """data/build/review/nganh_cip_review.csv: every draft ngành -> CIP link with what a reviewer needs to judge it, and
    empty verdict columns; nganh_cip_for_people.csv: links the reviewer was unsure of."""
    gloss_path = curated / "nganh_gloss_en.tsv"
    gloss = {}
    if gloss_path.exists():
        for line in gloss_path.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                code, text = line.split("\t", 1)
                gloss[code] = text
    names = dict(conn.execute("SELECT code, name FROM moet_major"))
    parents = dict(conn.execute("SELECT code, parent_code FROM moet_major"))
    titles = dict(conn.execute("SELECT code, title FROM cip"))
    occ_titles = dict(conn.execute("SELECT code, title FROM occupation"))
    occ_of: dict[str, list[str]] = defaultdict(list)
    for cip, o in conn.execute("SELECT cip_code, occupation_code FROM cip_occupation ORDER BY cip_code, occupation_code"):
        occ_of[cip].append(o)
    programs: dict[str, list[str]] = defaultdict(list)
    for code, name in conn.execute("SELECT DISTINCT moet_code, name FROM program WHERE in_scope = 1 AND moet_code IS "
                                   "NOT NULL ORDER BY moet_code, name"):
        if len(programs[code]) < 4:
            programs[code].append(name)
    for r in mapping.sort_values(["nganh_code", "rank"]).itertuples():
        if r.status == "unsure":
            review.add("nganh_cip_for_people", nganh_code=r.nganh_code, nganh_name=names.get(r.nganh_code, ""),
                       rank=r.rank, cip_code=r.cip_code, cip_title=titles.get(r.cip_code, ""),
                       reviewer_comment=getattr(r, "review_comment", ""),
                       cip_occupations="; ".join(occ_titles.get(o, o) for o in occ_of.get(r.cip_code, [])[:12]),
                       decision="", note="")
        if r.status != "draft":
            continue
        review.add("nganh_cip_review", nganh_code=r.nganh_code, nganh_name=names.get(r.nganh_code, ""),
                   nhom_nganh=names.get(parents.get(r.nganh_code), ""),
                   program_names="; ".join(programs.get(r.nganh_code, [])), gloss_en=gloss.get(r.nganh_code, ""),
                   rank=r.rank, cip_code=r.cip_code, cip_title=titles.get(r.cip_code, ""), match=r.match,
                   confidence=r.confidence, retrieved=r.retrieved, note=r.note,
                   cip_occupations="; ".join(occ_titles.get(o, o) for o in occ_of.get(r.cip_code, [])[:12]),
                   verdict="", correct_cip="", comment="")


def _load_names(conn, curated: Path) -> None:
    """Vietnamese names of occupations, knowledge areas and Holland types (drafts until reviewed)."""
    path = curated / NAMES_FILE
    if not path.exists():
        return
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    known_occ = {c for (c,) in conn.execute("SELECT code FROM occupation")}
    df = df[(df["kind"] != "occupation") | df["key"].isin(known_occ)]
    conn.executemany("INSERT INTO name_vi VALUES (?,?,?,?,?,?)",
                     [(r["kind"], r["key"], r["name_vi"], r["description_vi"] if r["kind"] == "riasec" else None,
                       r["status"], r["origin"]) for _, r in df.iterrows() if r["name_vi"].strip()])
