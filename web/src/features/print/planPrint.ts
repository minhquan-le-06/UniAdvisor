// A separate, deliberately plain document for the browser's "Save as PDF" print flow.  The JSON plan remains the
// source of truth for reopening a plan; this document is only a pleasant-to-read snapshot for a student or parent.
import type { Chosen, Meta, PlanJson, WishItem } from "../../api/types";

export type PrintPlan = {
  plan: PlanJson;
  meta: Meta;
  labels: ReadonlyMap<string, string>;
  chosen: Chosen | null;
  problem: string | null;
  createdAt?: Date;
};

const esc = (value: string | number | null | undefined) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]!));

const text = (value: string | null | undefined, fallback = "Chưa chọn") => value ? esc(value) : fallback;

function table(rows: [string, string][]): string {
  return `<table class="details"><tbody>${rows.map(([label, value]) => `<tr><th scope="row">${esc(label)}</th><td>${value}</td></tr>`).join("")}</tbody></table>`;
}

function labelFor(code: string, meta: Meta, labels: ReadonlyMap<string, string>): string {
  return labels.get(code) ?? meta.schools.find((school) => school.code === code)?.name ?? code;
}

function levelClass(level: WishItem["level"]): string {
  return `level-${level.replace("_", "-")}`;
}

function printWish(wish: WishItem): string {
  const cutoffs = wish.cutoffs.map((cutoff) => `Điểm chuẩn ${cutoff.year}: ${esc(cutoff.text)}`).join("<br>");
  return `<tr>
    <td class="number">${wish.nv}</td>
    <td><span class="level ${levelClass(wish.level)}">${esc(wish.level_name)}</span></td>
    <td><strong>${esc(wish.program)}</strong><br><span class="muted">${esc(wish.school)}${wish.city ? ` · ${esc(wish.city)}` : ""}</span></td>
    <td>${esc(wish.score)}</td>
    <td>${cutoffs || "Chưa có"}</td>
    <td>${esc(wish.tuition)}</td>
  </tr>`;
}

