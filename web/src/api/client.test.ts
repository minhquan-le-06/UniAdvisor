import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, headers } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("headers", () => {
  it("sends the access code only when there is one", () => {
    expect(headers(null)).toEqual({ "Content-Type": "application/json" });
    expect(headers("abc")["X-Access-Code"]).toBe("abc");
  });
});

describe("api", () => {
  it("calls the server and returns the JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", fetchMock);
    expect(await api.health()).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.objectContaining({ method: "GET" }));
  });

  it("sends the plan in the body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    await api.chat({ format: "uniadvisor-plan" } as never, "xin chào");
    const init = fetchMock.mock.calls[0][1];
    expect(JSON.parse(init.body)).toEqual({ plan: { format: "uniadvisor-plan" }, message: "xin chào" });
  });

  it("turns an error body into the message to show", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "Tệp lỗi." }) }));
    await expect(api.newPlan()).rejects.toMatchObject({ status: 422, message: "Tệp lỗi." });
    await expect(api.newPlan()).rejects.toBeInstanceOf(ApiError);
  });

  it("falls back to a general message when the body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 500, json: async () => { throw new Error("not json"); },
    }));
    await expect(api.meta()).rejects.toMatchObject({ status: 500, message: "Có lỗi xảy ra. Em thử lại nhé." });
  });

  it("says when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.meta()).rejects.toMatchObject({ status: 0 });
  });
});
