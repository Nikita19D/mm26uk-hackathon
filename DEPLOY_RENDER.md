# Render Deployment Guide for Magento Hyva Converter API

## 1) Deploy on Render

1. Push this repo to GitHub.
2. In Render, click New + and choose Blueprint.
3. Select this repository. Render will read [render.yaml](render.yaml).
4. In Render Environment settings, set secrets:
   - `API_KEY`
   - `MAGENTO_API_TOKEN`
5. Deploy.

## 2) Get the Live API URL (for Magento developers)

After deploy, Render gives your service a public URL in this format:

- `https://<service-name>.onrender.com`

Magento developers use that base URL as the API host.

Examples:

- Health: `https://<service-name>.onrender.com/health`
- Convert one prompt: `https://<service-name>.onrender.com/v1/hyva-transform`
- Scan repo: `https://<service-name>.onrender.com/v1/repo/scan`
- Convert repo: `https://<service-name>.onrender.com/v1/repo/convert`

## 3) Magento CLI example call

```bash
curl -X POST "https://<service-name>.onrender.com/v1/repo/convert" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <MAGENTO_API_TOKEN>" \
  -d '{
    "repo_path": "/opt/render/project/src",
    "dry_run": true,
    "modified_after": "2026-07-01T00:00:00Z",
    "business_context": "Keep pricing, tax, and stock logic unchanged.",
    "preserve_business_logic": true
  }'
```

## 4) Important Notes

- `MAGENTO_REPO_ROOT` is set to `/opt/render/project/src` so the API can only operate inside the checked-out project.
- Keep `MAGENTO_API_TOKEN` secret and rotate it regularly.
- Start with `dry_run: true` before writing real changes.
