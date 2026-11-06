"""Run the suite against an ephemeral, SCRAM-authenticated local PostgreSQL cluster.

No downloads or system installation. Supply an existing native PostgreSQL bin directory.
Only the fresh temporary cluster is started/stopped; an existing database is never used.
"""

import argparse
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    return subprocess.run(command, check=True, cwd=ROOT, **kwargs)


@contextmanager
def cluster_directory():
    directory = Path(tempfile.mkdtemp(prefix="algotrade-pg-"))
    try:
        yield directory
    finally:
        if (directory / "data" / "postmaster.pid").exists():
            print(f"Retaining cluster with possible running server: {directory}", flush=True)
        else:
            shutil.rmtree(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", required=True, type=Path)
    parser.add_argument(
        "--check-public-instruments",
        action="store_true",
        help="After isolated tests, migrate this temporary DB and import the real public NSE file",
    )
    args = parser.parse_args()
    binaries = args.bin_dir.resolve()
    for name in ("initdb", "pg_ctl", "postgres"):
        if not (binaries / name).is_file():
            parser.error(f"Missing PostgreSQL binary: {name}")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    # Releasing the port before PostgreSQL binds is unavoidable; a collision fails startup.
    with cluster_directory() as directory:
        data = directory / "data"
        password_file = directory / "password"
        bootstrap_password, app_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        password_file.touch(mode=0o600)
        password_file.write_text(bootstrap_password)
        run(
            [
                str(binaries / "initdb"),
                "-D",
                str(data),
                "--username=algotrade_bootstrap",
                f"--pwfile={password_file}",
                "--auth-local=scram-sha-256",
                "--auth-host=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
            ],
            capture_output=True,
        )
        password_file.unlink()
        control = [str(binaries / "pg_ctl"), "-D", str(data), "-w", "-t", "30"]
        started = False
        try:
            # Mark before startup so cleanup is attempted even after a startup timeout.
            started = True
            run(
                [
                    *control,
                    "-l",
                    str(directory / "postgres.log"),
                    "-o",
                    f"-h 127.0.0.1 -p {port} -k '' -c timezone=UTC",
                    "start",
                ],
                capture_output=True,
            )
            with psycopg.connect(
                host="127.0.0.1",
                port=port,
                dbname="postgres",
                user="algotrade_bootstrap",
                password=bootstrap_password,
                autocommit=True,
            ) as connection:
                connection.execute(
                    sql.SQL(
                        "CREATE ROLE algotrade_verify LOGIN PASSWORD {} "
                        "NOSUPERUSER NOCREATEDB NOCREATEROLE"
                    ).format(sql.Literal(app_password))
                )
                connection.execute("CREATE DATABASE algotrade_test OWNER algotrade_verify")
                version = connection.execute("SHOW server_version").fetchone()[0]
            url = URL.create(
                "postgresql+psycopg",
                username="algotrade_verify",
                password=app_password,
                host="127.0.0.1",
                port=port,
                database="algotrade_test",
            )
            environment = os.environ.copy()
            environment.update(
                {
                    "TRADING_MODE": "OBSERVATION",
                    "LIVE_ENABLED": "false",
                    "TEST_POSTGRES_URL": url.render_as_string(hide_password=False),
                }
            )
            print(
                f"PostgreSQL {version}; loopback only, SCRAM; non-superuser test role.", flush=True
            )
            run([sys.executable, "-m", "pytest", "--tb=short"], env=environment)
            if args.check_public_instruments:
                live_data_environment = {
                    **environment,
                    "APP_ENV": "test",
                    "DATABASE_URL": url.render_as_string(hide_password=False),
                }
                run([sys.executable, "-m", "alembic", "upgrade", "head"], env=live_data_environment)
                run([sys.executable, "-m", "scripts.sync_instruments"], env=live_data_environment)
        finally:
            if started:
                stopped = subprocess.run(
                    [*control, "-m", "fast", "stop"],
                    cwd=ROOT,
                    capture_output=True,
                )
                # Never remove a data directory while its server may still be running.
                if stopped.returncode and (data / "postmaster.pid").exists():
                    raise RuntimeError("Temporary server failed to stop; manual cleanup required")
            print("Temporary PostgreSQL stopped; no persistent database configured.", flush=True)


if __name__ == "__main__":
    main()