/** Builds a self-contained A4 document. All student-provided strings are HTML-escaped before they enter the popup. */
export function buildPlanPrintHtml({ plan, meta, labels, chosen, problem, createdAt = new Date() }: PrintPlan): string {
  const subjectNames = new Map(meta.subjects.map((subject) => [subject.code, subject.name]));
  const areaNames = new Map(meta.areas.map((area) => [area.code, area.label]));
  const categoryNames = new Map(meta.categories.map((category) => [category.code, category.label]));
  const scoreCodes = [...meta.subjects.map((subject) => subject.code).filter((code) => code in plan.profile.scores),
    ...Object.keys(plan.profile.scores).filter((code) => !subjectNames.has(code))];
  const scores = scoreCodes.map((code) => [subjectNames.get(code) ?? code,
    new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(plan.profile.scores[code] ?? 0)] as [string, string]);
  const directions = plan.majors.shortlist.map((item, index) => {
    const close = item.close.map((code) => labelFor(code, meta, labels)).join(", ");
    return `<li><strong>Hướng học ${index + 1}: ${esc(labelFor(item.main, meta, labels))}</strong>${close ? `<br><span class="muted">Ngành gần: ${esc(close)}</span>` : ""}</li>`;
  }).join("");
  const wishes = chosen?.wish_items ?? [];
  const date = new Intl.DateTimeFormat("vi-VN", { dateStyle: "long" }).format(createdAt);
  const scoreKind = plan.profile.score_kind === "real" ? "Điểm thi thật" : "Điểm dự kiến";
  const favorite = plan.profile.favorite_school ? labelFor(plan.profile.favorite_school, meta, labels) : null;
  const report = chosen ? `<section class="card">
      <p class="eyebrow">Phương án em đã chọn</p>
      <h2>${esc(chosen.header?.name ?? "Danh sách nguyện vọng")}</h2>
      ${chosen.header?.help ? `<p>${esc(chosen.header.help)}</p>` : ""}
      ${chosen.no_admission_warning ? `<p class="warning"><strong>Lưu ý:</strong> ${esc(chosen.no_admission_warning)}</p>` : ""}
      ${chosen.notes.map((note) => `<p class="warning">${esc(note)}</p>`).join("")}
      ${wishes.length ? `<div class="table-wrap"><table class="wishes"><thead><tr><th>NV</th><th>Mức</th><th>Trường và chương trình</th><th>Điểm của em</th><th>Điểm chuẩn</th><th>Học phí</th></tr></thead><tbody>${wishes.map(printWish).join("")}</tbody></table></div>
        <p class="caption">${esc(chosen.score_caption)}</p>` : `<p>Danh sách hiện chưa có nguyện vọng để in.</p>`}
    </section>` : `<section class="card"><h2>Danh sách nguyện vọng</h2>
      <p>${problem ? esc(problem) : "Em chưa chốt một phương án, nên bản in hiện có thông tin hồ sơ và hướng học."}</p>
    </section>`;

  return `<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kế hoạch UniAdvisor ${plan.admission_year}</title>
  <style>
    @page { size: A4; margin: 14mm; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #1f1a17; background: #fff; font: 10.5pt/1.5 Arial, "Segoe UI", sans-serif; }
    main { max-width: 182mm; margin: 0 auto; }
    .cover { padding: 0 0 8mm; border-bottom: 2px solid #ff6b4a; }
    .brand { color: #d9441f; font-weight: 800; font-size: 11pt; letter-spacing: .04em; }
    h1 { margin: 3mm 0 2mm; font-size: 24pt; line-height: 1.15; }
    h2 { margin: 0 0 3mm; font-size: 15pt; line-height: 1.25; }
    p { margin: 0 0 2.5mm; }
    .muted, .caption { color: #62564f; }
    .caption { font-size: 8.7pt; }
    .eyebrow { margin-bottom: 1mm; color: #c2330f; font-size: 8.5pt; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; margin-top: 6mm; }
    .card { break-inside: avoid; margin-top: 6mm; padding: 5mm; border: 1px solid #e2c9ba; border-radius: 3mm; }
    .grid .card { margin-top: 0; }
    .details { width: 100%; border-collapse: collapse; }
    .details th, .details td { padding: 1.7mm 0; border-bottom: 1px solid #f0dfd4; text-align: left; vertical-align: top; }
    .details th { width: 47%; color: #62564f; font-weight: 600; }
    .details tr:last-child th, .details tr:last-child td { border-bottom: 0; }
    ul { margin: 0; padding-left: 5mm; }
    li + li { margin-top: 2mm; }
    .table-wrap { overflow: hidden; border: 1px solid #e2c9ba; border-radius: 2.5mm; }
    .wishes { width: 100%; border-collapse: collapse; font-size: 8.6pt; }
    .wishes thead { display: table-header-group; }
    .wishes tr { break-inside: avoid; }
    .wishes th { padding: 2mm; background: #fff3ec; text-align: left; vertical-align: bottom; }
    .wishes td { padding: 2mm; border-top: 1px solid #f0dfd4; vertical-align: top; }
    .number { font-weight: 800; text-align: center; }
    .level { display: inline-block; padding: .7mm 1.5mm; border-radius: 99px; font-weight: 700; white-space: nowrap; }
    .level-mo-uoc { background: #f9d8e9; color: #7f1d5a; }
    .level-thu-suc { background: #ffe0ca; color: #8a2d00; }
    .level-vua-suc { background: #dfe7ff; color: #233e9b; }
    .level-an-toan { background: #d6f2f6; color: #09606e; }
    .warning { padding: 2.5mm 3mm; border-left: 3px solid #d99a21; background: #fff7df; }
    footer { margin-top: 7mm; padding-top: 3mm; border-top: 1px solid #e2c9ba; color: #62564f; font-size: 8.4pt; }
    @media print { .screen-note { display: none; } }
    @media screen { body { background: #f6eee9; padding: 16px; } main { background: #fff; padding: 14mm; box-shadow: 0 4px 24px #0002; } .screen-note { margin: 0 0 6mm; padding: 3mm; background: #eaf3ff; color: #1b4f8f; } }
  </style>
</head>
<body>
  <main>
    <p class="screen-note">Hộp thoại in sẽ mở. Chọn <strong>Lưu dưới dạng PDF</strong> để lưu bản này.</p>
    <header class="cover"><div class="brand">UNIADVISOR</div><h1>Kế hoạch xét tuyển đại học</h1><p>Năm tuyển sinh ${esc(plan.admission_year)} · Xuất ngày ${esc(date)}</p></header>
    <div class="grid">
      <section class="card"><h2>Thông tin của em</h2>${table([
        ["Loại điểm", esc(scoreKind)], ["Tỉnh/thành phố", text(plan.profile.home_province)],
        ["Khu vực", esc(areaNames.get(plan.profile.area) ?? plan.profile.area)],
        ["Đối tượng ưu tiên", esc(categoryNames.get(plan.profile.category) ?? plan.profile.category)],
        ["Ngân sách học phí", plan.profile.budget_trieu == null ? "Chưa chọn" : `${esc(plan.profile.budget_trieu)} triệu đồng/năm`],
        ["Ưu tiên gần nhà", plan.profile.near_home ? "Có" : "Không"], ["Trường em thích", text(favorite)],
      ])}</section>
      <section class="card"><h2>Điểm em đã nhập</h2>${scores.length ? table(scores) : "<p>Em chưa nhập điểm.</p>"}</section>
    </div>
    <section class="card"><h2>Hướng học</h2>${directions ? `<ol>${directions}</ol>` : "<p>Em chưa chọn hướng học.</p>"}</section>
    ${report}
    <footer>Bản PDF này để xem hoặc in. Để mở lại và tiếp tục điều chỉnh kế hoạch trong UniAdvisor, hãy giữ tệp <strong>ke-hoach-uniadvisor.json</strong>.</footer>
  </main>
</body>
</html>`;
}

export function writePrintLoading(target: Window): void {
  target.document.open();
  target.document.write(`<!doctype html><html lang="vi"><head><title>Đang chuẩn bị bản in</title><style>body{font-family:Arial,"Segoe UI",sans-serif;padding:32px;color:#1f1a17}</style></head><body><p>Đang chuẩn bị bản in kế hoạch...</p></body></html>`);
  target.document.close();
}
