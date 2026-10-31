# URL Shortener

Production-oriented URL shortening service built with FastAPI, SQLAlchemy, SQLite, and a clean service/repository split.

## Overview

The service supports shortening URLs, redirecting short links, and retrieving basic analytics. The implementation keeps business logic inside the service layer and leaves routes as thin request/response adapters.

## Features

- Shorten valid `http` and `https` URLs.
- Redirect short codes to their original destinations.
- Track click counts and last access timestamps.
- Optionally set a time-to-live for each shortened URL.
- Expose health and analytics endpoints.
- Generate short codes from numeric database IDs using Base62 encoding.
- Include structured logging and test coverage for the core flows.

## Architecture

The request path is intentionally simple:

Client -> FastAPI Routes -> Service Layer -> Repository Layer -> Database

- Routes validate input shape and map HTTP concerns.
- Services contain business rules, code generation, and orchestration.
- Repositories encapsulate persistence concerns.
- Utilities provide reusable helpers such as Base62 conversion and URL validation.

## Folder Structure

```text
app/
  api/routes.py
  core/config.py
  core/logging.py
  db/database.py
  db/models.py
  repositories/url_repository.py
  schemas/url.py
  services/shortener.py
  utils/base62.py
  utils/validators.py
  main.py
tests/
```

## Setup

1. Create a virtual environment with Python 3.12+.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and adjust values as needed.

4. Run the API:

```bash
uvicorn app.main:app --reload
```

## Environment Variables

- `DATABASE_URL`: SQLAlchemy database URL. SQLite is the default, but PostgreSQL can be enabled by changing this value.
- `BASE_URL`: Base public URL used when generating short links.
- `LOG_LEVEL`: Logging verbosity such as `INFO` or `DEBUG`.

## API Examples

### Shorten a URL

```bash
curl -X POST http://localhost:8000/api/v1/shorten \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","ttl_seconds":3600}'
```

Example response:

```json
{
  "short_code": "1",
  "short_url": "http://localhost:8000/1",
  "expires_at": "2026-07-03T15:00:00Z"
}
```

### Redirect

```bash
curl -I http://localhost:8000/1
```

### Analytics

```bash
curl http://localhost:8000/api/v1/stats/1
```

### Health Check

```bash
curl http://localhost:8000/health
```

## Testing

Run the test suite with:

```bash
pytest
```

The tests cover:

- Base62 encoding and decoding.
- URL validation.
- URL creation.
- Redirect lookup and click tracking.
- Analytics responses.

## Scalability Considerations

These are not implemented in this project, but they fit naturally into the architecture:

- Redis caching: cache short code lookups in the repository or service layer to reduce database reads for hot links.
- Load balancing: place multiple FastAPI instances behind a balancer; the stateless API design already supports horizontal scaling.
- Read replicas: direct analytics and redirect reads to replicas while keeping writes on the primary database.
- PostgreSQL migration: change `DATABASE_URL` and run migrations; the SQLAlchemy model layer is database-agnostic.
- Background worker for analytics: batch non-critical click events asynchronously to reduce redirect latency.
- Custom aliases: add an alternate code generation strategy in the service layer while preserving the repository contract.
- URL expiration: add an `expires_at` column and enforce it in the service before redirects.
- Rate limiting: apply middleware or a gateway-level rule before the API layer to limit abuse.
- Prometheus metrics: instrument route timing, redirect counts, and error rates from the application layer.
- Docker deployment: containerize the app and database separately for consistent environments.
- Kubernetes deployment: run the API as a deployment with readiness/liveness probes and autoscaling.

## Notes

The current implementation uses SQLite for local simplicity, but the code structure is ready for a PostgreSQL-backed deployment with configuration-only changes.