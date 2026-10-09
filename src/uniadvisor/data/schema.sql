-- UniAdvisor v2 database schema (SQLite).
-- Official names in moet_major; the names students know live in display_name (a reviewed table, spec 3.6).
-- Every fact records its source. Unknown values are NULL, never guessed.

PRAGMA foreign_keys = ON;

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE source (
    id           TEXT PRIMARY KEY,          -- e.g. 'vnexpress', 'moet_tt09_2022'
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,             -- 'website', 'export', 'regulation', 'curated'
    location     TEXT,                      -- URL or input file
    retrieved_at TEXT,
    note         TEXT
);

-- MOET catalog (Thông tư 09/2022/TT-BGDĐT): lĩnh vực > nhóm ngành > ngành.
CREATE TABLE moet_major (
    code        TEXT PRIMARY KEY,
    level       TEXT NOT NULL CHECK (level IN ('linh_vuc', 'nhom_nganh', 'nganh')),
    name        TEXT NOT NULL,
    parent_code TEXT REFERENCES moet_major (code),
    former_code TEXT,
    note        TEXT,
    source_id   TEXT NOT NULL REFERENCES source (id)
);

-- Names students know, and search words, for nhóm ngành and ngành (spec 3.6). Rows come from
-- data/curated/display_names.csv; a code without a row is shown under its official name.
CREATE TABLE display_name (
    code         TEXT PRIMARY KEY REFERENCES moet_major (code),
    display_name TEXT,                       -- NULL: show the official name
    aliases      TEXT,                       -- '; '-separated search words (abbreviations, everyday words)
    status       TEXT NOT NULL CHECK (status IN ('draft', 'reviewed')),
    origin       TEXT NOT NULL,              -- 'group_labels_old_repo', 'agent_draft', a reviewer's name
    source_id    TEXT NOT NULL REFERENCES source (id)
);

CREATE TABLE subject (
    code      TEXT PRIMARY KEY,                -- 'TO', 'VA', 'N1', ...
    name      TEXT NOT NULL,
    is_exam   INTEGER NOT NULL CHECK (is_exam IN (0, 1)),  -- 0: a school-run test (năng khiếu)
    source_id TEXT NOT NULL REFERENCES source (id)
);

-- Subject combinations (tổ hợp). A combination is listed even when its subjects are unknown.
CREATE TABLE combo (
    code        TEXT PRIMARY KEY,
    subjects_known INTEGER NOT NULL CHECK (subjects_known IN (0, 1)),
    source_id   TEXT REFERENCES source (id)
);

CREATE TABLE combo_subject (
    combo_code   TEXT NOT NULL REFERENCES combo (code),
    position     INTEGER NOT NULL,
    subject_code TEXT NOT NULL REFERENCES subject (code),   -- may repeat (two talent tests are both 'NK')
    PRIMARY KEY (combo_code, position)
);

CREATE TABLE school (
    code               TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    school_type        TEXT,                -- 'university', 'academy', 'branch', 'college'
    is_military_police INTEGER CHECK (is_military_police IN (0, 1)),
    city               TEXT CHECK (city IN ('HN', 'HCM')),   -- NULL: neither / unknown
    city_basis         TEXT NOT NULL,       -- how the city was decided (rule name or 'override')
    in_scope           INTEGER NOT NULL CHECK (in_scope IN (0, 1)),
    scope_reason       TEXT,                -- why out of scope (NULL when in scope)
    source_id          TEXT NOT NULL REFERENCES source (id)
);

-- Other names students use for a school (English abbreviations, everyday names), for the chat's name matching
-- (spec 5). Rows come from data/curated/school_aliases.csv.
CREATE TABLE school_alias (
    school_code TEXT NOT NULL REFERENCES school (code),
    alias       TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('draft', 'reviewed')),
    origin      TEXT NOT NULL,
    source_id   TEXT NOT NULL REFERENCES source (id),
    PRIMARY KEY (school_code, alias)
);

