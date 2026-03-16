"""Rippling connector for the LakeflowConnect interface.

Supports 14 tables from the Rippling REST API and legacy Platform API.
Tables that support CDC use updated_at as the cursor field; others use
snapshot ingestion.

Pagination varies by endpoint:
- Newer REST API (rest.ripplingapis.com): cursor-based via next_link
- Legacy Platform API (api.rippling.com/platform/api): offset-based
- leave-types: no pagination (single response)
- legal-entities: derived from the companies endpoint
"""

import time
from typing import Iterator

import requests
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

from databricks.labs.community_connector.interface import LakeflowConnect

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://rest.ripplingapis.com"
LEGACY_BASE_URL = "https://api.rippling.com/platform/api"
DEFAULT_PAGE_SIZE = 100
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0
RETRIABLE_STATUS_CODES = {429, 500, 502, 503}
REQUEST_TIMEOUT = 30
CDC_CURSOR_FIELD = "updated_at"

# ---------------------------------------------------------------------------
# Table configuration
# ---------------------------------------------------------------------------

# Tables served by the newer REST API (cursor-based pagination via next_link).
_REST_ENDPOINTS: dict[str, str] = {
    "companies": "/companies",
    "departments": "/departments",
    "employment_types": "/employment-types",
    "levels": "/levels",
    "teams": "/teams",
    "tracks": "/tracks",
    "users": "/users",
    "work_locations": "/work-locations",
    "workers": "/workers",
}

# Tables served by the legacy Platform API (offset-based pagination).
_LEGACY_ENDPOINTS: dict[str, str] = {
    "custom_fields": "/custom_fields",
    "leave_balances": "/leave_balances",
    "leave_requests": "/leave_requests",
    "leave_types": "/company_leave_types",
}

# Legal entities are extracted from the companies endpoint.
_DERIVED_TABLES = {"legal_entities"}

# All supported tables.
SUPPORTED_TABLES = sorted(
    list(_REST_ENDPOINTS.keys())
    + list(_LEGACY_ENDPOINTS.keys())
    + list(_DERIVED_TABLES)
)

# Extra query params appended to every request for specific tables.
_EXTRA_PARAMS: dict[str, dict] = {
    "workers": {"expand": "custom_fields,user"},
    "leave_requests": {"expand": "worker"},
    "leave_balances": {"expand": "worker"},
}

# ---------------------------------------------------------------------------
# Table metadata
# ---------------------------------------------------------------------------

# Tables that have updated_at and support CDC.
_CDC_TABLES = {
    "companies",
    "employment_types",
    "users",
    "work_locations",
    "workers",
    "legal_entities",
}

# Tables that lack a reliable cursor field; use snapshot ingestion.
_SNAPSHOT_TABLES = {
    "custom_fields",
    "departments",
    "leave_balances",
    "leave_requests",
    "leave_types",
    "levels",
    "teams",
    "tracks",
}


def _build_table_metadata() -> dict[str, dict]:
    """Build metadata for each table."""
    metadata: dict[str, dict] = {}
    for t in SUPPORTED_TABLES:
        if t in _CDC_TABLES:
            metadata[t] = {
                "primary_keys": ["id"],
                "ingestion_type": "cdc",
                "cursor_field": CDC_CURSOR_FIELD,
            }
        else:
            metadata[t] = {
                "primary_keys": ["id"],
                "ingestion_type": "snapshot",
                "cursor_field": None,
            }
    # leave_balances uses 'role' as the primary key (no 'id' field).
    metadata["leave_balances"]["primary_keys"] = ["role"]
    return metadata


TABLE_METADATA = _build_table_metadata()


# ---------------------------------------------------------------------------
# Static schemas (based on API documentation)
# ---------------------------------------------------------------------------

_ADDRESS_SCHEMA = StructType([
    StructField("streetLine1", StringType(), True),
    StructField("streetLine2", StringType(), True),
    StructField("city", StringType(), True),
    StructField("state", StringType(), True),
    StructField("zip", StringType(), True),
    StructField("country", StringType(), True),
    StructField("phone", StringType(), True),
    StructField("isRemote", BooleanType(), True),
])

_NAME_SCHEMA = StructType([
    StructField("formatted", StringType(), True),
    StructField("given_name", StringType(), True),
    StructField("middle_name", StringType(), True),
    StructField("family_name", StringType(), True),
    StructField("preferred_given_name", StringType(), True),
    StructField("preferred_family_name", StringType(), True),
])

_EMAIL_SCHEMA = StructType([
    StructField("value", StringType(), True),
    StructField("type", StringType(), True),
    StructField("primary", BooleanType(), True),
])

