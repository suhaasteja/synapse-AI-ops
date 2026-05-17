# AI Factory Ops Deployment (Vercel + Render)

This guide deploys:
- **Frontend**: Next.js (`ai-factory-ops/web`) on Vercel
- **Backend**: FastAPI (`ai-factory-ops/src/api.py`) on Render

## 1) Backend on Render (Blueprint)

A ready-to-use `render.yaml` is included at repository root.

### Validate Blueprint
```bash
render login
render workspace set <workspace-id-or-name>
render blueprints validate ./render.yaml
```

### Create service (if not created yet)
Use either:
- Render dashboard Blueprint sync, or
- CLI service creation with equivalent flags.

Example CLI creation:
```bash
render services create \
  --name ai-factory-ops-api \
  --type web_service \
  --runtime python \
  --repo <your-github-repo-url> \
  --branch main \
  --root-directory cisco-track/ai-factory-ops \
  --build-command "pip install -r requirements.txt" \
  --start-command "uvicorn src.api:app --host 0.0.0.0 --port \$PORT" \
  --health-check-path /health \
  --plan free \
  --region oregon \
  --env-var PYTHON_VERSION=3.12 \
  --env-var ALLOWED_ORIGINS=https://synapse-ai-ops.vercel.app
```

### Update existing service
```bash
render services update <service-id-or-name> \
  --root-directory cisco-track/ai-factory-ops \
  --build-command "pip install -r requirements.txt" \
  --start-command "uvicorn src.api:app --host 0.0.0.0 --port \$PORT" \
  --health-check-path /health
```

### Deploy + monitor
```bash
render deploys create <service-id> --wait
render logs --resources <service-id> --tail
```

## 2) Frontend on Vercel

Set project root directory to:
- `ai-factory-ops/web`

Set env var in Vercel:
- `NEXT_PUBLIC_API_BASE_URL=https://<your-render-service>.onrender.com` (set this in Vercel for `https://synapse-ai-ops.vercel.app`)

Deploy and open:
- `https://synapse-ai-ops.vercel.app`

## 3) Environment variables

### Backend (Render)
- `GOOGLE_API_KEY` and/or `GEMINI_API_KEY`
- `OPENAI_API_KEY` (optional)
- `AIFOPS_ROUTER_MODEL` (optional)
- `AIFOPS_EXPLAINER_MODEL` (optional)
- `ALLOWED_ORIGINS` (comma-separated if multiple)
- `DUCKDB_PATH` (optional; set when using a Render disk for persistent writes)

### Frontend (Vercel)
- `NEXT_PUBLIC_API_BASE_URL`

## 4) DuckDB notes

Render filesystem is ephemeral by default.
- If DB is read-only and bundled in repo, runtime writes are not preserved.
- Current `render.yaml` is free-tier compatible (no disk block).
- If DB needs writes/persistence, switch to Starter+ and add a disk:
  - mount path `/data`
  - set `DUCKDB_PATH=/data/ai_factory.duckdb`
- Keep `numInstances: 1` when writing to DuckDB.

## 5) API checks

After deploy:
```bash
curl https://<render-service>.onrender.com/health
```

Optional chat check:
```bash
curl -X POST https://<render-service>.onrender.com/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Why are latency and critical alerts high?"}'
```

## 6) Common issues

- **CORS errors**: set `ALLOWED_ORIGINS` to your Vercel domain(s).
- **Mixed content**: ensure frontend calls backend via `https://`.
- **Cold start latency** on lower Render plans.
- **DuckDB path errors**: verify `DUCKDB_PATH` and disk mount.
