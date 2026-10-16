// Render a page as the app does (start-up, plan store, router) against recorded API answers on the fake database
// (tools/web_fixtures.py). `api` calls are spied on, so a test can check what was sent.
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { vi } from "vitest";
import { api } from "./api/client";
import type { PlanJson } from "./api/types";
import { ToastProvider } from "./components/Toast";
import { Boot } from "./state/boot";
import fx from "./test-fixtures.json";

export const fixtures = fx as unknown as Record<string, any>;     // eslint-disable-line @typescript-eslint/no-explicit-any

export function mockApi() {
  const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
  return {
    health: vi.spyOn(api, "health").mockResolvedValue({ ok: true }),
    meta: vi.spyOn(api, "meta").mockResolvedValue(clone(fixtures.meta)),
    catalog: vi.spyOn(api, "catalog").mockResolvedValue(clone(fixtures.catalog)),
    newPlan: vi.spyOn(api, "newPlan").mockResolvedValue(clone(fixtures.plan)),
    searchMajors: vi.spyOn(api, "searchMajors").mockResolvedValue(clone(fixtures.search)),
    major: vi.spyOn(api, "major").mockResolvedValue(clone(fixtures.major)),
    proposedClose: vi.spyOn(api, "proposedClose").mockResolvedValue([]),
    questionnaire: vi.spyOn(api, "questionnaire").mockResolvedValue(clone(fixtures.questionnaire)),
    recommend: vi.spyOn(api, "recommend").mockResolvedValue(clone(fixtures.recommend)),
    choose: vi.spyOn(api, "choose").mockResolvedValue(clone(fixtures.choose)),
    chosen: vi.spyOn(api, "chosen").mockResolvedValue(clone(fixtures.chosen)),
    explain: vi.spyOn(api, "explain").mockResolvedValue(clone(fixtures.explain)),
    chat: vi.spyOn(api, "chat").mockResolvedValue(clone(fixtures.chat)),
    apply: vi.spyOn(api, "apply").mockResolvedValue(clone(fixtures.apply)),
    normalizePlan: vi.spyOn(api, "normalizePlan").mockImplementation(async (p) => ({ plan: p as PlanJson, warnings: [] })),
  };
}

/** Render `path` with a saved plan in this tab (or the empty one). */
export function renderApp(path: string, routes: ReactNode, plan?: PlanJson) {
  sessionStorage.clear();
  if (plan) sessionStorage.setItem("uniadvisor-plan", JSON.stringify({ plan, words: null }));
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Boot><Routes>{routes}<Route path="*" element={<div>khác</div>} /></Routes></Boot>
      </MemoryRouter>
    </ToastProvider>,
  );
}
