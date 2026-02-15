"""Spies package for AgeKeeper watchlist monitoring and alert orchestration.

This module group tracks watched players across lobby and spectate activity,
maintains match state, and emits Windows toast/audio alerts when relevant status
changes are detected. It also contains CLI entry points, task-registration
helpers, avatar/audio utilities, toast queue handling, and logging support used
by the main runtime in `spies.spies`.
"""

# Package marker for spy-monitoring modules.