# SIH26073 Vercel + Render hosting fix

## Target public URL
`https://sih2026-i4g2p0nzl-super-tech-titans1.vercel.app/`

The browser should always call relative paths such as `/api/v1/stations`.
Vercel must reverse-proxy `/api/*` to the Render FastAPI service, so the
browser never needs to know or use the Render URL directly.

## What was fixed in code

1. `frontend/src/main.jsx` was repaired. Python `CORSMiddleware` code had been
   pasted into this React file, `ReactDOM` was undefined, and the root was
   rendered twice.
2. The backend now supports an exact allow-list of hosted dashboard origins via
   `SIH_DASHBOARD_ORIGINS`.
3. Optional `SIH_PUBLIC_DASHBOARD_WRITES=1` permits only the configured hosted
   dashboard origin to use the demo simulation/evaluation POST endpoints.
   Telemetry, reset, and anomaly acknowledgement remain station-token protected.
4. `render.yaml` contains the correct build/start/health-check settings.

## Render deployment settings

If you use `render.yaml`, create/sync a Blueprint from this repo. Otherwise set:

- Runtime: Python 3
- Build command: `pip install -r backend/requirements.txt`
- Start command: `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`
- Health check path: `/api/v1/health`

Environment variables:

- `SIH_STATION_TOKEN=<a long random secret>`
- `SIH_DASHBOARD_ORIGINS=https://sih2026-i4g2p0nzl-super-tech-titans1.vercel.app`
- `SIH_PUBLIC_DASHBOARD_WRITES=1`

After Render is live, verify:

`https://YOUR-RENDER-SERVICE.onrender.com/api/v1/health`

It must return JSON with `"ok": true`.

## Vercel: preserve the exact PPT URL without rebuilding the frontend

Use a **Project-level Routing Rule** (Vercel project -> CDN -> Routing Rules):

- Name: `SIH API Proxy`
- Source: `/api/:path*`
- Action: Rewrite
- Destination: `https://YOUR-RENDER-SERVICE.onrender.com/api/:path*`

Publish the routing rule. Project-level routing rules are CDN configuration and
do not require a frontend rebuild.

### Make the PPT URL public

The supplied URL is currently behind Vercel Authentication. In
Project -> Settings/Security -> Deployment Protection, either:

- make this specific deployment/domain an exception, or
- use a protection mode that leaves the required public URL accessible.

Test the exact PPT URL in an incognito/private window while signed out of
Vercel. It must show the dashboard directly, not a Vercel sign-in page.

## Verification URLs

Once the routing rule is published, all of these should use the Vercel domain:

- `/api/v1/health`
- `/api/v1/stations`
- `/api/v1/evaluation/latest`
- `/api/v1/anomalies`

Example:
`https://sih2026-i4g2p0nzl-super-tech-titans1.vercel.app/api/v1/health`

The key test is that this Vercel URL returns the same health JSON as the Render
health URL.

## Important Render database note

The backend uses SQLite. Render's ordinary filesystem is ephemeral, so history
can be lost on a redeploy/restart unless you use persistent storage or move the
database to a managed database. This does not prevent frontend/backend
connectivity, but it matters for long-term anomaly history.
