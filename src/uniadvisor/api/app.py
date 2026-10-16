"""The web API. `create_app()` builds the application; run it with

    uvicorn uniadvisor.api.app:create_app --factory --host 0.0.0.0 --port 8000

Stateless: every call that concerns a student carries the plan (the plan file as JSON, ui/plan_file.py, schema 2) and
returns new data; nothing is stored, and request bodies are never logged. The database is loaded once, on the first call
that needs it (not at startup: a serverless function must be ready within seconds, and downloading and loading the data
takes longer), and is read only; no route returns a table, only what was computed for one student plus names and fixed
texts.
"""

from __future__ import annotations

import hmac
import json
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from uniadvisor.api import views
from uniadvisor.api.dbfetch import DatabaseUnavailable, ensure_database
from uniadvisor.api.settings import Settings
from uniadvisor.chat.pipeline import handle
from uniadvisor.planner.lists import Priority
from uniadvisor.ui import list_view, major_info, plan_file
from uniadvisor.ui.service import AppData
from uniadvisor.ui.state import PlanState

MAX_ITEMS_PER_CALL = 30
# The page loads only its own files (fonts are self-hosted); styles may be set inline by the components. Hugging Face
# shows a Space inside its own page, so that page may frame this one.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'; object-src 'none'; "
       "frame-ancestors 'self' https://huggingface.co https://*.hf.space")
OPEN_PATHS = ("/api/health",)            # reachable without the access code
RETRY_AFTER_FAILURE = 20.0                # seconds before a failed data load is tried again


class PlanBody(BaseModel):
    plan: dict


class ChatBody(PlanBody):
    message: str = Field(max_length=1000)


class ExplainBody(PlanBody):
    nv: int = Field(ge=1, le=15)


class ChooseBody(PlanBody):
    priority: str


class ApplyBody(PlanBody):
    items: list[dict] = Field(max_length=MAX_ITEMS_PER_CALL)


class QuizBody(BaseModel):
    picked: dict[str, str | list[str] | None] = Field(default_factory=dict)
    text: str = Field(default="", max_length=1000)


