"""Audio playback helpers for spy toast alerts."""

from pathlib import Path
import ctypes

WINMM = ctypes.windll.winmm
MCI_ALIAS = "AgeKeeperSpyAlert"


def play_alert_audio(audio_path: Path) -> None:
    """Play the configured local alert sound through the Windows MCI API."""
    # Toast custom file audio can be ignored in some desktop app contexts.
    # Use the Windows MCI API to play the local media file directly.
    if not audio_path.exists():
        print(f"Audio file not found: {audio_path}")
        return

    path_str = str(audio_path.resolve()).replace('"', '""')
    WINMM.mciSendStringW(f"close {MCI_ALIAS}", None, 0, None)
    open_result = WINMM.mciSendStringW(
        f'open "{path_str}" type mpegvideo alias {MCI_ALIAS}',
        None,
        0,
        None,
    )
    if open_result != 0:
        print(f"Failed to open alert audio with MCI (code: {open_result})")
        return

    play_result = WINMM.mciSendStringW(f"play {MCI_ALIAS}", None, 0, None)
    if play_result != 0:
        print(f"Failed to play alert audio with MCI (code: {play_result})")
