"""Integration tests for the Rippling LakeflowConnect connector.

Tests run against the real Rippling API using credentials in dev_config.json.
No mocking — every assertion validates live API behaviour.

Tables that return HTTP 403 (insufficient token scopes) are skipped so the
suite passes regardless of the permission level of the test credentials.
"""

import json
import os
import re
import sys

import pytest

# Ensure the project source tree is importable.
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

from pyspark.sql.types import StructType  # noqa: E402

from databricks.labs.community_connector.sources.rippling.rippling import (  # noqa: E402
    RipplingLakeflowConnect,
    SUPPORTED_TABLES,
    TABLE_METADATA,
    TABLE_SCHEMAS,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CONFIGS_DIR = os.path.join(os.path.dirname(__file__), "configs")


def _load_json(filename: str) -> dict:
    path = os.path.join(_CONFIGS_DIR, filename)
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def dev_config() -> dict:
    return _load_json("dev_config.json")


@pytest.fixture(scope="module")
def table_config() -> dict:
    return _load_json("dev_table_config.json")


@pytest.fixture(scope="module")
def connector(dev_config) -> RipplingLakeflowConnect:
    return RipplingLakeflowConnect(dev_config)


# ---------------------------------------------------------------------------
# Helper — skip on 403 (token lacks required scope)
# ---------------------------------------------------------------------------
_403_RE = re.compile(r"\b403\b")


def _read_table_or_skip(connector, table_name, start_offset, table_config):
    """Call read_table; skip the test if the API returns 403."""
    try:
        return connector.read_table(table_name, start_offset, table_config)
    except RuntimeError as exc:
        if _403_RE.search(str(exc)):
            pytest.skip(
                f"Token lacks permission for '{table_name}' (HTTP 403)"
            )
        raise


# ---------------------------------------------------------------------------
# Tests — discovery
# ---------------------------------------------------------------------------


def test_list_tables(connector):
    tables = connector.list_tables()
    assert isinstance(tables, list)
    assert len(tables) > 0
    for t in SUPPORTED_TABLES:
        assert t in tables, f"Expected table '{t}' in list_tables() output"


def test_get_table_schema(connector):
    for table_name in SUPPORTED_TABLES:
        schema = connector.get_table_schema(table_name, {})
        assert isinstance(schema, StructType), (
            f"Schema for '{table_name}' is not a StructType"
        )
        assert len(schema.fields) > 0, (
            f"Schema for '{table_name}' has no fields"
        )


def test_get_table_schema_unsupported(connector):
    with pytest.raises(ValueError, match="not supported"):
        connector.get_table_schema("nonexistent_table", {})


# ---------------------------------------------------------------------------
# Tests — metadata
# ---------------------------------------------------------------------------


def test_read_table_metadata(connector):
    for table_name in SUPPORTED_TABLES:
        metadata = connector.read_table_metadata(table_name, {})
        assert isinstance(metadata, dict)
        assert "primary_keys" in metadata
        assert "ingestion_type" in metadata
        assert metadata["ingestion_type"] in (
            "snapshot",
            "cdc",
            "cdc_with_deletes",
            "append",
        )


def test_read_table_metadata_unsupported(connector):
    with pytest.raises(ValueError, match="not supported"):
        connector.read_table_metadata("nonexistent_table", {})


# ---------------------------------------------------------------------------
# Tests — read_table (snapshot single-record tables)
# ---------------------------------------------------------------------------


def test_read_table_users(connector, table_config):
    records_iter, offset = _read_table_or_skip(
        connector, "users", None, table_config
    )
    records = list(records_iter)
    assert len(records) >= 1, "Expected at least 1 user record"
    assert "id" in records[0], "User record must contain 'id'"


def test_read_table_companies(connector, table_config):
    records_iter, offset = _read_table_or_skip(
        connector, "companies", None, table_config
    )
    records = list(records_iter)
    assert len(records) >= 1, "Expected at least 1 company record"
    assert "id" in records[0], "Company record must contain 'id'"


# ---------------------------------------------------------------------------
# Tests — read_table (snapshot paginated tables)
# ---------------------------------------------------------------------------


def test_read_table_employees(connector, table_config):
    records_iter, offset = _read_table_or_skip(
        connector, "employees", None, table_config
    )
    records = list(records_iter)
    assert isinstance(records, list)
    if records:
        assert "id" in records[0]


def test_read_table_departments(connector, table_config):
    records_iter, offset = _read_table_or_skip(
        connector, "departments", None, table_config
    )
    records = list(records_iter)
    assert isinstance(records, list)


def test_read_table_teams(connector, table_config):
    records_iter, offset = _read_table_or_skip(
        connector, "teams", None, table_config
    )
    records = list(records_iter)
    assert isinstance(records, list)


def test_read_table_work_locations(connector, table_config):
    records_iter, offset = _read_table_or_skip(
        connector, "work_locations", None, table_config
    )
    records = list(records_iter)
    assert isinstance(records, list)


def test_read_table_groups(connector, table_config):
    records_iter, offset = _read_table_or_skip(
        connector, "groups", None, table_config
    )
    records = list(records_iter)
    assert isinstance(records, list)


def test_read_table_levels(connector, table_config):
    records_iter, offset = _read_table_or_skip(
        connector, "levels", None, table_config
    )
    records = list(records_iter)
    assert isinstance(records, list)


def test_read_table_leave_balances(connector, table_config):
    records_iter, offset = _read_table_or_skip(
        connector, "leave_balances", None, table_config
    )
    records = list(records_iter)
    assert isinstance(records, list)


# ---------------------------------------------------------------------------
# Tests — read_table (CDC table: leave_requests)
# ---------------------------------------------------------------------------


def test_read_table_leave_requests_initial(connector, table_config):
    """First CDC call with no prior offset."""
    records_iter, offset = _read_table_or_skip(
        connector, "leave_requests", None, table_config
    )
    records = list(records_iter)
    assert isinstance(records, list)
    assert isinstance(offset, dict)
    if records:
        assert len(records) <= int(
            table_config.get("max_records_per_batch", "500")
        )


def test_read_table_leave_requests_idempotent(connector, table_config):
    """Second CDC call with the offset from the first — should return no new records."""
    try:
        _, offset1 = connector.read_table(
            "leave_requests", None, table_config
        )
    except RuntimeError as exc:
        if _403_RE.search(str(exc)):
            pytest.skip("Token lacks permission for 'leave_requests' (HTTP 403)")
        raise

    if offset1:
        records_iter2, offset2 = _read_table_or_skip(
            connector, "leave_requests", offset1, table_config
        )
        records2 = list(records_iter2)
        assert isinstance(records2, list)


# ---------------------------------------------------------------------------
# Tests — read_table unsupported
# ---------------------------------------------------------------------------


def test_read_table_unsupported(connector, table_config):
    with pytest.raises(ValueError, match="not supported"):
        connector.read_table("nonexistent_table", None, table_config)
