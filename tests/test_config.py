"""Config must never hand agent code anything but the read-only role."""

import pytest

from sqlagent import config


@pytest.fixture
def clean_env(monkeypatch):
    for var in ("SQLAGENT_RO_PASSWORD", "POSTGRES_ADMIN_PASSWORD", "EXAMPLE_VAR"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_load_env_parses_and_skips_comments(tmp_path, clean_env):
    env = tmp_path / ".env"
    env.write_text("# a comment\nEXAMPLE_VAR = value=with=equals\nnot a pair\n")
    config.load_env(env)
    assert config.os.environ["EXAMPLE_VAR"] == "value=with=equals"


def test_load_env_does_not_override_real_environment(tmp_path, clean_env):
    clean_env.setenv("EXAMPLE_VAR", "from-shell")
    env = tmp_path / ".env"
    env.write_text("EXAMPLE_VAR=from-file\n")
    config.load_env(env)
    assert config.os.environ["EXAMPLE_VAR"] == "from-shell"


def test_load_env_missing_file_is_noop(tmp_path, clean_env):
    config.load_env(tmp_path / "does-not-exist")


def test_ro_dsn_uses_read_only_role_and_never_admin_password(clean_env, tmp_path):
    clean_env.setattr(config, "ROOT", tmp_path)  # ignore any real .env
    clean_env.setenv("SQLAGENT_RO_PASSWORD", "ro-secret")
    clean_env.setenv("POSTGRES_ADMIN_PASSWORD", "admin-secret")
    dsn = config.ro_dsn()
    assert "user=sqlagent_ro" in dsn
    assert "password=ro-secret" in dsn
    assert "admin-secret" not in dsn
    assert "user=postgres" in config.admin_dsn()


def test_ro_dsn_fails_loudly_without_password(clean_env, tmp_path):
    clean_env.setattr(config, "ROOT", tmp_path)
    with pytest.raises(KeyError):
        config.ro_dsn()
