import { describe, expect, it } from "vitest";
import type { PlanJson } from "../api/types";
import { reducer, type State } from "./plan";
import { addPick, electivesOf, forServer, missingLocal, removePick, setElective, setItem, setScore } from "./planOps";

const empty: PlanJson = {
  format: "uniadvisor-plan", schema_version: 2, admission_year: 2027,
  profile: { scores: {}, score_kind: "expected", home_province: null, area: "KV3", category: "none", graduation_year: null,
             budget_trieu: null, near_home: false, favorite_school: null },
  majors: { picks: [], shortlist: [], answers: {} },
  lists: { chosen: null, recommended: [] },
  adjustments: { extra_points: {}, own_scores: {}, cutoff_shifts: {}, removed_schools: [], removed_programs: [] },
};

describe("plan store", () => {
  it("keeps one undo step per confirmed change, none for typing", () => {
    let s: State = { plan: empty, undo: [], words: null };
    s = reducer(s, { type: "edit", fn: (p) => setScore(p, "TO", 8) });
    expect(s.undo).toHaveLength(0);
    s = reducer(s, { type: "commit", plan: setScore(s.plan, "TO", 9) });
    expect(s.plan.profile.scores.TO).toBe(9);
    s = reducer(s, { type: "undo" });
    expect(s.plan.profile.scores.TO).toBe(8);
    expect(reducer(s, { type: "undo" })).toBe(s);          // nothing more to undo
  });
});

describe("plan edits", () => {
  it("swaps an elective and drops its old score; unscored subjects are not sent", () => {
    let p = setScore(setScore(empty, "TO", 8), "VA", 7);
    p = setElective(p, ["TO", "VA"], 0, "LI");
    p = setScore(p, "LI", 6.5);
    p = setElective(p, ["TO", "VA"], 1, "HO");
    expect(electivesOf(p, ["TO", "VA"])).toEqual(["LI", "HO"]);
    expect(forServer(p).profile.scores).toEqual({ TO: 8, VA: 7, LI: 6.5 });
    p = setElective(p, ["TO", "VA"], 0, "N1");
    expect("LI" in p.profile.scores).toBe(false);
  });

  it("caps picks, and removing a pick removes its hướng học", () => {
    let p = empty;
    for (const c of ["1", "2", "3", "4", "5", "6", "7"]) p = addPick(p, c);
    expect(p.majors.picks).toHaveLength(6);
    p = setItem(p, 0, "1", ["9", "8", "7"]);
    expect(p.majors.shortlist).toEqual([{ main: "1", close: ["9", "8"] }]);
    p = removePick(p, "1");
    expect(p.majors.shortlist).toEqual([]);
  });

  it("knows what the list still needs", () => {
    expect(missingLocal(empty)).toEqual(["scores", "home_province", "shortlist"]);
  });
});