CREATE TABLE program (
    id               TEXT PRIMARY KEY,      -- '{school_code}:{program_code}' (+ '~n' for split programs)
    school_code      TEXT NOT NULL REFERENCES school (code),
    program_code     TEXT NOT NULL,         -- the school's own code
    name             TEXT NOT NULL,         -- the school's program name
    city             TEXT CHECK (city IN ('HN', 'HCM')),   -- where it is taught: the school's city unless
                                            -- the name names another campus ('Kinh tế (Cơ sở HCM)')
    moet_code        TEXT REFERENCES moet_major (code),
    moet_code_basis  TEXT,                  -- 'unipilot', 'program_code', 'override'; NULL when unknown
    is_mixed_method  INTEGER CHECK (is_mixed_method IN (0, 1)),  -- latest year (2026); NULL when unknown.
                                            -- 1: the exam score is combined with học bạ, V-ACT, certificates...
    mixed_method_basis TEXT,                -- evidence for is_mixed_method
    score_scale      INTEGER CHECK (score_scale IN (30, 40, 100)),  -- scale of the latest cutoff; NULL: no cutoff
    scale_basis      TEXT NOT NULL,
    in_scope         INTEGER NOT NULL CHECK (in_scope IN (0, 1)),
    scope_reason     TEXT,
    tuition_min_vnd  INTEGER,               -- per year; NULL when unknown
    tuition_max_vnd  INTEGER,
    tuition_year     INTEGER,
    tuition_raw      TEXT,
    tuition_source_id TEXT REFERENCES source (id),
    tuition_basis    TEXT,                  -- NULL: stated per year; else how it was converted to per year
                                            -- (school_docs.FACTOR_BASES, e.g. 'semesters_per_year_owner_rule', 'free')
    source_ids       TEXT NOT NULL          -- ';'-joined sources listing this program
);

-- Combinations a program accepts for the THPT exam method.
CREATE TABLE program_combo (
    program_id TEXT NOT NULL REFERENCES program (id),
    combo_code TEXT NOT NULL REFERENCES combo (code),
    source_id  TEXT NOT NULL REFERENCES source (id),
    PRIMARY KEY (program_id, combo_code)
);

-- Subject weights other than 1 (e.g. Tiếng Anh x2 on a 40-point scale). Absent row = weight 1.
CREATE TABLE program_weight (
    program_id   TEXT NOT NULL REFERENCES program (id),
    subject_code TEXT NOT NULL REFERENCES subject (code),
    weight       REAL NOT NULL,
    source_id    TEXT NOT NULL REFERENCES source (id),
    evidence     TEXT,
    PRIMARY KEY (program_id, subject_code)
);

-- Chosen THPT-method cutoffs. combo_key '*' = one cutoff for every combination;
-- otherwise the ';'-joined sorted combinations the cutoff applies to.
-- All comparisons use score_30: the published score converted linearly to the 30-point scale
-- (score * 30 / scale; owner decision 2026-10-06).
CREATE TABLE cutoff (
    program_id  TEXT NOT NULL REFERENCES program (id),
    year        INTEGER NOT NULL,
    combo_key   TEXT NOT NULL,
    score       REAL NOT NULL,              -- as published
    scale       INTEGER NOT NULL CHECK (scale IN (30, 40, 100)),
    scale_basis TEXT NOT NULL,
    score_30    REAL NOT NULL,              -- score * 30 / scale
    is_mixed_method INTEGER NOT NULL CHECK (is_mixed_method IN (0, 1)),  -- the score combines the exam with
                                            -- other criteria (học bạ, V-ACT, certificates...)
    mixed_method_basis TEXT,                -- evidence when is_mixed_method = 1
    source_id   TEXT NOT NULL REFERENCES source (id),
    source_url  TEXT,
    PRIMARY KEY (program_id, year, combo_key)
);

-- Every cutoff value seen in any source, and what happened to it.
CREATE TABLE cutoff_observation (
    id          INTEGER PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES source (id),
    school_code TEXT NOT NULL,
    program_code TEXT NOT NULL,
    program_id  TEXT,                       -- NULL when it could not be linked to a program
    year        INTEGER NOT NULL,
    combos      TEXT,
    score       REAL,
    raw_score   TEXT,
    note        TEXT,
    status      TEXT NOT NULL,              -- 'chosen', 'agrees', 'disagrees', 'unused', 'excluded:<reason>'
    cache_check TEXT NOT NULL,              -- 'verified', 'mismatch', 'not_cached': row checked against the cached page
    source_url  TEXT
);

