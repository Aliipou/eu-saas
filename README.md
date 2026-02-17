# EU Multi-Tenant Cloud Platform

EU-Grade Multi-Tenant Cloud Platform with cost-aware billing, GDPR-native compliance, and production-grade SaaS architecture.

## Architecture

```
src/
  domain/           # Business rules, models, domain services (zero dependencies)
  application/      # Use cases, orchestration, Celery tasks
  infrastructure/   # Database, auth, observability, external adapters
  presentation/     # FastAPI endpoints, middleware, schemas
```

**Clean Architecture** with strict dependency inversion: `Presentation -> Application -> Domain <- Infrastructure`.

### Key Design Decisions

- **Schema-per-tenant PostgreSQL isolation** for data residency and GDPR compliance
- **RS256 JWT** (asymmetric) with 15-minute access tokens, 7-day refresh tokens
- **Argon2id** password hashing (OWASP recommended)
- **RFC 9457 Problem Details** for all error responses
- **Tamper-evident audit log** with SHA-256 hash chain
- **Cost anomaly detection** via z-score analysis (2.5 sigma threshold, 7-day rolling window)

## Tech Stack

| Layer          | Technology                                  |
|----------------|---------------------------------------------|
| API Framework  | FastAPI 0.110+                              |
| Database       | PostgreSQL 16 (schema-per-tenant)           |
| ORM            | SQLAlchemy 2.0+ (async)                     |
| Migrations     | Alembic                                     |
| Task Queue     | Celery 5.3+ with Redis broker               |
| Auth           | python-jose (RS256), argon2-cffi            |
| Observability  | Prometheus, structlog (JSON), Loki, Grafana |
| Validation     | Pydantic v2                                 |
| Python         | 3.12+                                       |

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Redis 7+

### Local Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure environment
export APP_POSTGRES_HOST=localhost
export APP_POSTGRES_USER=postgres
export APP_POSTGRES_PASSWORD=postgres
export APP_POSTGRES_DB=eu_multitenant
export APP_REDIS_URL=redis://localhost:6379/0
export APP_JWT_PRIVATE_KEY="$(cat private.pem)"
export APP_JWT_PUBLIC_KEY="$(cat public.pem)"

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn presentation.main:app --reload --host 0.0.0.0 --port 8000

# Start Celery worker (separate terminal)
celery -A application.tasks.celery_app worker --loglevel=info

# Start Celery beat scheduler (separate terminal)
celery -A application.tasks.celery_app beat --loglevel=info
```

### Docker

```bash
cd deploy/docker
docker compose up -d
```

Services: API (:8000), PostgreSQL (:5432), Redis (:6379), Prometheus (:9090), Grafana (:3000), Loki (:3100).

## API Endpoints

### Tenants
| Method   | Path                             | Description              |
|----------|----------------------------------|--------------------------|
| `POST`   | `/api/v1/tenants`                | Create tenant            |
| `GET`    | `/api/v1/tenants`                | List tenants (paginated) |
| `GET`    | `/api/v1/tenants/{id}`           | Get tenant details       |
| `PATCH`  | `/api/v1/tenants/{id}`           | Update tenant            |
| `POST`   | `/api/v1/tenants/{id}/suspend`   | Suspend tenant           |
| `POST`   | `/api/v1/tenants/{id}/activate`  | Reactivate tenant        |
| `DELETE` | `/api/v1/tenants/{id}`           | Deprovision tenant       |

### Authentication
| Method | Path                    | Description         |
|--------|-------------------------|---------------------|
| `POST` | `/api/v1/auth/register` | Register user       |
| `POST` | `/api/v1/auth/login`    | Login (get tokens)  |
| `POST` | `/api/v1/auth/refresh`  | Refresh tokens      |
| `POST` | `/api/v1/auth/logout`   | Logout              |
| `GET`  | `/api/v1/auth/me`       | Current user        |

### Billing
| Method | Path                                     | Description           |
|--------|------------------------------------------|-----------------------|
| `GET`  | `/api/v1/tenants/{id}/costs`             | Cost breakdown        |
| `GET`  | `/api/v1/tenants/{id}/costs/current`     | Current period costs  |
| `GET`  | `/api/v1/tenants/{id}/costs/projection`  | Monthly projection    |
| `GET`  | `/api/v1/tenants/{id}/invoices`          | List invoices         |
| `GET`  | `/api/v1/tenants/{id}/invoices/{inv_id}` | Invoice detail        |
| `GET`  | `/api/v1/tenants/{id}/anomalies`         | Cost anomalies        |

### GDPR Compliance
| Method | Path                                          | Description          |
|--------|-----------------------------------------------|----------------------|
| `POST` | `/api/v1/tenants/{id}/gdpr/export`            | Request data export  |
| `GET`  | `/api/v1/tenants/{id}/gdpr/export/{job_id}`   | Export status        |
| `POST` | `/api/v1/tenants/{id}/gdpr/erase`             | Right to erasure     |
| `GET`  | `/api/v1/tenants/{id}/gdpr/retention`         | Get retention policy |
| `PUT`  | `/api/v1/tenants/{id}/gdpr/retention`         | Update retention     |
| `GET`  | `/api/v1/tenants/{id}/audit-log`              | Audit trail          |

### Operations
| Method | Path       | Description  |
|--------|------------|--------------|
| `GET`  | `/health`  | Health check |
| `GET`  | `/metrics` | Prometheus   |

## Tenant Lifecycle

```
PENDING -> PROVISIONING -> ACTIVE -> SUSPENDED -> DEPROVISIONING -> DELETED
                              |          ^
                              +----------+
