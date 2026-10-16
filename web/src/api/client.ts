// The only place that talks to the server. Every call that concerns a student sends the plan with it; the server keeps
// nothing. The access code (when the server asks for one) is kept for this tab only.
import type {
  ApplyResult, Chosen, ChatReply, MajorDetail, MajorHit, Meta, PlanJson, QuizResult, Recommend, Missing,
  WishExplanation,
} from "./types";

const CODE_KEY = "uniadvisor-access-code";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function accessCode(): string | null {
  try {
    return sessionStorage.getItem(CODE_KEY);
  } catch {
    return null;                       // storage can be blocked: the page still works without it
  }
}

export function setAccessCode(code: string): void {
  try {
    sessionStorage.setItem(CODE_KEY, code);
  } catch {
    /* ignore */
  }
}

export function headers(code: string | null = accessCode()): Record<string, string> {
  return code ? { "Content-Type": "application/json", "X-Access-Code": code } : { "Content-Type": "application/json" };
}

let onUnauthorized: (() => void) | null = null;

/** Called when the server asks for the access code (401); the app shows the code box. */
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { method, headers: headers(), body: body === undefined ? undefined : JSON.stringify(body), signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "Không kết nối được máy chủ. Em kiểm tra mạng rồi thử lại nhé.");
  }
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    let detail = "Có lỗi xảy ra. Em thử lại nhé.";
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* keep the general message */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ ok: boolean }>("GET", "/api/health"),
  meta: () => request<Meta>("GET", "/api/meta"),
  catalog: () => request<{ code: string; label: string; level: string }[]>("GET", "/api/catalog"),
  newPlan: () => request<PlanJson>("GET", "/api/plan/new"),
  normalizePlan: (plan: unknown) => request<{ plan: PlanJson; warnings: string[] }>("POST", "/api/plan/normalize", { plan }),
  searchMajors: (q: string, signal?: AbortSignal) =>
    request<MajorHit[]>("GET", `/api/majors/search?q=${encodeURIComponent(q)}`, undefined, signal),
  major: (code: string) => request<MajorDetail>("GET", `/api/majors/${encodeURIComponent(code)}`),
  proposedClose: (code: string, exclude: string[]) =>
    request<{ code: string; label: string }[]>("GET", `/api/majors/${encodeURIComponent(code)}/close?exclude=${exclude.join(",")}`),
  questionnaire: (picked: Record<string, string | string[] | null>, text: string) =>
    request<QuizResult>("POST", "/api/questionnaire", { picked, text }),
  recommend: (plan: PlanJson, signal?: AbortSignal) =>
    request<Recommend | Missing>("POST", "/api/lists/recommend", { plan }, signal),
  choose: (plan: PlanJson, priority: string) =>
    request<{ plan: PlanJson; words: { good: string[]; bad: string[] } }>("POST", "/api/lists/choose", { plan, priority }),
  chosen: (plan: PlanJson, signal?: AbortSignal) => request<Chosen | Missing>("POST", "/api/lists/chosen", { plan }, signal),
  explain: (plan: PlanJson, nv: number) => request<WishExplanation>("POST", "/api/wishes/explain", { plan, nv }),
  chat: (plan: PlanJson, message: string) => request<ChatReply>("POST", "/api/chat", { plan, message }),
  apply: (plan: PlanJson, items: unknown[]) => request<ApplyResult>("POST", "/api/changes/apply", { plan, items }),
};
