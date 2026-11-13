"""
Unit tests for test database safety guards (Phase 8F).
"""
import pytest
from app.core.test_safety import validate_test_database_url, validate_admin_database_url


def test_safety_guard_refuses_supabase_url():
    """Safety guard must strictly refuse Supabase remote URLs."""
    supabase_url = "postgresql+asyncpg://postgres:secret@db.xyzcompany.supabase.co:5432/postgres"
    with pytest.raises(RuntimeError) as exc_info:
        validate_test_database_url(supabase_url)
    assert "Non-local database host 'db.xyzcompany.supabase.co' is strictly forbidden" in str(exc_info.value)


def test_safety_guard_refuses_remote_ip_url():
    """Safety guard must strictly refuse non-localhost IPs."""
    remote_ip_url = "postgresql+asyncpg://postgres:secret@192.168.1.100:5432/sais_test"
    with pytest.raises(RuntimeError) as exc_info:
        validate_test_database_url(remote_ip_url)
    assert "Non-local database host '192.168.1.100' is strictly forbidden" in str(exc_info.value)


def test_safety_guard_refuses_production_or_default_db_name():
    """Safety guard must refuse database names that do not end in '_test'."""
    local_prod_url = "postgresql+asyncpg://postgres:secret@localhost:5432/sais"
    with pytest.raises(RuntimeError) as exc_info:
        validate_test_database_url(local_prod_url)
    assert "Target database name 'sais' is not allowed for testing" in str(exc_info.value)

    local_postgres_url = "postgresql+asyncpg://postgres:secret@localhost:5432/postgres"
    with pytest.raises(RuntimeError) as exc_info:
        validate_test_database_url(local_postgres_url)
    assert "Target database name 'postgres' is not allowed for testing" in str(exc_info.value)


@pytest.mark.parametrize("param", ["host=db.supabase.co", "hostaddr=10.0.0.1", "service=prod_service"])
def test_safety_guard_refuses_destination_query_parameters(param):
    """Safety guard must refuse any query parameters that could override connection destination."""
    url_with_param = f"postgresql+asyncpg://postgres:secret@localhost:5432/sais_test?{param}"
    with pytest.raises(RuntimeError) as exc_info:
        validate_test_database_url(url_with_param)
    assert "Forbidden query parameter(s) in database URL" in str(exc_info.value)


def test_safety_guard_accepts_valid_localhost_test_db():
    """Safety guard must accept localhost / 127.0.0.1 / ::1 ending in _test."""
    valid_urls = [
        "postgresql+asyncpg://postgres:secret@localhost:5432/sais_test",
        "postgresql+asyncpg://sais_test_user:secret@127.0.0.1:5432/sais_test",
        "postgresql+asyncpg://postgres:secret@[::1]:5432/sais_test",
    ]
    for url in valid_urls:
        validate_test_database_url(url)  # Must not raise


def test_admin_safety_guard_refuses_remote_host():
    """Admin DB safety guard must refuse remote connections."""
    remote_admin = "postgresql://postgres:secret@db.xyz.supabase.co:5432/postgres"
    with pytest.raises(RuntimeError) as exc_info:
        validate_admin_database_url(remote_admin)
    assert "Non-local host" in str(exc_info.value)


def test_admin_safety_guard_refuses_non_admin_db():
    """Admin DB safety guard must only allow 'postgres' or 'template1'."""
    invalid_admin = "postgresql://postgres:secret@localhost:5432/sais_test"
    with pytest.raises(RuntimeError) as exc_info:
        validate_admin_database_url(invalid_admin)
    assert "Admin database name 'sais_test' is invalid" in str(exc_info.value)


def test_admin_safety_guard_accepts_valid_localhost_postgres():
    """Admin DB safety guard allows localhost postgres."""
    validate_admin_database_url("postgresql://postgres:secret@localhost:5432/postgres")
    validate_admin_database_url("postgresql://postgres:secret@127.0.0.1:5432/template1")


@pytest.mark.postgres
def test_conftest_guard_validates_postgres_url(postgres_url):
    """Fixture postgres_url triggers Guard Place 2."""
    assert postgres_url.endswith("_test")

