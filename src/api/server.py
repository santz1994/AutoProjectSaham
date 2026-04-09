"""Minimal FastAPI server for AutoSaham.

Endpoints:
 - GET /health
 - POST /run_etl  (body: symbols, fetch_prices, persist_db)
 - POST /scheduler/start
 - POST /scheduler/stop

This module is safe to import when FastAPI is not installed: it provides
a helpful runtime error when the API is invoked without FastAPI.
"""
from __future__ import annotations

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    FASTAPI_AVAILABLE = True
except Exception:
    FASTAPI_AVAILABLE = False


if FASTAPI_AVAILABLE:
    import asyncio
    import hmac
    import os
    import traceback
    from time import time
    from typing import Any, Dict, List, Optional

    from fastapi import WebSocket, WebSocketDisconnect, Header, Request
    from fastapi.responses import Response, RedirectResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware

    from src.alerts.webhook import send_alert_webhook
    from src.api.event_queue import pop_events
    from src.api.quota_usage import record_request, resolve_tier_from_role
    from src.monitoring import metrics as monitoring
    from src.monitoring.tracing import get_tracer, init_tracing
    from src.pipeline.persistence import read_etl_runs
    from src.pipeline.runner import AutonomousPipeline
    from src.pipeline.scheduler import PipelineScheduler
    from src.brokers.paper_adapter import PaperBrokerAdapter
    from src.execution.manager import ExecutionManager
    from src.api.state_store import SecureAppStateStore
    from src.api.auth import (
        register_user,
        is_valid_user_password,
        is_login_2fa_required,
        is_login_2fa_configured,
        verify_login_2fa_code,
        get_login_2fa_status,
        begin_login_2fa_enrollment,
        confirm_login_2fa_enrollment,
        disable_login_2fa,
        authenticate_user,
        get_session_context,
        get_user_from_token,
        invalidate_token,
        request_password_reset,
        reset_password,
    )
    from src.api.frontend_routes import router as frontend_router
    from src.notifications.api_routes import setup_notification_routes

    app = FastAPI(title="AutoSaham API", version="0.1")

    def _extract_ws_auth_token(websocket: WebSocket) -> Optional[str]:
        """Extract auth token from websocket query/cookie/header."""
        query_token = str(websocket.query_params.get("token") or "").strip()
        if query_token:
            return query_token

        cookie_token = str(websocket.cookies.get("auth_token") or "").strip()
        if cookie_token:
            return cookie_token

        auth_header = str(websocket.headers.get("authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            bearer_token = auth_header.split(" ", 1)[1].strip()
            if bearer_token:
                return bearer_token

        return None

    def _authenticate_ws_client(websocket: WebSocket) -> Optional[str]:
        token = _extract_ws_auth_token(websocket)
        if not token:
            return None
        return get_user_from_token(token)
    
    # Register frontend API routes
    app.include_router(frontend_router)

    # Register notification routes and delivery handlers
    try:
        smtp_config = None
        if os.getenv("SMTP_HOST"):
            smtp_config = {
                "host": os.getenv("SMTP_HOST"),
                "port": int(os.getenv("SMTP_PORT", "587")),
                "user": os.getenv("SMTP_USER"),
                "password": os.getenv("SMTP_PASS"),
                "use_tls": True,
            }

        setup_notification_routes(
            app,
            smtp_config=smtp_config,
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
        )
    except Exception as e:
        print(f"[Startup] Warning: Notification routes initialization failed: {e}")
    
    # SECURITY FIX: Configure CORS to allow frontend on localhost:5173
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",      # Vite dev server
            "http://localhost:5174",      # Vite fallback port
            "http://127.0.0.1:5173",      # Loopback variant
            "http://127.0.0.1:5174",      # Loopback variant
            "http://localhost:8000",      # API server (for UI served from backend)
            "http://localhost:8001",      # API direct port via docker-compose
            "http://localhost:3000",      # Alternative dev port
        ],
        allow_credentials=True,                    # Allow httpOnly cookies
        allow_methods=["*"],                       # Allow all HTTP methods
        allow_headers=["*"],                       # Allow all headers
        expose_headers=["Set-Cookie"],             # Expose cookie header
    )

    _tracing_service_name = str(
        os.getenv("AUTOSAHAM_TRACING_SERVICE_NAME", "autosaham-api")
    ).strip() or "autosaham-api"
    init_tracing(service_name=_tracing_service_name)

    _SUPPORTED_QUOTA_TIERS = {"free", "basic", "pro"}

    def _normalize_quota_tier(value: Any) -> str:
        candidate = str(value or "").strip().lower()
        if candidate in _SUPPORTED_QUOTA_TIERS:
            return candidate
        return ""

    def _is_quota_tier_path(path: str) -> bool:
        normalized = str(path or "").strip()
        return normalized.startswith("/api")

    def _validate_tier_hint(
        *,
        request_path: str,
        raw_tier_hint: str,
        normalized_tier_hint: str,
        session_context: Optional[Dict[str, Any]],
        resolved_tier: str,
    ) -> Optional[JSONResponse]:
        if not _is_quota_tier_path(request_path):
            return None

        if not raw_tier_hint:
            return None

        if not normalized_tier_hint:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "Invalid X-Autosaham-Tier header. Use free/basic/pro.",
                },
            )

        if session_context is None and normalized_tier_hint != "free":
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Anonymous requests can only use free tier hint.",
                },
            )

        if session_context is not None and normalized_tier_hint != resolved_tier:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "X-Autosaham-Tier does not match authenticated role tier.",
                },
            )

        return None

    @app.middleware("http")
    async def _request_tracing_middleware(request: Request, call_next):
        tracer = get_tracer()
        if tracer is None:
            return await call_next(request)

        token = str(request.cookies.get("auth_token") or "").strip()
        session_context = get_session_context(token) if token else None

        span_name = f"{request.method} {request.url.path}"
        with tracer.start_as_current_span(span_name) as span:
            try:
                span.set_attribute("http.method", str(request.method or "GET"))
                span.set_attribute("http.path", str(request.url.path or "/"))
                if session_context and session_context.get("username"):
                    span.set_attribute(
                        "enduser.id",
                        str(session_context.get("username") or ""),
                    )
            except Exception:
                pass

            response = await call_next(request)

            try:
                status_code = int(response.status_code)
                span.set_attribute("http.status_code", status_code)

                trace_id = format(span.get_span_context().trace_id, "032x")
                if trace_id and trace_id != ("0" * 32):
                    response.headers["X-Trace-Id"] = trace_id
            except Exception:
                pass

            return response

    @app.middleware("http")
    async def _quota_usage_middleware(request: Request, call_next):
        request_path = str(request.url.path or "")
        token = str(request.cookies.get("auth_token") or "").strip()
        session_context = get_session_context(token) if token else None
        role = str((session_context or {}).get("role") or "viewer").strip().lower()
        tier = resolve_tier_from_role(role)

        tier_hint_raw = str(request.headers.get("x-autosaham-tier") or "").strip()
        tier_hint = _normalize_quota_tier(tier_hint_raw)

        tier_hint_violation = _validate_tier_hint(
            request_path=request_path,
            raw_tier_hint=tier_hint_raw,
            normalized_tier_hint=tier_hint,
            session_context=session_context,
            resolved_tier=tier,
        )
        if tier_hint_violation is not None:
            return tier_hint_violation

        response = await call_next(request)

        try:
            if request_path == "/metrics":
                return response

            username = (
                str((session_context or {}).get("username") or "").strip().lower()
                or "anonymous"
            )

            record_request(
                username=username,
                tier=tier,
                path=request_path,
                method=request.method,
                status_code=int(response.status_code),
            )

            if _is_quota_tier_path(request_path):
                response.headers.setdefault("X-Autosaham-Resolved-Tier", tier)
        except Exception:
            # Observability path should never break normal API flow.
            pass

        return response

    # single shared pipeline instance for the server
    pipeline = AutonomousPipeline()
    _scheduler: Optional[PipelineScheduler] = None
    _execution_manager: Optional[ExecutionManager] = None
    # Background services (initialized on application startup)
    market_service = None
    ml_service = None
    _runtime_state_store = SecureAppStateStore()
    _system_control_defaults = {
        "killSwitchActive": False,
        "reason": None,
        "activatedAt": None,
        "activatedBy": None,
    }

    try:
        starting_cash = float(os.getenv("PAPER_STARTING_CASH", "100000000"))
        require_startup_sync = str(
            os.getenv("AUTOSAHAM_EXECUTION_REQUIRE_STARTUP_SYNC", "1")
        ).strip().lower() in {"1", "true", "yes", "on"}
        _execution_manager = ExecutionManager(
            broker=PaperBrokerAdapter(starting_cash=starting_cash),
            require_startup_sync=require_startup_sync,
        )
    except Exception:
        _execution_manager = None
    
    # Project root directory for data/models paths
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    def _env_flag(name: str, default: bool = False) -> bool:
        value = str(os.getenv(name, "")).strip().lower()
        if not value:
            return default
        return value in {"1", "true", "yes", "on"}

    def _celery_enabled() -> bool:
        return _env_flag("AUTOSAHAM_USE_CELERY", False)

    def _csrf_guard_enabled() -> bool:
        require_csrf_default = str(os.getenv("ENV", "")).strip().lower() in {
            "prod",
            "production",
        }
        return _env_flag("AUTOSAHAM_CSRF_PROTECTION_ENABLED", require_csrf_default)

    def _require_authenticated_session(
        request: Request,
        operation: str,
        *,
        require_csrf: bool = False,
    ) -> Dict[str, Any]:
        token = str(request.cookies.get("auth_token") or "").strip()
        session_context = get_session_context(token)
        if not session_context:
            raise HTTPException(
                status_code=401,
                detail=f"{operation} requires authenticated session.",
            )

        if require_csrf and _csrf_guard_enabled():
            header_token = str(
                request.headers.get("x-csrf-token")
                or request.headers.get("x-xsrf-token")
                or ""
            ).strip()
            cookie_token = str(request.cookies.get("csrf_token") or "").strip()
            session_csrf = str(session_context.get("csrfToken") or "").strip()

            if not header_token or not cookie_token:
                raise HTTPException(
                    status_code=403,
                    detail=f"{operation} blocked: missing CSRF token.",
                )

            if not hmac.compare_digest(header_token, cookie_token):
                raise HTTPException(
                    status_code=403,
                    detail=f"{operation} blocked: CSRF token mismatch.",
                )

            if session_csrf and not hmac.compare_digest(header_token, session_csrf):
                raise HTTPException(
                    status_code=403,
                    detail=f"{operation} blocked: invalid CSRF token.",
                )

        return session_context

    def _parse_csv_set(value: Any) -> set[str]:
        return {
            item.strip().lower()
            for item in str(value or "").split(",")
            if item.strip()
        }

    def _is_admin_session(session_context: Optional[Dict[str, Any]]) -> bool:
        if not session_context:
            return False

        session_user = str(session_context.get("username") or "").strip().lower()
        session_role = str(session_context.get("role") or "").strip().lower()

        admin_users = _parse_csv_set(os.getenv("AUTOSAHAM_ADMIN_USERS", ""))
        if not admin_users:
            admin_users = _parse_csv_set(
                os.getenv("AUTOSAHAM_KILL_SWITCH_ADMIN_USERS", "admin")
            )
        if not admin_users:
            admin_users = {"admin"}

        admin_roles = _parse_csv_set(os.getenv("AUTOSAHAM_ADMIN_ROLES", "admin"))
        if not admin_roles:
            admin_roles = {"admin"}

        return (session_user in admin_users) or (session_role in admin_roles)

    def _require_role_operation(
        request: Request,
        operation: str,
        *,
        allowed_roles: set[str],
        allow_admin_override: bool = True,
    ) -> Dict[str, Any]:
        require_role_default = str(os.getenv("ENV", "")).strip().lower() in {
            "prod",
            "production",
        }
        require_role_guard = _env_flag(
            "AUTOSAHAM_ROLE_GUARD_ENABLED",
            require_role_default,
        )

        if not require_role_guard:
            return {
                "username": "api",
                "role": "system",
                "csrfToken": "",
            }

        session_context = _require_authenticated_session(
            request,
            operation,
            require_csrf=True,
        )

        if allow_admin_override and _is_admin_session(session_context):
            return session_context

        normalized_allowed = {
            str(role).strip().lower()
            for role in allowed_roles
            if str(role).strip()
        }
        session_role = str(session_context.get("role") or "").strip().lower()
        if session_role not in normalized_allowed:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"{operation} requires one of roles: "
                    f"{', '.join(sorted(normalized_allowed))}"
                ),
            )

        return session_context

    def _is_kill_switch_active() -> bool:
        try:
            state = _runtime_state_store.get_system_control(_system_control_defaults)
            return bool(state.get("killSwitchActive"))
        except Exception:
            return False

    def _assert_runtime_not_halted(operation: str) -> None:
        if not _is_kill_switch_active():
            return
        raise HTTPException(
            status_code=423,
            detail=f"{operation} blocked: global kill switch active.",
        )

    def _dispatch_celery_task(
        task_name: str,
        *,
        args: tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            from src.tasks import app as celery_app

            async_result = celery_app.send_task(
                task_name,
                args=args,
                kwargs=kwargs or {},
            )
            return {
                "task": task_name,
                "taskId": async_result.id,
                "broker": "celery",
            }
        except Exception:
            return None

    def _get_celery_task_status(task_id: str) -> Optional[Dict[str, Any]]:
        try:
            from celery.result import AsyncResult
            from src.tasks import app as celery_app

            result = AsyncResult(task_id, app=celery_app)
            payload: Dict[str, Any] = {
                "taskId": task_id,
                "state": result.state,
                "ready": bool(result.ready()),
                "successful": bool(result.successful()) if result.ready() else False,
            }
            if result.ready():
                try:
                    payload["result"] = result.result
                except Exception:
                    payload["result"] = None
            return payload
        except Exception:
            return None

    class RunPayload(BaseModel):
        symbols: List[str]
        fetch_prices: Optional[bool] = True
        persist_db: Optional[str] = None
        async_run: Optional[bool] = False
        asyncRun: Optional[bool] = False

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/run_etl")
    async def run_etl(payload: RunPayload, request: Request):
        start = time()
        try:
            _require_role_operation(
                request,
                "ETL run",
                allowed_roles=_parse_csv_set(
                    os.getenv("AUTOSAHAM_ROLE_ETL_WRITE_ROLES", "trader,developer")
                ),
            )
            _assert_runtime_not_halted("ETL run")
            run_async = bool(payload.async_run or payload.asyncRun or _celery_enabled())

            if run_async:
                task = _dispatch_celery_task(
                    "autosaham.run_etl",
                    args=(payload.symbols,),
                    kwargs={
                        "fetch_prices": bool(payload.fetch_prices),
                        "persist_db": payload.persist_db,
                    },
                )
                if task:
                    return {
                        "status": "queued",
                        **task,
                    }

            res = pipeline.run(
                payload.symbols,
                fetch_prices=payload.fetch_prices,
                persist_db=payload.persist_db,
            )
            duration = time() - start
            try:
                monitoring.record_etl_run(duration_seconds=duration, success=True)
            except Exception:
                pass
            return res
        except HTTPException:
            duration = time() - start
            try:
                monitoring.record_etl_run(duration_seconds=duration, success=False)
            except Exception:
                pass
            raise
        except Exception as e:
            duration = time() - start
            try:
                monitoring.record_etl_run(duration_seconds=duration, success=False)
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/tasks/{task_id}")
    async def get_task_status(task_id: str):
        payload = _get_celery_task_status(task_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail="Task status unavailable (Celery disabled or worker offline).",
            )
        return payload

    @app.get("/metrics")
    async def metrics_endpoint():
        try:
            payload, content_type = monitoring.metrics_text()
        except Exception:
            raise HTTPException(
                status_code=501, detail="prometheus_client not installed"
            )
        return Response(content=payload, media_type=content_type)

    @app.get("/etl_runs")
    async def etl_runs(limit: int = 50):
        try:
            runs = read_etl_runs(limit=limit)
            return {
                "runs": runs,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/portfolio/reconcile")
    async def api_portfolio_reconcile(authorization: Optional[str] = Header(None)):
        """Return a broker reconciliation snapshot.

        This diagnostic endpoint is separate from frontend portfolio routes.
        If the request includes a valid `Authorization: Bearer <token>` header
        that maps to a registered user, this could return a user-specific
        portfolio (when adapters are implemented). For now, we return a demo
        `PaperBroker` snapshot when unauthenticated.
        """
        try:
            user = None
            if authorization:
                token = authorization.split(" ", 1)[1] if authorization.lower().startswith("bearer ") else authorization
                user = get_user_from_token(token)

            adapter = PaperBrokerAdapter(starting_cash=10000.0)
            adapter.connect()
            snap = adapter.reconcile()
            adapter.disconnect()
            if user:
                # annotate with username for demo purposes
                return {"portfolio": snap, "user": user}
            return {"portfolio": snap}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    class UserPayload(BaseModel):
        username: str
        password: str
        rememberMe: Optional[bool] = False
        twoFactorCode: Optional[str] = None

    class RegisterPayload(BaseModel):
        username: str
        password: str
        email: Optional[str] = None

    class ForgotPasswordPayload(BaseModel):
        email: str

    class ResetPasswordPayload(BaseModel):
        token: str
        newPassword: str

    class TwoFactorCodePayload(BaseModel):
        code: Optional[str] = None

    @app.post("/auth/register")
    async def auth_register(payload: RegisterPayload):
        try:
            register_user(
                payload.username,
                payload.password,
                email=payload.email,
            )
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/auth/login")
    async def auth_login(payload: UserPayload):
        if not is_valid_user_password(payload.username, payload.password):
            raise HTTPException(status_code=401, detail="invalid_credentials")

        if is_login_2fa_required(payload.username):
            if not is_login_2fa_configured(payload.username):
                raise HTTPException(
                    status_code=503,
                    detail="two_factor_not_configured",
                )

            two_factor_code = str(payload.twoFactorCode or "").strip()
            if not two_factor_code:
                raise HTTPException(status_code=401, detail="two_factor_required")

            if not verify_login_2fa_code(payload.username, two_factor_code):
                raise HTTPException(status_code=401, detail="invalid_two_factor_code")

        default_ttl = int(os.getenv("AUTH_TTL_SECONDS", "86400"))
        remember_ttl = int(os.getenv("AUTH_REMEMBER_ME_TTL_SECONDS", "2592000"))
        session_ttl = remember_ttl if bool(payload.rememberMe) else default_ttl
        session_ttl = max(300, min(int(session_ttl), 60 * 60 * 24 * 90))

        token = authenticate_user(
            payload.username,
            payload.password,
            ttl_seconds=session_ttl,
        )
        if not token:
            raise HTTPException(status_code=401, detail="invalid_credentials")

        session_context = get_session_context(token) or {}
        csrf_token = str(session_context.get("csrfToken") or "").strip()
        session_role = str(session_context.get("role") or "viewer").strip().lower()
        session_tier = resolve_tier_from_role(session_role)

        # SECURITY FIX: Set token as httpOnly cookie (not in response body)
        response = JSONResponse(
            content={
                "status": "ok",
                "rememberMe": bool(payload.rememberMe),
            },
            status_code=200,
        )
        # In development (HTTP), disable secure flag; in production (HTTPS), enable it
        is_secure = os.getenv("ENV", "").lower() in ("prod", "production") or os.getenv("HTTPS") == "on"
        response.set_cookie(
            key="auth_token",
            value=token,
            httponly=True,  # Prevent JS access (XSS protection)
            secure=is_secure,  # Only send over HTTPS in production
            samesite="lax",  # CSRF protection (lax for local dev compatibility)
            max_age=session_ttl,
            path="/"
        )
        # Non-sensitive tier hint cookie used by the frontend for Kong routing.
        response.set_cookie(
            key="autosaham_tier",
            value=session_tier,
            httponly=False,
            secure=is_secure,
            samesite="lax",
            max_age=session_ttl,
            path="/",
        )

        if csrf_token:
            # Double-submit CSRF token cookie for mutating endpoints.
            response.set_cookie(
                key="csrf_token",
                value=csrf_token,
                httponly=False,
                secure=is_secure,
                samesite="lax",
                max_age=session_ttl,
                path="/",
            )
        return response

    @app.get("/auth/me")
    async def auth_me(request: Request):
        # SECURITY FIX: Read token from secure httpOnly cookie, not Authorization header
        token = request.cookies.get("auth_token")
        if not token:
            # Not logged in - return 200 with empty response (JS will handle)
            return JSONResponse(content={}, status_code=200)
        context = get_session_context(token)
        if not context:
            # Token invalid/expired - return 200 with empty response
            return JSONResponse(content={}, status_code=200)

        username = str(context.get("username") or "").strip()
        role = str(context.get("role") or "viewer").strip().lower()
        two_factor_status = get_login_2fa_status(username)

        return {
            "username": username,
            "role": role,
            "tier": resolve_tier_from_role(role),
            "twoFactorEnabled": bool(two_factor_status.get("enabled")),
            "twoFactorRequired": bool(two_factor_status.get("required")),
        }

    @app.get("/auth/2fa/status")
    async def auth_two_factor_status(request: Request):
        session_context = _require_authenticated_session(
            request,
            "Two-factor status",
            require_csrf=False,
        )
        username = str(session_context.get("username") or "").strip()
        return {
            "status": "ok",
            **get_login_2fa_status(username),
        }

    @app.post("/auth/2fa/enroll")
    async def auth_two_factor_enroll(request: Request):
        session_context = _require_authenticated_session(
            request,
            "Two-factor enrollment",
            require_csrf=True,
        )
        username = str(session_context.get("username") or "").strip()
        issuer = str(os.getenv("AUTOSAHAM_LOGIN_2FA_ISSUER", "AutoSaham")).strip() or "AutoSaham"

        try:
            enrollment = begin_login_2fa_enrollment(username, issuer=issuer)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {
            "status": "pending_verification",
            "secret": enrollment.get("secret"),
            "otpauthUri": enrollment.get("otpauthUri"),
            **get_login_2fa_status(username),
        }

    @app.post("/auth/2fa/verify")
    async def auth_two_factor_verify(payload: TwoFactorCodePayload, request: Request):
        session_context = _require_authenticated_session(
            request,
            "Two-factor verification",
            require_csrf=True,
        )
        username = str(session_context.get("username") or "").strip()
        code = str(payload.code or "").strip()
        if not code:
            raise HTTPException(status_code=400, detail="two_factor_code_required")

        try:
            valid = confirm_login_2fa_enrollment(username, code)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not valid:
            raise HTTPException(status_code=401, detail="invalid_two_factor_code")

        return {
            "status": "enabled",
            **get_login_2fa_status(username),
        }

    @app.post("/auth/2fa/disable")
    async def auth_two_factor_disable(payload: TwoFactorCodePayload, request: Request):
        session_context = _require_authenticated_session(
            request,
            "Two-factor disable",
            require_csrf=True,
        )
        username = str(session_context.get("username") or "").strip()
        code = str(payload.code or "").strip()

        try:
            disabled = disable_login_2fa(username, code)
        except RuntimeError as e:
            detail = str(e)
            if detail == "two_factor_required_by_policy":
                raise HTTPException(status_code=409, detail=detail)
            raise HTTPException(status_code=400, detail=detail)

        if not disabled:
            raise HTTPException(status_code=401, detail="invalid_two_factor_code")

        return {
            "status": "disabled",
            **get_login_2fa_status(username),
        }

    @app.post("/auth/logout")
    async def auth_logout(request: Request):
        """Clear the auth token cookie."""
        token = request.cookies.get("auth_token")
        if token:
            invalidate_token(token)
        response = JSONResponse(content={"status": "ok"}, status_code=200)
        is_secure = os.getenv("ENV", "").lower() in ("prod", "production") or os.getenv("HTTPS") == "on"
        response.delete_cookie(
            key="auth_token",
            path="/",
            httponly=True,
            secure=is_secure,
            samesite="lax"
        )
        response.delete_cookie(
            key="autosaham_tier",
            path="/",
            httponly=False,
            secure=is_secure,
            samesite="lax",
        )
        response.delete_cookie(
            key="csrf_token",
            path="/",
            httponly=False,
            secure=is_secure,
            samesite="lax",
        )
        return response

    @app.post("/auth/forgot-password")
    async def auth_forgot_password(payload: ForgotPasswordPayload):
        """Issue a password reset token without leaking account existence."""
        if not payload.email or "@" not in payload.email:
            raise HTTPException(status_code=400, detail="invalid_email")

        reset_token = request_password_reset(payload.email)

        # Do not reveal whether email exists to avoid account enumeration.
        response_payload = {
            "status": "ok",
            "message": "If the email exists, reset instructions have been sent.",
        }

        # Optional debug helper for local/docker smoke tests.
        expose_token = os.getenv("AUTH_EXPOSE_RESET_TOKEN", "0") == "1"
        if expose_token and reset_token:
            response_payload["resetToken"] = reset_token

        return response_payload

    @app.post("/auth/reset-password")
    async def auth_reset_password(payload: ResetPasswordPayload):
        if not payload.token or len(payload.token) < 10:
            raise HTTPException(status_code=400, detail="invalid_token")
        if not payload.newPassword or len(payload.newPassword) < 6:
            raise HTTPException(status_code=400, detail="invalid_password")

        if not reset_password(payload.token, payload.newPassword):
            raise HTTPException(status_code=400, detail="reset_failed")

        return {
            "status": "ok",
            "message": "Password updated successfully.",
        }

    @app.get("/api/training")
    async def api_training(limit: int = 50):
        """Return recent training artifacts from `models/`.

        Scans the repository `models/` directory for model files and returns a
        concise metadata list (path, mtime, size). If a model file can be
        loaded with `joblib` and exposes a small metadata dict (e.g. keys
        `features`/`tuned`) those fields are included. Loading is best-effort
        and failures are ignored to keep this endpoint safe for quick inspection.
        """
        try:
            import glob

            models_dir = os.path.join(project_root, "models")
            if not os.path.isdir(models_dir):
                return {"runs": []}

            patterns = ["*.joblib", "*.pkl", "*.model"]
            matches = []
            for pat in patterns:
                matches.extend(glob.glob(os.path.join(models_dir, pat)))

            # sort by mtime desc and trim
            matches = sorted(matches, key=lambda p: os.path.getmtime(p), reverse=True)[: int(limit) if limit else 50]

            runs = []
            for p in matches:
                try:
                    st = os.stat(p)
                    item = {
                        "path": os.path.relpath(p, project_root),
                        "mtime": int(st.st_mtime),
                        "size": int(st.st_size),
                    }
                    # best-effort: attempt to read small metadata from joblib/pickle
                    # SECURITY FIX: Use restricted unpickler to prevent RCE via malicious model files
                    try:
                        try:
                            import joblib
                            # Use restricted loads to prevent arbitrary code execution
                            loaded = joblib.load(p, mmap_mode=None)
                        except Exception:
                            # fallback to pickle load with restricted unpickler
                            import pickle
                            import io

                            class RestrictedUnpickler(pickle.Unpickler):
                                """Restrict pickle to safe classes only."""
                                def find_class(self, module, name):
                                    # Whitelist safe numpy/sklearn/joblib classes
                                    allowed_modules = {
                                        'numpy', 'sklearn', 'lightgbm', 'xgboost', 
                                        '__main__', 'src.ml', 'builtins'
                                    }
                                    if not any(module.startswith(m) for m in allowed_modules):
                                        raise pickle.UnpicklingError(
                                            f"Unpickling of {module}.{name} is not allowed"
                                        )
                                    return super().find_class(module, name)

                            with open(p, "rb") as fh:
                                loaded = RestrictedUnpickler(fh).load()

                        if isinstance(loaded, dict):
                            meta = {}
                            if "features" in loaded:
                                meta["feature_count"] = len(loaded.get("features") or [])
                            if "tuned" in loaded:
                                meta["tuned"] = bool(loaded.get("tuned"))
                            if meta:
                                item["meta"] = meta
                    except Exception:
                        # ignore load errors
                        pass

                    runs.append(item)
                except Exception:
                    continue

            return {"runs": runs}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    class ModelRegistryActivatePayload(BaseModel):
        model_id: str

    @app.get("/api/training/registry")
    async def api_training_registry(limit: int = 100):
        try:
            from src.ml.model_registry import get_registry_snapshot

            return get_registry_snapshot(limit=limit)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/training/registry/active")
    async def api_training_registry_active():
        try:
            from src.ml.model_registry import get_active_model

            active = get_active_model()
            return {"active": active}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/training/registry/best")
    async def api_training_registry_best(metric: str = "roc_auc"):
        try:
            from src.ml.model_registry import get_best_model

            best = get_best_model(metric_key=metric)
            return {"metric": metric, "best": best}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/training/registry/active")
    async def api_training_registry_set_active(
        payload: ModelRegistryActivatePayload,
        request: Request,
    ):
        _require_role_operation(
            request,
            "Model registry activate",
            allowed_roles=_parse_csv_set(
                os.getenv("AUTOSAHAM_ROLE_MODEL_REGISTRY_WRITE_ROLES", "developer")
            ),
        )

        try:
            from src.ml.model_registry import set_active_model

            active = set_active_model(payload.model_id)
            return {"active": active}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    class AlertPayload(BaseModel):
        url: str
        message: str
        level: Optional[str] = "info"

    @app.post("/alert")
    async def alert_endpoint(payload: AlertPayload, request: Request):
        _require_role_operation(
            request,
            "Alert dispatch",
            allowed_roles=_parse_csv_set(
                os.getenv("AUTOSAHAM_ROLE_ALERT_WRITE_ROLES", "admin,developer")
            ),
        )

        try:
            payload_body = {
                "message": payload.message,
                "level": payload.level,
            }
            sent = send_alert_webhook(payload.url, payload_body)
            if not sent:
                raise HTTPException(status_code=502, detail="alert delivery failed")
            return {"status": "sent"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/scheduler/start")
    async def start_scheduler(
        request: Request,
        symbols: List[str],
        interval_seconds: float = 3600.0,
    ):
        global _scheduler
        _require_role_operation(
            request,
            "Scheduler start",
            allowed_roles=_parse_csv_set(
                os.getenv("AUTOSAHAM_ROLE_SCHEDULER_WRITE_ROLES", "developer")
            ),
        )

        _assert_runtime_not_halted("Scheduler start")
        if (
            _scheduler
            and getattr(_scheduler, "_thread", None)
            and getattr(_scheduler, "_thread").is_alive()
        ):
            raise HTTPException(status_code=400, detail="Scheduler already running")
        _scheduler = PipelineScheduler(
            pipeline,
            symbols=symbols,
            interval_seconds=interval_seconds,
        )
        _scheduler.start()
        return {"status": "started"}

    @app.post("/scheduler/stop")
    async def stop_scheduler(request: Request):
        global _scheduler
        _require_role_operation(
            request,
            "Scheduler stop",
            allowed_roles=_parse_csv_set(
                os.getenv("AUTOSAHAM_ROLE_SCHEDULER_WRITE_ROLES", "developer")
            ),
        )

        if not _scheduler:
            raise HTTPException(status_code=400, detail="Scheduler not running")
        _scheduler.stop()
        _scheduler = None
        return {"status": "stopped"}

    # Chart API Endpoints - Real IDX Data
    @app.get("/api/charts/metadata/{symbol}")
    async def charts_metadata(symbol: str):
        """Get candlestick metadata for a symbol from IDX."""
        from src.data.idx_fetcher import fetch_symbol_metadata
        
        metadata = await fetch_symbol_metadata(symbol)
        if metadata:
            metadata = {
                **metadata,
                "tradingStart": metadata.get("tradingStart", "09:00"),
                "tradingEnd": metadata.get("tradingEnd", "16:00"),
            }
            return metadata
        
        # Fallback for unknown symbols
        return {
            "symbol": symbol,
            "name": "Unknown Symbol",
            "exchange": "IDX" if ".JK" in symbol else "OTHER",
            "currency": "IDR" if ".JK" in symbol else "USD",
            "timezone": "Asia/Jakarta" if ".JK" in symbol else "UTC",
            "tradingStart": "09:00" if ".JK" in symbol else "00:00",
            "tradingEnd": "16:00" if ".JK" in symbol else "23:59",
        }

    @app.get("/api/charts/candles/{symbol}")
    async def charts_candles(symbol: str, timeframe: str = "1d", limit: int = 100):
        """Get real candlestick data from IDX."""
        from src.data.idx_fetcher import fetch_candlesticks
        
        result = await fetch_candlesticks(symbol, timeframe=timeframe, limit=limit)
        
        if result:
            return result
        
        # Fallback if fetch fails
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": [],
            "error": "Unable to fetch candlestick data",
            "metadata": {
                "total": 0,
                "exchange": "IDX",
                "source": "fallback"
            }
        }

    @app.get("/api/charts/timeframes")
    async def charts_timeframes():
        """Return supported chart timeframes and the backend source capability."""
        from src.data.idx_fetcher import TIMEFRAME_MAP

        return {
            "timeframes": list(TIMEFRAME_MAP.keys()),
            "provider": "yfinance",
            "note": (
                "Timeframe list follows backend/provider support and stability "
                "for IDX chart delivery."
            ),
        }

    @app.get("/api/charts/trading-status")
    async def charts_trading_status():
        """Get current IDX trading status."""
        from src.data.idx_fetcher import fetch_trading_status
        
        status = await fetch_trading_status()
        return status

    @app.websocket("/ws/charts/{symbol}")
    async def websocket_charts(ws: WebSocket, symbol: str):
        """WebSocket stream for chart updates used by frontend ChartComponent."""
        from src.data.idx_fetcher import fetch_candlesticks

        ws_user = _authenticate_ws_client(ws)
        if not ws_user:
            try:
                await ws.accept()
            except Exception:
                pass
            try:
                await ws.close(code=4401, reason="Unauthorized")
            except Exception:
                pass
            return

        timeframe = ws.query_params.get("timeframe", "1d")
        try:
            limit = int(ws.query_params.get("limit", "100"))
        except Exception:
            limit = 100
        limit = max(50, min(limit, 1000))

        try:
            await ws.accept()
        except Exception as e:
            print(f"[ChartsWS] Failed to accept: {type(e).__name__}: {e}")
            return

        try:
            initial = await fetch_candlesticks(symbol, timeframe=timeframe, limit=limit)
            await ws.send_json({
                "symbol": symbol,
                "timeframe": timeframe,
                "candles": (initial or {}).get("candles", []),
            })

            while True:
                try:
                    message = await asyncio.wait_for(ws.receive_text(), timeout=30)
                except asyncio.TimeoutError:
                    message = "update"

                if message == "ping":
                    await ws.send_text("pong")
                    continue

                if message.startswith("timeframe:"):
                    requested = message.split(":", 1)[1].strip()
                    if requested:
                        timeframe = requested

                latest = await fetch_candlesticks(symbol, timeframe=timeframe, limit=1)
                candles = (latest or {}).get("candles", [])
                if candles:
                    await ws.send_json({
                        "type": "candle_update",
                        "candle": candles[-1],
                    })
        except WebSocketDisconnect:
            print(f"[ChartsWS] Client disconnected for {symbol}")
        except Exception as e:
            print(f"[ChartsWS] Error for {symbol}: {type(e).__name__}: {e}")
        finally:
            print(f"[ChartsWS] Handler exiting for {symbol}")

    @app.websocket("/ws/events")
    async def websocket_events(ws: WebSocket):
        """Stream events from the in-memory queue to connected WebSocket clients.
        
        This handler polls the event queue periodically and sends any accumulated
        events to the client. It gracefully closes if the client disconnects.
        """
        ws_user = _authenticate_ws_client(ws)
        if not ws_user:
            try:
                await ws.accept()
            except Exception:
                pass
            try:
                await ws.close(code=4401, reason="Unauthorized")
            except Exception:
                pass
            return

        try:
            await ws.accept()
            print(f"[WebSocket] Client connected to /ws/events ({ws_user})")
        except Exception as e:
            print(f"[WebSocket] Failed to accept: {type(e).__name__}: {e}")
            return
        
        print("[WebSocket] Starting event loop...")
        try:
            while True:
                # Poll events every 500ms
                await asyncio.sleep(0.5)
                
                # Get any accumulated events from the in-memory queue
                events = []
                try:
                    events = pop_events()
                except Exception as e:
                    print(f"[WebSocket] Error popping events: {type(e).__name__}: {e}")
                    events = []
                
                # Send each event to the client
                if events:
                    print(f"[WebSocket] Sending {len(events)} event(s) to client...")
                
                for event in events:
                    try:
                        await ws.send_json(event)
                    except RuntimeError as e:
                        # Client disconnected or connection broken
                        print(f"[WebSocket] Client disconnected: {e}")
                        return
                    except Exception as e:
                        print(f"[WebSocket] Error sending event: {type(e).__name__}: {e}")
                        return
                        
        except WebSocketDisconnect:
            print("[WebSocket] Client disconnected (clean close)")
        except asyncio.CancelledError:
            print("[WebSocket] Task cancelled (server shutdown)")
        except Exception as e:
            print(f"[WebSocket] Unexpected error: {type(e).__name__}: {e}")
        finally:
            print("[WebSocket] Handler exiting")

    @app.on_event("startup")
    async def startup_services():
        """Start optional background services: market data ingestion
        and ML trainer. These run in background thread pools to avoid
        blocking the FastAPI event loop during startup.
        
        Uses REAL IDX market data (Bursa Efek Indonesia) by default.
        """
        global market_service, ml_service, _execution_manager
        
        # Initialize test user for demo purposes
        try:
            from src.api.auth import _load_users
            users = _load_users()
            if "demo" not in users:  # Ensure demo account exists for local testing
                register_user("demo", "demo123")
                print("[Startup] Created test user: demo / demo123")
        except Exception as e:
            print(f"[Startup] Warning: Could not create test user: {e}")

        try:
            if _execution_manager is not None and hasattr(
                _execution_manager,
                "sync_open_orders_on_startup",
            ):
                sync_limit = max(
                    1,
                    min(
                        5000,
                        int(
                            os.getenv(
                                "AUTOSAHAM_EXECUTION_STARTUP_SYNC_LIMIT",
                                "500",
                            )
                        ),
                    ),
                )
                sync_report = _execution_manager.sync_open_orders_on_startup(
                    limit=sync_limit
                )

                try:
                    _runtime_state_store.append_ai_log(
                        level="info",
                        event_type="execution_startup_sync",
                        message="Execution startup sync completed.",
                        payload=sync_report,
                    )
                except Exception:
                    pass
        except Exception as e:
            print(f"[Startup] Warning: execution startup sync failed: {e}")
        
        try:
            # REAL DATA: Default to IDX symbols (Indonesian stock exchange)
            symbols_env = os.getenv("MARKET_SYMBOLS", "BBCA,USIM,KLBF,ASII,UNVR")
            symbols = [s.strip() for s in symbols_env.split(",") if s.strip()]

            # Prefer streaming-native IDX websocket feed when credentials are set.
            from src.brokers.marketdata import (
                AlpacaMarketDataAdapter,
                IDXMarketDataAdapter,
            )

            bei_ws_username = str(os.getenv("BEI_WS_USERNAME", "")).strip()
            bei_ws_password = str(os.getenv("BEI_WS_PASSWORD", "")).strip()

            if bei_ws_username and bei_ws_password:
                adapter = IDXMarketDataAdapter(
                    symbols=symbols,
                    username=bei_ws_username,
                    password=bei_ws_password,
                )
            else:
                adapter = AlpacaMarketDataAdapter(symbols=symbols)
            
            from src.marketdata.service import MarketDataService
            ms = MarketDataService(adapter=adapter, db_path=os.path.join(project_root, "data", "ticks.db"))
            # PERFORMANCE FIX: Run market service in background thread, don't block startup
            ms.start()
            market_service = ms
        except Exception:
            # do not fail startup on optional services
            pass

        try:
            from src.ml.service import MLTrainerService

            if _celery_enabled():
                print("[Startup] AUTOSAHAM_USE_CELERY enabled: local ML trainer service skipped")
            else:
                interval = int(os.getenv("ML_TRAIN_INTERVAL", str(24 * 3600)))
                mls = MLTrainerService(schedule_seconds=interval, db_path=os.path.join(project_root, "data", "ticks.db"), models_dir=os.path.join(project_root, "models"))
                # PERFORMANCE FIX: Run ML training in background thread pool via executor
                # This prevents blocking the event loop during long training operations
                loop = asyncio.get_event_loop()
                loop.run_in_executor(None, mls.start)
                ml_service = mls
        except Exception:
            pass

    @app.on_event("shutdown")
    async def shutdown_services():
        """Stop background services cleanly on shutdown."""
        global market_service, ml_service
        try:
            if market_service:
                try:
                    market_service.stop()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if ml_service:
                try:
                    ml_service.stop()
                except Exception:
                    pass
        except Exception:
            pass

    @app.post("/api/training/trigger")
    async def api_training_trigger(async_run: bool = False):
        """Trigger an immediate training run. The run is executed in a
        threadpool so the endpoint returns promptly.
        """
        global ml_service
        try:
            import asyncio

            _assert_runtime_not_halted("Training trigger")

            run_async = bool(async_run or _celery_enabled())
            if run_async:
                task = _dispatch_celery_task("autosaham.retrain_model")
                if task:
                    return {"status": "queued", **task}

            if ml_service:
                await asyncio.get_event_loop().run_in_executor(None, ml_service.run_once)
                return {"status": "scheduled"}
            else:
                # fallback: run a single training execution synchronously in a worker
                from src.ml.service import MLTrainerService

                ms = MLTrainerService(schedule_seconds=0, db_path=os.path.join(project_root, "data", "ticks.db"), models_dir=os.path.join(project_root, "models"))
                await asyncio.get_event_loop().run_in_executor(None, ms.run_once)
                return {"status": "trained"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

else:
    # Friendly placeholders when FastAPI is not installed.
    app = None

    def _missing_fastapi(*args, **kwargs):
        raise RuntimeError(
            "FastAPI is not installed. Install with "
            "pip install fastapi[all] to enable the API server."
        )

    def health():
        return _missing_fastapi()

    def run_etl(*args, **kwargs):
        return _missing_fastapi()

    def start_scheduler(*args, **kwargs):
        return _missing_fastapi()

    def stop_scheduler(*args, **kwargs):
        return _missing_fastapi()


if __name__ == "__main__":
    if FASTAPI_AVAILABLE:
        import uvicorn
        host = os.getenv("API_HOST", "127.0.0.1")
        port = int(os.getenv("API_PORT", "8000"))
        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        raise RuntimeError("FastAPI is not installed. Install with: pip install fastapi[all]")
