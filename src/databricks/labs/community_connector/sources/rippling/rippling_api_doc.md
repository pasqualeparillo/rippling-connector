# Rippling REST API Documentation

## Overview

Rippling is a workforce management platform that enables companies to manage HR, IT, and Finance functions in one system. The REST API provides programmatic access to Rippling's data and workflows.

**Official API docs:** https://developer.rippling.com/documentation/rest-api

---

## Authentication

### Method: Bearer Token (API Key or OAuth 2.0 Access Token)

All API requests must include an `Authorization` header with a Bearer token.

```
Authorization: Bearer <TOKEN>
```

**Two token types are supported:**

| Type | Use Case | How to Obtain |
|------|----------|---------------|
| API Token | Customer integrations (direct API access) | Generated via Rippling admin: Admin > Settings > API Tokens app |
| OAuth Access Token | Partner integrations (multi-tenant apps) | Exchanged via OAuth 2.0 authorization code flow |

#### API Token Flow (Customer)
1. Log in to Rippling as an admin.
2. Navigate to **Admin > Settings > API Tokens**.
3. Create a token with desired permission scopes.
4. Copy and store the token securely — it is only shown once.
5. Use in all requests as: `Authorization: Bearer <API_TOKEN>`

Tokens expire after **30 days of inactivity**.

#### OAuth 2.0 Flow (Partner)
- **Authorization endpoint:** `https://api.rippling.com/api/o/authorize/`
- **Token endpoint:** `https://api.rippling.com/api/o/token/`
- **Token exchange:** POST to token endpoint with `Authorization: Basic <base64(client_id:client_secret)>` and `grant_type=authorization_code`
- **Token refresh:** POST to token endpoint with `grant_type=refresh_token`
- **JWKS endpoint:** `https://rest.ripplingapis.com/jwks_keys`

**Note:** All Rippling Application Partners must use OAuth 2.0 (not API tokens) for multi-company integrations.

### Scopes

Scopes follow the `{resource_name}.{read|write}` convention. Common scopes for read operations:

| Scope | Resource |
|-------|----------|
| `companies.read` | Company data |
| `workers.read` | Worker profiles |
| `users.read` | User accounts |
| `departments.read` | Department structure |
| `teams.read` | Team data |
| `custom-fields.read` | Custom field definitions |

Additional scopes may be required for expanded fields (e.g., `compensation.read` to read worker compensation data). Fields not accessible due to insufficient scope are returned in a `__meta.redacted_fields` object.

---

## Base URL

| Environment | Base URL |
|-------------|----------|
| Production | `https://rest.ripplingapis.com` |
| Sandbox | `https://rest.ripplingsandboxapis.com` |

**Legacy base URL (Base API / Platform API):** `https://api.rippling.com/platform/api`

The newer REST API (`rest.ripplingapis.com`) uses cursor-based pagination and is the preferred domain for new integrations. The legacy `api.rippling.com/platform/api` domain uses offset-based pagination and is documented as a reference for older integrations.

---

## Versioning

API versioning is **header-based**, using the `Rippling-Api-Version` header with a date value in `YYYY-MM-DD` format.

```
Rippling-Api-Version: 2023-08-01
```

- If no version header is specified, the request is served with the **default version** associated with the token.
- Breaking changes result in a new dated version.
- Customers can specify a default version when creating an API token, preventing unintended breakage from version upgrades.

---

## Rate Limits

TBD: Specific numeric rate limits are not publicly documented by Rippling. Official documentation states that "all API products are subject to rate limits." Implement error handling for HTTP `429 Too Many Requests` responses. No `X-RateLimit-*` headers are documented.

**Recommended practice:** Throttle bulk syncs; add retry logic with exponential backoff on 429 responses.

---

## Common Request Headers

| Header | Required | Value |
|--------|----------|-------|
| `Authorization` | Yes | `Bearer <TOKEN>` |
| `Accept` | Recommended | `application/json` |
| `Rippling-Api-Version` | Optional | `YYYY-MM-DD` (e.g., `2023-08-01`) |

---

## Pagination

### Newer REST API (`rest.ripplingapis.com`) — Cursor-Based

The newer REST API uses **cursor-based pagination**.

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `limit` | integer | 50 | 100 | Number of records per page |
| `cursor` | string | — | — | Opaque cursor bookmark from previous response |

**Response structure:**
```json
{
  "next_link": "/workers?limit=100&cursor=dXNlcjpVMEc5V0ZYTlo&order_by=created_at+desc",
  "results": [ ... ]
}
```

- Fetch `next_link` to retrieve the next page.
- When `next_link` is absent or null, all pages have been retrieved.

### Legacy Platform API (`api.rippling.com/platform/api`) — Offset-Based

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `limit` | integer | — | 100 | Records per page |
| `offset` | integer | 0 | — | Starting index for result set |

Iterate by incrementing `offset` by `limit` until an empty result array is returned.

**Note for `company_activity`:** Uses a `next` cursor parameter rather than offset.

---

## API Design Conventions

