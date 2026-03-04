from typing import Any, Dict, Callable, Awaitable

class EngineContext:
    def __init__(
        self,
        game_id: str,
        cartridge_id: str,
        _dispatcher: Callable[[str, str, str], Awaitable[None]],
        _scheduler: Callable[[str, Any], None],
        _task_scheduler: Callable[[str, str, str, dict, int], None],
        _ender: Callable[[str], Awaitable[None]],
        trigger_data: Dict[str, Any]
    ):
        self.game_id = game_id
        self.cartridge_id = cartridge_id
        self._dispatcher = _dispatcher
        self._scheduler = _scheduler
        self._task_scheduler = _task_scheduler
        self._ender = _ender
        self.trigger_data = trigger_data
        
        # Buffer for deferred task scheduling
        self.pending_tasks = []

    async def send(self, channel_key: str, message: str):
        """Sends a message to a specific channel key (e.g., 'aux-comm')."""
        if self._dispatcher:
            await self._dispatcher(self.game_id, channel_key, message)

    async def reply(self, message: str):
        """Reply to the channel that triggered the input."""
        channel_id = self.trigger_data.get('channel_id')
        if channel_id and self._dispatcher:
            # We pass the raw channel ID directly
            await self._dispatcher(self.game_id, channel_id, message)

    async def end(self):
        """Ends the game."""
        if self._ender:
            await self._ender(self.game_id)

    def schedule(self, coro: Any):
        """
        LEGACY: Schedules a background task (fire-and-forget).
        """
        if self._scheduler:
            self._scheduler(self.game_id, coro)

    def schedule_task(self, operation: str, data: dict = None, delay: int = 0):
        """
        Buffers an event-driven task. Will be dispatched by the engine after state saves.
        """
        self.pending_tasks.append((operation, data, delay))