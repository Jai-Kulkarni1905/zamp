# Deploy

One Docker container on **Render** (free web service) with a **Neon** Postgres database. FastAPI serves
both the API and the built React app, so there is one URL and no CORS setup.

```
GitHub repo ──(auto deploy on push)──> Render: Docker build ──> https://<name>.onrender.com
                                              │
                                              └── DATABASE_URL ──> Neon Postgres
```

## What is in the image

- `Dockerfile` stage 1 builds `frontend/dist` with Node; stage 2 is Python 3.13 slim with only
  `requirements.txt` (runtime). Test-data tools and pytest live in `requirements-dev.txt` and are not shipped.
- `data/seed` (vendors, POs), `data/fixtures` (recorded Gemini extractions) and `data/invoices` (the 8 test
  PDFs) are copied in. Uploaded PDFs are stored in the database, not on disk (A62).
- Runs as a non-root user. Port comes from `$PORT`. Health check: `GET /api/health`.

## One-time setup

1. **Neon**: open the project, click **Connect**, copy the connection string
   (`postgresql://...neon.tech/neondb?sslmode=require...`). Note the region (shown on the project page).
2. **Render**: sign in with GitHub, choose **New > Blueprint**, pick this repo. Render reads `render.yaml`.
   - If the Neon region is not Singapore (`ap-southeast-1`), change `region:` in `render.yaml` to the closest
     Render region first (Neon `us-east-*` > `virginia`, `eu-central-1` > `frankfurt`, `us-west-2` > `oregon`).
     Every stage writes an event, so a cross-region database adds seconds to each run.
3. Render asks for the three secrets:

   | Key | Value |
   |---|---|
   | `GEMINI_API_KEY` | from your local `.env` |
   | `DATABASE_URL` | the Neon connection string, pasted as is (`postgresql://` is converted for psycopg) |
   | `ADMIN_TOKEN` | any password; required by `POST /api/admin/reset` |

4. **Apply**. The first build takes a few minutes. Tables are created and vendors and POs are seeded on
   first start.

## Settings in `render.yaml`

| Key | Value | Why |
|---|---|---|
| `LLM_MODE` | `live` | Known test files hit the recorded cache (0 Gemini calls); a new PDF makes exactly one call |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Same model the fixtures were recorded with |
| `STAGE_DELAY_MS` | `300` | Each stage visibly lights up in the live view (demo pacing only) |

## After deploy

```bash
python scripts/rehearse.py --base-url https://<name>.onrender.com --admin-token <ADMIN_TOKEN>
```

Resets, runs all 8 invoices in demo order over HTTP, follows every live stream, checks section 7, the
dashboard numbers and PO balances, twice. It waits for a sleeping service to wake first.

## Operating notes

- **Cold start**: the free plan sleeps after 15 minutes idle; the next request takes about a minute.
  Open the URL a few minutes before a demo (see `docs/demo-script.md`).
- **Reset before a demo**: run the rehearsal (it ends in the demo state), or
  `curl -X POST https://<name>.onrender.com/api/admin/reset -H "X-Admin-Token: <token>"` for an empty dashboard.
- **Rotate the Gemini key**: change `GEMINI_API_KEY` in Render > Environment; Render redeploys.
- **Quota**: anyone with the URL can upload a new PDF, which costs one Gemini call. Set `LLM_MODE=fixture` in
  Render to make the deployment cache-only (new PDFs then end in ERROR "no recorded extraction").
- **Deploys**: every push to the default branch redeploys (`autoDeploy: true`). Runs and PDFs live in
  Postgres, so a redeploy keeps the demo state.
- **Region**: the live service ended up in Render's US West region, not Singapore. Runs take about 3.8s
  (mostly the 300ms demo pause per stage), so it was left there.
- **Phones on mobile data**: if the URL does not load, first wait a minute (cold start), then try a
  different DNS (Private DNS `dns.google`). Some Indian carriers block by domain name; a custom domain on the
  same Render service is the durable fix.