- URL paths use **lower kebab-case** (e.g., `/leave-requests`, `/work-locations`).
- JSON field names use **lower snake_case** (e.g., `created_at`, `work_email`).
- All dates are in **UTC using ISO 8601** format.
- Resource endpoints use **plural nouns** (e.g., `/workers`, `/users`, `/departments`).
- **Field expansion:** Use the `?expand=field1,field2` query parameter to inline related objects. Up to 10 fields with 2 levels of nesting are supported (e.g., `?expand=manager,manager.level`).
- Fields not accessible due to scope restrictions appear in `__meta.redacted_fields`.

---

## Endpoints

### 1. companies

**Description:** Returns the list of companies accessible with the current token. Each company may have associated legal entities.

**Endpoint (newer REST API):**
```
GET https://rest.ripplingapis.com/companies
```

**Endpoint (legacy Platform API — single current company):**
```
GET https://api.rippling.com/platform/api/companies/current
```

**Required Scope:** `companies.read`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100, default 50) |
| `cursor` | string | No | Cursor for next page (newer API) |

**Response Schema — Company Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the company |
| `created_at` | string (ISO 8601) | Record creation timestamp |
| `updated_at` | string (ISO 8601) | Record last updated timestamp |
| `name` | string | Company display name |
| `legal_name` | string | Legal registered name of the company |
| `primary_email` | string | Primary contact email |
| `phone` | string | Company phone number |
| `address` | object | Company address (see Address schema) |
| `work_locations` | array[object] | List of work locations associated with the company |
| `parent_legal_entity_id` | string | ID of the parent legal entity |
| `parent_legal_entity` | object | Nested parent legal entity (see LegalEntity schema) |
| `legal_entities_id` | array[string] | Array of legal entity IDs |
| `legal_entities` | array[object] | Array of legal entity objects (see LegalEntity schema) |
| `__meta` | object | Metadata including `redacted_fields` |

**Address Schema (nested):**

| Field | Type | Description |
|-------|------|-------------|
| `streetLine1` | string | Street address line 1 |
| `streetLine2` | string | Street address line 2 |
| `city` | string | City |
| `state` | string | State/province code |
| `zip` | string | Postal/ZIP code |
| `country` | string | Country code |
| `phone` | string | Address phone number |
| `isRemote` | boolean | Whether the location is remote |

**LegalEntity Schema (nested):**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier |
| `created_at` | string (ISO 8601) | Creation timestamp |
| `updated_at` | string (ISO 8601) | Last updated timestamp |
| `tax_identifier` | string | Tax ID (EIN, etc.) |
| `country` | object | Country object with `code` property |
| `legal_name` | string | Legal name of the entity |
| `entity_level` | string | Hierarchy level of the legal entity |
| `registration_date` | string | Registration date |
| `mailing_address` | object | Mailing address (see Address schema) |
| `physical_address` | object | Physical address (see Address schema) |
| `parent_id` | string | Parent entity ID |
| `management_type` | string | Management type: `EOR` or `PEO` |
| `company_id` | string | Associated company ID |

**Pagination:** Cursor-based (newer API); returns `next_link` in response.

**Example Request:**
```bash
curl -X GET 'https://rest.ripplingapis.com/companies' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 2. departments

**Description:** Returns the list of departments for the company.

**Endpoint (newer REST API):**
```
GET https://rest.ripplingapis.com/departments
```

**Endpoint (legacy Platform API):**
```
GET https://api.rippling.com/platform/api/departments
```

**Required Scope:** `departments.read`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100, default 50) |
| `cursor` | string | No | Cursor for next page |
| `offset` | integer | No | Offset for legacy API pagination |

**Response Schema — Department Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the department |
| `name` | string | Department name |
| `parent` | string or null | ID of the parent department (null if top-level) |

**Pagination:** Cursor-based (newer API) or offset-based (legacy).

**Example Request:**
```bash
curl -X GET 'https://rest.ripplingapis.com/departments' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 3. employment-types

**Description:** Returns the list of employment types configured for the company (e.g., Full-Time Employee, Part-Time Contractor).

**Endpoint (newer REST API):**
```
GET https://rest.ripplingapis.com/employment-types
```

**Retrieve single employment type:**
```
GET https://rest.ripplingapis.com/employment-types/{id}
```

**Required Scope:** `workers.read` (employment types are tied to worker data access)

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100, default 50) |
| `cursor` | string | No | Cursor for next page |

**Response Schema — CompanyEmploymentType Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the employment type |
| `created_at` | string (ISO 8601) | Record creation timestamp |
| `updated_at` | string (ISO 8601) | Record last updated timestamp |
| `label` | string | Display label of the employment type |
| `name` | string | Internal name (for non-custom employment types) |
| `type` | string | Worker classification: `CONTRACTOR` or `EMPLOYEE` |
| `compensation_time_period` | string | Compensation period: `HOURLY` or `SALARIED` |

**Pagination:** Cursor-based.

