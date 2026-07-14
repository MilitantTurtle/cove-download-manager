# Paste into Codex personalisation

Use Cove Download Manager only through its official `cove-api.cmd` client.
Replace `C:\path\to\cove-api` below with the installed client directory.

Rules:

1. Run `cove-api.cmd health` before the first downloader operation in a task.
   The wrapper automatically launches Cove when it is not running and waits for
   API readiness; do not launch Cove separately unless the wrapper reports a
   startup error.
2. Available commands are `health`, `settings`, `add`, `list`, `status`,
   `pause`, `resume`, and `cancel`.
3. Treat stdout as JSON. A command succeeded only when the top-level `ok` field
   is `true`. If it is `false`, report the error code and message accurately.
4. For `add`, omit `--directory` and `--connections` unless the user specifies
   them; the wrapper then uses the current Cove UI defaults. Use `--name` when
   the user supplies a filename or the original source URL clearly identifies
   the expected filename. For Hugging Face `/resolve/` URLs, pass the basename
   from the original URL so Xet/CAS redirects do not leave a content-hash
   filename. Never invent a filename when it is ambiguous.
5. When the user specifies a destination folder, pass its absolute path using
   `--directory "PATH"`. Any absolute folder is allowed. If it does not exist,
   add `--create-directory` only when creating that requested folder is intended.
6. Preserve the returned integer `task_id`; it is Cove's authoritative control
   identifier. A nullable `gid` is informational only. Never invent a task ID.
7. Poll `status TASK_ID` no more often than once every five seconds. Stop polling
   on `completed`, `error`, or `removed`.
8. Never run `cancel` unless the user explicitly asks to stop/cancel that
   download. Cancellation keeps the partial file and never deletes files.
9. Never read, print, or expose Cove's `api_token` or `rpc_secret`. Never call
   aria2 RPC directly when this wrapper can perform the operation.
10. If the wrapper returns `cove_executable_not_found`, `cove_start_failed`, or
    `cove_start_timeout`, report that exact error to the user. Do not bypass the
    wrapper or call aria2 directly.
11. Do not claim Cove's scheduling, HLS conversion, category routing, or UI
    concurrent-queue limit applies to wrapper-created downloads.

Examples:

```text
C:\path\to\cove-api\cove-api.cmd add "https://example.com/file.zip"
C:\path\to\cove-api\cove-api.cmd add "https://example.com/model.gguf" --directory "D:\Models"
C:\path\to\cove-api\cove-api.cmd status 123
C:\path\to\cove-api\cove-api.cmd list
```
