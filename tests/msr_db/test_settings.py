import pytest
from psycopg.conninfo import conninfo_to_dict

from msr_db.registry import like_prefix
from msr_db.settings import DatabaseSettings, database_configured


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("MSR_DB_HOST", "MSR_DB_NAME", "MSR_DB_API_PASSWORD", "MSR_DB_WORKER_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MSR_ENV", "local")
    return monkeypatch


def test_login_role_carries_the_environment_suffix(env: pytest.MonkeyPatch) -> None:
    env.setenv("MSR_DB_HOST", "db.internal")
    env.setenv("MSR_DB_API_PASSWORD", "s3cret")
    info = conninfo_to_dict(DatabaseSettings().conninfo("api"))
    assert info == {
        "host": "db.internal",
        "port": "5432",
        "dbname": "msr",
        "user": "msr_api_local",
        "password": "s3cret",
        "application_name": "msr-api",
    }
    assert DatabaseSettings().user("reader") == "data_reader_local"


def test_a_missing_password_names_its_variable(env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="MSR_DB_WORKER_PASSWORD"):
        DatabaseSettings().conninfo("worker")


def test_configured_only_with_a_host(env: pytest.MonkeyPatch) -> None:
    assert not database_configured()
    env.setenv("MSR_DB_HOST", "postgres")
    assert database_configured()


@pytest.mark.parametrize(
    ("prefix", "pattern"),
    [("cat", "cat%"), ("100%", "100\\%%"), ("a_b", "a\\_b%"), ("c:\\x", "c:\\\\x%")],
)
def test_like_prefix_escapes_wildcards(prefix: str, pattern: str) -> None:
    assert like_prefix(prefix) == pattern
