"""Synthetic cross-site browser proof; never uses a real profile, broker or operational DB."""

import argparse
import asyncio
import io
import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import uvicorn
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from pydantic import SecretStr
from websockets.asyncio.client import connect

from backend.app.brokers.oauth import AUTHORIZATION_URL, UpstoxOAuth
from backend.app.config import Settings
from backend.app.main import create_app
from scripts.bootstrap_local import ROOT

CODE = "synthetic-browser-code"
PASSWORD = "synthetic-browser-password"
TOKEN = "synthetic-browser-bearer"


async def verify(
    chrome_binary,
    origin,
    provider_origin,
    profile,
    probes,
    exchanges,
    access,
    *,
    auth_accessibility=False,
):
    chrome = subprocess.Popen(
        [
            str(chrome_binary),
            "--headless=new",
            "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1",
            "--user-data-dir=" + str(profile),
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-sync",
            "--disable-popup-blocking",
            "--no-proxy-server",
            "--use-mock-keychain",
            "--host-resolver-rules=MAP * 127.0.0.1, EXCLUDE localhost",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ws = None
    reader = None
    tasks = set()
    pending = {}
    sessions = {}
    serial = 0
    exceptions = []
    login_failure_status = None
    overview_failure_status = None
    try:
        deadline = time.monotonic() + 15
        while not (profile / "DevToolsActivePort").exists():
            if chrome.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Synthetic Chrome startup unavailable")
            await asyncio.sleep(0.1)
        lines = (profile / "DevToolsActivePort").read_text().splitlines()
        ws = await connect(
            "ws://127.0.0.1:" + lines[0] + lines[1], max_size=16 * 1024 * 1024, proxy=None
        )

        async def send(method, params=None, session=None):
            nonlocal serial
            serial += 1
            identity = serial
            future = asyncio.get_running_loop().create_future()
            pending[identity] = future
            payload = {"id": identity, "method": method, "params": params or {}}
            if session:
                payload["sessionId"] = session
            await ws.send(json.dumps(payload))
            return await asyncio.wait_for(future, 15)

        async def event(message):
            method = message.get("method")
            params = message.get("params", {})
            session = message.get("sessionId")
            if method == "Target.attachedToTarget":
                sid = params["sessionId"]
                target = params["targetInfo"]
                if target["type"] == "page":
                    await send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]}, sid)
                    await send("Runtime.enable", session=sid)
                    await send("Page.enable", session=sid)
                    sessions[target["targetId"]] = sid
                await send("Runtime.runIfWaitingForDebugger", session=sid)
            elif method == "Fetch.requestPaused":
                url = params["request"]["url"]
                identity = params["requestId"]
                failure = (
                    login_failure_status
                    if url == origin + "/api/auth/login"
                    else overview_failure_status
                    if url == origin + "/api/overview"
                    else None
                )
                if failure is not None:
                    await send(
                        "Fetch.fulfillRequest",
                        {
                            "requestId": identity,
                            "responseCode": failure,
                            "responseHeaders": [
                                {"name": "Content-Type", "value": "application/json"}
                            ],
                        },
                        session,
                    )
                elif url.startswith(AUTHORIZATION_URL + "?"):
                    state = parse_qs(urlsplit(url).query)["state"][0]
                    destination = provider_origin + "/authorize?" + urlencode({"state": state})
                    await send(
                        "Fetch.fulfillRequest",
                        {
                            "requestId": identity,
                            "responseCode": 302,
                            "responseHeaders": [
                                {"name": "Location", "value": destination},
                                {"name": "Cache-Control", "value": "no-store"},
                            ],
                        },
                        session,
                    )
                elif url.startswith(origin + "/") or url.startswith(provider_origin + "/"):
                    await send("Fetch.continueRequest", {"requestId": identity}, session)
                else:
                    await send(
                        "Fetch.failRequest",
                        {"requestId": identity, "errorReason": "BlockedByClient"},
                        session,
                    )
            elif method == "Runtime.exceptionThrown":
                exceptions.append(True)

        async def read():
            async for raw in ws:
                message = json.loads(raw)
                if "id" in message:
                    future = pending.pop(message["id"], None)
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(
                                RuntimeError("Synthetic browser protocol command failed")
                            )
                        else:
                            future.set_result(message.get("result", {}))
                else:
                    task = asyncio.create_task(event(message))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)

        reader = asyncio.create_task(read())
        await send(
            "Target.setAutoAttach",
            {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True},
        )
        target = (await send("Target.createTarget", {"url": "about:blank"}))["targetId"]
        deadline = time.monotonic() + 10
        while target not in sessions:
            if time.monotonic() > deadline:
                raise RuntimeError("Synthetic main target unavailable")
            await asyncio.sleep(0.05)
        main = sessions[target]

        async def evaluate(expression, session=main):
            value = await send(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": True,
                    "userGesture": True,
                },
                session,
            )
            if "exceptionDetails" in value:
                raise RuntimeError("Synthetic page evaluation failed")
            return value.get("result", {}).get("value")

        async def until(expression, session=main):
            deadline = time.monotonic() + 15
            while not await evaluate(expression, session):
                if time.monotonic() > deadline:
                    raise RuntimeError("Synthetic browser checkpoint timed out")
                await asyncio.sleep(0.1)

        await send("Page.navigate", {"url": origin + "/"}, main)
        await until(
            'document.readyState === "complete" && document.getElementById("password") !== null'
        )
        await until('document.getElementById("feedback").textContent.includes("Sign in to load")')
        await evaluate(
            'document.getElementById("password").focus();'
            'document.getElementById("password").value="synthetic-incorrect-password";true'
        )
        await send(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
                "text": "\r",
            },
            main,
        )
        await send(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
                "text": "\r",
            },
            main,
        )
        await until(
            'document.getElementById("feedback").textContent === "Password not recognized."'
        )
        auth_checks = {
            "failed_login_focus": await evaluate('document.activeElement.id === "password"'),
            "invalid_password_identified": await evaluate(
                'document.getElementById("password").getAttribute("aria-invalid") === "true"'
            ),
            "error_description_linked": await evaluate(
                'document.getElementById("password").getAttribute("aria-describedby")'
                ' === "feedback"'
            ),
            "password_cleared_after_failure": await evaluate(
                'document.getElementById("password").value === ""'
            ),
            "status_atomic": await evaluate(
                'document.getElementById("feedback").getAttribute("aria-atomic") === "true"'
            ),
        }
        if auth_accessibility:
            tree = await send("Accessibility.getFullAXTree", session=main)
            password_nodes = [
                node
                for node in tree["nodes"]
                if node.get("role", {}).get("value") == "textbox"
                and node.get("name", {}).get("value") == "Administrator password"
            ]
            auth_checks["accessible_error_description"] = any(
                node.get("description", {}).get("value") == "Password not recognized."
                for node in password_nodes
            )
            auth_checks["form_not_busy_after_failure"] = await evaluate(
                'document.getElementById("login-form").getAttribute("aria-busy") === "false"'
            )
            await evaluate(
                'document.getElementById("password").dispatchEvent(new Event("input"));true'
            )
            auth_checks["editing_clears_invalid_state"] = await evaluate(
                'document.getElementById("password").getAttribute("aria-invalid") === "false"'
            )
        await evaluate(
            'document.getElementById("password").value='
            + json.dumps(PASSWORD)
            + '; document.getElementById("login-form").requestSubmit(); true'
        )
        await until(
            '!document.getElementById("oauth-connect").hidden && !document.getElementByI'
            'd("oauth-connect").disabled'
        )
        await until('!document.querySelector("#login-form button").disabled')
        auth_checks["successful_login_focus"] = await evaluate(
            'document.activeElement.id === "account-title"'
        )
        await evaluate('document.getElementById("oauth-connect").click(); true')
        await until(
            '(async()=>{const r=await fetch("/api/broker/oauth/status");return r.ok && ('
            'await r.json()).state === "STORED_UNVERIFIED"})()'
        )
        await until(
            'document.getElementById("oauth-connect").textContent === "Authorize Upstox OAuth"'
        )
        callback_sessions = []
        for _tid, sid in list(sessions.items()):
            if sid == main:
                continue
            try:
                if await evaluate('location.pathname === "/auth/upstox/callback"', sid):
                    callback_sessions.append(sid)
            except RuntimeError:
                pass
        if len(callback_sessions) != 1:
            raise RuntimeError("Synthetic popup return not found")
        popup = callback_sessions[0]
        await until(
            'document.getElementById("oauth-return-status").textContent.includes("saved locally")',
            popup,
        )
        if not await evaluate(
            'location.search === "" && sessionStorage.getItem("algotrade.upstox.flow") ='
            "== null && window.opener === null",
            popup,
        ):
            raise RuntimeError("Callback cleanup/binding boundary failed")
        if len(exchanges) != 1 or not probes["callback"] or any(probes["callback"]):
            raise RuntimeError("Strict cookie callback boundary failed")
        if probes["finish"] != [True]:
            raise RuntimeError("Authenticated finish cookie missing")
        # Same state in another unbound tab must not talk to the original dashboard.
        await evaluate(
            '(async()=>{window.__syntheticFlow=await (await fetch("/api/broker/oauth/sta'
            'rt",{method:"POST",headers:{"X-CSRF-Token":csrfToken}})).json();return true'
            ";})()"
        )
        state = await evaluate("window.__syntheticFlow.state")
        forged = (
            await send(
                "Target.createTarget",
                {
                    "url": origin
                    + "/auth/upstox/callback?"
                    + urlencode({"code": CODE, "state": state})
                },
            )
        )["targetId"]
        deadline = time.monotonic() + 10
        while forged not in sessions:
            if time.monotonic() > deadline:
                raise RuntimeError("Synthetic unbound target unavailable")
            await asyncio.sleep(0.05)
        await until(
            'document.getElementById("oauth-return-status") !== null && document.getElem'
            'entById("oauth-return-status").textContent.includes("Invalid authorization '
            'return")',
            sessions[forged],
        )
        if len(exchanges) != 1:
            raise RuntimeError("Unbound return caused a token exchange")
        await evaluate(
            '(async()=>{const f=window.__syntheticFlow;const r=await fetch("/api/broker/'
            'oauth/finish",{method:"POST",headers:{"Content-Type":"application/json","X-'
            'CSRF-Token":csrfToken},body:JSON.stringify({state:f.state,flow_nonce:f.flow'
            "_nonce,denied:true})});delete window.__syntheticFlow;return r.ok;})()"
        )
        if not any("/auth/upstox/callback" in line for line in access):
            raise RuntimeError("Synthetic access log capture unavailable")
        if any(CODE in line or "state=" in line or "flow_nonce" in line for line in access):
            raise RuntimeError("Sensitive callback fields reached server access logs")
        if exceptions:
            raise RuntimeError("Synthetic browser JavaScript exception")
        if auth_accessibility:
            overview_failure_status = 401
            await evaluate('document.getElementById("account-title").focus();loadOverview()')
            auth_checks["expired_session_focus"] = await evaluate(
                'document.activeElement.id === "password"'
            )
            await evaluate('document.getElementById("theme").focus();loadOverview()')
            auth_checks["visible_control_focus_preserved"] = await evaluate(
                'document.activeElement.id === "theme"'
            )
            overview_failure_status = None
            await evaluate(
                'document.getElementById("password").value='
                + json.dumps(PASSWORD)
                + ';document.getElementById("login-form").requestSubmit();true'
            )
            await until(
                'document.getElementById("signin").hidden && '
                '!document.querySelector("#login-form button").disabled'
            )
        await evaluate('document.getElementById("logout").focus();true')
        await send(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
                "text": "\r",
            },
            main,
        )
        await send(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
                "text": "\r",
            },
            main,
        )
        await until('document.getElementById("feedback").textContent.includes("Signed out.")')
        auth_checks["signed_out_focus"] = await evaluate('document.activeElement.id === "password"')
        if auth_accessibility:
            for status, message in [(429, "Too many attempts."), (503, "Sign-in unavailable.")]:
                login_failure_status = status
                await evaluate(
                    'document.getElementById("password").value='
                    + json.dumps(PASSWORD)
                    + ';document.getElementById("login-form").requestSubmit();true'
                )
                await until(
                    'document.getElementById("feedback").textContent.includes('
                    + json.dumps(message)
                    + ") && "
                    '!document.querySelector("#login-form button").disabled'
                )
                auth_checks["service_error_" + str(status)] = await evaluate(
                    'document.activeElement.id === "password" && '
                    'document.getElementById("password").getAttribute("aria-invalid")'
                    ' === "false" && '
                    'document.getElementById("password").value === "" && '
                    'document.getElementById("login-form").getAttribute("aria-busy") === "false"'
                )
            login_failure_status = None
        if auth_accessibility and not all(auth_checks.values()):
            raise RuntimeError("Synthetic authentication accessibility checks failed")
        report = {
            "state": "SYNTHETIC_BROWSER_VERIFIED",
            "strict_cookie_absent_on_cross_site_callback": True,
            "authenticated_cookie_present_on_finish": True,
            "popup_opener_detached": True,
            "popup_marker_removed": True,
            "callback_query_cleared": True,
            "unbound_tab_rejected": True,
            "single_mock_token_exchange": True,
            "access_logs_scrubbed": True,
            "javascript_exceptions": 0,
            "real_broker_used": False,
            "operational_database_used": False,
            "live_enabled": False,
            "authentication_accessibility": auth_checks,
        }
        print(json.dumps(report), flush=True)
        try:
            await send("Browser.close")
        except Exception:
            pass
    finally:
        if reader:
            reader.cancel()
        for task in tasks:
            task.cancel()
        if ws:
            await ws.close()
        if chrome.poll() is None:
            chrome.terminate()
            try:
                await asyncio.to_thread(chrome.wait, 10)
            except subprocess.TimeoutExpired:
                chrome.kill()
                await asyncio.to_thread(chrome.wait, 10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome-binary", type=Path, required=True)
    parser.add_argument("--auth-accessibility", action="store_true")
    args = parser.parse_args()
    chrome_binary = args.chrome_binary.resolve()
    if not chrome_binary.is_file() or not os.access(chrome_binary, os.X_OK):
        parser.error("A local executable Chrome/Chromium binary is required; nothing is downloaded")
    temp = Path(tempfile.mkdtemp(prefix="algotrade-oauth-browser-")).resolve()
    temp.chmod(0o700)
    server = None
    thread = None
    provider = None
    provider_thread = None
    listener = None
    logger = logging.getLogger("algotrade")
    disabled = logger.disabled
    logger.disabled = True
    access_logger = logging.getLogger("uvicorn.access")
    old_handlers = access_logger.handlers[:]
    old_level = access_logger.level
    old_propagate = access_logger.propagate
    logs = []

    class Capture(logging.Handler):
        def emit(self, record):
            logs.append(record.getMessage())

    access_logger.handlers = [Capture()]
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False
    try:
        old_cwd = Path.cwd()
        old_env = {key: os.environ.get(key) for key in ["APP_ENV", "DATABASE_URL"]}
        try:
            os.chdir(temp)
            os.environ.update(APP_ENV="test", DATABASE_URL="sqlite:///" + str(temp / "test.sqlite"))
            cfg = Config(str(ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(ROOT / "backend/migrations"))
            with redirect_stderr(io.StringIO()):
                command.upgrade(cfg, "head")
        finally:
            os.chdir(old_cwd)
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = "http://127.0.0.1:" + str(port)

        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                state = parse_qs(urlsplit(self.path).query).get("state", [""])[0]
                if len(state) != 43:
                    self.send_error(400)
                    return
                destination = (
                    origin + "/auth/upstox/callback?" + urlencode({"code": CODE, "state": state})
                )
                body = (
                    "<!doctype html><script>location.replace("
                    + json.dumps(destination)
                    + ")</script>"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        provider_origin = "http://localhost:" + str(provider.server_port)
        provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
        provider_thread.start()
        settings = Settings(
            _env_file=None,
            app_env="test",
            cookie_secure=False,
            trading_mode="OBSERVATION",
            live_enabled=False,
            session_minutes=15,
            database_url="sqlite:///" + str(temp / "test.sqlite"),
            admin_password_hash=PasswordHasher().hash(PASSWORD),
            allowed_hosts=["127.0.0.1", "localhost"],
            allowed_origins=[origin],
            upstox_analytics_token=SecretStr(""),
            upstox_analytics_expires_at=None,
            upstox_client_id="synthetic-client",
            upstox_client_secret=SecretStr("synthetic-private-value"),
            upstox_redirect_uri=origin + "/auth/upstox/callback",
            upstox_oauth_vault_dir=str(temp / "vault"),
        )
        app = create_app(settings)
        exchanges = []
        probes = {"callback": [], "finish": []}

        def exchange(request):
            exchanges.append(True)
            return httpx.Response(200, json={"access_token": TOKEN})

        app.state.oauth_client = UpstoxOAuth(transport=httpx.MockTransport(exchange))

        async def probe(scope, receive, send):
            if scope["type"] == "http":
                path = scope.get("path")
                cookies = dict(scope.get("headers", [])).get(b"cookie", b"")
                if path == "/auth/upstox/callback":
                    probes["callback"].append(b"admin_session=" in cookies)
                elif path == "/api/broker/oauth/finish":
                    probes["finish"].append(b"admin_session=" in cookies)
            await app(scope, receive, send)

        server = uvicorn.Server(
            uvicorn.Config(
                probe,
                host="127.0.0.1",
                port=port,
                log_config=None,
                access_log=True,
                log_level="info",
            )
        )
        thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("Synthetic app startup unavailable")
            time.sleep(0.05)
        asyncio.run(
            verify(
                chrome_binary,
                origin,
                provider_origin,
                temp / "chrome-profile",
                probes,
                exchanges,
                logs,
                auth_accessibility=args.auth_accessibility,
            )
        )
    finally:
        if server:
            server.should_exit = True
        if thread:
            thread.join(10)
        if provider:
            provider.shutdown()
            provider.server_close()
        if provider_thread:
            provider_thread.join(5)
        if listener:
            listener.close()
        logger.disabled = disabled
        access_logger.handlers = old_handlers
        access_logger.setLevel(old_level)
        access_logger.propagate = old_propagate
        if thread and thread.is_alive():
            raise RuntimeError("Synthetic browser fixture cleanup incomplete")
        else:
            shutil.rmtree(temp)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("SYNTHETIC_BROWSER_VERIFICATION_FAILED:" + type(error).__name__, flush=True)
        raise SystemExit(1) from None
