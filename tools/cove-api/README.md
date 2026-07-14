# Cove local API command-line client

This is the dependency-free command-line client for Cove Download Manager's
official, versioned local API. It is not a proxy: file bytes travel directly
between Cove's transfer backend and the remote server.

Every command prints exactly one JSON object. The distinct API token is read
from Cove's settings and is never included in output.

## AI operating instructions

- [`AI_WRAPPER_OPERATING_RULES.md`](AI_WRAPPER_OPERATING_RULES.md) is a
  ready-to-use instruction set for agents that run this command-line client.
- [`AI_DIRECT_API_OPERATING_RULES.md`](AI_DIRECT_API_OPERATING_RULES.md) is a
  separate instruction set for agents with a trusted local HTTP integration
  that calls Cove's native API directly.

The wrapper is usually the better interface for smaller local models because
it reduces the operation to a small command vocabulary and handles Cove
startup, settings discovery, authentication, validation, and stable JSON
output. Direct API access is useful when an agent host already provides those
capabilities reliably.

## Requirements

- Windows with Python 3.10 or newer.
- Launch Cove once before first use so it creates `settings.json`.

For every command, the wrapper checks Cove's API first. If Cove is not
running, it launches the configured executable, waits up to 30 seconds for the
local API, and then continues the original command. Successful JSON
includes `"cove_started": true` when that invocation launched it.

The wrapper checks, in order:

1. `--settings PATH`
2. the `COVE_SETTINGS` environment variable
3. portable settings beside Cove
4. `%USERPROFILE%\.config\cove\settings.json`

## Commands

Run these from PowerShell or Command Prompt:

```powershell
tools\cove-api\cove-api.cmd health
tools\cove-api\cove-api.cmd settings
tools\cove-api\cove-api.cmd list
```

Add a download using Cove's current default directory and connection count:

```powershell
tools\cove-api\cove-api.cmd add "https://example.com/file.zip"
```

Override selected values:

```powershell
tools\cove-api\cove-api.cmd add "https://example.com/file.zip" --directory "D:\Downloads" --name "example.zip" --connections 8
```

PowerShell can split signed URLs containing `&` when invoking a `.cmd` file.
For those URLs, keep the URL out of the command line and read it from an
environment variable instead:

```powershell
$env:COVE_DOWNLOAD_URL = $signedUrl
tools\cove-api\cove-api.cmd add --url-env COVE_DOWNLOAD_URL --directory "D:\Downloads"
Remove-Item Env:COVE_DOWNLOAD_URL
```

`--url-env NAME` passes the environment variable's value to Cove unchanged.
It is mutually exclusive with the positional URL.

Control a download using the integer `task_id` returned by `add`:

```powershell
tools\cove-api\cove-api.cmd status 123
tools\cove-api\cove-api.cmd pause 123
tools\cove-api\cove-api.cmd resume 123
tools\cove-api\cove-api.cmd cancel 123
```

`cancel` stops the transfer but deliberately keeps partial and completed files.
There is no file-deletion command.

## Defaults and safety

When directory or connection options are omitted, the client leaves them out
of the request. Cove's QueueManager resolves the current UI defaults on its Qt
thread at request time.

An explicitly requested destination may be any absolute folder path. Existing
folders are accepted, or the AI can pass `--create-directory` to create a new
one. Relative destinations are rejected. Filenames cannot contain paths, drive
prefixes, control characters, or Windows reserved device names.

To restore destination restrictions later, set
`allow_any_absolute_directory` to `false` in `wrapper_config.json`; the
`allowed_download_roots` list and Cove's current default directory will then be
enforced.

`cove_executable` may be left empty. The client then discovers a versioned
portable executable placed beside the client or in the repository's `release`
directory. Set the field or `COVE_EXECUTABLE` when Cove lives elsewhere.

The client calls only Cove's authenticated API on `127.0.0.1`. The API rejects
browser origins, oversized bodies, relative destinations, unsafe filenames,
and unauthenticated operational requests. It supports HTTP, HTTPS, FTP and
magnet links.

Every add, status read, pause, resume, and cancellation is marshalled onto
Cove's Qt thread and goes through `QueueManager`, including its persistence,
UI updates, and normal status transitions.

## Exit behaviour

The JSON field `ok` is the authoritative result. The process also uses nonzero
exit codes for failures:

- `2`: settings/configuration or command syntax
- `3`: Cove could not be launched, did not become ready, or API transport failed
- `4`: Cove's API rejected the operation
- `5`: input validation failed
