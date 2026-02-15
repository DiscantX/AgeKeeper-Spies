"""Register or deregister Spies for headless startup on Windows.

This script manages a Scheduled Task that starts `spies.spies` on user logon.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import re
from pathlib import Path


DEFAULT_TASK_NAME = r"AgeKeeper\Spies"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_python() -> str:
    return str(Path(sys.executable).resolve())


def _default_pythonw() -> str:
    python_exe = Path(_default_python())
    if python_exe.name.lower() == "python.exe":
        pythonw_exe = python_exe.with_name("pythonw.exe")
        if pythonw_exe.exists():
            return str(pythonw_exe)
    return str(python_exe)


def _build_task_action(project_root: Path, python_exe: str) -> str:
    script_path = project_root / "spies" / "spies.py"
    return f'"{python_exe}" "{script_path}"'


def _run_schtasks(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["schtasks", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _normalize_task_name(task_name: str) -> str:
    normalized = task_name.strip()
    if not normalized:
        return normalized
    if not normalized.startswith("\\"):
        normalized = "\\" + normalized
    return normalized


def _task_name_candidates(task_name: str) -> list[str]:
    candidates: list[str] = []
    raw = task_name.strip()
    normalized = _normalize_task_name(task_name)
    if raw:
        candidates.append(raw)
    if normalized and normalized not in candidates:
        candidates.append(normalized)
    return candidates


def _resolve_existing_task_name(task_name: str) -> str | None:
    for candidate in _task_name_candidates(task_name):
        result = _run_schtasks(["/Query", "/TN", candidate])
        if result.returncode == 0:
            return candidate
    discovered = _discover_task_names()
    lowered_candidates = {c.lower() for c in _task_name_candidates(task_name)}
    leaf = task_name.strip().split("\\")[-1].lower()
    fuzzy_matches = []
    for name in discovered:
        lower_name = name.lower()
        if lower_name in lowered_candidates:
            return name
        if leaf and (lower_name.endswith("\\" + leaf) or ("\\" + leaf + "\\") in lower_name):
            fuzzy_matches.append(name)
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]
    return None


def _discover_task_names() -> list[str]:
    result = _run_schtasks(["/Query", "/FO", "LIST"])
    if result.returncode != 0:
        return []
    # Typical output line: "TaskName: \AgeKeeper\Spies"
    matches = re.findall(r"(?mi)^TaskName:\s*(.+?)\s*$", result.stdout)
    return [m.strip() for m in matches if m.strip()]


def task_exists(task_name: str) -> bool:
    return _resolve_existing_task_name(task_name) is not None


def register_task(task_name: str, python_exe: str) -> int:
    project_root = _project_root()
    action = _build_task_action(project_root, python_exe)
    target_task_name = _normalize_task_name(task_name)

    args = [
        "/Create",
        "/SC",
        "ONLOGON",
        "/TN",
        target_task_name,
        "/TR",
        action,
        "/F",
    ]

    result = _run_schtasks(args)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode

    print(f"Registered task: {target_task_name}")
    print(f"Action: {action}")
    return 0


def deregister_task(task_name: str) -> int:
    existing_name = _resolve_existing_task_name(task_name)
    if existing_name is None:
        print(f"Task not found: {task_name}")
        return 0

    result = _run_schtasks(["/Delete", "/TN", existing_name, "/F"])
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode

    print(f"Deregistered task: {existing_name}")
    return 0


def show_status(task_name: str) -> int:
    existing_name = _resolve_existing_task_name(task_name)
    if existing_name is None:
        print(f"Task not found: {task_name}")
        return 1

    result = _run_schtasks(["/Query", "/TN", existing_name, "/V", "/FO", "LIST"])

    print(result.stdout.strip())
    return 0


def start_task(task_name: str) -> int:
    existing_name = _resolve_existing_task_name(task_name)
    if existing_name is None:
        print(f"Task not found: {task_name}")
        return 1

    result = _run_schtasks(["/Run", "/TN", existing_name])
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode

    print(f"Start requested for task: {existing_name}")
    return 0


def stop_task(task_name: str) -> int:
    existing_name = _resolve_existing_task_name(task_name)
    if existing_name is None:
        print(f"Task not found: {task_name}")
        return 1

    result = _run_schtasks(["/End", "/TN", existing_name])
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode

    print(f"Stop requested for task: {existing_name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage AgeKeeper Spies background process registration."
    )
    parser.add_argument(
        "--task-name",
        default=DEFAULT_TASK_NAME,
        help=f"Scheduled task name (default: {DEFAULT_TASK_NAME})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_parser = subparsers.add_parser(
        "register",
        help="Register background process to run on logon.",
    )
    register_parser.add_argument(
        "--python",
        default=_default_pythonw(),
        help="Python executable to run spies with (default: pythonw when available).",
    )

    subparsers.add_parser(
        "deregister",
        help="Remove the registered background task.",
    )
    subparsers.add_parser(
        "status",
        help="Show current registration status.",
    )
    subparsers.add_parser(
        "start",
        help="Start the scheduled task now.",
    )
    subparsers.add_parser(
        "stop",
        help="Stop the scheduled task if it is running.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "register":
        return register_task(args.task_name, args.python)

    if args.command == "deregister":
        return deregister_task(args.task_name)

    if args.command == "status":
        return show_status(args.task_name)
    if args.command == "start":
        return start_task(args.task_name)
    if args.command == "stop":
        return stop_task(args.task_name)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
