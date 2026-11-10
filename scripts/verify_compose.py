"""Verify an isolated Compose project using generated disposable credentials.

Default: build, migrate, check auth/restarts/outages and remove only this run's resources.
--config-only: validate configuration without a Docker engine. No user .env is read/modified.
"""

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from argon2 import PasswordHasher
from pydantic import SecretStr

from scripts.bootstrap_local import start_runtime
from scripts.configure_upstox_oauth import FIELDS, save_oauth_settings

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_APP_SECRET = "synthetic$setup#quote'and\"double=ok"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-bin", type=Path, help="Optional standalone Compose executable")
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument(
        "--oauth-vault", action="store_true", help="Verify optional private OAuth volume"
    )
    parser.add_argument(
        "--bootstrap", action="store_true", help="Exercise the real bootstrap startup helper"
    )
    args = parser.parse_args()
    if args.bootstrap and args.compose_bin:
        parser.error("--bootstrap uses Docker Compose via docker; omit --compose-bin")
    executable = [str(args.compose_bin.resolve())] if args.compose_bin else ["docker", "compose"]
    project = "algotrade-verify-" + secrets.token_hex(6)
    port = 8000
    if not args.config_only:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix=project + "-") as directory:
        environment_file = Path(directory) / ".env"
        password = secrets.token_urlsafe(32)
        database_password = secrets.token_urlsafe(32)
        origin = f"http://127.0.0.1:{port}"
        variables = {
            "APP_ENV": "development",
            "TRADING_MODE": "OBSERVATION",
            "LIVE_ENABLED": "false",
            "POSTGRES_USER": "algotrade_verify",
            "POSTGRES_DB": "algotrade_test",
            "POSTGRES_PASSWORD": database_password,
            "DATABASE_URL": f"postgresql+psycopg://algotrade_verify:{database_password}@db:5432/algotrade_test",
            "ADMIN_PASSWORD_HASH": PasswordHasher().hash(password),
            "COOKIE_SECURE": "false",
            "ALLOWED_HOSTS": json.dumps(["localhost", "127.0.0.1"]),
            "ALLOWED_ORIGINS": json.dumps([origin]),
            "APP_BIND_PORT": str(port),
        }
        if args.oauth_vault:
            variables.update(
                UPSTOX_CLIENT_ID="synthetic-compose-client",
                UPSTOX_CLIENT_SECRET=SYNTHETIC_APP_SECRET,
                UPSTOX_REDIRECT_URI=origin + "/auth/upstox/callback",
            )
        environment_file.touch(mode=0o600)
        environment_file.write_text(
            "\n".join(
                f"{key}='{value}'"
                for key, value in variables.items()
                if not args.oauth_vault or key not in FIELDS
            )
            + "\n"
        )
        if args.oauth_vault:
            saved = save_oauth_settings(
                Path(directory),
                variables["UPSTOX_CLIENT_ID"],
                SecretStr(variables["UPSTOX_CLIENT_SECRET"]),
                variables["UPSTOX_REDIRECT_URI"],
            )
            assert saved["saved"] and not saved["registration_verified"]
        environment = {**os.environ, **variables, "APP_ENV_FILE": str(environment_file)}
        base = [
            *executable,
            "--project-name",
            project,
            "--project-directory",
            str(ROOT),
            "--file",
            str(ROOT / "docker-compose.yml"),
            "--env-file",
            str(environment_file),
        ]
        if args.oauth_vault:
            base.extend(["--file", str(ROOT / "docker-compose.oauth.yml")])

        def compose(*arguments):
            result = subprocess.run(
                [*base, *arguments], env=environment, cwd=ROOT, capture_output=True, text=True
            )
            if result.returncode:
                # Do not dump expanded configuration, environment values or container logs.
                raise RuntimeError(f"Compose {arguments[0]} failed (exit {result.returncode})")
            return result.stdout

        configuration = json.loads(compose("config", "--format", "json"))
        services = configuration["services"]
        if args.oauth_vault:
            assert services["app"]["environment"]["UPSTOX_CLIENT_SECRET"] in (
                SYNTHETIC_APP_SECRET,
                SYNTHETIC_APP_SECRET.replace("$", "$$"),
            )
        assert not services["db"].get("ports"), "Database must not publish a host port"
        assert services["app"]["ports"][0]["host_ip"] == "127.0.0.1"
        # Compose config escapes dollars to keep its serialized output round-trippable.
        # The actual container login below independently checks the runtime hash.
        assert services["app"]["environment"]["ADMIN_PASSWORD_HASH"] in (
            variables["ADMIN_PASSWORD_HASH"],
            variables["ADMIN_PASSWORD_HASH"].replace("$", "$$"),
        )
        assert services["app"]["environment"]["DATABASE_URL"] == variables["DATABASE_URL"]
        assert services["app"]["read_only"] is True
        assert "ALL" in services["app"]["cap_drop"]
        if args.oauth_vault:
            assert services["app"]["environment"]["UPSTOX_OAUTH_VAULT_DIR"] == (
                "/var/lib/algotrade/oauth"
            )
            mounts = services["app"]["volumes"]
            assert len(mounts) == 1 and mounts[0]["type"] == "volume"
            assert mounts[0]["target"] == "/var/lib/algotrade/oauth"
            assert not services["migrate"].get("volumes")
            assert not services["migrate"]["environment"].get("UPSTOX_OAUTH_VAULT_DIR")
        print(
            "Compose configuration verified; private DB, loopback app, literal secrets preserved.",
            flush=True,
        )
        if args.config_only:
            return
        try:
            compose("ps", "--format", "json")
        except RuntimeError:
            raise RuntimeError(
                "Docker engine is unavailable; no verification containers were started. "
                "Start Docker and rerun this command."
            ) from None
        failure = None

        def bootstrap(*, opt_in):
            result = start_runtime(
                ROOT,
                {
                    "values": variables,
                    "project": project,
                    "origin": origin,
                    "admin_password": password,
                    "admin_password_file": None,
                },
                "docker",
                oauth_vault=opt_in,
                environment_file=environment_file,
            )
            assert result["login_verified"]
            assert result["oauth_vault_enabled"] is args.oauth_vault
            assert not result["recording_started"] and not result["live_enabled"]

        try:
            print("Building and starting isolated verification containers…", flush=True)
            if args.bootstrap:
                bootstrap(opt_in=args.oauth_vault)
            else:
                compose("up", "--build", "--wait", "--wait-timeout", "180")
            with httpx.Client(base_url=origin, timeout=10, trust_env=False) as client:

                def ready():
                    deadline = time.monotonic() + 45
                    while time.monotonic() < deadline:
                        try:
                            if client.get("/health/ready").status_code == 200:
                                return
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.25)
                    raise RuntimeError("Container readiness did not recover")

                ready()
                assert client.get("/").status_code == 200
                assert client.get("/api/overview").status_code == 401
                assert client.get("/api/broker/status").status_code == 401
                assert client.get("/api/instruments/status").status_code == 401
                assert client.get("/api/candles/status").status_code == 401
                assert client.get("/api/option-chain/status").status_code == 401
                assert client.get("/api/observations/sessions").status_code == 401
                assert client.get("/api/observations/captures").status_code == 401
                assert (
                    client.get(
                        "/api/observations/preflight",
                        params={"instrument_key": "NSE_INDEX|Synthetic"},
                    ).status_code
                    == 401
                )
                assert (
                    client.get(
                        "/api/observations/calendar",
                        params={"from_date": "2026-11-08", "to_date": "2026-11-08"},
                    ).status_code
                    == 401
                )
                login = client.post(
                    "/api/auth/login", json={"password": password}, headers={"Origin": origin}
                )
                assert login.status_code == 200
                assert "HttpOnly" in login.headers["set-cookie"]
                csrf = login.json()["csrf_token"]
                if args.oauth_vault:
                    verify_oauth_volume(compose, client, origin, csrf)
                assert client.get("/api/broker/status").json()["state"] == "NOT_CONFIGURED"
                assert (
                    client.post("/api/broker/check", headers={"Origin": origin}).status_code == 403
                )
                probe = client.post(
                    "/api/broker/check", headers={"Origin": origin, "X-CSRF-Token": csrf}
                )
                assert probe.status_code == 200
                assert probe.json()["state"] == "NOT_CONFIGURED"
                assert client.get("/api/instruments/status").json()["state"] == "NOT_IMPORTED"
                assert client.get("/api/candles/status").json()["state"] == "NOT_IMPORTED"
                assert client.get("/api/option-chain/status").json()["state"] == "NOT_CAPTURED"
                assert (
                    client.post("/api/option-chain/capture", headers={"Origin": origin}).status_code
                    == 403
                )
                assert (
                    client.post("/api/candles/import", headers={"Origin": origin}).status_code
                    == 403
                )
                assert (
                    client.post("/api/instruments/sync", headers={"Origin": origin}).status_code
                    == 403
                )
                assert (
                    compose(
                        "exec", "-T", "app", "python", "-c", "import os; print(os.getuid())"
                    ).strip()
                    == "10001"
                )
                assert (
                    compose(
                        "exec",
                        "-T",
                        "app",
                        "python",
                        "-c",
                        "from datetime import UTC,datetime; "
                        "from backend.app.market_data.feed import FeedPlan,decode_frame; "
                        "from backend.app.market_data.feed_lifecycle import FeedRunner; "
                        "from backend.app.brokers.feed_transport import NoRedirectConnect; "
                        "from backend.vendor.upstox import MarketDataFeed_pb2 as pb; "
                        "m=pb.FeedResponse(type=pb.market_info,currentTs=1000); "
                        "m.marketInfo.segmentStatus['NSE_INDEX']=pb.NORMAL_CLOSE; "
                        "print(decode_frame(m.SerializeToString(), "
                        "FeedPlan('a'*64,('NSE_INDEX|Synthetic',)), "
                        "datetime.fromtimestamp(1,UTC)).message_type)",
                    ).strip()
                    == "market_info"
                )
                preflight = client.get(
                    "/api/observations/preflight", params={"instrument_key": "NSE_INDEX|Synthetic"}
                ).json()
                assert preflight["state"] == "BLOCKED"
                assert "CREDENTIAL_MISSING" in preflight["blockers"]
                assert preflight["checks"]["schema"] == "CURRENT"
                assert preflight["checks"]["write_privileges"] == "TABLE_GRANTS_PRESENT"
                assert (
                    not preflight["recording_started"] and not preflight["broker_access_verified"]
                )
                assert client.get("/api/observations/sessions").json()["sessions"] == []
                schedule = client.get(
                    "/api/observations/calendar",
                    params={"from_date": "2026-11-08", "to_date": "2026-11-08"},
                ).json()
                assert schedule["days"][0]["state"] == "SPECIAL_SESSION"
                coverage = client.get(
                    "/api/observations/coverage",
                    params={
                        "from_date": "2026-11-06",
                        "to_date": "2026-11-06",
                        "instrument_key": "NSE_FO|Synthetic",
                    },
                ).json()
                assert coverage["counts"]["events"] == 0
                assert coverage["qualifying_observation_days"] == 0
                assert coverage["calendar"]["kind"] == "OFFICIAL_BASELINE"
                recorded_id = compose(
                    "exec",
                    "-T",
                    "app",
                    "python",
                    "-c",
                    "from backend.app.config import Settings; "
                    "from backend.app.database import build_engine; "
                    "from backend.app.market_data.feed import FeedRequest; "
                    "from backend.app.market_data.feed_lifecycle import LifecyclePolicy; "
                    "from backend.app.market_data.observations import "
                    "start_session,finish_session; "
                    "e=build_engine(Settings()); "
                    "i=start_session(e,FeedRequest(instrument_keys=('NSE_INDEX|Synthetic',)), "
                    "LifecyclePolicy(), 'SYNTHETIC'); finish_session(e,i,'FRAME_LIMIT',0); "
                    "print(i); e.dispose()",
                ).strip()
                capture_id = compose(
                    "exec",
                    "-T",
                    "app",
                    "python",
                    "-c",
                    "from backend.app.config import Settings; "
                    "from backend.app.database import build_engine; "
                    "from backend.app.market_data.feed import FeedRequest; "
                    "from backend.app.market_data.supervision_store import "
                    "CapturePolicy,create_capture,finish_capture; "
                    "e=build_engine(Settings()); "
                    "i=create_capture(e,FeedRequest(instrument_keys=('NSE_INDEX|Synthetic',)), "
                    "CapturePolicy(max_sessions=1), 'SYNTHETIC'); "
                    "finish_capture(e,i,'SESSION_LIMIT'); print(i); e.dispose()",
                ).strip()
                compose("restart", "--no-deps", "app")
                ready()
                state = client.get("/api/overview")
                assert state.status_code == 200, "Session must survive application restart"
                recording = client.get(f"/api/observations/sessions/{recorded_id}").json()
                assert recording["session"]["status"] == "CLOSED"
                assert recording["session"]["source"] == "SYNTHETIC"
                assert recording["session"]["observed_interval_ms"] == 0
                assert recording["session"]["qualifying_observation_days"] == 0
                capture = client.get(f"/api/observations/captures/{capture_id}").json()["capture"]
                assert capture["status"] == "CLOSED" and capture["event_count"] == 0
                assert capture["source"] == "SYNTHETIC" and not capture["health_current"]
                assert capture["qualifying_observation_days"] == 0
                assert state.json()["balance"] is None
                assert state.json()["entries_enabled"] is False
                assert state.json()["live_enabled"] is False
                if args.oauth_vault:
                    # Container replacement, rather than restart, proves volume persistence.
                    if args.bootstrap:
                        compose("rm", "--stop", "--force", "app")
                        # Deliberately omit opt-in: the existing exact-project volume retains it.
                        bootstrap(opt_in=False)
                    else:
                        compose("up", "--force-recreate", "--no-deps", "--wait", "app")
                    ready()
                    assert client.get("/api/broker/oauth/status").json()["vault_state"] == (
                        "STORED_UNVERIFIED"
                    )
                    assert compose("exec", "-T", "app", "python", "-c", VAULT_PROOF).strip() == (
                        "PRIVATE_ENCRYPTED_ROUNDTRIP_VERIFIED"
                    )
                compose("stop", "db")
                assert client.get("/health/live").status_code == 200
                assert client.get("/health/ready").status_code == 503
                assert client.get("/api/overview").status_code == 503
                compose("start", "db")
                ready()
                assert client.get("/api/overview").status_code == 200
                assert (
                    client.post("/api/auth/logout", headers={"Origin": origin}).status_code == 403
                )
                token = client.cookies.get("admin_session")
                assert (
                    client.post(
                        "/api/auth/logout", headers={"Origin": origin, "X-CSRF-Token": csrf}
                    ).status_code
                    == 204
                )
                client.cookies.set("admin_session", token)
                assert client.get("/api/overview").status_code == 401
                for path in ("/api/orders", "/api/live/activate"):
                    assert client.post(path, json={}).status_code == 404
            print(
                "Container checks passed: migrations, non-root UID, auth, "
                "restarts, outage recovery, no execution.",
                flush=True,
            )
            if args.bootstrap:
                print("Bootstrap startup verified; no operator settings or runtime modified.")
        except BaseException as exc:
            failure = exc
            raise
        finally:
            try:
                compose("down", "--volumes", "--remove-orphans", "--timeout", "10")
                print(
                    "Removed only the isolated verification project's containers and volumes.",
                    flush=True,
                )
            except RuntimeError:
                if failure is None:
                    raise
                print(f"Cleanup could not be confirmed for project {project}.", file=sys.stderr)


