"""ASGI account endpoints and cookie/Bearer authentication for the personal app."""

from __future__ import annotations

import asyncio
import hmac
import os
import re
from collections.abc import Callable
from http.cookies import CookieError, SimpleCookie
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.web.access_policy import headers_to_legacy_dict
from src.web.auth_store import COOKIE_NAME, REMEMBER_SECONDS, AuthSession, AuthStore, LoginLimited

AUTHENTICATED_STATE = "meshcore_authenticated"
AUTH_SERVICE_STATE = "meshcore_auth_service"
AUTH_SESSION_STATE = "meshcore_auth_session"
AUTH_CREDENTIAL_STATE = "meshcore_auth_credential"
PUBLIC_AUTH_PATHS = frozenset({"/api/auth/login", "/api/auth/session"})
ACCOUNT_PATHS = frozenset(
    {"/api/auth/session", "/api/auth/credentials", "/api/auth/logout", "/api/auth/api-token"}
)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _cookie_token(headers: dict[str, str]) -> str:
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("cookie", ""))
    except CookieError:
        return ""
    morsel = cookie.get(COOKIE_NAME)
    return morsel.value if morsel is not None else ""


def _same_origin(scope: Scope, headers: dict[str, str], *, required: bool = False) -> bool:
    origin = headers.get("origin", "")
    if not origin:
        return not required and headers.get("sec-fetch-site", "") not in ("cross-site", "same-site")
    try:
        parsed = urlsplit(origin)
        expected_scheme = (
            str(scope.get("scheme", "http")).replace("wss", "https").replace("ws", "http")
        )
        return (
            parsed.scheme == expected_scheme
            and parsed.netloc.lower() == headers.get("host", "").lower()
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status, headers={"Cache-Control": "no-store"})


