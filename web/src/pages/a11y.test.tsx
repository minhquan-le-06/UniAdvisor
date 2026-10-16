// Accessibility checks of the four pages with axe-core (what jsdom can check: names, roles, labels, structure; colour
// contrast is checked on the tokens instead, see tokens.css).
import { screen } from "@testing-library/react";
import axe from "axe-core";
import { Route } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { fixtures, mockApi, renderApp } from "../test-utils";
import Chosen from "./Chosen";
import Input from "./Input";
import Landing from "./Landing";
import Lists from "./Lists";

beforeEach(() => { mockApi(); });

async function violations(container: HTMLElement) {
  const r = await axe.run(container, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`);
}

describe("accessibility", () => {
  it("landing", async () => {
    const { container } = renderApp("/", <Route path="/" element={<Landing />} />);
    await screen.findByText(/Chọn ngành, xếp/);
    expect(await violations(container)).toEqual([]);
  });
  it("input page", async () => {
    const { container } = renderApp("/bat-dau", <Route path="/bat-dau" element={<Input />} />, fixtures.student);
    await screen.findByText("Kể cho mình nghe về em");
    expect(await violations(container)).toEqual([]);
  });
  it("three lists", async () => {
    const { container } = renderApp("/phuong-an", <Route path="/phuong-an" element={<Lists />} />, fixtures.student);
    await screen.findByText("Ba phương án gợi ý cho em");
    expect(await violations(container)).toEqual([]);
  });
  it("chosen list", async () => {
    const { container } = renderApp("/danh-sach", <Route path="/danh-sach" element={<Chosen />} />, fixtures.choose.plan);
    await screen.findByText(/nguyện vọng của em/);
    expect(await violations(container)).toEqual([]);
  });
});
