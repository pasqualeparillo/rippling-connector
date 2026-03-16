"""Rippling connector for the LakeflowConnect interface.

Supports 14 tables from the Rippling REST API (rest.ripplingapis.com).
All tables use CDC with updated_at as the cursor field.
Schemas are inferred dynamically from a live sample response so they
automatically reflect each company's custom fields and API version.

Pagination: cursor-based via next_link URL returned in each response.
"""

import time
from datetime import datetime, timezone
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
DEFAULT_PAGE_SIZE = 100
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0
RETRIABLE_STATUS_CODES = {429, 500, 502, 503}
REQUEST_TIMEOUT = 30
CDC_CURSOR_FIELD = "updated_at"

# ---------------------------------------------------------------------------
# Table configuration
# ---------------------------------------------------------------------------

_ENDPOINTS: dict[str, str] = {
    "companies":        "/companies/",
    "custom_fields":    "/custom-fields/",
    "departments":      "/departments/",
    "employment_types": "/employment-types/",
    "leave_balances":   "/leave-balances/",
    "leave_requests":   "/leave-requests/",
    "leave_types":      "/leave-types/",
    "legal_entities":   "/legal-entities/",
    "levels":           "/levels/",
    "teams":            "/teams/",
    "tracks":           "/tracks/",
    "users":            "/users/",
    "work_locations":   "/work-locations/",
    "workers":          "/workers/",
}

# Extra query params appended to every request for these tables.
_EXTRA_PARAMS: dict[str, dict] = {
    "workers":        {"expand": "custom_fields,user"},
    "leave_requests": {"expand": "worker"},
    "leave_balances": {"expand": "worker"},
}

# All tables support CDC via updated_at.
TABLE_METADATA: dict[str, dict] = {
    t: {"primary_keys": ["id"], "ingestion_type": "cdc", "cursor_field": CDC_CURSOR_FIELD}
    for t in _ENDPOINTS
}

SUPPORTED_TABLES = list(_ENDPOINTS.keys())


# ---------------------------------------------------------------------------
# Dynamic schema inference
# ---------------------------------------------------------------------------

def _py_to_spark(value) -> object:
    """Map a Python value to the most appropriate Spark DataType."""
    if isinstance(value, bool):
        return BooleanType()
    if isinstance(value, int):
        return LongType()
    if isinstance(value, float):
        return DoubleType()
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return ArrayType(_dict_to_struct(value[0]), True)
        return ArrayType(StringType(), True)
    if isinstance(value, dict):
        return _dict_to_struct(value)
    return StringType()


def _dict_to_struct(record: dict) -> StructType:
    """Recursively convert a sample dict into a StructType."""
    fields = [
        StructField(key, StringType() if val is None else _py_to_spark(val), True)
        for key, val in record.items()
    ]
    return StructType(fields) if fields else StructType([StructField("value", StringType(), True)])


# ---------------------------------------------------------------------------
# Connector implementation
# ---------------------------------------------------------------------------

class RipplingLakeflowConnect(LakeflowConnect):
    """LakeflowConnect implementation for the Rippling HR platform."""

    def __init__(self, options: dict[str, str]) -> None:
        super().__init__(options)
        self._api_token = options["api_token"]
        self._base_url = options.get("base_url", BASE_URL)
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        })
        self._init_ts = datetime.now(timezone.utc).isoformat()
        self._schema_cache: dict[str, StructType] = {}

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

    def _first_page(self, table_name: str, extra_params: dict | None = None) -> requests.Response:
        """Request the first page for a table."""
        url = f"{self._base_url}{_ENDPOINTS[table_name]}"
        params: dict = {"limit": DEFAULT_PAGE_SIZE}
        params.update(_EXTRA_PARAMS.get(table_name, {}))
        if extra_params:
            params.update(extra_params)
        return self._get(url, params=params)

    def _paginate(self, table_name: str) -> Iterator[dict]:
        """Yield all records across all pages, following next_link."""
        resp = self._first_page(table_name)
        while True:
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to read '{table_name}': {resp.status_code} {resp.text}"
                )
            body = resp.json()
            yield from body.get("results", [])
            next_link = body.get("next_link")
            if not next_link:
                break
            resp = self._get(next_link)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_table(self, table_name: str) -> None:
        if table_name not in SUPPORTED_TABLES:
            raise ValueError(
                f"Table '{table_name}' is not supported. "
                f"Supported: {SUPPORTED_TABLES}"
            )

    # ------------------------------------------------------------------
    # Interface methods
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        return list(SUPPORTED_TABLES)

    def get_table_schema(self, table_name: str, table_options: dict[str, str]) -> StructType:
        """Infer schema from a live sample record (cached per session)."""
        self._validate_table(table_name)
        if table_name in self._schema_cache:
            return self._schema_cache[table_name]

        resp = self._first_page(table_name, extra_params={"limit": 1})
        fallback = StructType([
            StructField("id", StringType(), True),
            StructField("created_at", StringType(), True),
            StructField("updated_at", StringType(), True),
        ])
        if resp.status_code != 200:
            self._schema_cache[table_name] = fallback
            return fallback

        results = resp.json().get("results", [])
        schema = _dict_to_struct(results[0]) if results else fallback
        self._schema_cache[table_name] = schema
        return schema

    def read_table_metadata(self, table_name: str, table_options: dict[str, str]) -> dict:
        self._validate_table(table_name)
        return dict(TABLE_METADATA[table_name])

    def read_table(
        self,
        table_name: str,
        start_offset: dict,
        table_options: dict[str, str],
    ) -> tuple[Iterator[dict], dict]:
        """CDC read: fetch records filtered by updated_at > cursor."""
        self._validate_table(table_name)
        cursor = start_offset.get("cursor") if start_offset else None

        # Nothing new if we are already at or past init time.
        if cursor and cursor >= self._init_ts:
            return iter([]), start_offset

        max_records = int(table_options.get("max_records_per_batch", "1000"))
        records: list[dict] = []

        for record in self._paginate(table_name):
            rec_ts = record.get(CDC_CURSOR_FIELD, "")
            if cursor and rec_ts <= cursor:
                continue
            records.append(record)
            if len(records) >= max_records:
                break

        if not records:
            return iter([]), start_offset or {}

        max_cursor = max(r.get(CDC_CURSOR_FIELD, "") for r in records)
        end_offset = {"cursor": max_cursor}

        if start_offset and start_offset == end_offset:
            return iter([]), start_offset

        return iter(records), end_offset