def client_ip(request: Request) -> str:
    """The address rate limits count. On Vercel its own header carries the client's address; behind another proxy
    the last X-Forwarded-For entry is the address that proxy saw; without a proxy the socket address."""
    for name in ("x-vercel-forwarded-for", "x-real-ip"):
        if value := request.headers.get(name):
            return value.split(",")[0].strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def create_app(settings: Settings | None = None, data: AppData | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.data, app.state.problem, app.state.failed_at = data, None, 0.0
        app.state.load_lock = threading.Lock()
        yield

    def load_data(app: FastAPI) -> AppData:
        """The data, loaded on first use (one request loads it, the others wait for it)."""
        if app.state.data is not None:
            return app.state.data
        with app.state.load_lock:
            if app.state.data is not None:
                return app.state.data
            if app.state.problem and time.monotonic() - app.state.failed_at < RETRY_AFTER_FAILURE:
                raise DatabaseUnavailable(app.state.problem)
            try:
                d = AppData.load(ensure_database())
            except DatabaseUnavailable as e:
                # Not a crash: health says what is missing (the message names settings, never a secret), the other
                # routes answer 503, and the next try comes after a short pause.
                app.state.problem, app.state.failed_at = str(e), time.monotonic()
                raise
            # The cached properties are filled lazily and are not locked: fill them before others use the data.
            d.indexes, d.classifier, d.programs_by_id
            app.state.data, app.state.problem = d, None
            return d

    app = FastAPI(title="UniAdvisor API", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None,
                  lifespan=lifespan)

    # ------------------------------------------------------------ guards
    if cfg.rate_limit:
        limiter = Limiter(key_func=client_ip, default_limits=[cfg.rate_limit])
        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)

        @app.exception_handler(RateLimitExceeded)
        async def too_many(request: Request, exc: RateLimitExceeded):
            return JSONResponse({"detail": "Em gửi yêu cầu hơi nhanh. Đợi một chút rồi thử lại nhé."}, status_code=429,
                                headers={"Retry-After": "30"})
    else:
        limiter = None

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            if request.method in ("POST", "PUT", "PATCH"):
                length = request.headers.get("content-length")
                if length is None:
                    return JSONResponse({"detail": "Thiếu độ dài nội dung yêu cầu."}, status_code=411)
                if not length.isdigit() or int(length) > cfg.max_body:
                    return JSONResponse({"detail": "Yêu cầu quá lớn."}, status_code=413)
            if cfg.access_code and path not in OPEN_PATHS and request.method != "OPTIONS":
                given = request.headers.get("x-access-code", "")
                if not hmac.compare_digest(given.encode(), cfg.access_code.encode()):
                    return JSONResponse({"detail": "Cần mã truy cập."}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            # The built frontend: hashed assets never change; the page itself is checked each time.
            response.headers["Cache-Control"] = ("public, max-age=31536000, immutable" if path.startswith("/assets/")
                                                 else "no-cache")
            response.headers["Content-Security-Policy"] = CSP
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    if cfg.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origins), allow_methods=["GET", "POST"],
                           allow_headers=["Content-Type", "X-Access-Code"])

    @app.exception_handler(DatabaseUnavailable)
    async def no_database(request: Request, exc: DatabaseUnavailable):
        return JSONResponse({"detail": "Dữ liệu chưa sẵn sàng."}, status_code=503)

    # ------------------------------------------------------------ helpers
    def app_data(request: Request) -> AppData:
        return load_data(request.app)

    def parse(d: AppData, plan: dict) -> tuple[PlanState, list[str]]:
        try:
            return plan_file.load(json.dumps(plan), d.known())
        except plan_file.PlanFileError as e:
            raise HTTPException(422, str(e)) from None

    def dump(d: AppData, state: PlanState) -> dict:
        return json.loads(plan_file.dump(state, d.admission_year))

    # ------------------------------------------------------------ routes
    @app.get("/api/health")
    def health(request: Request):
        st = request.app.state
        return {"ok": True, "data": st.data is not None, **({"problem": st.problem} if st.problem else {})}
    if limiter:
        limiter.exempt(health)

    @app.get("/api/meta")
    def meta(request: Request):
        return views.meta(app_data(request))

    @app.get("/api/catalog")
    def catalog(request: Request):
        return views.catalog(app_data(request))

    @app.get("/api/plan/new")
    def plan_new(request: Request):
        d = app_data(request)
        return dump(d, PlanState())

    @app.post("/api/plan/normalize")
    def plan_normalize(request: Request, body: PlanBody):
        """Check a plan (a loaded file): the plan as the server reads it, and what was dropped or fixed."""
        d = app_data(request)
        state, warnings = parse(d, body.plan)
        return {"plan": dump(d, state), "warnings": warnings}

    @app.get("/api/majors/search")
    def majors_search(request: Request, q: str = Query(max_length=100)):
        return major_info.search(app_data(request), q)

    @app.get("/api/majors/{code}")
    def major(request: Request, code: str):
        d = app_data(request)
        if code not in d.catalog.majors:
            raise HTTPException(404, "Không có ngành này.")
        return major_info.detail(d, code)

    @app.get("/api/majors/{code}/close")
    def major_close(request: Request, code: str, exclude: str = Query("", max_length=100)):
        d = app_data(request)
        if code not in d.catalog.majors:
            raise HTTPException(404, "Không có ngành này.")
        return views.proposed_close(d, code, {c for c in exclude.split(",") if c})

    @app.post("/api/questionnaire")
    def questionnaire(request: Request, body: QuizBody):
        return views.questionnaire(app_data(request), body.picked, body.text)

    @app.post("/api/lists/recommend")
    def lists_recommend(request: Request, body: PlanBody):
        d = app_data(request)
        state, _ = parse(d, body.plan)
        return views.recommend(d, state)

    @app.post("/api/lists/choose")
    def lists_choose(request: Request, body: ChooseBody):
        """Record the student's choice in the plan, with the three lists as recommended at that moment."""
        d = app_data(request)
        state, _ = parse(d, body.plan)
        if body.priority not in {p.value for p in Priority}:
            raise HTTPException(422, "Phương án không hợp lệ.")
        if state.missing_for_list():
            raise HTTPException(422, "Em cần nhập điểm, tỉnh/thành và hướng học 1 trước.")
        recs = d.recommend(state)
        state.recommended = list_view.snapshot(recs)
        state.list_choice = body.priority
        card = next((c for c in list_view.summary(d, state, recs).cards if c.priority.value == body.priority), None)
        return {"plan": dump(d, state), "words": {"good": card.good[:1], "bad": card.bad[:1]} if card else {}}

    @app.post("/api/lists/chosen")
    def lists_chosen(request: Request, body: PlanBody):
        d = app_data(request)
        state, _ = parse(d, body.plan)
        return views.chosen(d, state)

    @app.post("/api/wishes/explain")
    def wishes_explain(request: Request, body: ExplainBody):
        d = app_data(request)
        state, _ = parse(d, body.plan)
        out = views.explain(d, state, body.nv)
        if out is None:
            raise HTTPException(404, "Không có nguyện vọng này.")
        return out

    @app.post("/api/chat")
    def chat(request: Request, body: ChatBody):
        d = app_data(request)
        state, _ = parse(d, body.plan)
        reply = handle(body.message, d.chat_context(state, d.list_for(state)), d.classifier)
        return views.chat_reply(d, state, reply)

    @app.post("/api/changes/apply")
    def changes_apply(request: Request, body: ApplyBody):
        """Apply the changes the student confirmed. 'undo' is the browser's own (it keeps the earlier plans)."""
        d = app_data(request)
        state, _ = parse(d, body.plan)
        try:
            items = [views.item_from_json(i) for i in body.items]
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        res = d.apply_items(state, items)
        return {"plan": dump(d, res.state), "done": res.done, "errors": res.errors, "diff": res.diff,
                "changed": res.applied}

    # ------------------------------------------------------------ the built frontend
    dist = cfg.web_dist
    if dist is not None and (dist / "index.html").is_file():
        index = dist / "index.html"
        root = dist.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Không tìm thấy.")
            target = (dist / path).resolve() if path else index
            if path and target.is_file() and root in target.parents:
                return FileResponse(target)
            if path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
                raise HTTPException(404, "Không tìm thấy.")     # a missing file is not a page
            return FileResponse(index)         # the single-page app decides what to show

    return app
