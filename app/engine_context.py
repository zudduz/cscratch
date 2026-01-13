from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional

@dataclass
class EngineContext:
    game_id: str
    _dispatcher: Callable[[str, str, str], Coroutine] 
    _scheduler: Callable[[str, Coroutine], None]      
    _ender: Callable[[str], Coroutine]
    trigger_data: Dict[str, str] = field(default_factory=dict)

    async def send(self, channel_key: str, text: str):
        """Send a message immediately to a logical channel (e.g. 'picnic')."""
        await self._dispatcher(self.game_id, channel_key, text)

    async def reply(self, text: str):
        """Helper to reply to the channel that triggered this context."""
        cid = self.trigger_data.get('channel_id')
        if cid:
            await self._dispatcher(self.game_id, cid, text)

    def spawn(self, task: Coroutine):
        """Schedule a background task (e.g. a scan) to run independently."""
        self._scheduler(self.game_id, task)

    async def end(self):
        """Signals the engine to terminate the game (freeze state)."""
        await self._ender(self.game_id)
