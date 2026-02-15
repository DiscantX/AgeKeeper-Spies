import argparse

from spies import task_registration


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgeKeeper spies runner.")
    parser.add_argument(
        "--tail-logs",
        action="store_true",
        help="Tail the spies log file instead of starting the spies process.",
    )
    parser.add_argument(
        "--tail-lines",
        type=int,
        default=100,
        help="How many recent lines to print before following logs (default: 100).",
    )
    parser.add_argument(
        "--no-follow",
        action="store_true",
        help="When used with --tail-logs, print lines and exit without follow mode.",
    )
    parser.add_argument(
        "--task-register",
        action="store_true",
        help="Register spies as a Windows Scheduled Task (headless startup).",
    )
    parser.add_argument(
        "--task-deregister",
        action="store_true",
        help="Remove the scheduled task registration.",
    )
    parser.add_argument(
        "--task-status",
        action="store_true",
        help="Show scheduled task status.",
    )
    parser.add_argument(
        "--task-start",
        action="store_true",
        help="Start the scheduled task now.",
    )
    parser.add_argument(
        "--task-stop",
        action="store_true",
        help="Stop the scheduled task if it is running.",
    )
    parser.add_argument(
        "--task-name",
        default=task_registration.DEFAULT_TASK_NAME,
        help=f"Scheduled task name (default: {task_registration.DEFAULT_TASK_NAME}).",
    )
    parser.add_argument(
        "--task-python",
        default=task_registration._default_pythonw(),
        help="Python executable used for task registration (default: pythonw when available).",
    )
    return parser


def handle_task_cli(cli_args) -> int | None:
    actions = [
        cli_args.task_register,
        cli_args.task_deregister,
        cli_args.task_status,
        cli_args.task_start,
        cli_args.task_stop,
    ]
    selected = sum(bool(action) for action in actions)
    if selected == 0:
        return None
    if selected > 1:
        print(
            "Choose only one task action: --task-register, --task-deregister, "
            "--task-status, --task-start, --task-stop"
        )
        return 2

    if cli_args.task_register:
        return task_registration.register_task(
            task_name=cli_args.task_name,
            python_exe=cli_args.task_python,
        )
    if cli_args.task_deregister:
        return task_registration.deregister_task(task_name=cli_args.task_name)
    if cli_args.task_start:
        return task_registration.start_task(task_name=cli_args.task_name)
    if cli_args.task_stop:
        return task_registration.stop_task(task_name=cli_args.task_name)
    return task_registration.show_status(task_name=cli_args.task_name)
