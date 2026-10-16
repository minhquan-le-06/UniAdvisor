import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { fixtures, mockApi, renderApp } from "../test-utils";
import Lists from "./Lists";

let calls: ReturnType<typeof mockApi>;
beforeEach(() => { calls = mockApi(); });

describe("three lists page", () => {
  it("shows the three cards, the recommended one, and chooses a list", async () => {
    const user = userEvent.setup();
    renderApp("/phuong-an", <><Route path="/phuong-an" element={<Lists />} /><Route path="/danh-sach" element={<div>danh sách</div>} /></>,
              fixtures.student);
    expect(await screen.findByText("Ba phương án gợi ý cho em")).toBeInTheDocument();
    for (const c of fixtures.recommend.cards) expect(screen.getByRole("article", { name: `Phương án ${c.name}` })).toBeInTheDocument();
    expect(screen.getByText(`Gợi ý cho em: ${fixtures.recommend.pick.name}`)).toBeInTheDocument();
    const sent = calls.recommend.mock.calls[0][0];
    expect(sent.majors.shortlist).toEqual(fixtures.student.majors.shortlist);

    await user.click(screen.getAllByRole("button", { name: /Chọn phương án này/ })[0]);
    expect(await screen.findByText("danh sách")).toBeInTheDocument();
    expect(calls.choose.mock.calls[0][1]).toBe(fixtures.recommend.cards[0].priority);
    const saved = JSON.parse(sessionStorage.getItem("uniadvisor-plan")!);
    expect(saved.plan.lists.chosen).toBe("dung_nganh");
    expect(saved.words).toEqual(fixtures.choose.words);
  });

  it("sends a student without what the list needs back to the form", async () => {
    calls.recommend.mockResolvedValue({ missing: ["home_province"], missing_text: ["tỉnh/thành nơi em ở"] } as never);
    renderApp("/phuong-an", <Route path="/phuong-an" element={<Lists />} />);
    expect(await screen.findByText(/Chưa đủ thông tin/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /Quay lại nhập/ })).toBeEnabled());
  });
});