-- Share of a school's graduates of one ngành who have a job ("tỷ lệ sinh viên tốt nghiệp có việc làm"), as the
-- school's own document states it. Rows come from data/curated/school_employment.csv (school_docs.load_employment).
CREATE TABLE school_employment (
    school_code     TEXT NOT NULL REFERENCES school (code),
    moet_code       TEXT NOT NULL REFERENCES moet_major (code),
    graduation_year INTEGER NOT NULL,        -- the graduating class the survey covers
    rate            REAL NOT NULL CHECK (rate BETWEEN 0 AND 1),
    source_file     TEXT NOT NULL,           -- the captured file in data/manual_sources (and page)
    reviewed_by     TEXT,
    reviewed_on     TEXT,
    note            TEXT,                    -- what the document leaves unclear (survey month, definition...)
    source_id       TEXT NOT NULL REFERENCES source (id),
    PRIMARY KEY (school_code, moet_code, graduation_year)
);

-- Step 6: occupations (O*NET 31.0, CC BY 4.0, USDOL/ETA) and per-ngành facts (src/uniadvisor/facts/build.py).
CREATE TABLE occupation (
    code        TEXT PRIMARY KEY,              -- O*NET-SOC 2019 code, e.g. '15-1252.00'
    title       TEXT NOT NULL,
    description TEXT,
    job_zone    INTEGER,                       -- O*NET Job Zone 1-5 (preparation needed)
    source_id   TEXT NOT NULL REFERENCES source (id)
);

CREATE TABLE occupation_knowledge (
    occupation_code TEXT NOT NULL REFERENCES occupation (code),
    element_id      TEXT NOT NULL,
    element         TEXT NOT NULL,             -- knowledge area, e.g. 'Mathematics'
    importance      REAL NOT NULL,             -- O*NET importance, 1-5
    PRIMARY KEY (occupation_code, element_id)
);

CREATE TABLE occupation_interest (
    occupation_code TEXT NOT NULL REFERENCES occupation (code),
    riasec          TEXT NOT NULL,             -- Realistic, Investigative, Artistic, Social, Enterprising, Conventional
    score           REAL NOT NULL,             -- O*NET occupational interest, 1-7
    PRIMARY KEY (occupation_code, riasec)
);

CREATE TABLE occupation_work_context (         -- O*NET Work Context (owner decision 2026-10-08, step 7)
    occupation_code TEXT NOT NULL REFERENCES occupation (code),
    element_id      TEXT NOT NULL,             -- '4.C.2.a.1.c', or '4.C.3.d.8:3' for a category share
    element         TEXT NOT NULL,             -- e.g. 'Outdoors, Exposed to All Weather Conditions'
    scale           TEXT NOT NULL,             -- 'CX': mean 1-5 (frequency, importance...); 'CTP': % in the category
    value           REAL NOT NULL,
    PRIMARY KEY (occupation_code, element_id)
);

CREATE TABLE occupation_related (
    occupation_code TEXT NOT NULL REFERENCES occupation (code),
    related_code    TEXT NOT NULL REFERENCES occupation (code),
    tier            TEXT NOT NULL,             -- 'Primary-Short', 'Primary-Long', 'Supplemental'
    idx             INTEGER NOT NULL,
    PRIMARY KEY (occupation_code, related_code)
);

CREATE TABLE cip (
    code      TEXT PRIMARY KEY,                -- CIP 2020 field of study, e.g. '11.0701'
    title     TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES source (id)
);

CREATE TABLE cip_occupation (                  -- O*NET Resource Center crosswalk CIP 2020 -> O*NET-SOC 2019
    cip_code        TEXT NOT NULL REFERENCES cip (code),
    occupation_code TEXT NOT NULL REFERENCES occupation (code),
    PRIMARY KEY (cip_code, occupation_code)
);