**Example Request:**
```bash
curl -X GET 'https://rest.ripplingapis.com/employment-types' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 4. leave-balances

**Description:** Returns leave balance data for employees. Each entry contains the employee's role ID and an array of leave balances per leave type.

**Endpoint (legacy Platform API — list all):**
```
GET https://api.rippling.com/platform/api/leave_balances
```

**Endpoint (legacy Platform API — single role):**
```
GET https://api.rippling.com/platform/api/leave_balances/{role}
```

**Required Scope:** TBD: Not explicitly documented; likely requires `workers.read` and leave-related scope.

**Query Parameters (list endpoint):**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100) |
| `offset` | integer | No | Pagination offset |

**Path Parameters (single-role endpoint):**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `role` | string | Yes | Unique identifier of the employee role |

**Response Schema — LeaveBalance Container:**

| Field | Type | Description |
|-------|------|-------------|
| `role` | string | Unique identifier of the employee role |
| `balances` | array[object] | Array of leave balance entries per leave type |

**LeaveBalance Entry Schema (within `balances`):**

| Field | Type | Description |
|-------|------|-------------|
| `company_leave_type_id` | string | ID of the company leave type |
| `unlimited` | boolean | Whether the leave balance is unlimited |
| `remaining_balance` | integer | Remaining balance in minutes (excluding future requests) |
| `remaining_balance_with_future` | integer | Remaining balance in minutes (including future requests) |

**Pagination:** Offset-based (legacy API).

**Example Request:**
```bash
curl -X GET 'https://api.rippling.com/platform/api/leave_balances' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 5. leave-requests

**Description:** Returns leave requests for the company, with filtering options by date range, status, employee, and leave policy.

**Endpoint (legacy Platform API):**
```
GET https://api.rippling.com/platform/api/leave_requests
```

**Required Scope:** TBD: Not explicitly documented; likely requires `workers.read` and leave-related scope.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | No | Filter by leave request ID |
| `role` | string | No | Filter by employee role ID |
| `requestedBy` | string | No | Filter by the user who submitted the request |
| `status` | string | No | Filter by status: `PENDING`, `APPROVED`, `REJECTED`, `CANCELED` |
| `startDate` | string | No | Filter: requests starting on or after this date (ISO 8601) |
| `endDate` | string | No | Filter: requests ending on or before this date (ISO 8601) |
| `leavePolicy` | string | No | Filter by leave policy ID |
| `processedBy` | string | No | Filter by the user who processed the request |
| `from` | string | No | Alias for startDate in some contexts |
| `to` | string | No | Alias for endDate in some contexts |
| `limit` | integer | No | Max records per page (max 100) |
| `offset` | integer | No | Pagination offset |

**Response Schema — LeaveRequest Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the leave request |
| `role` | string | Unique identifier of the employee taking leave |
| `roleName` | string | Display name of the employee |
| `status` | string | Status: `PENDING`, `APPROVED`, `REJECTED`, `CANCELED` |
| `startDate` | string | Leave start date (ISO 8601) |
| `endDate` | string | Leave end date (ISO 8601) |
| `leavePolicy` | string | Unique identifier of the leave policy |
| `policyDisplayName` | string | Display name of the leave policy |
| `leaveTypeUniqueId` | string | Unique identifier of the leave type |
| `numHours` | number | Duration in hours |
| `numMinutes` | number | Duration in minutes |
| `reasonForLeave` | string | Employee-provided reason for the leave |
| `requestedBy` | string | ID of the user who submitted the request |
| `requestedByName` | string | Name of the requester |
| `processedAt` | string (ISO 8601) | Timestamp when the request was processed |
| `processedBy` | string | ID of the user who processed the request |
| `processedByName` | string | Name of the processor |
| `managedBy` | string | System managing this leave: `PTO`, `LEAVES`, `TILT` |
| `isPaid` | boolean | Whether the leave is paid |
| `dates` | array[string] | Individual dates covered by the leave request |
| `partialDays` | object | Partial day leave configuration |
| `comments` | string | Comments on the leave request |
| `roleTimezone` | string | Timezone of the employee |
| `createdAt` | string (ISO 8601) | Record creation timestamp |
| `updatedAt` | string (ISO 8601) | Record last updated timestamp |

**Pagination:** Offset-based (legacy API).

**Example Request:**
```bash
curl -X GET 'https://api.rippling.com/platform/api/leave_requests?status=APPROVED&startDate=2024-01-01&limit=100' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 6. leave-types

**Description:** Returns the leave types configured for the company. Each leave type represents a category of leave (e.g., Vacation, Sick, Parental).

**Endpoint (legacy Platform API):**
```
GET https://api.rippling.com/platform/api/company_leave_types
```

**Required Scope:** TBD: Not explicitly documented; likely requires `workers.read` or leave-related scope.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `managedBy` | string | No | Filter by managing system: `PTO`, `LEAVES`, `TILT` |

**Response Schema — CompanyLeaveType Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the leave type |
| `key` | string | Machine-readable key for the leave type |
| `name` | string | Display name of the leave type |
| `description` | string | Description of the leave type |
| `unpaid` | boolean | Whether this leave type is unpaid |
| `managedBy` | string | System managing this type: `PTO`, `LEAVES`, or `TILT` |

**managedBy Values:**
- `PTO` — Managed by Rippling's Time Off application
- `LEAVES` — Managed by Rippling's Leave Management application
- `TILT` — Managed by the third-party partner Tilt

**Pagination:** TBD: No pagination parameters documented for this endpoint; likely returns all results in a single response.

**Example Request:**
```bash
curl -X GET 'https://api.rippling.com/platform/api/company_leave_types?managedBy=LEAVES' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 7. legal-entities

