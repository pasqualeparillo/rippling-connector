# Lakeflow Rippling Community Connector

This documentation describes how to configure and use the **Rippling** Lakeflow community connector to ingest HR platform data from the Rippling REST API into Databricks.


## Prerequisites

- **Rippling account**: You need a Rippling admin account (or equivalent permissions) to generate API credentials.
- **Authentication credentials**: Either an API token **or** OAuth 2.0 credentials (see [Obtaining Credentials](#obtaining-the-required-credentials)).
- **Network access**: The environment running the connector must be able to reach `https://rest.ripplingapis.com`.
- **Lakeflow / Databricks environment**: A workspace where you can register a Lakeflow community connector and run ingestion pipelines.


## Setup

### Required Connection Parameters

This connector supports two authentication methods. Choose **one**:

#### Option A — API Token (Bearer)

| Name        | Type   | Required | Description                                                                                      | Example           |
|-------------|--------|----------|--------------------------------------------------------------------------------------------------|-------------------|
| `api_token` | string | yes      | Static API token generated from the Rippling admin console. Sent as `Authorization: Bearer …`. | `rip_live_xxx…`   |

#### Option B — OAuth 2.0

| Name            | Type   | Required | Description                                                                                                              | Example           |
|-----------------|--------|----------|--------------------------------------------------------------------------------------------------------------------------|-------------------|
| `client_id`     | string | yes      | OAuth application client ID from the Rippling developer console.                                                         | `abc123`          |
| `client_secret` | string | yes      | OAuth application client secret from the Rippling developer console.                                                     | `s3cr3t…`         |
| `refresh_token` | string | yes      | OAuth refresh token obtained after completing the authorization flow. Exchanged at runtime for a short-lived access token via `https://app.rippling.com/api/o/token/`. | `1/…` |

> **No `externalOptionsAllowList` required.** The Rippling connector does not use table-specific options that need to be passed through from the connection layer, so you do not need to include `externalOptionsAllowList` as a connection parameter.

---

### Obtaining the Required Credentials

#### API Token (simpler, recommended for internal integrations)

1. Sign in to the **Rippling Admin Console** (`https://app.rippling.com`).
2. Navigate to **Settings → App Management → API Access** (exact path may vary by Rippling plan).
3. Click **Create API Key** (or **Generate Token**).
4. Assign the appropriate read scopes for the HR objects you want to ingest.
5. Copy the generated token and store it securely. Use this value as the `api_token` connection parameter.

> The token inherits the permissions of its creator. Make sure the admin account used has read access to all objects you intend to sync.

#### OAuth 2.0 (preferred for partner integrations)

1. Register an application in the **Rippling Developer Console** (`https://developer.rippling.com`).
2. Note the **Client ID** and **Client Secret** assigned to your application.
3. Complete the OAuth 2.0 authorization code flow to obtain a **refresh token**:
   - Redirect users (or yourself) to Rippling's authorization endpoint.
   - Exchange the returned authorization code for tokens at `https://app.rippling.com/api/o/token/`.
4. Store the `client_id`, `client_secret`, and `refresh_token` securely. The connector exchanges the refresh token for a short-lived access token at runtime.

---

### Create a Unity Catalog Connection

A Unity Catalog connection for this connector can be created in two ways via the UI:

1. Follow the **Lakeflow Community Connector** UI flow from the **Add Data** page.
2. Select any existing Lakeflow Community Connector connection for this source or create a new one.
3. Provide the credentials for your chosen authentication method (API token **or** OAuth 2.0).

Since this connector has no table-specific options that require pass-through, `externalOptionsAllowList` does not need to be configured.

The connection can also be created using the standard Unity Catalog API.


## Supported Objects

The Rippling connector exposes a **static list** of 14 tables:

- `companies`
- `custom_fields`
- `departments`
- `employment_types`
- `leave_balances`
- `leave_requests`
- `leave_types`
- `legal_entities`
- `levels`
- `teams`
- `tracks`
- `users`
- `work_locations`
- `workers`

### Object summary, primary keys, and ingestion mode

All tables use **CDC** ingestion with `updated_at` as the incremental cursor. Pagination is cursor-based via the `next_link` URL returned in each API response.

| Table              | Description                                                                       | Ingestion Type | Primary Key | Incremental Cursor | API Expand Parameters          |
|--------------------|-----------------------------------------------------------------------------------|----------------|-------------|--------------------|---------------------------------|
| `companies`        | Top-level company entities in the Rippling account.                               | `cdc`          | `id`        | `updated_at`       | —                               |
| `custom_fields`    | Custom field definitions configured for the company.                              | `cdc`          | `id`        | `updated_at`       | —                               |
| `departments`      | Organizational departments within the company.                                    | `cdc`          | `id`        | `updated_at`       | —                               |
| `employment_types` | Employment type definitions (e.g., full-time, part-time, contractor).             | `cdc`          | `id`        | `updated_at`       | —                               |
| `leave_balances`   | Employee leave balance records.                                                   | `cdc`          | `id`        | `updated_at`       | `expand=worker`                 |
| `leave_requests`   | Leave/time-off requests submitted by employees.                                   | `cdc`          | `id`        | `updated_at`       | `expand=worker`                 |
| `leave_types`      | Leave policy type definitions (e.g., vacation, sick leave).                       | `cdc`          | `id`        | `updated_at`       | —                               |
| `legal_entities`   | Legal entity records associated with the company.                                 | `cdc`          | `id`        | `updated_at`       | —                               |
| `levels`           | Job levels/grades defined for the company. ¹                                     | `cdc`          | `id`        | `updated_at`       | —                               |
| `teams`            | Team groupings within the company. ¹                                             | `cdc`          | `id`        | `updated_at`       | —                               |
| `tracks`           | Career tracks defined for the company. ¹                                         | `cdc`          | `id`        | `updated_at`       | —                               |
| `users`            | Rippling user accounts (login identities).                                        | `cdc`          | `id`        | `updated_at`       | —                               |
| `work_locations`   | Physical and remote work locations registered in Rippling.                        | `cdc`          | `id`        | `updated_at`       | —                               |
| `workers`          | Employee/worker records, including custom field values and linked user identity.  | `cdc`          | `id`        | `updated_at`       | `expand=custom_fields,user`     |

> ¹ **`levels`, `teams`, and `tracks`** may return **empty result sets** if these features are not configured for your company in Rippling. This is expected behaviour and is not an error.

### Schema highlights

- **Dynamic schema inference**: The connector samples a live record from each table on first access to infer the Spark schema. This means the schema automatically reflects your company's custom fields and the current API version — no manual schema definition is required.
- **`workers`**: Includes expanded `custom_fields` (company-specific) and the linked `user` object. The schema will vary between Rippling accounts based on configured custom fields.
- **`leave_balances` / `leave_requests`**: Each record includes an expanded `worker` sub-object with key employee identifiers.
- **Nested objects**: Rippling returns many fields as nested JSON objects. The connector preserves these as Spark `StructType` or `ArrayType` columns rather than flattening them.
- **Nullable fields**: Fields absent in the API response are surfaced as `null`.


## Table Configurations

### Source & Destination

These are set directly under each `table` object in the pipeline spec:

| Option                | Required | Description                                              |
|-----------------------|----------|----------------------------------------------------------|
| `source_table`        | Yes      | Table name in the source system (see supported list above) |
| `destination_catalog` | No       | Target catalog (defaults to pipeline's default)          |
| `destination_schema`  | No       | Target schema (defaults to pipeline's default)           |
| `destination_table`   | No       | Target table name (defaults to `source_table`)           |

### Common `table_configuration` options

These are set inside the `table_configuration` map:

| Option          | Required | Description                                                                                                          |
|-----------------|----------|----------------------------------------------------------------------------------------------------------------------|
| `scd_type`      | No       | `SCD_TYPE_1` (default) or `SCD_TYPE_2`. Applicable to CDC tables only.                                             |
| `primary_keys`  | No       | List of columns to override the connector's default primary keys (default: `["id"]` for all tables).               |
| `sequence_by`   | No       | Column used to order records for SCD Type 2 change tracking (e.g., `updated_at`).                                   |

### Source-specific `table_configuration` options

| Option                    | Required | Default | Description                                                                                                         |
|---------------------------|----------|---------|---------------------------------------------------------------------------------------------------------------------|
| `max_records_per_batch`   | No       | `1000`  | Maximum number of records returned per pipeline execution. Limits API consumption per run. Applies to all tables.  |


## Data Type Mapping

Rippling API JSON fields are mapped to Spark types as follows:

| Rippling / JSON Type      | Example Fields                                     | Spark Type                          | Notes                                                                                        |
|---------------------------|----------------------------------------------------|-------------------------------------|----------------------------------------------------------------------------------------------|
| integer                   | `id`, counts                                       | `LongType`                          | All integer values are stored as 64-bit long to avoid overflow.                             |
| float / decimal           | salary amounts, balance quantities                 | `DoubleType`                        |                                                                                              |
| boolean                   | `is_active`, flags                                 | `BooleanType`                       |                                                                                              |
| string                    | `name`, `status`, `email`                          | `StringType`                        | Includes ISO 8601 datetime strings (`created_at`, `updated_at`).                            |
| object                    | `worker`, `user`, `manager`, `department`          | `StructType` (nested)               | Nested objects are preserved as structs rather than flattened.                              |
| array of objects          | `custom_fields`, `roles`                           | `ArrayType(StructType(…), True)`    | Arrays of objects are preserved as arrays of structs.                                       |
| array of primitives       | tags, IDs                                          | `ArrayType(StringType(), True)`     |                                                                                              |
| `null` / absent field     | optional fields                                    | same base type, nullable            | Missing or null fields are surfaced as `null`.                                              |

> **Note**: Because schemas are inferred dynamically from a live sample record, actual column names and types reflect the current state of your Rippling account. Fields that are `null` in the sample record will be typed as `StringType` (the safe default). Re-running the connector after populating previously empty fields may produce an updated schema.


## How to Run

### Step 1: Clone/Copy the Source Connector Code

Use the **Lakeflow Community Connector** UI to copy or reference the Rippling connector source in your workspace. This places the connector code (e.g., `rippling.py`) under a project path that Lakeflow can load.

### Step 2: Configure Your Pipeline

In your pipeline code (e.g., `ingest.py`), configure a `pipeline_spec` that references:

- A **Unity Catalog connection** that uses this Rippling connector.
- One or more **tables** to ingest.

Example `pipeline_spec` snippet:

```json
{
  "pipeline_spec": {
    "connection_name": "rippling_connection",
    "object": [
      {
        "table": {
          "source_table": "workers",
          "table_configuration": {
            "max_records_per_batch": "2000"
          }
        }
      },
      {
        "table": {
          "source_table": "departments"
        }
      },
      {
        "table": {
          "source_table": "leave_requests",
          "table_configuration": {
            "scd_type": "SCD_TYPE_2",
            "sequence_by": "updated_at"
          }
        }
      },
      {
        "table": {
          "source_table": "users"
        }
      }
    ]
  }
}
```

- `connection_name` must point to the UC connection configured with your Rippling credentials.
- `source_table` must be one of the supported table names listed above (exact casing required).
- All tables use CDC ingestion; no additional required options are needed beyond `source_table`.

### Step 3: Run and Schedule the Pipeline

Run the pipeline using your standard Lakeflow / Databricks orchestration (e.g., a scheduled job or workflow).

- On the **first run**, the connector fetches all available records (no cursor is set yet).
- On **subsequent runs**, it uses the stored `updated_at` cursor and only fetches records updated since the last successful run.

#### Best Practices

- **Start small**: Begin by syncing a small subset of tables (e.g., `workers`, `departments`) to validate configuration and data shape before adding all 14 tables.
- **Use incremental sync**: All tables use CDC with `updated_at`, which minimises API calls on repeated runs.
- **Tune batch size**: Use `max_records_per_batch` to control how many records are processed per run. The default is `1000`; increase it for large tenants with many employees.
- **Expect empty tables**: `levels`, `teams`, and `tracks` may return no rows if your company has not configured these features in Rippling — this is normal and not an error.
- **Schema drift**: Because schemas are dynamically inferred, adding new custom fields in Rippling may introduce new columns on the next pipeline run. Ensure downstream consumers are tolerant of schema evolution.
- **Rate limits**: The connector automatically retries on HTTP `429`, `500`, `502`, and `503` responses with exponential backoff (up to 5 attempts). If you are hitting sustained rate limits, increase the pipeline schedule interval.

#### Troubleshooting

**Common Issues:**

- **Authentication failures (`401` / `403`)**:
  - Verify that the `api_token` is correct, not expired, and has not been revoked.
  - For OAuth, confirm that the `refresh_token` is still valid and that the `client_id` / `client_secret` are correct.
  - Ensure the Rippling user/app associated with the credentials has read permission for the objects being synced.

- **Empty results for `levels`, `teams`, or `tracks`**:
  - These tables are only populated if the corresponding features (Levels, Teams, Career Tracks) are enabled and configured in your Rippling account. Empty results are expected and do not indicate a bug.

- **Schema mismatch or missing columns**:
  - The schema is inferred from the first live record. If the sample record has `null` for a field that later contains a typed value, the column may be typed as `StringType`. Re-run schema inference after ensuring the table has representative data.
  - Custom fields on `workers` are specific to each Rippling account; schemas will differ between environments.

- **`RuntimeError: Failed to read '<table>': 4xx/5xx`**:
  - Check API credentials and network connectivity to `https://rest.ripplingapis.com`.
  - Verify that the Rippling plan you are on includes API access for the endpoint being called.

- **Slow initial sync**:
  - On the first run, all records are fetched. For large companies with many workers or leave records, this may take several minutes. Subsequent incremental runs will be much faster.


## References

- Connector implementation: `src/databricks/labs/community_connector/sources/rippling/rippling.py`
- Connector spec: `src/databricks/labs/community_connector/sources/rippling/connector_spec.yaml`
- Rippling REST API documentation: `https://developer.rippling.com/docs/rippling-api`
- Rippling API base URL: `https://rest.ripplingapis.com`
