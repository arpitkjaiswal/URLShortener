# URL Shortener

**A little link. A long way.** A full-stack link management app built with FastAPI, SQLAlchemy, PostgreSQL, and vanilla JavaScript. Shorten a URL, share it, track visits, and manage links from a private browser workspace.

[![Tests](https://github.com/arpitkjaiswal/URLShortener/actions/workflows/ci.yml/badge.svg)](https://github.com/arpitkjaiswal/URLShortener/actions/workflows/ci.yml)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/arpitkjaiswal/URLShortener)

![Desktop dashboard](docs/dashboard-desktop.webp)

Screenshots show a real local test run. [View the mobile layout](docs/dashboard-mobile.webp). Your deployed links will use your Render hostname.

## What it does

- **Short links:** seven-character, cryptographically random Base62 codes, with database-enforced uniqueness and collision retries.
- **Reliable redirects:** public HTTP 307 redirects, atomic click increments, and no redirect caching. HEAD checks do not inflate clicks.
- **Expiration:** optional lifetime from one second to one year. Expired links stop redirecting; their owners can still inspect analytics or delete them.
- **Private management:** each browser receives an HTTP-only workspace cookie. Only that workspace can list, inspect, or delete its links; recipients need no cookie to follow a shared link.
- **Dashboard:** copy links, view analytics, search, paginate, refresh, and delete with confirmation. Responsive desktop and mobile layouts, keyboard-accessible dialogs, and visible error/retry states.
- **Persistence:** SQLite for local development and PostgreSQL for deployment. Existing URL tables receive a non-destructive additive migration.
- **Deployment:** Render Blueprint, database-aware health checks, same-origin frontend requests, and automatic public URL configuration.
- **Verification:** API and regression tests, a PostgreSQL CI job, lint checks, and a Chromium browser flow.

**No account signup is required.** Workspace access is tied to this browser's cookie, not to an email address. Clearing cookies, changing domain, or switching browsers creates a new workspace. Save the short URLs you want to keep. There is no account recovery or cross-device synchronization.

## Run locally

Use Python **3.12**. From your terminal:

```bash
git clone https://github.com/arpitkjaiswal/URLShortener.git
cd URLShortener
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell (use this instead)
.venv\Scripts\Activate.ps1
```

Then:

```bash
pip install -r URL-SHORTNER/requirements-dev.txt
cd URL-SHORTNER
cp .env.example .env
uvicorn app.main:app --reload
```

On Windows, replace `cp .env.example .env` with `Copy-Item .env.example .env`.

Open **http://localhost:8000**. The API docs are at **http://localhost:8000/docs**. SQLite tables are created automatically at startup. Use the same origin as `BASE_URL`; if you prefer `http://127.0.0.1:8000`, set that exact value in `.env` and restart.

The application source lives in `URL-SHORTNER/` (the original repository folder name). Run Uvicorn from that directory.

## Deploy on Render

### Recommended setup: Blueprint

1. Click **Deploy to Render** above, or open Render → **New → Blueprint** and connect this repository.
2. Select the **main** branch and the root-level **render.yaml** file.
3. Review the web service and PostgreSQL database plans, then deploy. The Blueprint connects `DATABASE_URL` automatically.
4. Wait for the web service's health check to pass, then open the assigned `https://…onrender.com` address.
5. Create a link, open it, check that **Insights** shows a click, and delete it. See the [deployment checklist](docs/DEPLOYMENT.md) for the full smoke test.

**Do not add `BASE_URL=http://localhost:8000` on Render.** Leave `BASE_URL` unset unless using a custom domain; the application uses Render's `RENDER_EXTERNAL_URL` automatically. The frontend and API run in one web service, so there is no separate frontend deployment or CORS setup.

### Manual web service settings

First create a Render PostgreSQL database. Create a **Web Service**, not a Static Site, using this repository:

| Setting | Value |
| --- | --- |
| Branch | `main` |
| Runtime | Python 3 |
| Root Directory | `URL-SHORTNER` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health Check Path | `/health` |
| `PYTHON_VERSION` | `3.12.14` |
| `DATABASE_URL` | Your PostgreSQL **Internal Database URL**, in the same region |
| `BASE_URL` | Leave unset; set only for a custom domain |

**For a lasting resume demo:** the supplied Blueprint uses free resources as a starting point. Render's free web services sleep after 15 minutes without traffic, and free PostgreSQL databases expire after 30 days. Upgrade the database before expiration or configure a persistent external PostgreSQL service. Use an always-on web plan if you want interviewers to avoid a cold start. These are hosting limitations, not issues fixed by application code. [Render free-tier documentation](https://render.com/docs/free).

Never use local SQLite on an ephemeral Render filesystem. The application deliberately refuses to start on Render without PostgreSQL, instead of appearing to work and then losing links on restart. No paid resources are provisioned by cloning this repository; Render shows the plans before you deploy.

## Configuration

| Variable | Local default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./url_shortener.db` | PostgreSQL required on Render; `postgres://`, `postgresql://`, and `postgresql+psycopg://` are supported |
| `BASE_URL` | `RENDER_EXTERNAL_URL`, otherwise `http://localhost:8000` | Public origin for generated links; no path, query, or credentials |
| `LOG_LEVEL` | `INFO` | Application log level |
| `CREATE_LIMIT_PER_MINUTE` | `30` | Link creation attempts per client IP, per process |
| `PORT` | Supplied by Render | Used by the Render start command |

Set secrets in Render's Environment settings, never in Git. `.env`, virtual environments, SQLite databases, and Python bytecode are ignored.

## API quickstart

Management endpoints require a workspace cookie. This works with `curl` as well as the dashboard:

```bash
# 1. Initialize a workspace and keep the cookie jar private.
curl -c cookies.txt http://localhost:8000/api/v1/session

# 2. Create a link in that workspace.
curl -b cookies.txt -X POST http://localhost:8000/api/v1/shorten \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","ttl_seconds":3600}'
```

Example response (your code and expiry will differ):

```json
{
  "short_code": "7xKp2Qw",
  "short_url": "http://localhost:8000/7xKp2Qw",
  "expires_at": "2026-11-01T12:00:00Z"
}
```

Use the returned `short_code` in the following commands:

```bash
# A GET counts a visit and returns the destination in the Location header.
curl -i http://localhost:8000/7xKp2Qw

# A HEAD checks the destination without counting a visit.
curl -I http://localhost:8000/7xKp2Qw

# Private analytics, collection, summary, and deletion.
curl -b cookies.txt http://localhost:8000/api/v1/stats/7xKp2Qw
curl -b cookies.txt 'http://localhost:8000/api/v1/urls?limit=10&offset=0&q=example'
curl -b cookies.txt http://localhost:8000/api/v1/summary
curl -b cookies.txt -X DELETE http://localhost:8000/api/v1/urls/7xKp2Qw
```

| Method | Endpoint | Access / behavior |
| --- | --- | --- |
| GET | `/` | Dashboard |
| GET | `/health` | Database connectivity check; 200 healthy, 503 unavailable |
| GET | `/api/v1/session` | Initialize or renew the browser workspace cookie |
| POST | `/api/v1/shorten` | Workspace required; 201 on creation |
| GET | `/{short_code}` | Public redirect; increments clicks atomically |
| HEAD | `/{short_code}` | Public redirect headers; no click increment |
| GET | `/api/v1/stats/{short_code}` | Owner-only analytics, including expired links |
| GET | `/api/v1/urls` | Owner-only paginated collection; `limit` 1–50, `offset`, `q` |
| GET | `/api/v1/summary` | Owner-only counts of links, clicks, active and expired links |
| DELETE | `/api/v1/urls/{short_code}` | Owner only; 204 on deletion |

Malformed input returns 400/422, missing workspace cookies return 401, foreign-origin mutations return 403, unknown or inaccessible links return 404, creation throttling returns 429 with `Retry-After`, and database failures return a safe 503 response. Missing/expired links show a helpful page to browsers.

## Architecture and decisions

```mermaid
flowchart TD
    Browser[Browser dashboard] --> Routes[FastAPI routes]
    Routes --> Workspace[Workspace authorization]
    Workspace --> Service[Shortener service]
    Service --> Repository[SQLAlchemy repository]
    Repository --> DB[(PostgreSQL / local SQLite)]
    Visitor[Shared-link visitor] --> Redirect[Atomic redirect and click update]
    Redirect --> Repository
```

- **No frontend build pipeline:** HTML/CSS/JavaScript assets are served by FastAPI and call relative `/api/v1/...` URLs.
- **Layered backend:** routes handle HTTP, the service validates and generates codes, and the repository executes SQL.
- **Random codes:** seven characters from 62 symbols provide `62^7` possible values. A unique database index remains the source of truth, with bounded retries on actual collisions. Codes are not passwords; anyone holding a short URL can visit it.
- **Durable analytics:** a single `UPDATE ... SET clicks = clicks + 1 ... RETURNING original_url` records a visit before the redirect response. This prevents lost increments under concurrency and removes the previous unreliable background-task path. Clicks measure requests, including bots and previews—not unique humans or confirmed page loads.
- **Immediate deletion/expiry:** redirects use the database rather than per-process caches, avoiding stale links across instances. This trades one database write per visit for consistency and simpler operation.
- **UTC timestamps:** a SQLAlchemy type normalizes stored and returned timestamps so SQLite and PostgreSQL behave consistently.
- **Anonymous ownership:** a random 256-bit cookie is hashed before storage alongside each URL. Owner filters are part of the SQL for listing, analytics, and deletion.
- **Startup migration:** missing nullable columns and indexes are added without deleting old records. A PostgreSQL advisory lock serializes initialization during rolling deploys. Legacy records remain redirectable but are not assigned to arbitrary new browser workspaces.

## Tests

From the repository root with the virtual environment active:

```bash
pip install -r URL-SHORTNER/requirements-dev.txt
python -m pytest --cov=app --cov-report=term-missing
ruff check URL-SHORTNER
ruff format --check URL-SHORTNER
```

Test coverage includes the complete lifecycle, concurrent increments, collision retries, expiry, UTC timestamps, cookie isolation, cross-origin protection, rate limits, input validation, pagination, search, migrations, persistence across application restarts, and database error handling.

For PostgreSQL, point the suite at a **dedicated test database**. Each test creates and drops its own temporary schema:

```bash
TEST_DATABASE_URL='postgresql://user:password@localhost:5432/shortener_test' python -m pytest -q
```

For real browser checks:

```bash
pip install -r URL-SHORTNER/requirements-browser.txt
playwright install chromium
python URL-SHORTNER/tests/browser_smoke.py
```

The browser script starts its own temporary server/database and checks creation, copy, insights, redirects, private workspaces, XSS handling, expiry, deletion, search, pagination, network recovery, and mobile layout. Screenshots are written to `test-results/`. On Linux CI, install browser system dependencies with `playwright install --with-deps chromium`.

[GitHub Actions](https://github.com/arpitkjaiswal/URLShortener/actions) runs SQLite, PostgreSQL 17, and browser jobs. The badge above shows the current result; local test success alone is not a live Render deployment check.

## Project layout

```text
.github/workflows/ci.yml       SQLite, PostgreSQL, lint and browser checks
render.yaml                    Render web service + PostgreSQL Blueprint
docs/                          Deployment guide and real browser screenshots
URL-SHORTNER/
  app/
    api/routes.py              HTTP contracts and redirects
    core/                      Settings, workspace cookies and throttling
    db/                        Models, UTC handling, connections and migration
    repositories/              SQL operations and owner filtering
    schemas/                   Pydantic request and response validation
    services/                  Validation and short-code generation
    static/                    Responsive frontend and missing-link page
    utils/                     URL validation and Base62 helpers
    main.py                    App factory, lifespan and error handling
  tests/                       API, regression and browser checks
  .env.example                 Local configuration template
  requirements*.txt           Runtime and test dependencies
```

## Scope and honest limitations

This is a portfolio-ready application, not a commercial abuse-resistant URL shortening platform. It does not provide account login/recovery, malware scanning, custom aliases, unique-visitor attribution, or a distributed analytics queue. The bounded in-memory creation limiter resets on process restart and applies per process; the Blueprint deliberately starts one worker. For higher traffic, add edge/distributed rate limiting, monitoring, backups, account-based access, and versioned migrations for future schema changes. Do not shorten confidential or credential-bearing URLs.

## Explain it on your resume

> Built a full-stack URL shortener using FastAPI, SQLAlchemy, PostgreSQL, and JavaScript, with expiring links, atomic click analytics, browser-scoped management, automated API/browser tests, and a Render deployment Blueprint.

After you deploy and verify the public URL, add it next to the repository link. Avoid invented traffic, latency, uptime, or performance claims. In an interview, demonstrate create → redirect → analytics → delete, then explain why atomic SQL avoids lost updates and why PostgreSQL is necessary for persistent hosting.

Built by [Arpit Kumar Jaiswal](https://github.com/arpitkjaiswal).