**Description:** Legal entity data in Rippling is accessible through the companies endpoint as an embedded/expanded field. There is no confirmed dedicated `/legal-entities` list endpoint in publicly documented API references. Legal entities are returned within the `legal_entities` array field on company objects, and as an expandable field on worker objects via `?expand=legal_entity`.

**Primary access pattern — via companies endpoint:**
```
GET https://rest.ripplingapis.com/companies
```

**Expand on workers:**
```
GET https://rest.ripplingapis.com/workers?expand=legal_entity
```

**Required Scope:** `companies.read`

**Response Schema — LegalEntity Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the legal entity |
| `created_at` | string (ISO 8601) | Record creation timestamp |
| `updated_at` | string (ISO 8601) | Record last updated timestamp |
| `tax_identifier` | string | Tax ID (e.g., EIN for US entities) |
| `country` | object | Country object with `code` property |
| `legal_name` | string | Legal registered name of the entity |
| `entity_level` | string | Hierarchy level in the organization structure |
| `registration_date` | string | Entity registration date |
| `mailing_address` | object | Mailing address (see Address schema under companies) |
| `physical_address` | object | Physical address (see Address schema under companies) |
| `parent_id` | string or null | ID of the parent entity |
| `parent` | object or null | Nested parent entity object |
| `management_type` | string | `EOR` (Employer of Record) or `PEO` (Professional Employer Organization) |
| `company_id` | string | Associated company ID |

**Note:** If Rippling has added a dedicated `/legal-entities` list endpoint in newer API versions, it would follow the pattern: `GET https://rest.ripplingapis.com/legal-entities` with standard cursor-based pagination. Check the official developer portal at https://developer.rippling.com/documentation/rest-api/reference for the latest endpoint availability.

---

### 8. teams

**Description:** Returns the list of teams configured for the company. Teams support parent/child hierarchy (subteams).

**Endpoint (newer REST API):**
```
GET https://rest.ripplingapis.com/teams
```

**Endpoint (legacy Platform API):**
```
GET https://api.rippling.com/platform/api/teams
```

**Required Scope:** `teams.read`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100, default 50) |
| `cursor` | string | No | Cursor for next page |
| `offset` | integer | No | Offset for legacy API |

**Response Schema — Team Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the team |
| `name` | string | Team name |
| `parent` | string or null | ID of the parent team (null if top-level) |

**Pagination:** Cursor-based (newer API) or offset-based (legacy).

**Example Request:**
```bash
curl -X GET 'https://rest.ripplingapis.com/teams' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 9. levels

**Description:** Returns the organizational levels configured for the company (e.g., IC1, IC2, Manager, Director, VP, Executive). Levels represent seniority or role tiers.

**Endpoint (newer REST API):**
```
GET https://rest.ripplingapis.com/levels
```

**Endpoint (legacy Platform API):**
```
GET https://api.rippling.com/platform/api/levels
```

**Required Scope:** TBD: Not explicitly documented; likely `workers.read` or `companies.read`.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100, default 50) |
| `cursor` | string | No | Cursor for next page |
| `offset` | integer | No | Offset for legacy API |

**Response Schema — Level Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the level |
| `name` | string | Display name of the level (e.g., "Manager", "Executive") |
| `parent` | string or null | ID of the parent level (null if top-level) |

**Pagination:** Cursor-based (newer API) or offset-based (legacy).

**Example Request:**
```bash
curl -X GET 'https://rest.ripplingapis.com/levels' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 10. tracks

**Description:** Returns the career tracks configured for the company. Tracks represent career paths or job ladders (e.g., Engineering Track, Management Track). The `tracks` field is referenced as an expandable field on worker profiles.

**Endpoint (newer REST API — inferred from naming conventions):**
```
GET https://rest.ripplingapis.com/tracks
```

**Endpoint (legacy Platform API — inferred):**
```
GET https://api.rippling.com/platform/api/tracks
```

TBD: A dedicated `list-tracks` endpoint page was not found in publicly indexed documentation. The tracks resource appears in the API (referenced as an expandable field on workers and mentioned in the Prismatic component integration as a picklist object). The endpoint URL above is inferred from Rippling's URL naming conventions (lower kebab-case plural nouns). Verify availability at https://developer.rippling.com/documentation/rest-api/reference.

**Required Scope:** TBD: Likely `workers.read` or `companies.read`.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100, default 50) |
| `cursor` | string | No | Cursor for next page |

**Response Schema — Track Object (inferred):**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the track |
| `name` | string | Display name of the track (e.g., "Engineering Track") |
| `description` | string | Description of the career track |

