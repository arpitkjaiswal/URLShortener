# Linkly · URL Shortener

A responsive FastAPI link workspace with Light, Dark, and System themes, custom aliases, campaign links, expiry, QR downloads, bulk shortening, private daily analytics, titles and tags, pause/resume, searchable pagination, CSV export, and private management sessions.

## What’s new

- **Light / Dark / System:** choose a theme in the header. Only the theme preference is stored locally; System follows your device automatically. Storage-blocked browsers still work.
- **A complete link library:** search by destination, alias, title, or tag across the entire database. Filter by active, paused, or expired status and tag; sort and navigate 20 links per page. Summary totals cover the entire library. CSV exports the currently displayed page, clearly labelled in the interface.
- **Titles and tags:** select Edit on a link to give it a memorable name and a tag. These remain private.
- **Pause / Resume:** temporarily stop redirects without deleting the address, title, or click history. Resuming respects existing expiry; edit expiry separately to reactivate an expired link. Paused links return the same generic 404 as unavailable links.
- **Batch studio:** authenticated owners can shorten up to 20 destinations per request. Results identify successes and failures individually; only failed rows remain in the input for retry. The batch shares the same creation rate limit as single links. A 16 KiB API payload limit still applies.
- **Campaign builder:** add optional UTM source, medium, and campaign values before shortening. Existing query parameters and fragments are preserved; supplied UTM values replace only their matching parameters. UTM values are visible in the destination URL.
- **Private daily analytics:** Insights displays the last 14 UTC days and all-time counts, including paused or expired links. Daily counts begin with this upgrade; older all-time counts remain unchanged. No IP addresses, visitor identifiers, or referrer histories are stored.
- **Share anywhere:** copy, use the browser’s native share sheet where available, or download a QR code. Share falls back to copying on unsupported browsers.

## Develop locally

Use Python 3.12.14. Run these commands from the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```

Open the app on port 8000. SQLite is used locally. Set `ADMIN_TOKEN` to a long, random private access key in `.env` (at least 32 random characters recommended). Management stays locked if it is missing. The dashboard’s **Management access** section exchanges this key for a 30-minute HttpOnly, SameSite=Strict session cookie; the key is not stored in browser storage. HTTPS deployments use Secure cookies. Login survives reload until expiry; **Lock dashboard** revokes the session, clears the private view, and locks other open tabs. Public visitors can create short links, download QR codes, and follow links. Listing, analytics, editing, and deletion always require authorization. This is a single-owner dashboard, not a multi-user account system.

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
| `ADMIN_TOKEN` | Private key protecting all list, stats, edit, and delete endpoints. Management stays locked when unset; use Render’s Generate option. |
| `LOG_LEVEL` | Defaults to `INFO`. |
| `REDIS_URL` | Optional Redis cache; not required for the single-worker Blueprint. |

## API

- `POST /api/v1/shorten`: `{ "url": "https://example.com", "custom_alias": "hello", "ttl_seconds": 86400 }`. Alias and expiry are optional. Aliases use 3–32 letters, numbers, underscores, or hyphens and are case-sensitive. Reserved aliases and duplicates return an error. Expiry is limited to 10 years.
- `GET /{short_code}`: redirect and record a click; expired/deleted/unknown links return 404.
- `GET /api/v1/qr/{short_code}`: SVG QR download without recording a click.
- `GET /api/v1/urls?limit=50`: legacy recent-links API (maximum 50).
- `GET /api/v1/library`: authenticated paginated library. Query fields: `q` (max 200 chars), `state=all|active|paused|expired`, `tag`, `sort=newest|oldest|clicks`, `page` (1-based), `page_size` (1–50). Returns items, match count, current page, page count, global summary, and up to 100 tag suggestions.
- `POST /api/v1/bulk`: authenticated `{ "urls": ["https://example.com", "https://example.org"] }`. Returns per-row index, destination, short URL or error. Rows commit independently; successful rows are not rolled back because another destination is invalid. If the connection fails before results arrive, check the library before retrying to avoid duplicates.
- `GET /api/v1/analytics/{short_code}`: authenticated 14-day UTC daily aggregates and metadata, including paused and expired links.
- `GET /api/v1/stats/{short_code}`: clicks, creation, expiry, and last access for active links.
- `PATCH /api/v1/urls/{short_code}`: optionally update `url`, `title` (max 120 chars), `tag` (max 40 chars), `is_paused`, and `ttl_seconds`. `ttl_seconds: null` removes expiry; omission preserves expiry. Keeps the short code and click history.
- `DELETE /api/v1/urls/{short_code}`: permanent deletion with cache invalidation.
- `GET /health`: database-aware health probe.
- `POST /api/v1/auth/login`: `{ "key": "your-private-management-key" }` creates a 30-minute browser session.
- `GET /api/v1/auth/session`: remaining session lifetime.
- `POST /api/v1/auth/logout`: revoke the current session.

API clients can supply `X-Admin-Token` for protected endpoints. Browser sessions use cookies; session-based writes require an `Origin` header matching the configured public `BASE_URL`. For custom domains, configure `BASE_URL` to match the address used in the browser. Public Swagger/OpenAPI endpoints are disabled; the API contract is documented here.

Workspace search and filtering query all stored links; totals cover the entire library, while CSV export covers the currently displayed page. Expired and paused links remain manageable and retain their analytics. QR codes are generated locally by the server, without sending link data to an external QR service. Destination URLs are rendered as text rather than HTML. CSV cells are escaped to avoid spreadsheet formula execution.

## Privacy and abuse controls

- Private management fails closed without a key. Requests without authentication never return your link list or analytics. Session tokens are random, stored as hashes in bounded server memory, expire after 30 minutes, and are revoked on logout, key rotation, or process restart. No new database tables or paid services are required.
- Login: 5 attempts per client per minute. Failed management authentication: 10 attempts per client per minute. Public creation: 20 per client per minute. QR generation: 60 per client per minute. Limits return HTTP 429 with `Retry-After`.
- Limits and sessions are local to the single worker. They reset on restart and are not a distributed DDoS defense. Clients behind a shared proxy may share a limit. Do not configure the ASGI server to trust forwarded addresses from arbitrary clients.
- API write payloads are limited to 16 KiB. URL validation rejects embedded credentials, invalid ports, backslashes, and unescaped whitespace/control characters.
- Responses use `Cache-Control: no-store`, a restrictive Content Security Policy, frame protection, MIME sniffing protection, and `Referrer-Policy: no-referrer`. HTTPS responses add HSTS. Destination URLs are not included in application log messages; platform/server logs may still record request paths.
- A public short link is not a secret or a password-protected document: anyone who has it can follow it and discover its destination. Custom aliases are easier to guess. Never use link shortening as access control for private documents. The public creation endpoint remains open and rate limited; it does not detect phishing or guarantee destination safety.

## Scope

This is a single-owner link tool. Account registration, per-user ownership, billing, abuse detection, and distributed rate limiting are not included. Add gateway-level abuse controls before running a high-traffic public shortener. Existing SQLite data is not automatically migrated into Neon PostgreSQL; a new Neon database starts empty. On startup, SQLAlchemy adds the `link_details` and `daily_clicks` tables if missing. The existing `urls` table is not rewritten, and existing codes and counts are preserved. Setup is repeatable on SQLite and PostgreSQL. Back up production data before any deployment; future changes to existing columns should use versioned migrations.
