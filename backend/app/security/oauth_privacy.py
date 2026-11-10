"""Scrub callback query strings in the original ASGI scope before application/server logging."""

import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

OAUTH_API_PATHS = {
    "/api/broker/oauth/start",
    "/api/broker/oauth/finish",
    "/api/broker/oauth/status",
}


class OAuthPrivacyMiddleware:
    def __init__(self, app: ASGIApp, callback_paths: list[str]):
        self.app = app
        self.callbacks = {"/auth/upstox/callback", *callback_paths}
        self.callbacks |= {path + "/" for path in self.callbacks}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self.callbacks or path in OAUTH_API_PATHS:
            had_query = bool(scope.get("query_string", b""))
            query_size = len(scope.get("query_string", b""))
            scope["query_string"] = b""
            scope["raw_path"] = path.encode("ascii")
            if query_size > 16_384 or (had_query and path in OAUTH_API_PATHS):
                await JSONResponse({"detail": "OAUTH_QUERY_REJECTED"}, status_code=400)(
                    scope, receive, send
                )
                return
        if path not in OAUTH_API_PATHS or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        too_large = False
        try:
            async with asyncio.timeout(5):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > 16_384:
                        too_large = True
                        break
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await JSONResponse({"detail": "OAUTH_BODY_TIMEOUT"}, status_code=408)(
                scope, receive, send
            )
            return
        if too_large:
            await JSONResponse({"detail": "OAUTH_BODY_TOO_LARGE"}, status_code=413)(
                scope, receive, send
            )
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
