from typing import Any, Dict, Callable, Awaitable

class EngineContext:
    def __init__(
        self,
        game_id: str,
        _dispatcher: Callable[[str, str, str], Awaitable[None]],
        _scheduler: Callable[[str, Any], None],
        _ender: Callable[[str], Awaitable[None]],
        trigger_data: Dict[str, Any]
    ):
        self.game_id = game_id
        self._dispatcher = _dispatcher
        self._scheduler = _scheduler
        self._ender = _ender
        self.trigger_data = trigger_data

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
        Schedules a background task (fire-and-forget).
        This was the missing happy little tree!
        """
        if self._scheduler:
            # The game_engine._schedule_background_task expects (game_id, coroutine)
            self._scheduler(self.game_id, coro)
