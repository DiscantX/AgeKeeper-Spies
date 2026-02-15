from __future__ import annotations

from windows_toasts import ToastDismissedEventArgs, ToastFailedEventArgs


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
