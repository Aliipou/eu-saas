# ADR-001: Schema-Per-Tenant Isolation

## Status

Accepted

## Context

Multi-tenant SaaS platforms must isolate tenant data. Common approaches:
1. **Shared schema** with `tenant_id` column on every table
2. **Schema-per-tenant** within one database
3. **Database-per-tenant**

We need strong data isolation for GDPR compliance (EU data residency) while keeping operational costs manageable.

## Decision

Use **schema-per-tenant** isolation in PostgreSQL. Each tenant gets a dedicated schema (`tenant_{slug}`) with its own set of tables. Shared data (tenant registry, audit log) lives in the `public` schema.

## Consequences

### Positive
- Strong data isolation without the overhead of separate database instances
- `DROP SCHEMA CASCADE` enables clean GDPR Article 17 erasure
- Independent migration paths per tenant
- Query performance: no `tenant_id` filter on every query
- Connection pooling shared across all schemas

### Negative
- Schema count limited by PostgreSQL (practical limit ~10,000)
- Cross-tenant queries require explicit schema switching
- Migration complexity: must run per-tenant
- Connection `search_path` must be set per request

### Mitigations
- Celery task for batch migration execution
- Middleware sets `search_path` based on resolved tenant context
- Schema manager validates and sanitizes slug-to-schema mapping
