"""
Strict safety guards for test database connections.

Guarantees that tests, migrations, and test scripts NEVER connect to
a remote/production database (such as Supabase) or touch non-test data.
"""
import urllib.parse
from typing import Set

ALLOWED_HOSTS: Set[str] = {"localhost", "127.0.0.1", "::1"}
FORBIDDEN_QUERY_KEYS: Set[str] = {"host", "hostaddr", "service"}


def validate_test_database_url(url: str, context: str = "Test DB") -> None:
    """
    Validate that a test database URL strictly points to a local test database.

    Rules:
      1. Host must be localhost, 127.0.0.1, or ::1.
      2. Database name must end in '_test' (e.g. 'sais_test').
      3. Query string must not contain host, hostaddr, or service parameters.
    """
    if not url or not isinstance(url, str):
        raise RuntimeError(f"[{context}] Database URL is empty or invalid.")

    parsed = urllib.parse.urlsplit(url)

    # 1. Reject query parameters that could override connection destination
    if parsed.query:
        params = urllib.parse.parse_qs(parsed.query)
        found = FORBIDDEN_QUERY_KEYS.intersection(k.lower() for k in params.keys())
        if found:
            raise RuntimeError(
                f"[{context}] Forbidden query parameter(s) in database URL: {sorted(found)}. "
                "Overriding host/service via query parameters is strictly forbidden."
            )

    # 2. Host validation
    hostname = (parsed.hostname or "").strip().lower()
    if hostname not in ALLOWED_HOSTS:
        raise RuntimeError(
            f"[{context}] Non-local database host '{hostname}' is strictly forbidden. "
            f"Host must be one of: {sorted(ALLOWED_HOSTS)}."
        )

    # 3. Database name validation
    db_name = (parsed.path or "").strip("/").split("?")[0].strip().lower()
    if not db_name or not db_name.endswith("_test"):
        raise RuntimeError(
            f"[{context}] Target database name '{db_name}' is not allowed for testing. "
            "Test database name must strictly end in '_test' (e.g. 'sais_test')."
        )


def validate_admin_database_url(url: str, context: str = "Admin DB") -> None:
    """
    Validate that the administrative connection used to create/drop the test DB
    strictly points to a local PostgreSQL instance.

    Rules:
      1. Host must be localhost, 127.0.0.1, or ::1.
      2. Database name must be 'postgres' or 'template1'.
      3. Query string must not contain host, hostaddr, or service parameters.
    """
    if not url or not isinstance(url, str):
        raise RuntimeError(f"[{context}] Admin database URL is empty or invalid.")

    parsed = urllib.parse.urlsplit(url)

    if parsed.query:
        params = urllib.parse.parse_qs(parsed.query)
        found = FORBIDDEN_QUERY_KEYS.intersection(k.lower() for k in params.keys())
        if found:
            raise RuntimeError(
                f"[{context}] Forbidden query parameter(s) in admin database URL: {sorted(found)}."
            )

    hostname = (parsed.hostname or "").strip().lower()
    if hostname not in ALLOWED_HOSTS:
        raise RuntimeError(
            f"[{context}] Non-local host '{hostname}' is strictly forbidden for admin connections. "
            f"Host must be one of: {sorted(ALLOWED_HOSTS)}."
        )

    db_name = (parsed.path or "").strip("/").split("?")[0].strip().lower()
    if db_name not in ("postgres", "template1"):
        raise RuntimeError(
            f"[{context}] Admin database name '{db_name}' is invalid. "
            "Must be 'postgres' or 'template1'."
        )

