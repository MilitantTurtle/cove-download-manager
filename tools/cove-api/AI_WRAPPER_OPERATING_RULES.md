# AI operating rules: command-line wrapper

These instructions are for any AI agent that can run local commands. The
integrator must replace `C:\path\to\cove-api` with the installed client
directory. When Cove's settings are not discoverable automatically, the
integrator must also provide the absolute settings path with `--settings`
before the command name on every invocation.

Use Cove Download Manager only through its official `cove-api.cmd` client.

## Rules

1. Run `cove-api.cmd health` before the first downloader operation in a task.
   The wrapper automatically launches Cove when it is not running and waits for
   API readiness. Do not launch Cove separately unless the wrapper reports
   `cove_executable_not_found`, `cove_start_failed`, or `cove_start_timeout`.
2. Available commands are `health`, `settings`, `add`, `list`, `status`,
   `pause`, `resume`, and `cancel`.
3. Treat stdout as JSON. A command succeeds only when the top-level `ok` field
   is `true`. When it is `false`, report the exact `error.code` and
   `error.message`.
4. For `add`, the URL is required. Omit `--directory` and `--connections`
   unless the user specifies them; Cove then applies its current defaults.
5. Use `--name` when the user supplies a filename or the original source URL
   clearly identifies the expected filename. For Hugging Face `/resolve/`
   URLs, use the basename from the original URL so Xet/CAS redirects do not
   leave a content-hash filename. Never invent an ambiguous filename.
6. When the user specifies a destination folder, pass its absolute path using
   `--directory "PATH"`. If the folder does not exist, add
   `--create-directory` only when creating that requested folder is intended.
7. `--connections N` controls connections for that individual download and
   accepts an integer from 1 through 32. It does not control the number of
   downloads running concurrently.
8. Preserve the returned integer `task_id`. It is Cove's authoritative
   identifier for `status`, `pause`, `resume`, and `cancel`. The nullable `gid`
   is informational only. Never invent an identifier.
9. Poll `status TASK_ID` no more often than once every five seconds. Stop
   polling when the status is `completed`, `error`, or `removed`.
10. Run `cancel` only when the user explicitly asks to stop or cancel the
    download. Cancellation keeps partial and completed files; it never deletes
    them.
11. Never read, print, log, or expose Cove's `api_token` or `rpc_secret`. Never
    call aria2 RPC directly when the wrapper can perform the operation.
12. Do not claim Cove scheduling, HLS conversion, category routing, or the UI
    concurrent-queue limit applies to wrapper-created downloads.

## Command pattern

With automatically discovered settings:

```text
C:\path\to\cove-api\cove-api.cmd COMMAND [ARGUMENTS]
```

With explicit settings:

```text
C:\path\to\cove-api\cove-api.cmd --settings "C:\absolute\path\settings.json" COMMAND [ARGUMENTS]
```

Examples:

```text
C:\path\to\cove-api\cove-api.cmd health
C:\path\to\cove-api\cove-api.cmd add "https://example.com/file.zip"
C:\path\to\cove-api\cove-api.cmd add "https://example.com/model.gguf" --directory "D:\Models" --name "model.gguf" --connections 8
C:\path\to\cove-api\cove-api.cmd status 123
C:\path\to\cove-api\cove-api.cmd list
```
