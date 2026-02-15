import asyncio
from contextlib import suppress


class ToastQueueManager:
    """Queue and dedupe toast work for player status updates."""

    def __init__(
        self,
        get_match,
        build_toast_payload,
        display_payload,
        valid_statuses=("lobby", "spectate"),
        status_logger=None,
    ):
        self.get_match = get_match
        self.build_toast_payload = build_toast_payload
        self.display_payload = display_payload
        self.valid_statuses = set(valid_statuses)
        self.status_logger = status_logger

        self.toast_queue = asyncio.Queue()
        self.pending_wait_tasks = {}
        self.toast_status_by_key = {}
        self._worker_task = None

    @staticmethod
    def _build_toast_key(player_id: str, match_id, status: str):
        return (str(player_id), str(match_id), status)

    def start(self):
        """Start the queue worker if it is not already running."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._toast_queue_worker())
        return self._worker_task

    async def stop(self) -> None:
        """Stop the queue worker."""
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._worker_task
        self._worker_task = None

    def _enqueue_toast_for_player_match(self, player_id: str, match, status: str, match_id) -> None:
        key = self._build_toast_key(player_id, match_id, status)
        if self.toast_status_by_key.get(key) in ("queued", "shown"):
            return

        # Claim the key before expensive work so concurrent paths cannot double-enqueue.
        self.toast_status_by_key[key] = "queued"
        try:
            payload = self.build_toast_payload(player_id, match, status, match_id)
            if not payload:
                self.toast_status_by_key.pop(key, None)
                return
            payload["key"] = key
            self.toast_queue.put_nowait(payload)
        except Exception:
            if self.toast_status_by_key.get(key) == "queued":
                self.toast_status_by_key.pop(key, None)
            raise

    async def _toast_queue_worker(self) -> None:
        while True:
            payload = await self.toast_queue.get()
            key = payload.get("key")
            try:
                self.display_payload(payload)
                if key is not None:
                    self.toast_status_by_key[key] = "shown"
            finally:
                self.toast_queue.task_done()

    async def _wait_for_match_and_enqueue_toast(
        self,
        player_id: str,
        status: str,
        match_id,
        timeout_seconds: float = 12.0,
        poll_interval_seconds: float = 0.4,
    ) -> None:
        key = self._build_toast_key(player_id, match_id, status)
        start = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - start < timeout_seconds:
            match = self.get_match(status, match_id, print_match_count=False)
            if match:
                self._enqueue_toast_for_player_match(player_id, match, status, match_id)
                break
            await asyncio.sleep(poll_interval_seconds)
        self.pending_wait_tasks.pop(key, None)
        if self.toast_status_by_key.get(key) == "waiting":
            self.toast_status_by_key.pop(key, None)

    def _cancel_pending_wait_task(self, key) -> None:
        pending_task = self.pending_wait_tasks.get(key)
        if pending_task and not pending_task.done():
            pending_task.cancel()
        self.pending_wait_tasks.pop(key, None)

    def _show_or_queue_player_match(self, player_id: str, status: str, match_id) -> None:
        key = self._build_toast_key(player_id, match_id, status)
        state = self.toast_status_by_key.get(key)
        if state in ("queued", "shown"):
            return

        match = self.get_match(status, match_id, print_match_count=True)
        if match:
            self._cancel_pending_wait_task(key)
            self._enqueue_toast_for_player_match(player_id, match, status, match_id)
            return

        if status not in self.valid_statuses:
            return
        if key in self.pending_wait_tasks and not self.pending_wait_tasks[key].done():
            return

        self.toast_status_by_key[key] = "waiting"
        self.pending_wait_tasks[key] = asyncio.create_task(
            self._wait_for_match_and_enqueue_toast(player_id, status, match_id)
        )

    def handle_player_status_update(self, player_id: str, status: str, match_id) -> None:
        """Handle one player status update by enqueueing or waiting for match data."""
        if self.status_logger:
            self.status_logger(player_id, status, match_id)
        self._show_or_queue_player_match(player_id, status, match_id)
