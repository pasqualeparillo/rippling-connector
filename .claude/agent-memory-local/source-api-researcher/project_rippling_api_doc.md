---
name: rippling_api_doc
description: Rippling REST API documentation research completed - covers all 14 tables, key findings about dual API domains and schema details
type: project
---

# Rippling API Documentation Research - Completed

**Output file:** `src/databricks/labs/community_connector/sources/rippling/rippling_api_doc.md`

**Completed:** 2026-03-16

## Key Findings

### Two API Domains
- **Newer REST API:** `https://rest.ripplingapis.com` — cursor-based pagination, `next_link` in response
- **Legacy Platform API:** `https://api.rippling.com/platform/api` — offset-based pagination

### Authentication
- Bearer token via `Authorization: Bearer <TOKEN>` header
- API tokens for customers; OAuth 2.0 required for partners
- Token endpoint: `https://api.rippling.com/api/o/token/`
- Tokens expire after 30 days of inactivity

### Versioning
- Header: `Rippling-Api-Version: YYYY-MM-DD`
- Default version pinned to API token creation date

### Pagination (newer API)
- Cursor-based: `?limit=100&cursor=<opaque_cursor>`
- Response contains `next_link` field with full URL for next page
- Default limit 50, max 100

### Tables Documented (14 total)
1. `companies` — `GET /companies` — legal entities embedded
2. `departments` — `GET /departments` — id, name, parent
3. `employment-types` — `GET /employment-types` — id, label, type (CONTRACTOR/EMPLOYEE), compensation_time_period
4. `leave-balances` — legacy `GET /leave_balances` — role, company_leave_type_id, unlimited, remaining_balance (minutes)
5. `leave-requests` — legacy `GET /leave_requests` — full request lifecycle fields, filter by status/dates
6. `leave-types` — legacy `GET /company_leave_types` — key, name, unpaid, managedBy (PTO/LEAVES/TILT)
7. `legal-entities` — NO dedicated endpoint found; embedded in companies response and expandable on workers
8. `teams` — `GET /teams` — id, name, parent
9. `levels` — `GET /levels` — id, name, parent
10. `tracks` — NO confirmed dedicated endpoint; TBD, inferred URL: `GET /tracks`
11. `work-locations` — `GET /work-locations` — id, name, address object
12. `workers` — `GET /workers` — expandable: user, manager, legal_entity, employment_type, compensation, department
13. `users` — `GET /users` — id, active, username, name, emails, phone_numbers, addresses
14. `custom-fields` — legacy `GET /custom_fields` — id, type, title, mandatory (field definitions only)

### Important Notes
- No sandbox accounts available (blocks automated testing)
- `tracks` endpoint NOT confirmed in public docs — verify at developer portal
- `legal-entities` has NO dedicated list endpoint — access via companies or expand on workers
- Leave balance units are in minutes
- Worker `__meta.redacted_fields` shows inaccessible fields due to scope
- Rate limits: not publicly documented; handle HTTP 429 with retry/backoff