**Pagination:** Cursor-based (inferred from newer REST API conventions).

---

### 11. work-locations

**Description:** Returns the list of work locations for the company. Each work location has a physical address and can be used to determine where workers are based.

**Endpoint (newer REST API):**
```
GET https://rest.ripplingapis.com/work-locations
```

**Endpoint (legacy Platform API):**
```
GET https://api.rippling.com/platform/api/work_locations
```

**Required Scope:** TBD: Not explicitly documented; likely `companies.read` or `workers.read`.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100, default 50) |
| `cursor` | string | No | Cursor for next page |
| `offset` | integer | No | Offset for legacy API |

**Response Schema — WorkLocation Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the work location |
| `created_at` | string (ISO 8601) | Record creation timestamp |
| `updated_at` | string (ISO 8601) | Record last updated timestamp |
| `name` | string | Display name / nickname of the location |
| `address` | object | Address details (see Address schema) |

**Address Schema (nested):**

| Field | Type | Description |
|-------|------|-------------|
| `streetLine1` | string | Street address line 1 |
| `streetLine2` | string | Street address line 2 |
| `city` | string | City |
| `state` | string | State/province code |
| `zip` | string | Postal/ZIP code |
| `country` | string | Country code |
| `phone` | string | Location phone number |
| `isRemote` | boolean | Whether the location is a remote/virtual location |

**Pagination:** Cursor-based (newer API) or offset-based (legacy).

**Example Request:**
```bash
curl -X GET 'https://rest.ripplingapis.com/work-locations' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 12. workers

**Description:** Returns a paginated list of workers. A worker represents a person's HR "worker profile" — their employment or engagement with the company. A single person may have multiple worker records (e.g., active + past employment). Workers can have related data expanded inline via the `expand` parameter.

**Endpoint (newer REST API — list):**
```
GET https://rest.ripplingapis.com/workers
```

**Endpoint (newer REST API — single worker):**
```
GET https://rest.ripplingapis.com/workers/{id}
```

**Required Scope:** `workers.read`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100, default 50) |
| `cursor` | string | No | Cursor for next page |
| `expand` | string | No | Comma-separated list of fields to expand inline (up to 10, 2 levels of nesting) |
| `status` | string | No | Filter by worker status |
| `work_email` | string | No | Filter by work email address |
| `user_id` | string | No | Filter by user ID |
| `created_at` | string | No | Filter by creation date |
| `updated_at` | string | No | Filter by last updated date |

**Expandable Fields:**

| Expand Value | Description |
|--------------|-------------|
| `user` | Inline the associated user account object |
| `manager` | Inline the manager's worker object |
| `legal_entity` | Inline the legal entity object |
| `employment_type` | Inline the employment type object |
| `compensation` | Inline compensation details (requires `compensation.read` scope) |
| `department` | Inline the department object |

**Response Schema — Worker Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the worker profile |
| `created_at` | string (ISO 8601) | Record creation timestamp |
| `updated_at` | string (ISO 8601) | Record last updated timestamp |
| `user_id` | string | ID of the associated user account |
| `user` | string or object | User ID or expanded user object (if `expand=user`) |
| `manager` | string or object | Manager's worker ID or expanded worker object |
| `legal_entity` | string or object | Legal entity ID or expanded object |
| `employment_type` | string or object | Employment type ID or expanded object |
| `department` | string or object | Department ID or expanded object |
| `compensation` | object | Compensation details (if expanded and scope permits) |
| `__meta` | object | Metadata including `redacted_fields` for inaccessible fields |

**Expanded User Object Schema (when `expand=user`):**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | User ID |
| `created_at` | string (ISO 8601) | User creation timestamp |
| `updated_at` | string (ISO 8601) | User last updated timestamp |
| `active` | boolean | Whether the user account is active |
| `username` | string | Username |
| `name` | object | Name object (see Name schema) |
| `display_name` | string | Display/preferred name |
| `emails` | array[object] | Email addresses |
| `phone_numbers` | array[object] | Phone numbers |
| `addresses` | array[object] | Physical addresses |
| `photos` | array[object] | Profile photos |
| `preferred_language` | string | Preferred language |
| `locale` | string | Locale setting |
| `timezone` | string | Timezone |
| `number` | string | Employee number |

**Name Schema (within user.name):**

| Field | Type | Description |
|-------|------|-------------|
| `formatted` | string | Full formatted name |
| `given_name` | string | First name |
| `middle_name` | string | Middle name |
| `family_name` | string | Last name |
| `preferred_given_name` | string | Preferred first name |
| `preferred_family_name` | string | Preferred last name |

**Pagination:** Cursor-based; `next_link` in response body.

**Example Request:**
```bash
curl -X GET 'https://rest.ripplingapis.com/workers?limit=100&expand=user,employment_type,department,legal_entity' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

