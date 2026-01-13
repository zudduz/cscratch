import uuid
import logging
import asyncio
import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict

from . import persistence
from .models import GameState, Player, GameInterface
from .engine_context import EngineContext
from .ai_engine import AITool

CARTRIDGE_MAP = {
    "foster-protocol": "cartridges.foster_protocol.logic",
    "hms-bucket": "cartridges.hms_bucket.logic"
}

class GameEngine:
    def __init__(self):
        self.ai = AITool()
        self.locks = defaultdict(asyncio.Lock)
        self.interfaces = []
        self.running = False
        self.cron_task = None

    async def start(self):
        if self.running: return
        self.running = True
        logging.info("System: Game Engine Started.")
        self.cron_task = asyncio.create_task(self._cron_loop())

    def stop(self):
        self.running = False
        if self.cron_task:
            logging.info("System: Cancelling Cron Loop...")
            self.cron_task.cancel()

    async def register_interface(self, interface):
        self.interfaces.append(interface)

    async def start_new_game(self, story_id: str, host_id: str, host_name: str) -> str:
        game_id = str(uuid.uuid4())[:8]
        cartridge = await self._load_cartridge(story_id)
        
        logging.info(f"Game Engine: Creating Lobby for {game_id} (Host: {host_name})")
        
        new_game = GameState(
            id=game_id,
            story_id=story_id,
            host_id=host_id,
            status="setup",
            created_at=datetime.datetime.now(datetime.timezone.utc),
            metadata=cartridge.meta
        )
        
        await persistence.db.create_game_record(new_game)
        await self.join_game(game_id, host_id, host_name)
        return game_id

    async def join_game(self, game_id: str, user_id: str, user_name: str):
        game = await persistence.db.get_game_by_id(game_id)
        if game:
            for p in game.players:
                if p.id == user_id: return
        player = Player(id=user_id, name=user_name, joined_at=str(uuid.uuid1()))
        await persistence.db.add_player_to_game(game_id, player)

    async def register_interface_data(self, game_id: str, interface_data: dict):
        interface = GameInterface(**interface_data)
        await persistence.db.update_game_interface(game_id, interface)

    async def launch_match(self, game_id: str) -> dict:
        game = await persistence.db.get_game_by_id(game_id)
        if not game: return None

        cartridge = await self._load_cartridge(game.story_id)
        result = {}
        
        if hasattr(cartridge, 'on_game_start'):
            result = await cartridge.on_game_start(game.model_dump())
            if 'metadata' in result:
                 await persistence.db.update_game_metadata(game_id, result['metadata'])

        await persistence.db.set_game_active(game_id)
        return result

    async def find_game_by_channel(self, channel_id: str) -> GameState | None:
        return await persistence.db.get_game_by_channel_id(channel_id)

    async def end_game(self, game_id: str):
        """Ends the game state and locks all interfaces."""
        await persistence.db.mark_game_ended(game_id)
        
        game = await persistence.db.get_game_by_id(game_id)
        if not game: return
        
        # Trigger Interface Lockdowns
        for interface in self.interfaces:
            if hasattr(interface, 'lock_channels'):
                await interface.lock_channels(game_id, game.interface.model_dump())

    async def dispatch_input(self, channel_id: str, user_id: str, user_name: str, user_input: str):
        game = await persistence.db.get_game_by_channel_id(channel_id)
        if not game or game.status != 'active': return

        async with self.locks[game.id]:
            game = await persistence.db.get_game_by_id(game.id)
            
            trigger_data = {
                "channel_id": str(channel_id),
                "user_id": str(user_id),
                "user_name": str(user_name),
                "interface": game.interface.model_dump()
            }

            ctx = EngineContext(
                game_id=game.id,
                _dispatcher=self._dispatch_message_to_interfaces,
                _scheduler=self._schedule_background_task,
                _ender=self.end_game,
                trigger_data=trigger_data
            )

            cartridge = await self._load_cartridge(game.story_id)
            
            patch = await cartridge.handle_input(
                game.model_dump(), 
                user_input, 
                ctx, 
                Toolbox(self.ai)
            )

            if patch:
                await self._apply_state_patch(game.id, patch)

    async def dispatch_immediate_result(self, game_id: str, result: dict):
        msgs = result.get('messages', [])
        if msgs:
            for msg in msgs:
                await self._dispatch_message_to_interfaces(game_id, msg.get('channel'), msg.get('content'))

    def _schedule_background_task(self, game_id: str, coro: Any):
        asyncio.create_task(self._run_task_safely(game_id, coro))

    async def _run_task_safely(self, game_id: str, coro: Any):
        try:
            patch = await coro
            if patch:
                async with self.locks[game_id]:
                    await self._apply_state_patch(game_id, patch)
        except Exception as e:
            logging.error(f"Background Task Error (Game {game_id}): {e}")

    async def _apply_state_patch(self, game_id: str, patch: Dict[str, Any]):
        try:
            await persistence.db.update_game_metadata_fields(game_id, patch)
        except Exception as e:
            logging.error(f"State Patch Failed: {e}")

    async def _dispatch_message_to_interfaces(self, game_id: str, channel_key: str, text: str):
        game = await persistence.db.get_game_by_id(game_id)
        if not game: return
        
        channel_id = game.interface.channels.get(channel_key)
        if not channel_id:
             if channel_key.isdigit(): channel_id = channel_key
             else: return

        for interface in self.interfaces:
            if hasattr(interface, 'send_message'):
                await interface.send_message(channel_id, text)

    async def _load_cartridge(self, story_id):
        import importlib
        module_path = CARTRIDGE_MAP.get(story_id, CARTRIDGE_MAP["hms-bucket"])
        module = importlib.import_module(module_path)
        if story_id == "foster-protocol": return module.FosterProtocol()
        return module.HMSBucket()

    async def _cron_loop(self):
        try:
            while self.running:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

class Toolbox:
    def __init__(self, ai_tool):
        self.ai = ai_tool

engine = GameEngine()
