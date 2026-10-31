# Linkly · URL Shortener

A responsive FastAPI link shortener with custom aliases, expiry, QR downloads, click analytics, search, CSV export, and protected management actions.

## Develop locally

Use Python 3.12.14. Run these commands from the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```

Open the app on port 8000. SQLite is used locally. Set `ADMIN_TOKEN` to a private access key in `.env` before exposing the service publicly. The dashboard’s **Management access** section accepts this key; it stays in the current tab’s memory and clears on reload. Public visitors can create short links, download QR codes, and follow links. Listing, analytics, and deletion require the key when configured. This is a single-owner dashboard, not a multi-user account system.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q
```

Tests use temporary SQLite databases. Importing the app also initializes the configured database; use a separate `DATABASE_URL` when running tests if you do not want to initialize the local default database.

## Deploy for free: Render + Neon

`render.yaml` creates **one free Render web service**. It does not provision a paid database or disk. Use Neon’s free PostgreSQL plan to store links independently of Render restarts. No Redis, custom domain, or paid add-on is required. Free plans have usage limits and can change; choose the free option in both services and review the signup screens.

1. Create a free project at [Neon](https://neon.tech). Open **Connect**, select a PostgreSQL connection string, and copy it securely. Keep `sslmode=require` (or stronger verification) in the connection string.
2. Commit and push this repository to GitHub.
3. In [Render](https://render.com), select **New → Blueprint**, connect this repository, and use the root `render.yaml`. For an existing manual service, clear its old Root Directory setting: all app files now live at the repository root.
4. When prompted for `DATABASE_URL`, paste the Neon connection string. Keep the service plan **Free**. No Render database is needed.
5. Deploy and open the generated `.onrender.com` URL. Short links automatically use that address.
6. To manage links, copy the generated `ADMIN_TOKEN` from Render’s environment settings into the site’s **Management access** field. Visitors can shorten and share without this key.
7. Check a new short link, unlock the dashboard, and refresh to see its click count.

**Free hosting tradeoff:** Render can sleep when idle, so the first visit or redirect may wait while the app wakes. Neon can also suspend idle compute. Links remain stored in Neon, subject to its free-plan limits and retention policies. This setup is suitable for personal projects and light traffic; it does not promise instant redirects or unlimited usage.

Do not use SQLite for this Render deployment: the free service’s local files can disappear on restart or redeploy. The app checks for external PostgreSQL on Render and gives a clear configuration error if it is missing. Keep database credentials in Render’s environment settings, never in GitHub or chat.

For manual setup, choose a **Free** Python web service, leave **Root Directory blank**, build command `pip install -r requirements.lock`, and start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`. Set `DATABASE_URL` from Neon and a private `ADMIN_TOKEN` yourself.

The free `.onrender.com` domain works as-is. An optional custom domain can use `BASE_URL=https://your-domain.example`. One worker is used because the default cache is process-local.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLite locally; free Neon PostgreSQL connection string in Render. `postgres://` and `postgresql://` select the installed psycopg driver. |
| `BASE_URL` | Optional public origin; overrides `RENDER_EXTERNAL_URL`. Local default: `http://localhost:8000`. |
| `ADMIN_TOKEN` | Private key protecting all list, stats, and delete endpoints. Unset means open management for local development. |
| `LOG_LEVEL` | Defaults to `INFO`. |
| `REDIS_URL` | Optional Redis cache; not required for the single-worker Blueprint. |

## API

- `POST /api/v1/shorten`: `{ "url": "https://example.com", "custom_alias": "hello", "ttl_seconds": 86400 }`. Alias and expiry are optional. Aliases use 3–32 letters, numbers, underscores, or hyphens and are case-sensitive. Reserved aliases and duplicates return an error. Expiry is limited to 10 years.
- `GET /{short_code}`: redirect and record a click; expired/deleted/unknown links return 404.
- `GET /api/v1/qr/{short_code}`: SVG QR download without recording a click.
- `GET /api/v1/urls?limit=50`: recent links, newest first (maximum 50).
- `GET /api/v1/stats/{short_code}`: clicks, creation, expiry, and last access for active links.
- `DELETE /api/v1/urls/{short_code}`: permanent deletion with cache invalidation.
- `GET /health`: database-aware health probe.
- `/docs`: interactive API reference. For protected endpoints, supply the `X-Admin-Token` header.

Dashboard search, totals, and CSV export cover the latest 50 loaded links. Expired links stay visible in the list; active-link insights include last access. QR codes are generated locally by the server, without sending link data to an external QR service. Destination URLs are rendered as text rather than HTML. CSV cells are escaped to avoid spreadsheet formula execution.

## Scope

This is a single-owner link tool. Account registration, per-user ownership, billing, abuse detection, and distributed rate limiting are not included. Add gateway-level abuse controls before running a high-traffic public shortener. Existing SQLite data is not automatically migrated into Neon PostgreSQL; a new Neon database starts empty. Database table creation is automatic for new deployments; future schema changes should use versioned migrations.