**Example Response (abbreviated):**
```json
{
  "next_link": "/workers?limit=100&cursor=dXNlcjpVMEc5V0ZYTlo",
  "results": [
    {
      "id": "wkr_abc123",
      "created_at": "2023-01-15T10:00:00Z",
      "updated_at": "2024-06-01T08:30:00Z",
      "user_id": "usr_xyz789",
      "user": {
        "id": "usr_xyz789",
        "active": true,
        "name": {
          "formatted": "Jane Doe",
          "given_name": "Jane",
          "family_name": "Doe"
        },
        "emails": [{"value": "jane.doe@acme.com", "type": "work"}]
      },
      "department": {
        "id": "dept_eng",
        "name": "Engineering"
      },
      "__meta": {
        "redacted_fields": []
      }
    }
  ]
}
```

---

### 13. users

**Description:** Returns a paginated list of all users in the organization. A user represents an account that can authenticate and be granted access/roles in Rippling and connected apps. Unlike workers (which represent HR profiles), users represent the identity/authentication layer.

**Endpoint (newer REST API — list):**
```
GET https://rest.ripplingapis.com/users
```

**Endpoint (newer REST API — single user):**
```
GET https://rest.ripplingapis.com/users/{id}
```

**Required Scope:** `users.read`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100, default 50) |
| `cursor` | string | No | Cursor for next page |

**Response Schema — User Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the user |
| `created_at` | string (ISO 8601) | Record creation timestamp |
| `updated_at` | string (ISO 8601) | Record last updated timestamp |
| `active` | boolean | Whether the user account is active |
| `username` | string | Login username |
| `name` | object | Name object (see Name schema) |
| `display_name` | string | Display/preferred name |
| `emails` | array[object] | List of email address objects |
| `phone_numbers` | array[object] | List of phone number objects |
| `addresses` | array[object] | List of address objects |
| `photos` | array[object] | List of photo URL objects |
| `preferred_language` | string | Preferred language code |
| `locale` | string | Locale/region setting |
| `timezone` | string | User's timezone |
| `number` | string | Employee number |
| `__meta` | object | Metadata including `redacted_fields` |

**Name Schema (within name):**

| Field | Type | Description |
|-------|------|-------------|
| `formatted` | string | Full formatted name string |
| `given_name` | string | First name |
| `middle_name` | string | Middle name |
| `family_name` | string | Last name |
| `preferred_given_name` | string | Preferred first name |
| `preferred_family_name` | string | Preferred last name |

**Email Object Schema (within emails):**

| Field | Type | Description |
|-------|------|-------------|
| `value` | string | Email address |
| `type` | string | Email type (e.g., `work`, `personal`) |
| `primary` | boolean | Whether this is the primary email |

**Pagination:** Cursor-based; `next_link` in response body.