CREATE TABLE nganh_cip (                       -- data/curated/nganh_cip.csv (agent draft, reviewed)
    nganh_code TEXT NOT NULL REFERENCES moet_major (code),
    rank       INTEGER NOT NULL,
    cip_code   TEXT NOT NULL REFERENCES cip (code),
    match      TEXT NOT NULL,                  -- exact, close, partial, broader
    confidence TEXT NOT NULL,                  -- high, medium, low
    retrieved  TEXT NOT NULL,                  -- 'yes' when the CIP was among the retrieved candidates
    note       TEXT,
    status     TEXT NOT NULL,                  -- draft, reviewed, rejected, unsure (a reviewer's doubt; a person decides)
    origin     TEXT NOT NULL,
    source_id  TEXT NOT NULL REFERENCES source (id),
    PRIMARY KEY (nganh_code, cip_code)
);

CREATE TABLE nganh_occupation (                -- derived: weight and share each sum to 1 per ngành
    nganh_code      TEXT NOT NULL REFERENCES moet_major (code),
    occupation_code TEXT NOT NULL REFERENCES occupation (code),
    weight          REAL NOT NULL,             -- with inverse document frequency: for closeness
    share           REAL NOT NULL,             -- plain share of the ngành's fields of study
    display_rank    INTEGER,                   -- 1 = shown first; NULL = not shown ('All Other' family or postsecondary teacher)
    PRIMARY KEY (nganh_code, occupation_code)
);

CREATE TABLE nganh_knowledge (                 -- derived: weighted mean importance per knowledge area
    nganh_code TEXT NOT NULL REFERENCES moet_major (code),
    element    TEXT NOT NULL,
    importance REAL NOT NULL,
    PRIMARY KEY (nganh_code, element)
);

CREATE TABLE nganh_interest (                  -- derived: weighted mean RIASEC score
    nganh_code TEXT NOT NULL REFERENCES moet_major (code),
    riasec     TEXT NOT NULL,
    score      REAL NOT NULL,
    PRIMARY KEY (nganh_code, riasec)
);

CREATE TABLE nganh_work_context (             -- derived: weighted mean Work Context value
    nganh_code TEXT NOT NULL REFERENCES moet_major (code),
    element_id TEXT NOT NULL,
    element    TEXT NOT NULL,
    scale      TEXT NOT NULL,                  -- as occupation_work_context
    value      REAL NOT NULL,
    PRIMARY KEY (nganh_code, element_id)
);

CREATE TABLE nganh_close (                     -- derived: closest ngành, best first
    nganh_code      TEXT NOT NULL REFERENCES moet_major (code),
    other_code      TEXT NOT NULL REFERENCES moet_major (code),
    rank            INTEGER NOT NULL,
    score           REAL NOT NULL,
    occupation_part REAL NOT NULL,
    knowledge_part  REAL NOT NULL,
    PRIMARY KEY (nganh_code, other_code)
);

CREATE TABLE name_vi (                         -- Vietnamese names (data/curated/*_names_vi.csv), drafts until reviewed
    kind        TEXT NOT NULL CHECK (kind IN ('occupation', 'knowledge', 'riasec')),
    key         TEXT NOT NULL,                 -- occupation code, knowledge area (English name), RIASEC type
    name_vi     TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL,
    origin      TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);

CREATE TABLE fact_sheet (                      -- data/curated/fact_sheets/<code>.md (uniadvisor.facts.sheets)
    code        TEXT PRIMARY KEY REFERENCES moet_major (code),   -- nhóm ngành
    markdown    TEXT NOT NULL,                 -- the sheet without its front matter
    status      TEXT NOT NULL,                 -- draft, reviewed; the app shows only reviewed sheets
    written_by  TEXT NOT NULL,
    reviewed_by TEXT NOT NULL
);

CREATE INDEX idx_program_school ON program (school_code);
CREATE INDEX idx_program_moet ON program (moet_code);
CREATE INDEX idx_cutoff_program ON cutoff (program_id);
CREATE INDEX idx_obs_program ON cutoff_observation (program_id);
