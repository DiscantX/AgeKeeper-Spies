<img width="1226" height="344" alt="AgeKeeper Spies Banner" src="spies\assets\AgeKeeper-SpiesBanner_Cropped.png">

# AgeKeeper Spies

AgeKeeper Spies watches tracked AoE2 players and raises Windows toast
notifications when they enter or leave lobbies/games. It is designed to run
either interactively (`agekeeper-spies`) or headless at login via Windows
Scheduled Task.

## Features

- Real-time watchlist tracking for AoE2 player activity:
  - Track when a player joins a lobby.
  - Track when a player joins a match.
  - Track when a player leaves either.
- Toast alerts with player avatar, map, civ, and lobby/game context.
- Scheduled task lifecycle commands for headless startup:
  - Can be started upon Windows user logon.
  - Built-in log tail mode for live process monitoring.
  - Single-instance guard to prevent duplicate watcher processes.

## Requirements

- Windows (toast and scheduled task features are Windows-only).
- Python 3.11+.
- Network access for AoE2 API lookups and subscriptions.

## Installation

```bash
pip install "agekeeper-spies @ git+https://github.com/DiscantX/AgeKeeper-Spies.git@main"
```

Installed entrypoint:

```bash
agekeeper-spies
```

## Quickstart

### 1) Create your watchlist

Spies reads tracked players from `spies/watchlist.json`.

If the file does not exist, Spies creates a template on first run.

Example:

```json
[
  {
    "userName": "Hera",
    "profileid": "199325",
    "avatar_filepath": "spies/assets/default_avatar.png"
  },
  {
    "profileid": "123456"
  },
  {
    "userName": "TheViper"
  }
]
```

Rules:

- Each item can be a full object, a profile ID string, or a profile ID number.
- `profileid` and `userName` can be supplied together or separately.
- Missing usernames are resolved from IDs.
- Missing IDs are resolved from usernames.
- Providing a known ID will guarantee an accurate result.
- Providing a name may not produce an id, or it may produce an inaccurate one:
  - In the case of no id produced, it could be due to the fact that the search occurs in the leaderboards, and if a player is not ranked in the leaderboard, they will not appear.
  - An inaccurate id would be the result of multiple players having similar or the same names. The first search result is used.

- `avatar_filepath` is optional; default avatar is used if missing/empty. It will be updated automatically with the profile's Steam avatar the first time it is encountered or changed.

### 2) Start Spies

```bash
agekeeper-spies
```

### 3) Verify activity through logs

```bash
agekeeper-spies --tail-logs
```

## CLI Reference

Base command:

```bash
agekeeper-spies [options]
```

When no options are provided, Spies starts the watcher runtime.

### Log Tailing Arguments

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--tail-logs` | flag | `false` | Tail the Spies log instead of starting the watcher process. |
| `--tail-lines` | int | `100` | Print last N lines before follow mode starts. Must be `>= 0`. |
| `--no-follow` | flag | `false` | With `--tail-logs`, print requested lines and exit. |

Examples:

```bash
agekeeper-spies --tail-logs
agekeeper-spies --tail-logs --tail-lines 250
agekeeper-spies --tail-logs --tail-lines 0 --no-follow
```

### Scheduled Task Arguments (Windows)

Only one task action may be selected per command.

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--task-register` | flag | `false` | Register/update task to start Spies at user logon. |
| `--task-deregister` | flag | `false` | Remove the scheduled task. |
| `--task-status` | flag | `false` | Show detailed task status. |
| `--task-start` | flag | `false` | Request immediate task start. |
| `--task-stop` | flag | `false` | Request task stop if running. |
| `--task-name` | string | `AgeKeeper\Spies` | Task Scheduler name/path. |
| `--task-python` | string | `pythonw.exe` when available | Python executable used when registering the task. |

Examples:

```bash
agekeeper-spies --task-register
agekeeper-spies --task-status
agekeeper-spies --task-start
agekeeper-spies --task-stop
agekeeper-spies --task-deregister
agekeeper-spies --task-register --task-name "AgeKeeper\\Spies-Dev"
agekeeper-spies --task-register --task-python "C:\\Python311\\pythonw.exe"
```

## Common Command Recipes

Start watcher in foreground:

```bash
agekeeper-spies
```

Register headless startup at login:

```bash
agekeeper-spies --task-register
```

Start scheduled task:

```bash
agekeeper-spies --task-start
```

Show current scheduled task details:

```bash
agekeeper-spies --task-status
```

Tail only the latest 50 lines and exit:

```bash
agekeeper-spies --tail-logs --tail-lines 50 --no-follow
```

Follow logs live:

```bash
agekeeper-spies --tail-logs --tail-lines 200
```

## Logs

Resolved log file path order:

1. `AGEKEEPER_LOG_DIR/spies.log` when `AGEKEEPER_LOG_DIR` is set.
2. `%ProgramData%\AgeKeeper\logs\spies.log` when `%ProgramData%` exists.
3. Package fallback: `spies/logs/spies.log`.

Log format:

```text
YYYY-MM-DD HH:MM:SS | LEVEL | logger_name | message
```

Rotation policy:

- Max file size: `1,000,000` bytes.
- Backup files kept: `5`.

## Behavior and Exit Codes

### Process behavior

- Spies enforces single-instance execution using a process lock.
- If a second instance starts, it logs a warning and exits.
- If watchlist is empty, runtime exits after printing guidance.

### CLI constraints

- You cannot combine multiple task actions in one command.
- Invalid task action combinations return exit code `2`.
- `--tail-lines` must be non-negative; negative values return exit code `2`.

### Common non-zero exit results

- `1`: task not found (`--task-status`, `--task-start`, `--task-stop`) or log
  file missing when tailing.
- `2`: invalid CLI usage (for example, multiple task actions or invalid
  `--tail-lines` value).
- Other non-zero values may be returned directly from Windows `schtasks`.

## Troubleshooting

### No toasts appear

- Confirm you are on Windows.
- Confirm Spies is running: `agekeeper-spies --tail-logs`.
- Verify watchlist has valid players with resolvable IDs/usernames.
- Check Windows notification settings for app/system toast blocking.

### Task registration succeeds but nothing starts on login

- Check exact task path/name with:
  `agekeeper-spies --task-status --task-name "AgeKeeper\\Spies"`.
- Verify the `--task-python` path is valid and accessible at login.
- Confirm task history and last result in Task Scheduler UI.

### `Task not found`

- Use the same `--task-name` used during registration.
- Include folder path segments if task is under a folder:
  `AgeKeeper\\Spies` (default).

### Watchlist never resolves names/IDs

- Check network access and API availability.
- Start with explicit `profileid` values to bypass username lookup dependency.

### Log file not found when using `--tail-logs`

- Start Spies once to initialize logging.
- If using `AGEKEEPER_LOG_DIR`, verify folder permissions and existence.

## Developer Notes

- Package entrypoint: `agekeeper-spies = spies.spies:main`.
- Watchlist module: `spies/watchlist.py`.
- CLI parser: `spies/cli.py`.
- Task registration helpers: `spies/task_registration.py`.
- Logging utilities: `spies/logging_utils.py`.
- Runtime depends on `agekeeper` (lobby/shared/aoe2api modules).