**Example Request:**
```bash
curl -X GET 'https://rest.ripplingapis.com/users' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

### 14. custom-fields

**Description:** Returns the custom field definitions configured for the company. These define the metadata of custom fields that can be attached to employee/worker records.

**Endpoint (legacy Platform API):**
```
GET https://api.rippling.com/platform/api/custom_fields
```

**Required Scope:** `custom-fields.read`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max records per page (max 100) |
| `offset` | integer | No | Pagination offset |

**Response Schema — CustomField Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier of the custom field |
| `type` | string | Field type: `TEXT`, `DATE`, `NUMBER`, or other enum values |
| `title` | string | Display title/name of the custom field |
| `mandatory` | boolean | Whether this field is required for all employees |

**Note:** Custom field values attached to individual workers are accessible via `?expand=custom_fields` on the `/workers` endpoint (legacy employees endpoint). The `/custom_fields` endpoint returns only the field definitions (metadata), not the per-employee values.

**Pagination:** Offset-based (legacy API).

**Example Request:**
```bash
curl -X GET 'https://api.rippling.com/platform/api/custom_fields?limit=100&offset=0' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <TOKEN>'
```

---

## Incremental Sync Strategy

### Cursor / Timestamp Field

Workers and users include `created_at` and `updated_at` timestamps, which can be used for incremental sync. The workers endpoint supports filtering by `created_at` and `updated_at` as query parameters.

| Table | Cursor Field | Filter Param | Notes |
|-------|-------------|--------------|-------|
| `workers` | `updated_at` | `updated_at` | ISO 8601 timestamp |
| `users` | `updated_at` | TBD: Filter support not confirmed | Use full refresh as fallback |
| `companies` | `updated_at` | TBD | Small dataset; full refresh acceptable |
| `departments` | — | None documented | Full refresh recommended (small dataset) |
| `teams` | — | None documented | Full refresh recommended (small dataset) |
| `levels` | — | None documented | Full refresh recommended (small dataset) |
| `work-locations` | — | None documented | Full refresh recommended (small dataset) |
| `employment-types` | `updated_at` | TBD | Full refresh acceptable |
| `leave-requests` | `updatedAt` or `startDate` | `startDate`, `endDate` | Filter by date range for incremental |
| `leave-balances` | — | None documented | Full refresh recommended |
| `leave-types` | — | None documented | Full refresh (rarely changes) |
| `custom-fields` | — | None documented | Full refresh (rarely changes) |

### Recommended Approach for `workers` (Primary Incremental Table)

1. On first sync: paginate all workers with `cursor`-based pagination, store the last `updated_at` timestamp.
2. On subsequent syncs: filter with `?updated_at=<last_sync_timestamp>` and paginate through results.
3. Always include terminated workers by checking `status` filter or using the legacy `include_terminated` endpoint.

### Delete Handling

Rippling does not document a soft-delete flag or tombstone records in the publicly available API documentation. Use the `status` field on workers to detect terminations. TBD: Confirm whether deleted records are removed from API responses or marked with a status field.

### Lookback Window

Recommend a 1–7 day lookback on the `updated_at` filter to account for late-arriving updates or clock skew.

---

## Known Quirks and Notes

1. **Two API domains exist:** The newer `rest.ripplingapis.com` domain uses cursor-based pagination; the legacy `api.rippling.com/platform/api` domain uses offset-based pagination. Some endpoints (leave, custom-fields) are only documented on the legacy domain. Some reference implementations may use the legacy domain.

2. **Field expansion up to 10 fields:** The `expand` parameter supports up to 10 comma-separated fields with up to 2 levels of nesting. Avoid requesting more than needed to minimize response payload size.

3. **Scope-based field redaction:** Fields not accessible due to scope are returned in `__meta.redacted_fields` rather than causing a 401/403 error. Check this field during development to confirm all expected fields are accessible.

4. **OAuth required for partners:** API tokens are for customer-direct integrations only. Multi-tenant partner integrations must use OAuth 2.0 and go through Rippling's partner program.

5. **Version-pinned tokens:** When an API token is created, a default API version is associated with it. Requests without a `Rippling-Api-Version` header use that default version — this prevents accidental breaking changes on token renewal.

6. **`tracks` endpoint not confirmed:** The `tracks` resource is referenced in third-party integration tools and worker expand fields, but no dedicated public documentation page was found during research. Confirm endpoint availability via the official developer portal or Rippling support.

7. **`legal-entities` as embedded data:** Legal entities appear to be accessible primarily through the companies endpoint or as an expanded field on workers, not via a dedicated list endpoint. Confirm with Rippling if a `/legal-entities` endpoint exists.

8. **Leave balance units are in minutes:** The `remaining_balance` field is denominated in minutes, not hours or days. Convert as needed.

9. **No sandbox accounts:** Rippling does not offer free sandbox/test accounts. API access requires a live Rippling company account. This was noted as a blocker in the Airbyte OSS contribution for Rippling.

10. **`managedBy` field on leave-types:** Leave types can be managed by Rippling's internal apps (`PTO`, `LEAVES`) or by a third-party (`TILT`). Filter by this field to scope leave data to the relevant management system.

---

## Python Usage Examples

### Full Sync with Cursor Pagination (Newer REST API)

```python
import requests

BASE_URL = "https://rest.ripplingapis.com"
TOKEN = "<YOUR_API_TOKEN>"

def fetch_all(endpoint: str, params: dict = None) -> list:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {TOKEN}",
    }
    results = []
    url = f"{BASE_URL}/{endpoint}"
    query_params = dict(params or {})
    query_params["limit"] = 100

    while url:
        response = requests.get(url, headers=headers, params=query_params)
        response.raise_for_status()
        data = response.json()
        results.extend(data.get("results", []))
        next_link = data.get("next_link")
        if next_link:
            url = f"{BASE_URL}{next_link}"
            query_params = {}  # next_link includes all params
        else:
            break

    return results

# Fetch all workers with user and department expanded
workers = fetch_all("workers", {"expand": "user,employment_type,department,legal_entity"})
```

### Incremental Sync for Workers

```python
from datetime import datetime, timedelta

def fetch_workers_incremental(last_sync_timestamp: str) -> list:
    return fetch_all("workers", {
        "updated_at": last_sync_timestamp,
        "expand": "user,employment_type,department",
    })

# Example: sync records updated in the last 24 hours with 1-day lookback
lookback = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
updated_workers = fetch_workers_incremental(lookback)
```

### Offset-Based Pagination (Legacy Platform API)

```python
def fetch_all_legacy(path: str, params: dict = None) -> list:
    BASE_LEGACY = "https://api.rippling.com/platform/api"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {TOKEN}",
    }
    results = []
    offset = 0
    limit = 100

    while True:
        query_params = {**(params or {}), "limit": limit, "offset": offset}
        response = requests.get(f"{BASE_LEGACY}/{path}", headers=headers, params=query_params)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        results.extend(data)
        if len(data) < limit:
            break
        offset += limit

    return results

