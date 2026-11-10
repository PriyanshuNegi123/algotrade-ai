"""Prepare protected local settings and verify Compose startup without broker calls."""

import argparse
import fcntl
import io
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from dotenv.parser import parse_stream
from sqlalchemy.engine import URL, make_url

from backend.app.config import Settings

ROOT = Path(__file__).resolve().parents[1]
OAUTH_VAULT_PATH = "/var/lib/algotrade/oauth"


class BootstrapError(Exception):
    pass


def private_read(path: Path) -> str | None:
    if path.is_symlink():
        raise BootstrapError("SYMLINKED_SECRET_FILE")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise BootstrapError("UNSAFE_SECRET_FILE")
        if info.st_size > 1024 * 1024:
            raise BootstrapError("SECRET_FILE_SIZE")
        return stream.read()


def assignments(original: str) -> dict[str, str]:
    values = {}
    for binding in parse_stream(io.StringIO(original)):
        if binding.error:
            raise BootstrapError("ENV_SYNTAX_INVALID")
        if binding.key:
            if binding.key in values:
                raise BootstrapError("DUPLICATE_ENV_KEY")
            values[binding.key] = binding.value or ""
    return values


def private_write(path: Path, contents: str) -> None:
    private_read(path)  # Reject unsafe existing files before replacement.
    descriptor, temporary = tempfile.mkstemp(prefix=".algotrade-secret-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def secret_directory(root: Path) -> Path:
    path = root
    for part in (".local", "runtime"):
        path = path / part
        if path.is_symlink():
            raise BootstrapError("SYMLINKED_SECRET_DIRECTORY")
        path.mkdir(mode=0o700, exist_ok=True)
        if not path.is_dir() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
            raise BootstrapError("UNSAFE_SECRET_DIRECTORY")
    os.chmod(path, 0o700)
    return path


def project_name(values: dict[str, str]) -> str:
    name = values.get("COMPOSE_PROJECT_NAME") or "algotrade-ai-local"
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", name):
        raise BootstrapError("INVALID_LOCAL_PROJECT_NAME")
    return name


def prepare_runtime(root: Path, *, existing_volume: bool, port: int | None = None) -> dict:
    destination = root / ".env"
    existing = private_read(destination)
    original = existing if existing is not None else (root / ".env.example").read_text()
    values = assignments(original)
    changed = {}

    def fill(key, value):
        if not values.get(key):
            values[key] = value
            changed[key] = value

    fill("APP_ENV", "development")
    fill("TRADING_MODE", "OBSERVATION")
    fill("LIVE_ENABLED", "false")
    fill("COOKIE_SECURE", "false")
    if (
        values["APP_ENV"] != "development"
        or values["TRADING_MODE"] != "OBSERVATION"
        or values["LIVE_ENABLED"].lower() != "false"
        or values["COOKIE_SECURE"].lower() != "false"
    ):
        raise BootstrapError("LOCAL_MODE_CONFLICT")
    dburl = values.get("DATABASE_URL", "")
    parsed = make_url(dburl) if dburl else None
    placeholder = parsed is not None and parsed.password == "replace-locally"
    password = values.get("POSTGRES_PASSWORD") or (
        parsed.password if parsed and not placeholder else None
    )
    if existing_volume and not password:
        raise BootstrapError("EXISTING_VOLUME_PASSWORD_REQUIRED")
    if parsed and (
        parsed.drivername != "postgresql+psycopg"
        or parsed.host != "db"
        or parsed.port not in (None, 5432)
        or parsed.query
    ):
        raise BootstrapError("EXISTING_DATABASE_NOT_LOCAL_COMPOSE")
    fill("POSTGRES_USER", parsed.username if parsed and parsed.username else "algotrade")
    fill("POSTGRES_DB", parsed.database if parsed and parsed.database else "algotrade")
    for key in ("POSTGRES_USER", "POSTGRES_DB"):
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", values[key]):
            raise BootstrapError("INVALID_DATABASE_NAME")
    fill("POSTGRES_PASSWORD", password or secrets.token_urlsafe(32))
    if parsed and not placeholder:
        if (
            parsed.username != values["POSTGRES_USER"]
            or parsed.database != values["POSTGRES_DB"]
            or parsed.password != values["POSTGRES_PASSWORD"]
        ):
            raise BootstrapError("DATABASE_CREDENTIAL_CONFLICT")
    else:
        dburl = URL.create(
            "postgresql+psycopg",
            username=values["POSTGRES_USER"],
            password=values["POSTGRES_PASSWORD"],
            host="db",
            port=5432,
            database=values["POSTGRES_DB"],
        ).render_as_string(hide_password=False)
        values["DATABASE_URL"] = dburl
        changed["DATABASE_URL"] = dburl
    chosen = int(values.get("APP_BIND_PORT") or port or 8000)
    if not 1024 <= chosen <= 65535 or (port is not None and chosen != port):
        raise BootstrapError("LOCAL_PORT_CONFLICT")
    fill("APP_BIND_PORT", str(chosen))
    origin = f"http://127.0.0.1:{chosen}"
    if existing is None:
        values["ALLOWED_ORIGINS"] = json.dumps([origin, f"http://localhost:{chosen}"])
        changed["ALLOWED_ORIGINS"] = values["ALLOWED_ORIGINS"]
    fill("ALLOWED_HOSTS", json.dumps(["localhost", "127.0.0.1"]))
    fill("ALLOWED_ORIGINS", json.dumps([origin, f"http://localhost:{chosen}"]))
    fill("COMPOSE_PROJECT_NAME", project_name(values))
    for parent in (root / ".local", root / ".local" / "runtime"):
        if parent.is_symlink():
            raise BootstrapError("SYMLINKED_SECRET_DIRECTORY")
    password_path = root / ".local" / "runtime" / "admin-password.txt"
    generated = not bool(values.get("ADMIN_PASSWORD_HASH"))
    admin_password = None
    if generated:
        candidate = private_read(password_path)
        admin_password = candidate.strip() if candidate is not None else secrets.token_urlsafe(32)
        if not 12 <= len(admin_password) <= 256 or any(char in admin_password for char in "\r\n"):
            raise BootstrapError("INVALID_LOCAL_ADMIN_PASSWORD")
        fill("ADMIN_PASSWORD_HASH", PasswordHasher().hash(admin_password))
    else:
        candidate = private_read(password_path)
        if candidate:
            try:
                if PasswordHasher().verify(values["ADMIN_PASSWORD_HASH"], candidate.strip()):
                    admin_password = candidate.strip()
            except Argon2Error:
                pass
    options = {
        key: field.get_default(call_default_factory=True)
        for key, field in Settings.model_fields.items()
    }
    options.update({key.lower(): value for key, value in values.items()})
    for key in ("allowed_hosts", "allowed_origins"):
        if isinstance(options.get(key), str):
            options[key] = json.loads(options[key])
    config = Settings(_env_file=None, **options)
    if origin not in config.allowed_origins or "127.0.0.1" not in config.allowed_hosts:
        raise BootstrapError("LOCAL_ORIGIN_CONFLICT")
    lines = original.splitlines()
    rendered = []
    for line in lines:
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match[1] in changed:
            key = match[1]
            value = changed.pop(key)
            if "'" in value or "\n" in value or "\r" in value:
                raise BootstrapError("ENV_VALUE_ENCODING")
            rendered.append(f"{key}='{value}'")
        else:
            rendered.append(line)
    for key, value in changed.items():
        if "'" in value or "\n" in value or "\r" in value:
            raise BootstrapError("ENV_VALUE_ENCODING")
        rendered.append(f"{key}='{value}'")
    # Validate all encoded settings before writing either secret file.
    if generated:
        secret_directory(root)
        private_write(password_path, admin_password + "\n")
    private_write(destination, "\n".join(rendered) + "\n")
    return {
        "project": project_name(values),
        "port": chosen,
        "origin": origin,
        "admin_password_file": str(password_path) if generated or admin_password else None,
        "values": values,
        "admin_password": admin_password,
    }


def docker_binary() -> str:
    executable = shutil.which("docker")
    fallback = Path("/Applications/Docker.app/Contents/Resources/bin/docker")
    if executable:
        return executable
    if fallback.is_file():
        return str(fallback)
    raise BootstrapError("DOCKER_NOT_INSTALLED")


def invoke(command: list[str], *, environment=None, timeout=30) -> str:
    try:
        result = subprocess.run(
            command, env=environment, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode:
            raise BootstrapError("LOCAL_RUNTIME_COMMAND_FAILED")
        return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        raise BootstrapError("LOCAL_RUNTIME_COMMAND_UNAVAILABLE") from None


def local_engine(executable: str) -> None:
    host = os.environ.get("DOCKER_HOST")
    if host:
        if not host.startswith("unix://"):
            raise BootstrapError("LOCAL_UNIX_DOCKER_REQUIRED")
    else:
        contexts = json.loads(invoke([executable, "context", "inspect"]))
        if not contexts[0]["Endpoints"]["docker"]["Host"].startswith("unix://"):
            raise BootstrapError("LOCAL_UNIX_DOCKER_REQUIRED")
    if invoke([executable, "info", "--format", "{{.OSType}}"]).strip() != "linux":
        raise BootstrapError("LOCAL_DOCKER_ENGINE_UNAVAILABLE")


def oauth_volume_enabled(project: str, volumes: str, requested: bool) -> bool:
    # Persist opt-in through Docker's existing project-scoped volume, not another secret file.
    return requested or f"{project}_upstox_oauth" in volumes.splitlines()


def validate_oauth_mount(configuration: dict, project: str, enabled: bool) -> None:
    services = configuration["services"]
    app = services["app"]
    mounts = app.get("volumes", [])
    if not enabled:
        if mounts or app["environment"].get("UPSTOX_OAUTH_VAULT_DIR"):
            raise BootstrapError("OAUTH_VOLUME_OPT_IN_REQUIRED")
        return
    expected = configuration.get("volumes", {}).get("upstox_oauth", {})
    if (
        app["environment"].get("UPSTOX_OAUTH_VAULT_DIR") != OAUTH_VAULT_PATH
        or len(mounts) != 1
        or mounts[0].get("type") != "volume"
        or mounts[0].get("source") != "upstox_oauth"
        or mounts[0].get("target") != OAUTH_VAULT_PATH
        or mounts[0].get("read_only", False)
        or mounts[0].get("volume", {}).get("nocopy", False)
        or mounts[0].get("volume", {}).get("subpath")
        or expected.get("name") != f"{project}_upstox_oauth"
        or expected.get("external", False)
        or expected.get("driver", "local") != "local"
        or expected.get("driver_opts")
        or not app.get("read_only")
        or "ALL" not in app.get("cap_drop", [])
        or "no-new-privileges:true" not in app.get("security_opt", [])
        or services["migrate"].get("volumes")
    ):
        raise BootstrapError("UNSAFE_OAUTH_VOLUME_CONFIGURATION")


def start_runtime(
    root: Path,
    prepared: dict,
    executable: str,
    *,
    oauth_vault: bool = False,
    environment_file: Path | None = None,
) -> dict:
    # An explicit private test env file lets the isolated verifier exercise this exact path.
    environment_file = environment_file or root / ".env"
    values = prepared["values"]
    volumes = invoke([executable, "volume", "ls", "--format", "{{.Name}}"])
    oauth_vault = oauth_volume_enabled(prepared["project"], volumes, oauth_vault)
    environment = {
        **os.environ,
        **values,
        "APP_ENV_FILE": str(environment_file),
        "PATH": str(Path(executable).parent) + os.pathsep + os.environ.get("PATH", ""),
    }
    base = [
        executable,
        "compose",
        "--project-name",
        prepared["project"],
        "--project-directory",
        str(root),
        "--file",
        str(root / "docker-compose.yml"),
        "--env-file",
        str(environment_file),
    ]
    if oauth_vault:
        base.extend(["--file", str(root / "docker-compose.oauth.yml")])
    configuration = json.loads(
        invoke([*base, "config", "--format", "json"], environment=environment)
    )
    services = configuration["services"]
    validate_oauth_mount(configuration, prepared["project"], oauth_vault)
    if services["db"].get("ports") or services["app"]["ports"][0]["host_ip"] != "127.0.0.1":
        raise BootstrapError("UNSAFE_LOCAL_PORT_BINDING")
    if services["app"]["environment"]["ADMIN_PASSWORD_HASH"] not in (
        values["ADMIN_PASSWORD_HASH"],
        values["ADMIN_PASSWORD_HASH"].replace("$", "$$"),
    ):
        raise BootstrapError("COMPOSE_SECRET_INTERPOLATION")
    invoke(
        [*base, "up", "--build", "--wait", "--wait-timeout", "180"],
        environment=environment,
        timeout=300,
    )
    result = {
        "state": "READY_LOCAL",
        "url": prepared["origin"],
        "project": prepared["project"],
        "admin_password_file": prepared["admin_password_file"],
        "login_verified": False,
        "entries_enabled": False,
        "live_enabled": False,
        "recording_started": False,
        "oauth_vault_enabled": oauth_vault,
    }
    with httpx.Client(base_url=prepared["origin"], timeout=10, trust_env=False) as client:
        if (
            client.get("/health/ready").status_code != 200
            or client.get("/api/overview").status_code != 401
        ):
            raise BootstrapError("LOCAL_RUNTIME_HEALTH_FAILED")
        if prepared["admin_password"]:
            login = client.post(
                "/api/auth/login",
                json={"password": prepared["admin_password"]},
                headers={"Origin": prepared["origin"]},
            )
            if login.status_code != 200:
                raise BootstrapError("LOCAL_ADMIN_LOGIN_FAILED")
            overview = client.get("/api/overview")
            if (
                overview.status_code != 200
                or overview.json()["live_enabled"]
                or overview.json()["entries_enabled"]
            ):
                raise BootstrapError("LOCAL_MODE_VERIFICATION_FAILED")
            report = client.get(
                "/api/observations/preflight", params={"instrument_key": "NSE_INDEX|Nifty 50"}
            )
            if report.status_code != 200:
                raise BootstrapError("LOCAL_PREFLIGHT_FAILED")
            result["capture_preflight_state"] = report.json()["state"]
            result["capture_blockers"] = report.json()["blockers"]
            logout = client.post(
                "/api/auth/logout",
                headers={"Origin": prepared["origin"], "X-CSRF-Token": login.json()["csrf_token"]},
            )
            if logout.status_code != 204:
                raise BootstrapError("LOCAL_LOGOUT_FAILED")
            result["login_verified"] = True
    return result


@contextmanager
def bootstrap_lock(root: Path):
    directory = secret_directory(root)
    descriptor = os.open(
        directory / "bootstrap.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or info.st_nlink != 1 or not stat.S_ISREG(info.st_mode):
            raise BootstrapError("UNSAFE_BOOTSTRAP_LOCK")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BootstrapError("BOOTSTRAP_ALREADY_RUNNING") from None
        yield
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--oauth-vault", action="store_true", help="Opt in to durable private OAuth storage"
    )
    args = parser.parse_args()
    with bootstrap_lock(ROOT):
        executable = docker_binary()
        local_engine(executable)
        values = assignments(private_read(ROOT / ".env") or "")
        project = project_name(values)
        volumes = invoke([executable, "volume", "ls", "--format", "{{.Name}}"])
        existing = f"{project}_postgres_data" in volumes.splitlines()
        prepared = prepare_runtime(ROOT, existing_volume=existing, port=args.port)
        print(
            "Protected local settings prepared; starting private PostgreSQL and loopback app.",
            flush=True,
        )
        print(
            json.dumps(start_runtime(ROOT, prepared, executable, oauth_vault=args.oauth_vault)),
            flush=True,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error) if isinstance(error, BootstrapError) else "LOCAL_BOOTSTRAP_FAILED"
        raise SystemExit(
            f"Bootstrap stopped: {code}. Existing data/settings were not reset."
        ) from None
