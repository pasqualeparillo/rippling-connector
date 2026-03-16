"""Unit tests for the Rippling LakeflowConnect connector.

All HTTP calls are mocked — no real API calls are made.
Tests cover:
- list_tables: returns all 14 supported tables
- get_table_schema: returns valid StructType for each table
- read_table_metadata: correct primary_keys, ingestion_type, cursor_field
- read_table: correct records for every table, including pagination
- CDC vs snapshot ingestion behaviour
- Cursor-based (REST API) and offset-based (legacy API) pagination
- Error handling (missing token, unsupported table)
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure project source tree is importable.
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

from pyspark.sql.types import StructType  # noqa: E402

from databricks.labs.community_connector.sources.rippling.rippling import (  # noqa: E402
    RipplingLakeflowConnect,
    SUPPORTED_TABLES,
    TABLE_METADATA,
    _TABLE_SCHEMAS,
    _REST_ENDPOINTS,
    _LEGACY_ENDPOINTS,
    _DERIVED_TABLES,
    _CDC_TABLES,
    _SNAPSHOT_TABLES,
    BASE_URL,
    LEGACY_BASE_URL,
    DEFAULT_PAGE_SIZE,
    CDC_CURSOR_FIELD,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CONFIGS_DIR = os.path.join(os.path.dirname(__file__), "configs")


def _load_json(filename: str) -> dict:
    path = os.path.join(_CONFIGS_DIR, filename)
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def dev_config() -> dict:
    return _load_json("dev_config.json")


@pytest.fixture
def connector(dev_config) -> RipplingLakeflowConnect:
    """Create a connector with mocked session so no real HTTP calls are made."""
    with patch("requests.Session") as mock_session_cls:
        mock_session_cls.return_value = MagicMock()
        conn = RipplingLakeflowConnect(dev_config)
    return conn


# ---------------------------------------------------------------------------
# Mock response helper
# ---------------------------------------------------------------------------


def _mock_response(status_code: int = 200, json_data=None, headers=None):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = json.dumps(json_data) if json_data is not None else ""
    resp.headers = headers or {}
    return resp


# ---------------------------------------------------------------------------
# Sample records for each table
# ---------------------------------------------------------------------------

SAMPLE_RECORDS = {
    "companies": {
        "id": "comp_1",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-06-01T00:00:00Z",
        "name": "Acme Corp",
        "legal_name": "Acme Corporation LLC",
        "primary_email": "admin@acme.com",
        "phone": "+1-555-0100",
        "address": {
            "streetLine1": "123 Main St",
            "streetLine2": "",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94105",
            "country": "US",
            "phone": "+1-555-0100",
            "isRemote": False,
        },
        "parent_legal_entity_id": None,
        "legal_entities_id": ["le_1", "le_2"],
        "legal_entities": [
            {
                "id": "le_1",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-06-01T00:00:00Z",
                "tax_identifier": "12-3456789",
                "country": {"code": "US"},
                "legal_name": "Acme US",
                "entity_level": "subsidiary",
                "registration_date": "2024-01-01",
                "mailing_address": {
                    "streetLine1": "123 Main St",
                    "streetLine2": "",
                    "city": "San Francisco",
                    "state": "CA",
                    "zip": "94105",
                    "country": "US",
                    "phone": None,
                    "isRemote": False,
                },
                "physical_address": {
                    "streetLine1": "123 Main St",
                    "streetLine2": "",
                    "city": "San Francisco",
                    "state": "CA",
                    "zip": "94105",
                    "country": "US",
                    "phone": None,
                    "isRemote": False,
                },
                "parent_id": None,
                "management_type": "direct",
            }
        ],
    },
    "departments": {
        "id": "dept_1",
        "name": "Engineering",
        "parent": None,
    },
    "employment_types": {
        "id": "et_1",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-06-01T00:00:00Z",
        "label": "Full-time",
        "name": "full_time",
        "type": "employee",
        "compensation_time_period": "annual",
    },
    "leave_balances": {
        "role": "role_1",
        "balances": [
            {
                "company_leave_type_id": "lt_1",
                "unlimited": False,
                "remaining_balance": 80,
                "remaining_balance_with_future": 80,
            }
        ],
    },
    "leave_requests": {
        "id": "lr_1",
        "role": "role_1",
        "roleName": "Engineer",
        "status": "approved",
        "startDate": "2024-07-01",
        "endDate": "2024-07-05",
        "leavePolicy": "policy_1",
        "policyDisplayName": "Vacation",
        "leaveTypeUniqueId": "lt_1",
        "numHours": 40.0,
        "numMinutes": 2400.0,
        "reasonForLeave": "Vacation",
        "requestedBy": "user_1",
        "requestedByName": "Jane Doe",
        "processedAt": "2024-06-28T10:00:00Z",
        "processedBy": "mgr_1",
        "processedByName": "John Manager",
        "managedBy": "mgr_1",
        "isPaid": True,
        "dates": ["2024-07-01", "2024-07-02", "2024-07-03", "2024-07-04", "2024-07-05"],
        "comments": "Annual leave",
        "roleTimezone": "America/Los_Angeles",
        "createdAt": "2024-06-25T08:00:00Z",
        "updatedAt": "2024-06-28T10:00:00Z",
    },
    "leave_types": {
        "id": "lt_1",
        "key": "vacation",
        "name": "Vacation",
        "description": "Paid time off",
        "unpaid": False,
        "managedBy": "rippling",
    },
    "legal_entities": {
        "id": "le_1",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-06-01T00:00:00Z",
        "tax_identifier": "12-3456789",
        "country": {"code": "US"},
        "legal_name": "Acme US",
        "entity_level": "subsidiary",
        "registration_date": "2024-01-01",
        "mailing_address": {
            "streetLine1": "123 Main St",
            "streetLine2": "",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94105",
            "country": "US",
            "phone": None,
            "isRemote": False,
        },
        "physical_address": {
            "streetLine1": "123 Main St",
            "streetLine2": "",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94105",
            "country": "US",
            "phone": None,
            "isRemote": False,
        },
        "parent_id": None,
        "management_type": "direct",
        "company_id": "comp_1",
    },
    "levels": {
        "id": "lvl_1",
        "name": "Senior",
        "parent": None,
    },
    "teams": {
        "id": "team_1",
        "name": "Platform",
        "parent": None,
    },
    "tracks": {
        "id": "track_1",
        "name": "Engineering",
        "description": "Engineering career track",
    },
    "users": {
        "id": "user_1",
        "created_at": "2024-01-15T00:00:00Z",
        "updated_at": "2024-06-15T00:00:00Z",
        "active": True,
        "username": "jdoe",
        "name": {
            "formatted": "Jane Doe",
            "given_name": "Jane",
            "middle_name": None,
            "family_name": "Doe",
            "preferred_given_name": "Jane",
            "preferred_family_name": "Doe",
        },
        "display_name": "Jane Doe",
        "emails": [{"value": "jane@acme.com", "type": "work", "primary": True}],
        "phone_numbers": [{"value": "+1-555-0101", "type": "work"}],
        "photos": [{"value": "https://photos.example.com/jdoe.jpg", "type": "photo"}],
        "preferred_language": "en",
        "locale": "en-US",
        "timezone": "America/Los_Angeles",
        "number": "EMP001",
    },
    "work_locations": {
        "id": "wl_1",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-06-01T00:00:00Z",
        "name": "HQ",
        "address": {
            "streetLine1": "123 Main St",
            "streetLine2": "",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94105",
            "country": "US",
            "phone": "+1-555-0100",
            "isRemote": False,
        },
    },
    "workers": {
        "id": "worker_1",
        "created_at": "2024-01-15T00:00:00Z",
        "updated_at": "2024-06-15T00:00:00Z",
        "user_id": "user_1",
        "user": "user_1",
        "manager": "mgr_1",
        "legal_entity": "le_1",
        "employment_type": "et_1",
        "department": "dept_1",
    },
    "custom_fields": {
        "id": "cf_1",
        "type": "text",
        "title": "T-Shirt Size",
        "mandatory": False,
    },
}


# ---------------------------------------------------------------------------
# Tests -- initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    def test_missing_api_token_raises(self):
        with pytest.raises(ValueError, match="api_token"):
            with patch("requests.Session"):
                RipplingLakeflowConnect({})

    def test_empty_api_token_raises(self):
        with pytest.raises(ValueError, match="api_token"):
            with patch("requests.Session"):
                RipplingLakeflowConnect({"api_token": "  "})

    def test_valid_token_creates_connector(self, connector):
        assert connector is not None
        assert connector._access_token is not None


# ---------------------------------------------------------------------------
# Tests -- list_tables
# ---------------------------------------------------------------------------


class TestListTables:
    def test_returns_all_14_tables(self, connector):
        tables = connector.list_tables()
        assert isinstance(tables, list)
        assert len(tables) == 14

    def test_contains_all_expected_tables(self, connector):
        tables = connector.list_tables()
        expected = [
            "companies",
            "custom_fields",
            "departments",
            "employment_types",
            "leave_balances",
            "leave_requests",
            "leave_types",
            "legal_entities",
            "levels",
            "teams",
            "tracks",
            "users",
            "work_locations",
            "workers",
        ]
        for t in expected:
            assert t in tables, f"Expected '{t}' in list_tables()"

    def test_list_is_sorted(self, connector):
        tables = connector.list_tables()
        assert tables == sorted(tables)


# ---------------------------------------------------------------------------
# Tests -- get_table_schema
# ---------------------------------------------------------------------------


class TestGetTableSchema:
    @pytest.mark.parametrize("table_name", SUPPORTED_TABLES)
    def test_returns_struct_type(self, connector, table_name):
        schema = connector.get_table_schema(table_name, {})
        assert isinstance(schema, StructType)

    @pytest.mark.parametrize("table_name", SUPPORTED_TABLES)
    def test_schema_has_fields(self, connector, table_name):
        schema = connector.get_table_schema(table_name, {})
        assert len(schema.fields) > 0

    def test_unsupported_table_raises(self, connector):
        with pytest.raises(ValueError, match="not supported"):
            connector.get_table_schema("nonexistent_table", {})

    def test_companies_schema_fields(self, connector):
        schema = connector.get_table_schema("companies", {})
        field_names = [f.name for f in schema.fields]
        assert "id" in field_names
        assert "name" in field_names
        assert "address" in field_names

    def test_workers_schema_fields(self, connector):
        schema = connector.get_table_schema("workers", {})
        field_names = [f.name for f in schema.fields]
        assert "id" in field_names
        assert "user_id" in field_names
        assert "department" in field_names

    def test_leave_balances_schema_has_role(self, connector):
        schema = connector.get_table_schema("leave_balances", {})
        field_names = [f.name for f in schema.fields]
        assert "role" in field_names
        assert "balances" in field_names


# ---------------------------------------------------------------------------
# Tests -- read_table_metadata
# ---------------------------------------------------------------------------


class TestReadTableMetadata:
    @pytest.mark.parametrize("table_name", SUPPORTED_TABLES)
    def test_returns_dict_with_required_keys(self, connector, table_name):
        metadata = connector.read_table_metadata(table_name, {})
        assert isinstance(metadata, dict)
        assert "primary_keys" in metadata
        assert "ingestion_type" in metadata
        assert "cursor_field" in metadata

    @pytest.mark.parametrize("table_name", sorted(_CDC_TABLES))
    def test_cdc_tables_have_correct_metadata(self, connector, table_name):
        metadata = connector.read_table_metadata(table_name, {})
        assert metadata["ingestion_type"] == "cdc"
        assert metadata["cursor_field"] == CDC_CURSOR_FIELD
        assert metadata["primary_keys"] == ["id"]

    @pytest.mark.parametrize("table_name", sorted(_SNAPSHOT_TABLES))
    def test_snapshot_tables_have_correct_metadata(self, connector, table_name):
        metadata = connector.read_table_metadata(table_name, {})
        assert metadata["ingestion_type"] == "snapshot"
        assert metadata["cursor_field"] is None

    def test_leave_balances_primary_key_is_role(self, connector):
        metadata = connector.read_table_metadata("leave_balances", {})
        assert metadata["primary_keys"] == ["role"]

    def test_unsupported_table_raises(self, connector):
        with pytest.raises(ValueError, match="not supported"):
            connector.read_table_metadata("nonexistent_table", {})

    def test_metadata_is_a_copy(self, connector):
        """Ensure read_table_metadata returns a copy, not the shared dict."""
        meta1 = connector.read_table_metadata("companies", {})
        meta2 = connector.read_table_metadata("companies", {})
        assert meta1 is not meta2


# ---------------------------------------------------------------------------
# Tests -- read_table for REST API tables (cursor-based pagination)
# ---------------------------------------------------------------------------


class TestReadTableRestApi:
    """Test cursor-based pagination tables served by the REST API."""

    @pytest.mark.parametrize(
        "table_name",
        sorted(_REST_ENDPOINTS.keys()),
    )
    def test_single_page(self, connector, table_name):
        """Single page of results, no next_link."""
        record = SAMPLE_RECORDS[table_name]
        mock_resp = _mock_response(200, {"results": [record], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table(table_name, None, {})
        records = list(records_iter)

        assert len(records) == 1
        assert records[0] == record
        assert isinstance(offset, dict)

    @pytest.mark.parametrize(
        "table_name",
        sorted(_REST_ENDPOINTS.keys()),
    )
    def test_multi_page_cursor_pagination(self, connector, table_name):
        """Two pages with cursor-based pagination via next_link."""
        record = SAMPLE_RECORDS[table_name]
        record2 = dict(record)
        # Create a second record with a different id (or role for leave_balances)
        if "id" in record2:
            record2["id"] = record2["id"] + "_2"
        if "updated_at" in record2:
            record2["updated_at"] = "2024-07-01T00:00:00Z"

        page1_resp = _mock_response(
            200, {"results": [record], "next_link": "/next-page?cursor=abc"}
        )
        page2_resp = _mock_response(200, {"results": [record2], "next_link": None})
        connector._session.get = MagicMock(side_effect=[page1_resp, page2_resp])

        records_iter, offset = connector.read_table(table_name, None, {})
        records = list(records_iter)

        assert len(records) == 2
        assert connector._session.get.call_count == 2


# ---------------------------------------------------------------------------
# Tests -- read_table for Legacy API tables (offset-based pagination)
# ---------------------------------------------------------------------------


class TestReadTableLegacyApi:
    """Test offset-based pagination tables served by the Legacy Platform API."""

    @pytest.mark.parametrize(
        "table_name",
        sorted(set(_LEGACY_ENDPOINTS.keys()) - {"leave_types"}),
    )
    def test_single_page_offset(self, connector, table_name):
        """Single page of results (fewer than DEFAULT_PAGE_SIZE)."""
        record = SAMPLE_RECORDS[table_name]
        mock_resp = _mock_response(200, [record])
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table(table_name, None, {})
        records = list(records_iter)

        assert len(records) == 1
        assert records[0] == record

    @pytest.mark.parametrize(
        "table_name",
        sorted(set(_LEGACY_ENDPOINTS.keys()) - {"leave_types"}),
    )
    def test_multi_page_offset_pagination(self, connector, table_name):
        """Two pages with offset-based pagination."""
        record = SAMPLE_RECORDS[table_name]

        # First page: exactly DEFAULT_PAGE_SIZE records to trigger next page fetch
        full_page = [dict(record) for _ in range(DEFAULT_PAGE_SIZE)]
        # Second page: partial page (stops pagination)
        partial_page = [dict(record)]

        page1_resp = _mock_response(200, full_page)
        page2_resp = _mock_response(200, partial_page)
        connector._session.get = MagicMock(side_effect=[page1_resp, page2_resp])

        records_iter, offset = connector.read_table(table_name, None, {})
        records = list(records_iter)

        assert len(records) == DEFAULT_PAGE_SIZE + 1
        assert connector._session.get.call_count == 2

    def test_leave_types_no_pagination(self, connector):
        """leave_types fetches all records in a single request (no pagination)."""
        record = SAMPLE_RECORDS["leave_types"]
        mock_resp = _mock_response(200, [record])
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table("leave_types", None, {})
        records = list(records_iter)

        assert len(records) == 1
        assert records[0] == record
        assert connector._session.get.call_count == 1

    def test_offset_pagination_stops_on_empty(self, connector):
        """Offset pagination stops when an empty list is returned."""
        page1_resp = _mock_response(200, [SAMPLE_RECORDS["custom_fields"]] * DEFAULT_PAGE_SIZE)
        page2_resp = _mock_response(200, [])
        connector._session.get = MagicMock(side_effect=[page1_resp, page2_resp])

        records_iter, offset = connector.read_table("custom_fields", None, {})
        records = list(records_iter)

        assert len(records) == DEFAULT_PAGE_SIZE


# ---------------------------------------------------------------------------
# Tests -- read_table for derived table (legal_entities)
# ---------------------------------------------------------------------------


class TestReadTableLegalEntities:
    def test_legal_entities_derived_from_companies(self, connector):
        """legal_entities are extracted from the companies endpoint."""
        company = SAMPLE_RECORDS["companies"]
        mock_resp = _mock_response(200, {"results": [company], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table("legal_entities", None, {})
        records = list(records_iter)

        assert len(records) == 1
        assert records[0]["id"] == "le_1"
        assert records[0]["company_id"] == "comp_1"

    def test_legal_entities_adds_company_id(self, connector):
        """company_id is added to legal entity records if not present."""
        company = {
            "id": "comp_2",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-06-01T00:00:00Z",
            "name": "Beta Inc",
            "legal_entities": [
                {
                    "id": "le_3",
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-03-01T00:00:00Z",
                    "legal_name": "Beta Entity",
                }
            ],
        }
        mock_resp = _mock_response(200, {"results": [company], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table("legal_entities", None, {})
        records = list(records_iter)

        assert len(records) == 1
        assert records[0]["company_id"] == "comp_2"

    def test_legal_entities_company_with_no_entities(self, connector):
        """Company with no legal_entities yields nothing."""
        company = {
            "id": "comp_3",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-06-01T00:00:00Z",
            "name": "Gamma LLC",
        }
        mock_resp = _mock_response(200, {"results": [company], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table("legal_entities", None, {})
        records = list(records_iter)

        assert len(records) == 0

    def test_legal_entities_skips_non_dict_entries(self, connector):
        """Non-dict entries in legal_entities list are skipped."""
        company = {
            "id": "comp_4",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-06-01T00:00:00Z",
            "name": "Delta Corp",
            "legal_entities": ["le_id_string", {"id": "le_4", "updated_at": "2024-05-01T00:00:00Z"}],
        }
        mock_resp = _mock_response(200, {"results": [company], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table("legal_entities", None, {})
        records = list(records_iter)

        # Only the dict entry is yielded
        assert len(records) == 1
        assert records[0]["id"] == "le_4"


# ---------------------------------------------------------------------------
# Tests -- CDC ingestion behaviour
# ---------------------------------------------------------------------------


class TestCDCIngestion:
    def test_cdc_initial_read_returns_all_records(self, connector):
        """First CDC read (start_offset=None) returns all records."""
        record = SAMPLE_RECORDS["users"]
        mock_resp = _mock_response(200, {"results": [record], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table("users", None, {})
        records = list(records_iter)

        assert len(records) == 1
        assert offset == {"cursor": "2024-06-15T00:00:00Z"}

    def test_cdc_filters_by_cursor(self, connector):
        """CDC read with a cursor filters out older records."""
        old_record = {
            "id": "user_old",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-05-01T00:00:00Z",
            "active": True,
            "username": "old_user",
        }
        new_record = {
            "id": "user_new",
            "created_at": "2024-06-01T00:00:00Z",
            "updated_at": "2024-07-01T00:00:00Z",
            "active": True,
            "username": "new_user",
        }
        mock_resp = _mock_response(
            200, {"results": [old_record, new_record], "next_link": None}
        )
        connector._session.get = MagicMock(return_value=mock_resp)

        start_offset = {"cursor": "2024-06-01T00:00:00Z"}
        records_iter, offset = connector.read_table("users", start_offset, {})
        records = list(records_iter)

        assert len(records) == 1
        assert records[0]["id"] == "user_new"
        assert offset == {"cursor": "2024-07-01T00:00:00Z"}

    def test_cdc_no_new_records_returns_empty(self, connector):
        """CDC read where all records are at or before cursor returns empty."""
        record = {
            "id": "user_1",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-06-01T00:00:00Z",
            "active": True,
            "username": "jdoe",
        }
        mock_resp = _mock_response(200, {"results": [record], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        start_offset = {"cursor": "2024-06-01T00:00:00Z"}
        records_iter, offset = connector.read_table("users", start_offset, {})
        records = list(records_iter)

        assert len(records) == 0
        assert offset == start_offset

    def test_cdc_idempotent_offset(self, connector):
        """Calling CDC with the same offset returns empty (idempotent)."""
        record = {
            "id": "wl_1",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-06-01T00:00:00Z",
            "name": "HQ",
        }
        mock_resp = _mock_response(200, {"results": [record], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        # First call
        records_iter1, offset1 = connector.read_table("work_locations", None, {})
        list(records_iter1)

        # Second call with same offset should be empty
        connector._session.get = MagicMock(return_value=mock_resp)
        records_iter2, offset2 = connector.read_table("work_locations", offset1, {})
        records2 = list(records_iter2)

        assert len(records2) == 0
        assert offset2 == offset1


# ---------------------------------------------------------------------------
# Tests -- Snapshot ingestion behaviour
# ---------------------------------------------------------------------------


class TestSnapshotIngestion:
    def test_snapshot_first_read(self, connector):
        """First snapshot read returns records and done offset."""
        record = SAMPLE_RECORDS["departments"]
        mock_resp = _mock_response(200, {"results": [record], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table("departments", None, {})
        records = list(records_iter)

        assert len(records) == 1
        assert offset == {"done": "true"}

    def test_snapshot_second_read_returns_empty(self, connector):
        """Second snapshot read (done=true) returns empty."""
        start_offset = {"done": "true"}
        records_iter, offset = connector.read_table("departments", start_offset, {})
        records = list(records_iter)

        assert len(records) == 0
        assert offset == {"done": "true"}

    @pytest.mark.parametrize("table_name", sorted(_SNAPSHOT_TABLES))
    def test_all_snapshot_tables_return_done_offset(self, connector, table_name):
        """All snapshot tables return done offset on first read."""
        record = SAMPLE_RECORDS[table_name]

        if table_name in _REST_ENDPOINTS:
            mock_resp = _mock_response(200, {"results": [record], "next_link": None})
        else:
            mock_resp = _mock_response(200, [record])

        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table(table_name, None, {})
        records = list(records_iter)

        assert len(records) >= 1
        assert offset == {"done": "true"}


# ---------------------------------------------------------------------------
# Tests -- Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_read_unsupported_table_raises(self, connector):
        with pytest.raises(ValueError, match="not supported"):
            connector.read_table("nonexistent_table", None, {})

    def test_api_error_raises_runtime_error(self, connector):
        """Non-200 response raises RuntimeError."""
        mock_resp = _mock_response(500, {"error": "Internal Server Error"})
        # Need to exhaust retries (MAX_RETRIES=5)
        connector._session.get = MagicMock(return_value=mock_resp)

        with patch("time.sleep"):  # Don't actually wait
            with pytest.raises(RuntimeError, match="500"):
                records_iter, offset = connector.read_table("departments", None, {})
                list(records_iter)

    def test_403_raises_runtime_error(self, connector):
        """403 response raises RuntimeError (not retriable)."""
        mock_resp = _mock_response(403, {"error": "Forbidden"})
        connector._session.get = MagicMock(return_value=mock_resp)

        with pytest.raises(RuntimeError, match="403"):
            records_iter, offset = connector.read_table("departments", None, {})
            list(records_iter)


# ---------------------------------------------------------------------------
# Tests -- Retry behaviour
# ---------------------------------------------------------------------------


class TestRetryBehaviour:
    def test_retries_on_429(self, connector):
        """429 responses are retried with backoff."""
        retry_resp = _mock_response(429, {}, headers={"Retry-After": "0.01"})
        success_resp = _mock_response(
            200, {"results": [SAMPLE_RECORDS["departments"]], "next_link": None}
        )
        connector._session.get = MagicMock(side_effect=[retry_resp, success_resp])

        with patch("time.sleep"):
            records_iter, offset = connector.read_table("departments", None, {})
            records = list(records_iter)

        assert len(records) == 1

    def test_retries_on_502(self, connector):
        """502 responses are retried."""
        retry_resp = _mock_response(502, {})
        success_resp = _mock_response(
            200, {"results": [SAMPLE_RECORDS["users"]], "next_link": None}
        )
        connector._session.get = MagicMock(side_effect=[retry_resp, success_resp])

        with patch("time.sleep"):
            records_iter, offset = connector.read_table("users", None, {})
            records = list(records_iter)

        assert len(records) == 1


# ---------------------------------------------------------------------------
# Tests -- read_table for each of the 14 tables
# ---------------------------------------------------------------------------


class TestAllTables:
    """Smoke test: each of the 14 tables can be read with mocked responses."""

    @pytest.mark.parametrize("table_name", sorted(_REST_ENDPOINTS.keys()))
    def test_rest_table_read(self, connector, table_name):
        record = SAMPLE_RECORDS[table_name]
        mock_resp = _mock_response(200, {"results": [record], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table(table_name, None, {})
        records = list(records_iter)

        assert len(records) >= 1
        assert isinstance(offset, dict)

    @pytest.mark.parametrize("table_name", sorted(_LEGACY_ENDPOINTS.keys()))
    def test_legacy_table_read(self, connector, table_name):
        record = SAMPLE_RECORDS[table_name]
        mock_resp = _mock_response(200, [record])
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table(table_name, None, {})
        records = list(records_iter)

        assert len(records) >= 1
        assert isinstance(offset, dict)

    def test_legal_entities_read(self, connector):
        company = SAMPLE_RECORDS["companies"]
        mock_resp = _mock_response(200, {"results": [company], "next_link": None})
        connector._session.get = MagicMock(return_value=mock_resp)

        records_iter, offset = connector.read_table("legal_entities", None, {})
        records = list(records_iter)

        assert len(records) >= 1
        assert isinstance(offset, dict)


# ---------------------------------------------------------------------------
# Tests -- schema and record field alignment
# ---------------------------------------------------------------------------


class TestSchemaRecordAlignment:
    """Verify sample records have fields matching the schema."""

    @pytest.mark.parametrize("table_name", SUPPORTED_TABLES)
    def test_record_fields_subset_of_schema(self, connector, table_name):
        """All top-level fields in sample records should exist in the schema."""
        schema = connector.get_table_schema(table_name, {})
        schema_field_names = {f.name for f in schema.fields}
        record = SAMPLE_RECORDS[table_name]
        for key in record:
            # legal_entities in companies is not in schema (it's raw API data)
            if table_name == "companies" and key == "legal_entities":
                continue
            assert key in schema_field_names, (
                f"Record field '{key}' not in schema for '{table_name}'"
            )
