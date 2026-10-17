import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fixtures, mockApi, renderApp } from "../test-utils";
import Input from "./Input";

let calls: ReturnType<typeof mockApi>;
beforeEach(() => { calls = mockApi(); });

const savedPlan = () => JSON.parse(sessionStorage.getItem("uniadvisor-plan")!).plan;

describe("input page", () => {
  it("fills the profile and enables the lists once the list has what it needs", async () => {
    const user = userEvent.setup();
    renderApp("/bat-dau", <Route path="/bat-dau" element={<Input />} />);
    expect(await screen.findByText("Kể cho mình nghe về em")).toBeInTheDocument();
    expect(screen.getByText(/Còn thiếu:/)).toHaveTextContent("điểm các môn, tỉnh/thành");
    expect(screen.getByRole("button", { name: /Tiếp: Chọn ngành/ })).toBeDisabled();
    expect(screen.queryByPlaceholderText(/Ví dụ: CNTT/)).not.toBeInTheDocument();   // step 2 is not on this page yet

    await user.type(screen.getByLabelText("Toán"), "8,5");
    await user.type(screen.getByLabelText("Ngữ văn"), "7");
    const electives = screen.getByRole("group", { name: "Chọn 2 môn" });
    await user.click(within(electives).getByRole("checkbox", { name: "Vật lí" }));
    await user.type(await screen.findByLabelText("Điểm Vật lí"), "7,25");
    await waitFor(() => expect(savedPlan().profile.scores).toEqual({ TO: 8.5, VA: 7, LI: 7.25 }));
    expect(screen.getByText(/Còn thiếu:/)).toHaveTextContent("tỉnh/thành");
  });

  it("takes Toán to 0,05 and the other subjects to 0,25, and refuses anything else with a warning", async () => {
    const user = userEvent.setup();
    renderApp("/bat-dau", <Route path="/bat-dau" element={<Input />} />);
    const math = await screen.findByLabelText("Toán");
    await user.type(math, "8,35");
    await user.tab();
    await waitFor(() => expect(savedPlan().profile.scores).toEqual({ TO: 8.35 }));
    const lit = screen.getByLabelText("Ngữ văn");
    await user.type(lit, "7,3");
    await user.tab();
    expect(await screen.findByText(/Chỉ nhận bước 0,25/)).toBeInTheDocument();
    expect(savedPlan().profile.scores).toEqual({ TO: 8.35 });                 // the odd one was not taken
    await user.clear(lit);
    await user.type(lit, "7,25");
    await user.tab();
    await waitFor(() => expect(savedPlan().profile.scores).toEqual({ TO: 8.35, VA: 7.25 }));
    expect(screen.queryByText(/Chỉ nhận bước/)).not.toBeInTheDocument();
  });

  it("fills the khu vực from the school the student picks, and explains it behind a ?", async () => {
    const province = fixtures.meta.provinces[0] as string;
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      [province]: [["THPT Mẫu A", "KV1"], ["THPT Mẫu B", "KV2-NT"]],
    }))));
    const user = userEvent.setup();
    renderApp("/bat-dau", <Route path="/bat-dau" element={<Input />} />);
    expect(screen.queryByText(/Trường THPT em học/)).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /Tỉnh\/thành Chọn tỉnh\/thành/ }));
    await user.click(await screen.findByRole("option", { name: province }));
    await user.click(await screen.findByRole("button", { name: /Trường THPT em học/ }));
    await user.type(screen.getByPlaceholderText("Gõ tên trường để tìm..."), "mau b");
    await user.click(await screen.findByRole("option", { name: /THPT Mẫu B/ }));
    await waitFor(() => expect(savedPlan().profile.area).toBe("KV2-NT"));
    expect(screen.getByRole("status")).toHaveTextContent("KV2-NT");

    await user.click(screen.getByRole("button", { name: "Giải thích khu vực ưu tiên" }));
    expect(await screen.findByText("Khu vực ưu tiên là gì?")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("searches a ngành and picks it in step 2", async () => {
    const user = userEvent.setup();
    renderApp("/bat-dau?buoc=2", <Route path="/bat-dau" element={<Input />} />);
    await user.type(await screen.findByPlaceholderText(/Ví dụ: CNTT/), "cntt");
    const pick = await screen.findAllByRole("button", { name: "Chọn" });
    await user.click(pick[0]);
    expect(savedPlan().majors.picks).toEqual([fixtures.search[0].code]);
  });

  it("restores a saved plan and leads to the lists", async () => {
    renderApp("/bat-dau?buoc=3", <><Route path="/bat-dau" element={<Input />} /><Route path="/phuong-an" element={<div>3 phương án</div>} /></>,
              fixtures.student);
    const go = await screen.findByRole("button", { name: /Xem 3 phương án/ });
    expect(screen.getByText(/Đủ thông tin rồi/)).toBeInTheDocument();
    await userEvent.setup().click(go);
    expect(await screen.findByText("3 phương án")).toBeInTheDocument();
    expect(calls.newPlan).toHaveBeenCalled();
  });

  it("sends the answers of the questions and shows the suggestions", async () => {
    const user = userEvent.setup();
    renderApp("/bat-dau?buoc=2", <Route path="/bat-dau" element={<Input />} />);
    await user.click(await screen.findByRole("radio", { name: /Em chưa biết chọn gì/ }));
    const q = fixtures.meta.questions.find((x: { kind: string }) => x.kind === "single");
    await user.click(screen.getAllByRole("radio", { name: q.options[0].label })[0]);
    await user.click(screen.getByRole("button", { name: "Xem gợi ý" }));
    await waitFor(() => expect(calls.questionnaire).toHaveBeenCalled());
    expect(calls.questionnaire.mock.calls[0][0][q.id]).toBe(q.options[0].code);
    for (const g of fixtures.questionnaire.suggestions) expect(await screen.findByText(g.label)).toBeInTheDocument();
  });
});
