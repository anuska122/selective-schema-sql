import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PG_HOST = "127.0.0.1"
PG_PORT = 5434
PG_DATABASE = "bird"
RO_ROLE = "sqlagent_ro"


def load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _dsn(user: str, password_var: str) -> str:
    load_env()
    return (
        f"host={PG_HOST} port={PG_PORT} dbname={PG_DATABASE} user={user} password={os.environ[password_var]}"
    )


def ro_dsn() -> str:
    return _dsn(RO_ROLE, "SQLAGENT_RO_PASSWORD")


def admin_dsn() -> str:
    return _dsn("postgres", "POSTGRES_ADMIN_PASSWORD")
