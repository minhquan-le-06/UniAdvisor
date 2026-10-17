import { describe, expect, it } from "vitest";
import type { Chosen, Meta, PlanJson } from "../../api/types";
import { buildPlanPrintHtml } from "./planPrint";

const meta = {
  admission_year: 2027,
  subjects: [{ code: "TO", name: "Toán" }],
  compulsory: [], electives: [], max_electives: 0, provinces: [],
  areas: [{ code: "KV3", label: "Khu vực 3" }], categories: [{ code: "none", label: "Không thuộc diện ưu tiên" }],
  score_kinds: [], schools: [], limits: { max_picks: 6, max_items: 2, max_close: 2, scales: [], max_cutoff_shift: 0 },
  number_ranges: {}, questions: [], has_free_text: false,
  texts: { how_the_list_is_built: "", levels: [], extra_points_reminder: "", mixed_method_note: "", income_context: "", onet_credit: "", quiz_method_note: "", pentagon_note: "", lists: [], corners: [] },
} as unknown as Meta;

const plan: PlanJson = {
  format: "uniadvisor-plan", schema_version: 2, admission_year: 2027,
  profile: { scores: { TO: 8 }, score_kind: "expected", home_province: "<img src=x>", area: "KV3", category: "none", graduation_year: null, budget_trieu: 20, near_home: false, favorite_school: null },
  majors: { picks: ["7480201"], shortlist: [{ main: "7480201", close: [] }], answers: {} },
  lists: { chosen: "dung_nganh", recommended: [] },
  adjustments: { extra_points: {}, own_scores: {}, cutoff_shifts: {}, removed_schools: [], removed_programs: [] },
};

const chosen = {
  missing: [], header: { priority: "dung_nganh", name: "Đúng ngành nhất", help: "Ưu tiên ngành", slot: 0, pentagon: null, fallback_note: null, fees_note: null },
  list_choice: null, empty: false, empty_text: "", notes: [], favorite_note: null, expected_note: true, mixed_method: false,
  wishes: [], wish_items: [{ nv: 1, program_id: "A:1", level: "vua_suc", level_name: "vừa sức", school: "Trường A", school_code: "A", program: "Công nghệ thông tin", mixed: false, other_codes: [], item: 1, relation: "ngành chính", score: "25,0", score_value: 25, cutoffs: [{ year: 2026, text: "24,0" }], tuition: "20 triệu/năm", over_budget: false, city: "Hà Nội", far: false, favorite: false }],
  wish_numbers: [1], levels: ["vừa sức"], score_caption: "Điểm chuẩn theo thang 30.", no_admission_warning: null,
  chances: null, controls: { schools: [], wishes: [], removed_schools: [], removed_programs: [], shortlist: [], scores: {}, area: "KV3", category: "none", budget_trieu: null, near_home: false },
} as unknown as Chosen;

describe("buildPlanPrintHtml", () => {
  it("makes a readable printable plan and escapes student-entered text", () => {
    const html = buildPlanPrintHtml({ plan, meta, labels: new Map([["7480201", "Công nghệ thông tin"]]), chosen, problem: null, createdAt: new Date("2026-10-17") });
    expect(html).toContain("Kế hoạch xét tuyển đại học");
    expect(html).toContain("Đúng ngành nhất");
    expect(html).toContain("Công nghệ thông tin");
    expect(html).toContain("&lt;img src=x&gt;");
    expect(html).not.toContain("<img src=x>");
    expect(html).toContain("ke-hoach-uniadvisor.json");
  });
});
