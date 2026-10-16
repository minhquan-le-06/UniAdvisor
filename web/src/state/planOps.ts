// Pure edits of the plan file (schema 2, ui/plan_file.py). The page edits the plan directly while the student types;
// the server checks it on every call (plan_file.load), so a bad value here is reported there, never trusted.
import type { PlanJson, Priority } from "../api/types";

type Profile = PlanJson["profile"];

export const MAX_PICKS = 6;
export const MAX_ITEMS = 2;
export const MAX_CLOSE = 2;

export function setProfile(p: PlanJson, patch: Partial<Profile>): PlanJson {
  return { ...p, profile: { ...p.profile, ...patch } };
}

export function setScore(p: PlanJson, subject: string, value: number | null): PlanJson {
  const scores = { ...p.profile.scores };
  if (value == null) delete scores[subject];
  else scores[subject] = value;
  return setProfile(p, { scores });
}

/** Put `subject` in elective slot `slot` (0 or 1): the old elective of that slot loses its score. */
export function setElective(p: PlanJson, compulsory: string[], slot: 0 | 1, subject: string | null): PlanJson {
  const electives = electivesOf(p, compulsory);
  const old = electives[slot];
  const scores = { ...p.profile.scores };
  if (old && old !== subject) delete scores[old];
  if (subject && !(subject in scores)) scores[subject] = NaN;      // chosen, no score yet (dropped when sent)
  return setProfile(p, { scores });
}

/** The two electives in the order they were chosen (the plan keeps scores only, so: the keys after the compulsory). */
export function electivesOf(p: PlanJson, compulsory: string[]): (string | null)[] {
  const e = Object.keys(p.profile.scores).filter((s) => !compulsory.includes(s));
  return [e[0] ?? null, e[1] ?? null];
}

/** The plan as the server reads it: scores without a value are left out. */
export function forServer(p: PlanJson): PlanJson {
  const scores = Object.fromEntries(Object.entries(p.profile.scores).filter(([, v]) => Number.isFinite(v)));
  return { ...p, profile: { ...p.profile, scores } };
}

export function addPick(p: PlanJson, code: string): PlanJson {
  if (p.majors.picks.includes(code) || p.majors.picks.length >= MAX_PICKS) return p;
  return { ...p, majors: { ...p.majors, picks: [...p.majors.picks, code] } };
}

export function removePick(p: PlanJson, code: string): PlanJson {
  return {
    ...p,
    majors: {
      ...p.majors,
      picks: p.majors.picks.filter((c) => c !== code),
      shortlist: p.majors.shortlist.filter((e) => e.main !== code),
    },
  };
}

/** Hướng học `index` (0 or 1) becomes `main` with its close ngành; null removes it (hướng 2 moves up). */
export function setItem(p: PlanJson, index: number, main: string | null, close: string[] = []): PlanJson {
  const list = [...p.majors.shortlist];
  if (main == null) list.splice(index, 1);
  else list[index] = { main, close: close.filter((c) => c !== main).slice(0, MAX_CLOSE) };
  const seen = new Set<string>();
  const clean = list.filter((e) => e && !seen.has(e.main) && seen.add(e.main)).slice(0, MAX_ITEMS);
  return { ...p, majors: { ...p.majors, shortlist: clean } };
}

export function setClose(p: PlanJson, index: number, close: string[]): PlanJson {
  const e = p.majors.shortlist[index];
  return e ? setItem(p, index, e.main, close) : p;
}

export function setAnswers(p: PlanJson, answers: PlanJson["majors"]["answers"]): PlanJson {
  return { ...p, majors: { ...p.majors, answers } };
}

export function unchoose(p: PlanJson): PlanJson {
  return { ...p, lists: { ...p.lists, chosen: null } };
}

export function chosenOf(p: PlanJson): Priority | null {
  return p.lists.chosen;
}

/** What the list still needs, in the server's words (state.missing_for_list), checked locally to guide the page. */
export function missingLocal(p: PlanJson): ("scores" | "home_province" | "shortlist")[] {
  const out: ("scores" | "home_province" | "shortlist")[] = [];
  if (!Object.values(p.profile.scores).some(Number.isFinite)) out.push("scores");
  if (!p.profile.home_province) out.push("home_province");
  if (!p.majors.shortlist.length) out.push("shortlist");
  return out;
}
