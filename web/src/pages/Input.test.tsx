import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
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