_PHONE_SCHEMA = StructType([
    StructField("value", StringType(), True),
    StructField("type", StringType(), True),
])

_PHOTO_SCHEMA = StructType([
    StructField("value", StringType(), True),
    StructField("type", StringType(), True),
])

_COUNTRY_SCHEMA = StructType([
    StructField("code", StringType(), True),
])

_LEAVE_BALANCE_ENTRY_SCHEMA = StructType([
    StructField("company_leave_type_id", StringType(), True),
    StructField("unlimited", BooleanType(), True),
    StructField("remaining_balance", LongType(), True),
    StructField("remaining_balance_with_future", LongType(), True),
])

_TABLE_SCHEMAS: dict[str, StructType] = {
    "companies": StructType([
        StructField("id", StringType(), True),
        StructField("created_at", StringType(), True),
        StructField("updated_at", StringType(), True),
        StructField("name", StringType(), True),
        StructField("legal_name", StringType(), True),
        StructField("primary_email", StringType(), True),
        StructField("phone", StringType(), True),
        StructField("address", _ADDRESS_SCHEMA, True),
        StructField("parent_legal_entity_id", StringType(), True),
        StructField("legal_entities_id", ArrayType(StringType(), True), True),
    ]),
    "departments": StructType([
        StructField("id", StringType(), True),
        StructField("name", StringType(), True),
        StructField("parent", StringType(), True),
    ]),
    "employment_types": StructType([
        StructField("id", StringType(), True),
        StructField("created_at", StringType(), True),
        StructField("updated_at", StringType(), True),
        StructField("label", StringType(), True),
        StructField("name", StringType(), True),
        StructField("type", StringType(), True),
        StructField("compensation_time_period", StringType(), True),
    ]),
    "leave_balances": StructType([
        StructField("role", StringType(), True),
        StructField("balances", ArrayType(_LEAVE_BALANCE_ENTRY_SCHEMA, True), True),
    ]),
    "leave_requests": StructType([
        StructField("id", StringType(), True),
        StructField("role", StringType(), True),
        StructField("roleName", StringType(), True),
        StructField("status", StringType(), True),
        StructField("startDate", StringType(), True),
        StructField("endDate", StringType(), True),
        StructField("leavePolicy", StringType(), True),
        StructField("policyDisplayName", StringType(), True),
        StructField("leaveTypeUniqueId", StringType(), True),
        StructField("numHours", DoubleType(), True),
        StructField("numMinutes", DoubleType(), True),
        StructField("reasonForLeave", StringType(), True),
        StructField("requestedBy", StringType(), True),
        StructField("requestedByName", StringType(), True),
        StructField("processedAt", StringType(), True),
        StructField("processedBy", StringType(), True),
        StructField("processedByName", StringType(), True),
        StructField("managedBy", StringType(), True),
        StructField("isPaid", BooleanType(), True),
        StructField("dates", ArrayType(StringType(), True), True),
        StructField("comments", StringType(), True),
        StructField("roleTimezone", StringType(), True),
        StructField("createdAt", StringType(), True),
        StructField("updatedAt", StringType(), True),
    ]),
    "leave_types": StructType([
        StructField("id", StringType(), True),
        StructField("key", StringType(), True),
        StructField("name", StringType(), True),
        StructField("description", StringType(), True),
        StructField("unpaid", BooleanType(), True),
        StructField("managedBy", StringType(), True),
    ]),
    "legal_entities": StructType([
        StructField("id", StringType(), True),
        StructField("created_at", StringType(), True),
        StructField("updated_at", StringType(), True),
        StructField("tax_identifier", StringType(), True),
        StructField("country", _COUNTRY_SCHEMA, True),
        StructField("legal_name", StringType(), True),
        StructField("entity_level", StringType(), True),
        StructField("registration_date", StringType(), True),
        StructField("mailing_address", _ADDRESS_SCHEMA, True),
        StructField("physical_address", _ADDRESS_SCHEMA, True),
        StructField("parent_id", StringType(), True),
        StructField("management_type", StringType(), True),
        StructField("company_id", StringType(), True),
    ]),
    "levels": StructType([
        StructField("id", StringType(), True),
        StructField("name", StringType(), True),
        StructField("parent", StringType(), True),
    ]),
    "teams": StructType([
        StructField("id", StringType(), True),
        StructField("name", StringType(), True),
        StructField("parent", StringType(), True),
    ]),
    "tracks": StructType([
        StructField("id", StringType(), True),
        StructField("name", StringType(), True),
        StructField("description", StringType(), True),
    ]),
    "users": StructType([
        StructField("id", StringType(), True),
        StructField("created_at", StringType(), True),
        StructField("updated_at", StringType(), True),
        StructField("active", BooleanType(), True),
        StructField("username", StringType(), True),
        StructField("name", _NAME_SCHEMA, True),
        StructField("display_name", StringType(), True),
        StructField("emails", ArrayType(_EMAIL_SCHEMA, True), True),
        StructField("phone_numbers", ArrayType(_PHONE_SCHEMA, True), True),
        StructField("photos", ArrayType(_PHOTO_SCHEMA, True), True),
        StructField("preferred_language", StringType(), True),
        StructField("locale", StringType(), True),
        StructField("timezone", StringType(), True),
        StructField("number", StringType(), True),
    ]),
    "work_locations": StructType([
        StructField("id", StringType(), True),
        StructField("created_at", StringType(), True),
        StructField("updated_at", StringType(), True),
        StructField("name", StringType(), True),
        StructField("address", _ADDRESS_SCHEMA, True),
    ]),
    "workers": StructType([
        StructField("id", StringType(), True),
        StructField("created_at", StringType(), True),
        StructField("updated_at", StringType(), True),
        StructField("user_id", StringType(), True),
        StructField("user", StringType(), True),
        StructField("manager", StringType(), True),
        StructField("legal_entity", StringType(), True),
        StructField("employment_type", StringType(), True),
        StructField("department", StringType(), True),
    ]),
    "custom_fields": StructType([
        StructField("id", StringType(), True),
        StructField("type", StringType(), True),
        StructField("title", StringType(), True),
        StructField("mandatory", BooleanType(), True),
    ]),
}


