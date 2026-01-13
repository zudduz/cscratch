from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional

@dataclass
class EngineContext:
    game_id: str
    _dispatcher: Callable[[str, str, str], Coroutine] # func(game_id, channel, text)
    _scheduler: Callable[[str, Coroutine], None]      # func(game_id, coro)
    trigger_data: Dict[str, str] = field(default_factory=dict) # user_id, channel_id, etc.

    async def send(self, channel_key: str, text: str):
        """Send a message immediately to a logical channel (e.g. 'picnic')."""
        await self._dispatcher(self.game_id, channel_key, text)

    async def reply(self, text: str):
        """Helper to reply to the channel that triggered this context."""
        # We try to find the logical key associated with the channel_id
        # Since we don't have the map here, we rely on the engine or pass the raw ID.
        # However, our dispatcher expects a KEY.
        # If the dispatcher handles raw IDs (as fallback), we can pass the ID.
        cid = self.trigger_data.get('channel_id')
        if cid:
            await self._dispatcher(self.game_id, cid, text)

    def spawn(self, task: Coroutine):
        """Schedule a background task (e.g. a scan) to run independently."""
        self._scheduler(self.game_id, task)
