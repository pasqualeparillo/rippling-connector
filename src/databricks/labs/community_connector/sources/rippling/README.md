# Rippling Connector

A [LakeflowConnect](../../interface/README.md) community connector that syncs HR data from [Rippling](https://www.rippling.com) into Databricks.

## Overview

The Rippling connector fetches data from both the Rippling REST API (`rest.ripplingapis.com`) and the legacy Platform API (`api.rippling.com/platform/api`). It supports 14 tables covering workforce, organizational, and leave management data.

## Prerequisites

- A Rippling account with admin access
- A Rippling API token (see [Authentication](#authentication))
- Databricks workspace with Unity Catalog enabled

## Authentication

The connector supports two authentication methods:

### API Token (recommended)

1. Log in to Rippling as an admin
2. Navigate to **Settings → App Management → API Access**
3. Click **Create API Key** and copy the generated token
4. The token is sent as `Authorization: Bearer <api_token>` on every request

### OAuth 2.0

If your integration requires OAuth:

1. Register an application in the Rippling developer console
2. Complete the OAuth authorization flow to obtain a refresh token
3. Provide `client_id`, `client_secret`, and `refresh_token` — the connector exchanges the refresh token for a short-lived access token at runtime

## Supported Tables

| Table | API | Ingestion Type | Primary Key | Notes |
|-------|-----|----------------|-------------|-------|
| `companies` | REST | CDC | `id` | Top-level company record |
| `departments` | REST | Snapshot | `id` | |
| `employment_types` | REST | CDC | `id` | e.g. EMPLOYEE, CONTRACTOR |
| `leave_balances` | Legacy | Snapshot | `role` | Balance in minutes |
| `leave_requests` | Legacy | Snapshot | `id` | |
| `leave_types` | Legacy | Snapshot | `id` | No pagination |
| `legal_entities` | REST (derived) | CDC | `id` | Extracted from companies response |
| `levels` | REST | Snapshot | `id` | Job levels/grades |
| `teams` | REST | Snapshot | `id` | |
| `tracks` | REST | Snapshot | `id` | Career tracks |
| `work_locations` | REST | CDC | `id` | Office/remote locations |
| `workers` | REST | CDC | `id` | Core workforce record |
| `users` | REST | CDC | `id` | Identity/login records |
| `custom_fields` | Legacy | Snapshot | `id` | HR custom field definitions |

### Ingestion Types

- **CDC** (Change Data Capture): uses `updated_at` as a cursor field to sync only new/updated records on incremental runs
- **Snapshot**: fetches all records on every sync cycle (no reliable cursor field)

### Pagination

- **REST API tables**: cursor-based pagination via `next_link` in the response
- **Legacy API tables** (`leave_balances`, `leave_requests`, `custom_fields`): offset-based pagination
- **`leave_types`**: single-page response (no pagination)
- **`legal_entities`**: derived by expanding the `legal_entities` array on each company record

## Configuration

### `dev_config.json` (for local testing)

```json
{
    "api_token": "YOUR_RIPPLING_API_TOKEN"
}
```

For OAuth:

```json
{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "refresh_token": "YOUR_REFRESH_TOKEN"
}
```

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_url` | `https://rest.ripplingapis.com` | Override the REST API base URL (e.g. for sandbox: `https://rest.ripplingsandboxapis.com`) |

## Known Limitations

- **`tracks`**: No dedicated `/tracks` endpoint is publicly documented. The connector uses the inferred endpoint `GET /tracks` based on Rippling's naming conventions. If this endpoint is unavailable for your account, the table will return an error.
- **`legal_entities`**: No dedicated list endpoint is confirmed. Records are derived from the `legal_entities` array embedded in the `/companies` response.
- **`leave_balances`** primary key is `role` (not `id`) since the legacy leave balance API does not return an `id` field.
- Leave data (`leave_balances`, `leave_requests`, `leave_types`) comes from the legacy Platform API which may be deprecated in future Rippling API versions.

## Rate Limits

The connector implements exponential backoff with up to 5 retries for HTTP `429`, `500`, `502`, and `503` responses. The `Retry-After` header is respected when present.

## Running Tests

```bash
pytest tests/unit/sources/rippling/ -v
```

To verify credentials only:

```bash
python tests/unit/sources/rippling/auth_test.py
```
