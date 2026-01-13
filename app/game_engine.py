import uuid
import logging
import asyncio
import datetime
from typing import Dict, Any, List
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

    async def start(self):
        self.running = True
        logging.info("System: Game Engine Started.")
        asyncio.create_task(self._cron_loop())

    async def register_interface(self, interface):
        self.interfaces.append(interface)

    async def dispatch_immediate_result(self, game_id: str, result: dict):
        msgs = result.get('messages', [])
        if msgs:
            for msg in msgs:
                await self._dispatch_message_to_interfaces(game_id, msg.get('channel'), msg.get('content'))

    # --- 1. CORE INPUT LOOP ---
    async def dispatch_input(self, channel_id: str, user_id: str, user_name: str, user_input: str):
        game = await persistence.db.get_game_by_channel_id(channel_id)
        if not game or game.status != 'active': return

        async with self.locks[game.id]:
            # Refresh state inside lock
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
                trigger_data=trigger_data
            )

            cartridge = await self._load_cartridge(game.story_id)
            
            # PASS THE CTX TO THE CARTRIDGE
            patch = await cartridge.handle_input(
                game.model_dump(), 
                user_input, 
                ctx, 
                Toolbox(self.ai)
            )

            if patch:
                await self._apply_state_patch(game.id, patch)

    # --- 2. BACKGROUND TASKS ---
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

    # --- 3. STATE ---
    async def _apply_state_patch(self, game_id: str, patch: Dict[str, Any]):
        try:
            await persistence.db.update_game_metadata_fields(game_id, patch)
        except Exception as e:
            logging.error(f"State Patch Failed: {e}")

    # --- 4. OUTPUT ---
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
        while self.running:
            await asyncio.sleep(60)
            pass

class Toolbox:
    def __init__(self, ai_tool):
        self.ai = ai_tool

engine = GameEngine()
