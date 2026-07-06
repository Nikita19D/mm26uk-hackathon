# Magento Hyva Converter API

## Purpose

This service converts Magento storefront files to Hyva-compatible output with strong business-logic safety rules.

It supports:
- Single prompt conversion
- Repository scanning
- Multi-file repository conversion (dry-run or write mode)
- Optional post-conversion test command execution

Current health response:

```json
{"status":"ok","version":"2.1.0"}
```

## Core Behavior Rules

The conversion engine is configured to:
- Preserve business logic (pricing, tax, stock, promo, customer group behavior)
- Preserve backend safety and template contracts
- Prefer Tailwind and Alpine.js patterns for frontend modernization
- Keep risky business-critical logic unchanged if uncertain

## Authentication

Protected endpoints require:

`Authorization: Bearer <MAGENTO_API_TOKEN>`

Set the same `MAGENTO_API_TOKEN` value:
- On the API server (Render environment variables)
- In the Magento client that calls this API

## Required Environment Variables

- `API_KEY` : Gemini API key used by the conversion model
- `MAGENTO_API_TOKEN` : shared bearer token for API auth
- `MAGENTO_REPO_ROOT` : allowed root folder for repo operations
- `PORT` : provided automatically by Render

## API Base URL

After Render deployment, your base URL is:

`https://<your-service-name>.onrender.com`

Magento developers should use this base URL for all calls.

## Endpoints

### 1) Health
`GET /health`

Response example:

```json
{"status":"ok","version":"2.1.0"}
```

### 2) Single File/Prompt Conversion
`POST /v1/hyva-transform`

Request body:

```json
{
  "prompt": "Convert this Magento template content..."
}
```

Response body:

```json
{
  "request_id": "...",
  "transformed_template": "...",
  "model": "gemini-2.5-flash"
}
```

Alias:
- `POST /api/v1/hyva-transform`

### 3) Repository Scan
`POST /v1/repo/scan`

Key inputs:
- `repo_path` (required)
- `include_patterns` (optional)
- `exclude_dirs` (optional)
- `max_files` (optional)
- `modified_after` / `modified_before` (optional ISO-8601)

Example:

```json
{
  "repo_path": "/opt/render/project/src",
  "include_patterns": ["*.phtml", "*.xml", "*.js"],
  "modified_after": "2026-07-01T00:00:00Z",
  "max_files": 200
}
```

### 4) Repository Conversion
`POST /v1/repo/convert`

Key inputs:
- `repo_path` (required)
- `dry_run` (recommended true first)
- `run_tests` (optional)
- `test_commands` (optional)
- `max_files`, `max_file_size`
- `modified_after` / `modified_before`
- `business_context`
- `preserve_business_logic`

Example dry-run:

```json
{
  "repo_path": "/opt/render/project/src",
  "dry_run": true,
  "business_context": "Do not change tax, promo, stock, and pricing behavior.",
  "preserve_business_logic": true
}
```

### 5) Repository Tests Only
`POST /v1/repo/test`

Request body:

```json
{
  "repo_path": "/opt/render/project/src",
  "commands": [
    "php -v",
    "php bin/magento cache:status",
    "php bin/magento setup:di:compile"
  ]
}
```

## Input Rules

- `repo_path` must be inside `MAGENTO_REPO_ROOT`
- File matching is pattern-based (`*.phtml`, `*.xml`, `*.js` by default)
- Time filters use ISO-8601 (`2026-07-01T00:00:00Z`)
- Oversized files are skipped using `max_file_size`

## Output Rules

- Conversion output is code-only (no markdown/explanations)
- Business logic must remain behaviorally equivalent unless explicitly relaxed
- API responses include structured status and per-file conversion/test results

## Recommended Workflow

1. Check `GET /health`
2. Run `POST /v1/repo/scan`
3. Run `POST /v1/repo/convert` with `dry_run: true`
4. Review `changed_files`
5. Run real conversion with `dry_run: false`
6. Run tests (`run_tests: true` or `/v1/repo/test`)

## Render Deployment Notes

- `render.yaml` is included for Blueprint deploy
- Use `requirements.txt` as canonical dependency file
- Keep `.env` out of git (already ignored)

## Security Notes

- Never expose `MAGENTO_API_TOKEN` publicly
- Rotate tokens periodically
- Restrict access if possible (private networking/IP filtering)
- Be careful with repo-write endpoints in public environments