class AuthenticationService:
    def __init__(self, store: AuthStore) -> None:
        self.store = store
        self._initialized = False
        self._initialize_lock = asyncio.Lock()
        self.password_work = asyncio.Semaphore(1)
        self._password_tasks: set[asyncio.Task[Any]] = set()

    def owned_tasks(self) -> set[asyncio.Task[Any]]:
        """Retain finite KDF workers through request cancellation and server shutdown."""
        return set(self._password_tasks)

    async def password_call[T](self, function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Keep the one KDF slot reserved until a cancelled request's worker finishes."""
        if self.password_work.locked():
            raise LoginLimited("login_rate_limited")
        await self.password_work.acquire()
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        self._password_tasks.add(task)

        def finished(completed: asyncio.Task[T]) -> None:
            self._password_tasks.discard(completed)
            self.password_work.release()
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def initialize(self) -> None:
        async with self._initialize_lock:
            if not self._initialized:
                await asyncio.to_thread(self.store.initialize)
                await asyncio.to_thread(self.store.bootstrap_default)
                self._initialized = True

    async def authenticate(self, scope: Scope) -> tuple[AuthSession | None, bool]:
        await self.initialize()
        headers = headers_to_legacy_dict(scope.get("headers", ()))
        authorization = headers.get("authorization", "")
        api_key = headers.get("x-api-key", "")
        supplied = (
            authorization[7:]
            if authorization.startswith("Bearer ")
            else ("" if authorization else api_key)
        )
        session: AuthSession | None = None
        valid = False
        if authorization or api_key:
            if await asyncio.to_thread(self.store.account_ready):
                expected = os.getenv("BRIDGE_API_KEY", "")
                valid = bool(
                    expected
                    and supplied
                    and hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
                )
                if not valid:
                    valid = await asyncio.to_thread(self.store.valid_api_token, supplied)
        else:
            token = _cookie_token(headers)
            session = await asyncio.to_thread(self.store.session, token)
            valid = session is not None
            supplied = token
        state = scope.setdefault("state", {})
        state[AUTHENTICATED_STATE] = valid
        state[AUTH_SERVICE_STATE] = self
        state[AUTH_SESSION_STATE] = session
        state[AUTH_CREDENTIAL_STATE] = supplied
        return session, valid

    async def websocket_authorized(self, scope: Scope) -> bool:
        session, valid = await self.authenticate(scope)
        return valid and not (session is not None and session.must_change_credentials)

    async def session_payload(self, session: AuthSession | None) -> dict[str, Any]:
        return {
            "authenticated": session is not None,
            "requires_initial_setup": session.must_change_credentials
            if session is not None
            else not await asyncio.to_thread(self.store.account_ready),
            "username": session.username if session is not None else None,
            "csrf_token": session.csrf_token if session is not None else None,
            "must_change_credentials": session.must_change_credentials
            if session is not None
            else False,
            "api_key_configured": session is not None
            and (
                bool(os.getenv("BRIDGE_API_KEY", ""))
                or await asyncio.to_thread(self.store.api_token_configured)
            ),
        }

    async def cookie_response(self, request: Request, session: AuthSession) -> JSONResponse:
        response = JSONResponse(
            await self.session_payload(session), headers={"Cache-Control": "no-store"}
        )
        response.set_cookie(
            COOKIE_NAME,
            session.token,
            max_age=REMEMBER_SECONDS if session.remember else None,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path="/",
        )
        return response

    def install_routes(self, app: FastAPI) -> None:
        async def session_status(request: Request) -> JSONResponse:
            session = request.scope.get("state", {}).get(AUTH_SESSION_STATE)
            return JSONResponse(
                await self.session_payload(session), headers={"Cache-Control": "no-store"}
            )

        async def login(request: Request) -> JSONResponse:
            body = request.scope.get("state", {}).get("meshcore_body_json", {})
            username, password, remember = (
                body.get("username"),
                body.get("password"),
                body.get("remember", True),
            )
            if (
                not isinstance(username, str)
                or re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username) is None
                or not _password_input(password)
                or not isinstance(remember, bool)
            ):
                return _error(422, "invalid_login_payload")
            peer = str(request.client.host) if request.client else "unknown"
            try:
                result = await self.password_call(
                    self.store.login, username, password, remember=remember, peer=peer
                )
            except LoginLimited:
                response = _error(429, "login_rate_limited")
                response.headers["Retry-After"] = "900"
                return response
            if result is None:
                return _error(401, "invalid_credentials")
            return await self.cookie_response(request, result)

        async def logout(request: Request) -> JSONResponse:
            session = request.scope.get("state", {}).get(AUTH_SESSION_STATE)
            if not isinstance(session, AuthSession):
                return _error(401, "browser_session_required")
            await asyncio.to_thread(self.store.logout, session.token)
            response = JSONResponse({"authenticated": False}, headers={"Cache-Control": "no-store"})
            response.delete_cookie(
                COOKIE_NAME,
                path="/",
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="strict",
            )
            return response

        async def credentials(request: Request) -> JSONResponse:
            session = request.scope.get("state", {}).get(AUTH_SESSION_STATE)
            if not isinstance(session, AuthSession):
                return _error(401, "browser_session_required")
            body = request.scope.get("state", {}).get("meshcore_body_json", {})
            username, password, current = (
                body.get("username"),
                body.get("password"),
                body.get("current_password"),
            )
            needs_current = not session.must_change_credentials
            if (
                not isinstance(username, str)
                or not _password_input(password)
                or (needs_current and not _password_input(current))
                or (current is not None and current != "" and not _password_input(current))
            ):
                return _error(422, "invalid_credentials_payload")
            try:
                result = await self.password_call(
                    self.store.change_credentials, session.token, current or None, username, password
                )
            except LoginLimited:
                return _error(429, "login_rate_limited")
            except ValueError as error:
                message = str(error)
                status = 401 if message in ("invalid_current_password", "session_revoked") else 422
                return _error(status, message)
            return await self.cookie_response(request, result)

        async def api_token(request: Request) -> JSONResponse:
            session = request.scope.get("state", {}).get(AUTH_SESSION_STATE)
            if not isinstance(session, AuthSession):
                return _error(401, "browser_session_required")
            body = request.scope.get("state", {}).get("meshcore_body_json", {})
            current = body.get("current_password")
            if not _password_input(current):
                return _error(422, "invalid_credentials_payload")
            try:
                value = await self.password_call(
                    self.store.rotate_api_token, session.token, current
                )
            except LoginLimited:
                return _error(429, "login_rate_limited")
            except ValueError as error:
                return _error(401, str(error))
            return JSONResponse({"token": value}, headers={"Cache-Control": "no-store"})

        for path, handler, methods in (
            ("/api/auth/session", session_status, ["GET"]),
            ("/api/auth/login", login, ["POST"]),
            ("/api/auth/logout", logout, ["POST"]),
            ("/api/auth/credentials", credentials, ["PUT"]),
            ("/api/auth/api-token", api_token, ["POST"]),
        ):
            app.add_route(path, handler, methods=methods)