```

Each transition is validated by the domain `TenantLifecycleService` and recorded in the tamper-evident audit log.

## GDPR Compliance

- **Article 17 (Right to Erasure)**: 7-step pipeline: freeze tenant, export backup, cascade delete data, drop schema, purge caches, create audit entry, transition to DELETED
- **Article 20 (Data Portability)**: Export all tenant data as JSON/CSV/XML archive with manifest
- **Retention Policies**: Configurable per-tenant with soft-delete grace periods and hard-delete enforcement

## Testing

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests (requires PostgreSQL + Redis)
pytest tests/integration/ -v

# Contract tests
pytest tests/contract/ -v

# Load tests
locust -f tests/load/locustfile.py --host http://localhost:8000

# Full suite with coverage
pytest tests/unit/ -v --cov=src --cov-report=term-missing
```

### Test Categories

| Category    | Count | Focus                                    |
|-------------|-------|------------------------------------------|
| Unit        | 215   | Domain models, services, infrastructure  |
| Integration | 21    | Database, schema manager, lifecycle      |
| Contract    | 14    | OpenAPI schema, RFC 9457 validation      |
| Load        | -     | 100 concurrent users, p95 < 200ms       |

## Code Quality

```bash
# Linting
ruff check src/

# Formatting
black --check src/

# Type checking
mypy src/ --ignore-missing-imports

# Security scanning
bandit -r src/
safety check
```

## Deployment

### Kubernetes

```bash
kubectl apply -f deploy/k8s/namespace.yml
kubectl apply -f deploy/k8s/
```

### Terraform (Hetzner Cloud)

```bash
cd deploy/terraform
terraform init
terraform plan
terraform apply
```

## Configuration

All settings are loaded via environment variables with the `APP_` prefix (see `src/infrastructure/settings.py`).

| Variable                       | Default                          | Description                |
|--------------------------------|----------------------------------|----------------------------|
| `APP_POSTGRES_HOST`            | `localhost`                      | PostgreSQL host            |
| `APP_POSTGRES_PORT`            | `5432`                           | PostgreSQL port            |
| `APP_POSTGRES_DB`              | `eu_multitenant`                 | Database name              |
| `APP_REDIS_URL`                | `redis://localhost:6379/0`       | Redis connection URL       |
| `APP_JWT_PRIVATE_KEY`          | -                                | RS256 private key (PEM)    |
| `APP_JWT_PUBLIC_KEY`           | -                                | RS256 public key (PEM)     |
| `APP_JWT_ISSUER`               | `eu-multi-tenant-platform`       | JWT issuer claim           |
| `APP_JWT_ACCESS_TOKEN_MINUTES` | `15`                             | Access token TTL           |
| `APP_JWT_REFRESH_TOKEN_DAYS`   | `7`                              | Refresh token TTL          |
| `APP_CELERY_BROKER_URL`        | `redis://localhost:6379/1`       | Celery broker              |
| `APP_LOG_LEVEL`                | `INFO`                           | Log level                  |

## License

Proprietary
