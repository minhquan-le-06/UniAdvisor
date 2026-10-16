import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { fixtures, mockApi, renderApp } from "../test-utils";
import Chosen from "./Chosen";

let calls: ReturnType<typeof mockApi>;
beforeEach(() => { calls = mockApi(); });

const page = () => renderApp("/danh-sach", <><Route path="/danh-sach" element={<Chosen />} /><Route path="/phuong-an" element={<div>ba phương án</div>} /></>,
                             fixtures.choose.plan);
const saved = () => JSON.parse(sessionStorage.getItem("uniadvisor-plan")!).plan;

describe("chosen list page", () => {
  it("shows the wishes and explains one", async () => {
    const user = userEvent.setup();
    page();
    const first = fixtures.chosen.wish_items[0];
    expect(await screen.findByRole("article", { name: new RegExp(`Nguyện vọng 1: ${first.program}`) })).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: /Vì sao ở đây/ })[0]);
    const sheet = await screen.findByRole("dialog");
    expect(await within(sheet).findByText(fixtures.explain.verdict)).toBeInTheDocument();
    expect(calls.explain.mock.calls[0][1]).toBe(1);
  });

  it("applies a change from the chat after confirmation, and undoes it", async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole("button", { name: /Mở chat/ }));
    await user.type(screen.getByRole("textbox", { name: "Tin nhắn" }), "Toán em được 9");
    await user.click(screen.getByRole("button", { name: "Gửi" }));
    expect(await screen.findByText(fixtures.chat.items[0].description)).toBeInTheDocument();
    expect(calls.apply).not.toHaveBeenCalled();                          // nothing changes before "Xác nhận"
    await user.click(screen.getByRole("button", { name: "Xác nhận" }));
    await waitFor(() => expect(calls.apply).toHaveBeenCalled());
    expect(calls.apply.mock.calls[0][1]).toEqual([{ kind: "set_score", params: { subject: "TO", value: 9 }, open: [], text: "Toán em được 9" }]);
    await waitFor(() => expect(saved().profile.scores.TO).toBe(9));
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Hoàn tác" }));
    await waitFor(() => expect(saved().profile.scores.TO).toBe(8));
  });

  it("goes back to the three lists", async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole("button", { name: /Xem lại 3 phương án/ }));
    expect(await screen.findByText("ba phương án")).toBeInTheDocument();
    expect(saved().lists.chosen).toBeNull();
  });
});
