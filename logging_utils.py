from __future__ import annotations

import logging
import os
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path


def resolve_log_file() -> Path:
    override_dir = os.getenv("AGEKEEPER_LOG_DIR")
    if override_dir:
        return Path(override_dir) / "spies.log"

    programdata = os.getenv("ProgramData")
    if programdata:
        return Path(programdata) / "AgeKeeper" / "logs" / "spies.log"

    return Path(__file__).resolve().parent / "logs" / "spies.log"


def configure_rotating_logger(
    logger_name: str,
    preferred_log_file: Path,
    fallback_log_file: Path,
) -> tuple[logging.Logger, Path]:
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger, preferred_log_file

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    effective_log_file = preferred_log_file
    try:
        effective_log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            effective_log_file,
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        )
    except OSError:
        fallback_log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            fallback_log_file,
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        effective_log_file = fallback_log_file

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger, effective_log_file


def tail_logs(
    log_file: Path,
    lines: int = 100,
    follow: bool = True,
    poll_interval: float = 0.5,
) -> int:
    if lines < 0:
        print("--tail-lines must be >= 0")
        return 2

    if not log_file.exists():
        print(f"Log file does not exist yet: {log_file}")
        return 1

    try:
        with log_file.open("r", encoding="utf-8", errors="replace") as handle:
            if lines > 0:
                for line in deque(handle, maxlen=lines):
                    print(line, end="")
            else:
                handle.seek(0, os.SEEK_END)

            if not follow:
                return 0

            while True:
                line = handle.readline()
                if line:
                    print(line, end="", flush=True)
                    continue
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        return 0