# ---------------------------------------------------------------------------
# Connector implementation
# ---------------------------------------------------------------------------

class RipplingLakeflowConnect(LakeflowConnect):
    """LakeflowConnect implementation for the Rippling HR platform."""

    def __init__(self, options: dict[str, str]) -> None:
        super().__init__(options)
        self._base_url = options.get("base_url", BASE_URL).rstrip("/")
        self._legacy_base_url = LEGACY_BASE_URL
        self._api_version = options.get("api_version", "").strip() or None
        self._access_token = self._resolve_access_token(options)
        self._session = requests.Session()
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        if self._api_version:
            headers["Rippling-Api-Version"] = self._api_version
        self._session.headers.update(headers)

    @staticmethod
    def _resolve_access_token(options: dict[str, str]) -> str:
        """Resolve auth from api_token option."""
        api_token = (options.get("api_token") or "").strip()
        if not api_token:
            raise ValueError(
                "The 'api_token' option is required. Generate one from "
                "Rippling Admin > Settings > API Tokens."
            )
        return api_token

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        """GET with exponential backoff on retriable status codes."""
        backoff = INITIAL_BACKOFF
        resp = None
        for attempt in range(MAX_RETRIES):
            resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code not in RETRIABLE_STATUS_CODES:
                return resp
            if attempt < MAX_RETRIES - 1:
                wait = (
                    float(resp.headers.get("Retry-After", backoff))
                    if resp.status_code == 429
                    else backoff
                )
                time.sleep(wait)
                backoff *= 2
        return resp  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Pagination helpers
    # ------------------------------------------------------------------

    def _paginate_cursor(self, table_name: str) -> Iterator[dict]:
        """Paginate a REST API endpoint using cursor-based next_link."""
        endpoint = _REST_ENDPOINTS[table_name]
        url = f"{self._base_url}{endpoint}"
        params: dict = {"limit": DEFAULT_PAGE_SIZE}
        params.update(_EXTRA_PARAMS.get(table_name, {}))

        while True:
            resp = self._get(url, params=params)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to read '{table_name}': {resp.status_code} {resp.text}"
                )
            body = resp.json()
            yield from body.get("results", [])
            next_link = body.get("next_link")
            if not next_link:
                break
            # next_link may be a full URL or a relative path.
            url = next_link if next_link.startswith("http") else f"{self._base_url}{next_link}"
            params = {}

    def _paginate_offset(self, table_name: str) -> Iterator[dict]:
        """Paginate a legacy Platform API endpoint using offset-based pagination."""
        endpoint = _LEGACY_ENDPOINTS[table_name]
        url = f"{self._legacy_base_url}{endpoint}"
        extra = _EXTRA_PARAMS.get(table_name, {})
        offset = 0

        while True:
            params: dict = {"limit": DEFAULT_PAGE_SIZE, "offset": offset}
            params.update(extra)
            resp = self._get(url, params=params)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to read '{table_name}': {resp.status_code} {resp.text}"
                )
            data = resp.json()
            # Legacy endpoints return a bare list, not {"results": [...]}.
            records = data if isinstance(data, list) else data.get("results", [])
            if not records:
                break
            yield from records
            if len(records) < DEFAULT_PAGE_SIZE:
                break
            offset += DEFAULT_PAGE_SIZE

    def _fetch_no_pagination(self, table_name: str) -> Iterator[dict]:
        """Fetch all records from an endpoint that returns everything at once."""
        endpoint = _LEGACY_ENDPOINTS[table_name]
        url = f"{self._legacy_base_url}{endpoint}"
        resp = self._get(url)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to read '{table_name}': {resp.status_code} {resp.text}"
            )
        data = resp.json()
        records = data if isinstance(data, list) else data.get("results", [])
        yield from records

    def _fetch_legal_entities(self) -> Iterator[dict]:
        """Extract legal entities from the companies endpoint."""
        for company in self._paginate_cursor("companies"):
            legal_entities = company.get("legal_entities", [])
            if isinstance(legal_entities, list):
                for le in legal_entities:
                    if isinstance(le, dict):
                        # Attach company_id if not already present.
                        if "company_id" not in le:
                            le["company_id"] = company.get("id")
                        yield le

    def _fetch_all(self, table_name: str) -> Iterator[dict]:
        """Route to the appropriate fetcher based on table type."""
        if table_name == "legal_entities":
            return self._fetch_legal_entities()
        if table_name == "leave_types":
            return self._fetch_no_pagination(table_name)
        if table_name in _LEGACY_ENDPOINTS:
            return self._paginate_offset(table_name)
        if table_name in _REST_ENDPOINTS:
            return self._paginate_cursor(table_name)
        raise ValueError(f"No endpoint configured for table '{table_name}'")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_table(self, table_name: str) -> None:
        if table_name not in SUPPORTED_TABLES:
            raise ValueError(
                f"Table '{table_name}' is not supported. "
                f"Supported tables: {SUPPORTED_TABLES}"
            )

    # ------------------------------------------------------------------
    # Interface methods
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        return list(SUPPORTED_TABLES)

    def get_table_schema(
        self, table_name: str, table_options: dict[str, str]
    ) -> StructType:
        self._validate_table(table_name)
        return _TABLE_SCHEMAS[table_name]

    def read_table_metadata(
        self, table_name: str, table_options: dict[str, str]
    ) -> dict:
        self._validate_table(table_name)
        return dict(TABLE_METADATA[table_name])

    def read_table(
        self,
        table_name: str,
        start_offset: dict,
        table_options: dict[str, str],
    ) -> tuple[Iterator[dict], dict]:
        """Read records from a table.

        For CDC tables: filters records by updated_at > cursor on the
        client side. For snapshot tables: returns all records in a
        single batch with a sentinel offset.
        """
        self._validate_table(table_name)
        metadata = TABLE_METADATA[table_name]

        if metadata["ingestion_type"] == "snapshot":
            return self._read_snapshot(table_name, start_offset)

        return self._read_cdc(table_name, start_offset)

    # ------------------------------------------------------------------
    # Read strategies
    # ------------------------------------------------------------------

    def _read_snapshot(
        self, table_name: str, start_offset: dict
    ) -> tuple[Iterator[dict], dict]:
        """Snapshot read: return all records in one batch.

        Uses a sentinel offset {"done": "true"} to signal completion.
        On subsequent calls (when start_offset already has "done"),
        returns empty to stop pagination.
        """
        if start_offset and start_offset.get("done") == "true":
            return iter([]), start_offset

        records = list(self._fetch_all(table_name))
        end_offset = {"done": "true"}
        return iter(records), end_offset

    def _read_cdc(
        self, table_name: str, start_offset: dict
    ) -> tuple[Iterator[dict], dict]:
        """CDC read: fetch all records and filter by updated_at > cursor."""
        cursor = start_offset.get("cursor") if start_offset else None

        records: list[dict] = []
        for record in self._fetch_all(table_name):
            rec_ts = record.get(CDC_CURSOR_FIELD, "")
            if cursor and rec_ts and rec_ts <= cursor:
                continue
            records.append(record)

        if not records:
            return iter([]), start_offset or {"cursor": ""}

        max_cursor = max(
            (r.get(CDC_CURSOR_FIELD, "") for r in records),
            default="",
        )
        end_offset = {"cursor": max_cursor}

        if start_offset and start_offset == end_offset:
            return iter([]), start_offset

        return iter(records), end_offset
