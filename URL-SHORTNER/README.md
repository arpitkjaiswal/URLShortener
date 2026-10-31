# URL Shortener application

The full setup guide, screenshots, API examples, architecture, test commands, and resume summary are in the [repository README](../README.md).

## Start from this directory

```bash
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open http://localhost:8000. Use Python 3.12 and a virtual environment.

For Render, use the [root Blueprint](../render.yaml) or follow the [deployment guide](../docs/DEPLOYMENT.md). Do not copy the local SQLite configuration to Render; deployed data requires PostgreSQL.
