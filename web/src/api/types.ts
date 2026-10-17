// The JSON the API returns (src/uniadvisor/api/views.py). Written by hand next to that file: when a view changes, change
// the type here; tests/test_api.py checks the same keys on the Python side.

export type Priority = "dung_nganh" | "nghe_nghiep" | "hop_mon" | "tiet_kiem";
export type Corner = "hop_mon" | "nguyen_vong_cao" | "dung_nganh" | "hoc_phi" | "nghe_nghiep";

export type PlanJson = {
  format: "uniadvisor-plan";
  schema_version: number;
  admission_year: number;
  profile: {
    scores: Record<string, number>;
    score_kind: "expected" | "real";
    home_province: string | null;
    area: string;
    category: string;
    graduation_year: number | null;
    budget_trieu: number | null;
    near_home: boolean;
    favorite_school: string | null;
  };
  majors: {
    picks: string[];
    shortlist: { main: string; close: string[] }[];
    answers: Record<string, string | string[] | null>;
  };
  lists: { chosen: Priority | null; recommended: unknown[] };
  adjustments: {
    extra_points: Record<string, number>;
    own_scores: Record<string, { score: number; scale: number }>;
    cutoff_shifts: Record<string, number>;
    removed_schools: string[];
    removed_programs: string[];
  };
};

export type Question = {
  id: string;
  number: number;
  text: string;
  kind: "single" | "multi";
  max: number | null;
  not_in: string | null;
  hint: string;
  options: { code: string; label: string }[];
};

export type Meta = {
  admission_year: number;
  subjects: { code: string; name: string }[];
  compulsory: string[];
  electives: string[];
  max_electives: number;
  provinces: string[];
  areas: { code: string; label: string }[];
  categories: { code: string; label: string }[];
  score_kinds: string[];
  schools: { code: string; name: string }[];
  limits: { max_picks: number; max_items: number; max_close: number; scales: number[]; max_cutoff_shift: number };
  score_steps: Record<string, number>;      // the finest division of an exam score: "default", and Toán ("TO") finer
  number_ranges: Record<string, [number, number, number]>;
  questions: Question[];
  has_free_text: boolean;
  texts: {
    how_the_list_is_built: string;
    levels: { code: string; name: string; help: string }[];
    extra_points_reminder: string;
    mixed_method_note: string;
    income_context: string;
    onet_credit: string;
    quiz_method_note: string;
    pentagon_note: string;
    lists: { priority: Priority; name: string; help: string; slot: number }[];
    corners: { code: Corner; name: string; help: string }[];
  };
};

export type Pentagon = {
  values: Record<Corner, number | null>;      // 0-1, higher is better; null: no data (leave the corner out)
  unknown: Record<Corner, number>;            // share of admissions with no value for the corner
  none: number;                               // chance of no admission at the score entered
};

/** One row of the wish table; the keys are the Vietnamese column names (NV, Mức, Trường, Chương trình, ...). */
export type WishRow = Record<string, string | number>;

export type LevelCode = "mo_uoc" | "thu_suc" | "vua_suc" | "an_toan";

/** A wish with its parts apart, for cards (views.wish_items). */
export type WishItem = {
  nv: number;
  program_id: string;
  level: LevelCode;
  level_name: string;
  school: string;
  school_code: string;
  program: string;
  mixed: boolean;
  other_codes: string[];
  item: number;                               // hướng học 1 or 2
  relation: string;
  score: string;
  score_value: number;
  cutoffs: { year: number; text: string }[];
  tuition: string;
  over_budget: boolean;
  city: string;
  far: boolean;
  favorite: boolean;
};

export type ChanceRow = {
  shift: number;
  label: string;
  levels: { level: LevelCode; name: string; p: number; text: string }[];
};

export type Card = {
  priority: Priority;
  slot: number;                               // colour slot 0-2 (--color-list-N)
  name: string;
  fit: string;
  good: string[];
  bad: string[];
  notes: string[];
  warning: string | null;
  same_as: string | null;                     // replaces good/bad when the list nearly repeats another
  blocked: string | null;                     // replaces the card when no wish fits (no choose button)
  recommended: boolean;
  pentagon: Pentagon | null;
  n_wishes: number;
  wishes: WishRow[] | null;
  wish_items: WishItem[] | null;
  no_admission: number | null;
};

export type Missing = { missing: string[]; missing_text: string[] };

export type Recommend = {
  missing: [];
  intro: string;
  safe_line: string | null;
  notes: string[];
  pick: { priority: Priority; name: string; reason: string } | null;
  cards: Card[];
  no_answers_note: string | null;
  corner_rows: Record<string, string>[];
  at_least_one_text: string;
  snapshot: unknown[];
};

export type Controls = {
  schools: { code: string; name: string; extra: number; own: number | null; scales: number[]; shift: number }[];
  wishes: { id: string; nv: number; label: string }[];
  removed_schools: { code: string; name: string }[];
  removed_programs: { id: string; label: string }[];
  shortlist: { main: string; label: string; close: { code: string; label: string }[] }[];
  scores: Record<string, number>;
  area: string;
  category: string;
  budget_trieu: number | null;
  near_home: boolean;
};

export type Chosen = {
  missing: [];
  header: {
    priority: Priority;
    name: string;
    help: string;
    slot: number;
    pentagon: Pentagon | null;
    fallback_note: string | null;
    fees_note: string | null;
  } | null;
  list_choice: string | null;
  empty: boolean;
  empty_text: string;
  notes: string[];
  favorite_note: string | null;
  expected_note: boolean;
  mixed_method: boolean;
  wishes: WishRow[];
  wish_items: WishItem[];
  wish_numbers: number[];
  levels: string[];
  score_caption: string;
  no_admission_warning: string | null;
  chances: { lines: string[]; rows: ChanceRow[]; note: string } | null;
  controls: Controls;
};

export type WishExplanation = {
  wish_no: number;
  level: string;
  title: string;
  verdict: string;
  numbers: string[];
  why_in_list: string;
  placement: string;
  notices: string[];
  markdown: string;
};

export type ChangeItem = {
  kind: string;
  params: Record<string, unknown>;
  text: string;
  open: string[];                             // parameters still to ask (fill params[name] before applying)
  options: Record<string, [string | number, string][]>;
  description: string;
  labels: Record<string, string>;
  range: [number, number, number];            // lowest, highest, step for a number box
};

export type ChatReply = { answers: string[]; help: string | null; items: ChangeItem[] };
export type ApplyResult = { plan: PlanJson; done: string[]; errors: string[]; diff: string; changed: boolean };

export type MajorHit = {
  code: string;
  label: string;
  kind: string;
  official: string | null;
  matched: string | null;
  children: string[];
  more_children: boolean;
  where: string;
};

export type MajorDetail = {
  code: string;
  label: string;
  kind: string;
  official: string | null;
  where: string;
  top_combos: string[];
  interest_names: string[];
  knowledge: string[];
  children: string[];
  combos: { label: string; subjects: string[]; share_pct: number }[];
  jobs: string[];
  income: string;
  interests: { name: string; description: string }[];
  close: string[];
  sheet: string | null;
  has_facts: boolean;
  draft: boolean;
};

export type QuizResult = {
  answers: Record<string, string | string[] | null>;
  notes: string[];
  guesses: { question: string; option: string; words: string; text: string }[];
  maybe: { question: string; option: string; words: string; text: string }[];
  suggestions: { code: string; label: string; reasons: string[]; children: string[]; more_children: boolean }[];
  answered: number;
};
