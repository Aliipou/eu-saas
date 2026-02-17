# ADR-004: Clean Architecture

## Status

Accepted

## Context

The platform needs a maintainable architecture that supports:
- Independent testing of business logic
- Swappable infrastructure (database, cache, message broker)
- Clear boundaries between concerns
- Long-term maintainability

## Decision

Adopt **Clean Architecture** with four layers:

1. **Domain** (`src/domain/`): Models, domain services, events, exceptions. Zero external dependencies.
2. **Application** (`src/application/`): Use-case orchestration, Celery tasks. Depends only on domain.
3. **Infrastructure** (`src/infrastructure/`): Database repos, auth, GDPR handlers, observability. Implements domain ports.
4. **Presentation** (`src/presentation/`): FastAPI endpoints, middleware, schemas. Depends on application and infrastructure.

Dependency inversion is enforced via Python `Protocol` classes defined in the application layer and implemented by infrastructure adapters.

## Consequences

### Positive
- Domain logic is testable with in-memory adapters (no database needed)
- Infrastructure is swappable (e.g., replace PostgreSQL with another store)
- Clear responsibility boundaries
- Enforced by import structure and linting

### Negative
- More files and indirection than a simple layered approach
- Mapping between domain models and API schemas adds boilerplate
- Protocol classes add maintenance overhead

## Testing Strategy
- Unit tests use in-memory adapters (Protocol implementations)
- Integration tests use real PostgreSQL via testcontainers
- Contract tests validate API schema compliance
