# Render deployment guide

## Before deploying

The app runs as one Python web service with a PostgreSQL database. You do not need a separate frontend service, Node.js build, Redis instance, or manual table creation.

Use the `main` branch containing `render.yaml`. The service root is `URL-SHORTNER`, with this exact spelling and capitalization.

## Blueprint deployment

1. Sign into [Render](https://dashboard.render.com/).
2. Choose **New → Blueprint**, connect GitHub, and select `arpitkjaiswal/URLShortener`.
3. Select `main`, with `render.yaml` at the repository root.
4. Review the `url-shortener` web service and `url-shortener-db` PostgreSQL plans. The committed defaults use free plans.
5. Deploy. Render supplies `DATABASE_URL` from the database and sets `RENDER_EXTERNAL_URL` for public short links.
6. Open the web service's assigned public URL after `/health` passes.

The database's external IP allow list is empty in the Blueprint; the application connects over Render's private network. If you need external database administration, explicitly authorize your own IP in Render's database settings.

## Important: keep the demo available

Render's free web tier sleeps after 15 idle minutes. Its free PostgreSQL tier expires after 30 days. For a resume link that should remain usable, upgrade the database before it expires or supply a persistent external PostgreSQL database. Upgrade the web service if you need to avoid cold starts. Review current costs in Render before choosing a plan.

The app cannot prevent a hosting provider from expiring a free database. PostgreSQL protects data from web-service restarts; database retention and backups still depend on the database plan.

## Existing/manual service

If you already created the web service, set:

```text
Root Directory: URL-SHORTNER
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
Health Check Path: /health
PYTHON_VERSION: 3.12.14
DATABASE_URL: <PostgreSQL connection string>
```

For Render PostgreSQL, use the **Internal Database URL** and place the database and web service in the same region. For an external PostgreSQL provider, use its supplied connection string and TLS settings (usually `?sslmode=require`), and ensure it accepts connections from the Render service.

Leave `BASE_URL` unset to use Render's assigned HTTPS hostname. Do not set it to `localhost`, an IP address, or an API route.

## Custom domain

1. Add the domain to your Render web service and follow Render's DNS verification steps.
2. Once HTTPS works, set `BASE_URL=https://your-domain.example` and redeploy.
3. Open the dashboard at that exact domain. Cross-origin management requests are deliberately rejected.
4. Changing domains also changes the browser's cookie scope. Previous browser workspaces do not automatically transfer to the new domain, although existing short-link records remain in the database.

## Deployment smoke test

Use a non-confidential test destination such as `https://example.com`:

- Open `/health`; it must return `{"status":"healthy"}`.
- Open `/`; confirm that the dashboard loads without frontend errors.
- Create a link. Its URL must start with the actual public HTTPS hostname, not localhost.
- Copy the link and open it in another tab. It must redirect to the destination.
- Return to the dashboard, click **Refresh**, then **Insights**. Clicks should have increased.
- Reload the page. Your link should remain visible in the same browser.
- Open the dashboard in an incognito window. The first browser's collection should not appear; the shared short URL should still work.
- Create a link with a lifetime of 1 second. After it expires, opening the short URL should show the unavailable-link page, while its owner can still view analytics.
- Delete a link and verify that the old URL returns 404 immediately.
- Restart/redeploy the Render web service. Links should persist because the database is separate.
- Check the dashboard on a phone, and save the final public URL for your resume.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `Could not open requirements.txt` | Root Directory must be `URL-SHORTNER` |
| `No module named app` | Use the specified root directory and `uvicorn app.main:app` |
| PostgreSQL driver error | Build from the updated requirements, which include Psycopg 3 |
| App refuses SQLite on Render | Set `DATABASE_URL` to PostgreSQL; don't use the local `.env` |
| Health check fails / database 503 | Confirm the database is running, credentials are valid, regions/network access match, and a free database has not expired |
| Generated links point to localhost | Remove a stale `BASE_URL`; use Render's default URL or your real custom domain |
| Cross-origin error | Open the dashboard at the origin configured in `BASE_URL` |
| New empty workspace | Cookies were cleared, expired, blocked, or the browser/domain changed; there is no account recovery |
| 429 on creation | Wait for `Retry-After`; default is 30 attempts per client IP per minute |
| First visit is slow | A free Render web service may be waking from sleep |
| Legacy database rows missing from dashboard | Old rows have no ownership cookie; redirects still work, but they are not exposed to arbitrary visitors |

Schema initialization is additive and preserves existing rows. Back up your database before future schema changes; the startup migration is not a replacement for a full migration history as the project grows.

## Official references

- [FastAPI on Render](https://render.com/docs/deploy-fastapi)
- [Blueprint specification](https://render.com/docs/blueprint-spec)
- [Default environment variables](https://render.com/docs/environment-variables)
- [PostgreSQL connections](https://render.com/docs/postgresql-creating-connecting)
- [Free service limitations](https://render.com/docs/free)
