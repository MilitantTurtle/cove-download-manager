# AI operating rules: direct local API

These instructions are for AI agents with a trusted, non-browser local HTTP
tool. The host integration must start Cove and configure the API base URL and
bearer token before the AI uses the tool. The token must be injected as a
secret by the host; it must not be placed in the prompt or returned to the AI.

## Connection contract

- Base URL: `http://127.0.0.1:17681/api/v1` by default. Use Cove's configured
  `api_port` when it differs.
- Cove must already be running. Unlike the optional wrapper, the API does not
  launch Cove.
- `GET /health` is unauthenticated. Every other endpoint requires exactly one
  `Authorization: Bearer <token>` header supplied by the host integration.
- Never read, print, log, request, or expose `api_token` or `rpc_secret`.
- Use a local non-browser HTTP client. Requests with an `Origin` header are
  rejected, and the API never enables CORS or listens beyond `127.0.0.1`.
- Do not send query parameters. POST bodies must be UTF-8 JSON objects with
  `Content-Type: application/json`; control operations use an empty `{}` body.
- Treat the top-level JSON `ok` field as authoritative. On failure, report the
  exact `error.code` and `error.message`.

## Endpoints

| Method | Path | Purpose | Success |
|---|---|---|---|
| `GET` | `/health` | Check API readiness | `200` |
| `GET` | `/settings` | Read safe current defaults | `200` |
| `GET` | `/downloads` | List downloads | `200` |
| `POST` | `/downloads` | Add a download | `202` |
| `GET` | `/downloads/{task_id}` | Read one download | `200` |
| `POST` | `/downloads/{task_id}/pause` | Pause one download | `200` |
| `POST` | `/downloads/{task_id}/resume` | Resume one download | `200` |
| `POST` | `/downloads/{task_id}/cancel` | Cancel without deleting files | `200` |

## Add-download body

Send a JSON object to `POST /downloads`:

```json
{
  "url": "https://example.com/file.zip",
  "directory": "D:\\Downloads",
  "filename": "file.zip",
  "connections": 8,
  "speed_limit_kbps": 0,
  "create_directory": false
}
```

Field rules:

- `url` is required and supports HTTP, HTTPS, FTP, and magnet links.
- `directory` is optional and must be an absolute path. Omit it to use Cove's
  current default. If it does not exist, set `create_directory` to `true` only
  when creating that requested folder is intended.
- `filename` is optional and must be a safe basename, not a path. Supply it
  when the user provides a name or the original URL clearly identifies the
  expected filename. For Hugging Face `/resolve/` URLs, use the basename from
  the original URL to prevent a Xet/CAS content-hash filename. Never invent an
  ambiguous filename.
- `connections` is optional and must be an integer from 1 through 32. Omit it
  to use Cove's current per-download default. It does not control how many
  downloads run concurrently.
- `speed_limit_kbps` is optional and must be a non-negative integer. Zero means
  no per-download limit.
- `create_directory` is optional and defaults to `false`. It requires an
  explicit `directory`.
- Do not send unknown fields.

When a value is not requested, omit the optional field instead of guessing.

## Response handling

A successful add returns:

```json
{
  "ok": true,
  "download": {
    "task_id": 123,
    "gid": null,
    "status": "queued"
  }
}
```

The `download` object also includes URL, filename, directory, backend,
connections, speed limit, byte counts, transfer speed, progress, error, and
timestamps. Preserve the positive integer `task_id`; it is the authoritative
identifier for later operations. The nullable aria2 `gid` is informational
only and must never be used in place of `task_id`.

A failure returns this shape with an appropriate non-2xx HTTP status:

```json
{
  "ok": false,
  "error": {
    "code": "stable_error_code",
    "message": "Human-readable explanation."
  }
}
```

## Operating rules

1. Call `GET /health` before the first downloader operation in a task. If Cove
   is unavailable, report that it must be started; do not bypass Cove by
   calling aria2 directly.
2. Use `GET /settings` when the user asks what defaults will apply. Do not infer
   that response fields expose secrets; they do not.
3. Preserve every returned integer `task_id`. Never invent an identifier.
4. Poll `GET /downloads/{task_id}` no more often than once every five seconds.
   Stop polling on `completed`, `error`, or `removed`.
5. Call the cancel endpoint only when the user explicitly asks to stop or
   cancel that download. Cancellation retains partial and completed files.
6. Send `{}` to pause, resume, and cancel endpoints. Do not add fields.
7. Do not claim Cove scheduling, HLS conversion, category routing, or the UI
   concurrent-queue limit applies to API-created downloads.