# Only synthetic material is used in the disposable verification project's named volume.
VAULT_PROOF = """
import os, stat
from pathlib import Path
from backend.app.config import Settings
from backend.app.brokers.oauth import configured_app
from backend.app.brokers.oauth_store import OAuthTokenStore
p = Path(Settings().upstox_oauth_vault_dir)
assert os.getuid() == 10001 and p.stat().st_uid == 10001
assert stat.S_IMODE(p.stat().st_mode) == 0o700
for f in p.iterdir():
    assert f.stat().st_uid == 10001 and stat.S_IMODE(f.stat().st_mode) == 0o600
token = OAuthTokenStore(p).load(configured_app(Settings()))
assert Settings().upstox_client_secret.get_secret_value() == SYNTHETIC_APP_SECRET
assert token.access_token.get_secret_value() == 'synthetic-compose-bearer'
assert b'synthetic-compose-bearer' not in (p / 'token.enc').read_bytes()
assert not os.access('/app/backend', os.W_OK)
print('PRIVATE_ENCRYPTED_ROUNDTRIP_VERIFIED')
""".replace("SYNTHETIC_APP_SECRET", repr(SYNTHETIC_APP_SECRET))


def verify_oauth_volume(compose, client, origin, csrf):
    def contents():
        return compose(
            "exec",
            "-T",
            "app",
            "python",
            "-c",
            "from pathlib import Path; "
            "print(len(list(Path('/var/lib/algotrade/oauth').iterdir())))",
        ).strip()

    assert contents() == "0"
    status = client.get("/api/broker/oauth/status").json()
    assert status["can_start"] and status["vault_state"] == "OAUTH_VAULT_NOT_INITIALIZED"
    assert contents() == "0", "Status must not initialize storage"
    assert client.post("/api/broker/oauth/start", headers={"Origin": origin}).status_code == 403
    headers = {"Origin": origin, "X-CSRF-Token": csrf}
    response = client.post("/api/broker/oauth/start", headers=headers)
    assert response.status_code == 200
    flow = response.json()
    assert (
        client.post(
            "/api/broker/oauth/finish",
            headers=headers,
            json={"state": flow["state"], "flow_nonce": flow["flow_nonce"], "denied": True},
        ).status_code
        == 200
    )
    # A denied flow created only a key/lock; no provider request or bearer was produced.
    assert contents() == "2"
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        "from datetime import UTC,datetime; from pathlib import Path; "
        "from pydantic import SecretStr; from backend.app.config import Settings; "
        "from backend.app.brokers.oauth import configured_app,OAuthToken,daily_cutoff; "
        "from backend.app.brokers.oauth_store import OAuthTokenStore; "
        "s=Settings(); now=datetime.now(UTC); "
        "OAuthTokenStore(Path(s.upstox_oauth_vault_dir)).save(configured_app(s), "
        "OAuthToken(SecretStr('synthetic-compose-bearer'),now,now,daily_cutoff(now)))",
    )
    assert compose("exec", "-T", "app", "python", "-c", VAULT_PROOF).strip() == (
        "PRIVATE_ENCRYPTED_ROUNDTRIP_VERIFIED"
    )
    print("Optional OAuth volume: private UID/modes, CSRF, denial and encrypted roundtrip passed.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError) as error:
        raise SystemExit(f"Verification failed: {error}") from None