def _password_input(value: Any) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return False
    try:
        return len(value.encode("utf-8")) <= 1024
    except UnicodeEncodeError:
        return False


class BridgeAuthenticationMiddleware:
    def __init__(self, app: ASGIApp, service: AuthenticationService) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", "/")).rstrip("/") or "/"
        method = str(scope.get("method", "GET")).upper()
        headers = headers_to_legacy_dict(scope.get("headers", ()))
        protected = (
            scope["type"] == "websocket"
            or path.startswith("/api/")
            or path in ("/api", "/docs", "/redoc", "/openapi.json")
        )
        if not protected:
            await self.app(scope, receive, send)
            return
        session, valid = await self.service.authenticate(scope)
        error: tuple[int, str] | None = None
        if scope["type"] == "websocket":
            if not valid:
                error = (401, "auth_required")
            elif session is not None and not _same_origin(scope, headers, required=True):
                error = (403, "origin_not_allowed")
            elif session is not None and session.must_change_credentials:
                error = (403, "credentials_change_required")
        elif path == "/api/auth/login":
            if not _same_origin(scope, headers, required=True):
                error = (403, "origin_not_allowed")
            elif (
                headers.get("content-type", "").partition(";")[0].strip().lower()
                != "application/json"
            ):
                error = (415, "json_content_type_required")
        elif (
            path == "/api/auth/session" and session is not None and not _same_origin(scope, headers)
        ):
            error = (403, "origin_not_allowed")
        elif path not in PUBLIC_AUTH_PATHS:
            if not valid:
                error = (401, "auth_required")
            elif session is not None:
                if not _same_origin(scope, headers):
                    error = (403, "origin_not_allowed")
                elif session.must_change_credentials and path not in ACCOUNT_PATHS - {
                    "/api/auth/api-token"
                }:
                    error = (403, "credentials_change_required")
                elif method not in SAFE_METHODS:
                    if not hmac.compare_digest(
                        headers.get("x-csrf-token", "").encode("utf-8"),
                        session.csrf_token.encode("utf-8"),
                    ):
                        error = (403, "csrf_failed")
        if error is not None:
            status, code = error
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await _error(status, code)(scope, receive, send)
            return

        async def private_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = dict(message)
                vary = [
                    value.decode("latin-1")
                    for name, value in message.get("headers", ())
                    if name.lower() == b"vary"
                ]
                response_headers = [
                    (name, value)
                    for name, value in message.get("headers", ())
                    if name.lower() not in (b"cache-control", b"vary")
                ]
                response_headers.extend(
                    (
                        (b"cache-control", b"no-store"),
                        (
                            b"vary",
                            (", ".join(vary + ["Cookie", "Authorization", "X-Api-Key"])).encode(
                                "latin-1"
                            ),
                        ),
                    )
                )
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, private_send)
