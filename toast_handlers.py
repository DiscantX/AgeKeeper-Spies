from __future__ import annotations

from windows_toasts import ToastDismissedEventArgs, ToastFailedEventArgs


def configure_toast_launch_action(spy_toast, status: str, match, logger) -> None:
    """Set protocol launch action for supported statuses."""
    match status:
        case "lobby":
            response_type_id = 0
        case "spectate":
            response_type_id = 1
        case _:
            logger.warning("Unknown response type %s, cannot configure toast activation.", status)
            return

    match_id = match.get("matchid", -1)
    protocol_link = f"aoe2de://{response_type_id}/{match_id}"
    # Use protocol launch on the toast itself to avoid intermittent WinRT callback drops.
    spy_toast.launch_action = protocol_link
    logger.info("Toast launch action configured: %s", protocol_link)


def log_toast_dismissal(dismissed_event_args: ToastDismissedEventArgs, logger) -> None:
    """Log one toast dismissal event."""
    dismissal_reasons = {
        0: "UserCanceled",
        1: "ApplicationHidden",
        2: "TimedOut",
    }
    reason = dismissed_event_args.reason
    reason_value = int(reason)
    reason_name = dismissal_reasons.get(reason_value, str(reason))
    logger.info("Toast dismissed reason: %s (%s)", reason_name, reason_value)


def log_toast_failure(failed_event_args: ToastFailedEventArgs, logger) -> None:
    """Log one toast failure event."""
    logger.error("Toast failed: %s", failed_event_args.reason)