# Fetch leave requests for a date range
leave_requests = fetch_all_legacy(
    "leave_requests",
    {"startDate": "2024-01-01", "endDate": "2024-12-31", "status": "APPROVED"}
)
```

---

## Research Log

| Source Type | URL | Accessed (UTC) | Confidence | What It Confirmed |
|-------------|-----|----------------|------------|-------------------|
| Official Docs | https://developer.rippling.com/documentation/rest-api | 2026-03-16 | High | Main entry point; JS-rendered, content not directly extractable |
| Official Blog | https://www.rippling.com/blog/enterprise-grade-apis | 2026-03-16 | High | Base URL (`rest.ripplingapis.com`), cursor pagination, `next_link`, versioning header (`Rippling-Api-Version: YYYY-MM-DD`), field expansion, `limit`/`cursor` params, API design conventions |
| OpenAPI Spec (via Stoplight) | https://stoplight.io/api/v1/projects/rippling/rippling-api/nodes/RipplingOpenAPI.v1.yaml | 2026-03-16 | High | All endpoint paths for both `rest.ripplingapis.com` and `api.rippling.com/platform/api`, auth scheme (Bearer), key schemas for Employee, Company, LeaveRequest, Group |
| Knit API Reference | https://developers.getknit.dev/docs/rippling-usecases | 2026-03-16 | Medium | Endpoint paths for all resources, response schema fields for departments, teams, levels, custom fields, leave balances, leave requests |
| Knit Blog | https://www.getknit.dev/blog/rippling-api-directory-uJqCLO | 2026-03-16 | Medium | Full endpoint list including leave_requests, leave_balances, departments, work_locations, teams, levels, custom_fields |
| Rippling Enterprise API Blog | https://www.rippling.com/blog/enterprise-grade-apis | 2026-03-16 | High | Cursor-based pagination details, `order_by` support, field expansion, scope format (`{resource}.{read|write}`) |
| APITracker | https://apitracker.io/a/rippling | 2026-03-16 | Medium | OAuth 2.0 confirmation, OpenAPI/Swagger spec URL, base URLs for production and sandbox |
| Search Results (multiple) | https://developer.rippling.com/documentation/rest-api/reference/list-workers | 2026-03-16 | High | Workers endpoint URL, expandable fields (user, manager, legal_entity, employment_type, compensation, department), filter params |
| Search Results | https://developer.rippling.com/documentation/rest-api/reference/list-users | 2026-03-16 | High | Users endpoint URL, user schema fields (id, active, username, name, emails, phone_numbers, addresses) |
| Search Results | https://developer.rippling.com/documentation/rest-api/reference/list-companies | 2026-03-16 | High | Companies endpoint, legal entity nested fields |
| Search Results | https://developer.rippling.com/documentation/rest-api/reference/list-employment-types | 2026-03-16 | High | Employment types endpoint URL |
| Search Results | https://developer.rippling.com/documentation/rest-api/reference/schemas/companyemploymenttype | 2026-03-16 | High | CompanyEmploymentType schema: id, created_at, updated_at, label, name, type (CONTRACTOR/EMPLOYEE), compensation_time_period |
| Search Results | https://developer.rippling.com/documentation/rest-api/reference/list-work-locations | 2026-03-16 | High | Work locations endpoint URL, address schema fields |
| Search Results | https://developer.rippling.com/documentation/rest-api/reference/list-teams | 2026-03-16 | High | Teams endpoint URL confirmed |
| Search Results | https://developer.rippling.com/documentation/base-api/reference/get-levels | 2026-03-16 | High | Levels endpoint URL, response schema (id, name, parent), offset/limit params |
| Search Results | https://developer.rippling.com/documentation/base-api/reference/get-company-leave-types | 2026-03-16 | High | Leave types endpoint URL, managedBy filter, schema fields (key, name, description, unpaid, managedBy) |
| Search Results | https://developer.rippling.com/documentation/base-api/reference/get-leave-requests | 2026-03-16 | High | Leave requests endpoint, full schema fields (role, status, startDate, endDate, leavePolicy, numHours, managedBy, etc.) |
| Search Results | https://developer.rippling.com/documentation/base-api/reference/get-leave-balances | 2026-03-16 | High | Leave balances endpoint, schema (role, company_leave_type_id, unlimited, remaining_balance) |
| Search Results | https://developer.rippling.com/documentation/rest-api/essentials/custom-fields-api | 2026-03-16 | Medium | Custom fields endpoint, schema (id, type, title, mandatory) |
| Rippling Developer Versioning | https://developer.rippling.com/documentation/rest-api/guides/versioning | 2026-03-16 | High | Header-based versioning (`Rippling-Api-Version: YYYY-MM-DD`), default version per token |
| Serval Docs | https://docs.serval.com/sections/integrations/rippling | 2026-03-16 | Medium | Confirmed scopes: companies.read, users.read/write, workers.read/write, departments.read, teams.read, custom-fields.read, supergroups.read |
| Merge Blog | https://www.merge.dev/blog/how-to-fetch-employees-from-rippling-with-merge-hris-unified-api-using-python | 2026-03-16 | Medium | OAuth 2.0 auth flow, offset-based pagination on legacy API, employee response schema fields |
| Airbyte Discussion | https://github.com/airbytehq/airbyte/discussions/35260 | 2026-03-16 | Low | No sandbox available; connector work put on hold |
| Prismatic Component Docs | https://prismatic.io/docs/components/rippling/ | 2026-03-16 | Medium | Confirmed available picklist objects: Department, Employment Type, Team, User, Worker, Work Location |
