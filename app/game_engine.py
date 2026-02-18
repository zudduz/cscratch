import uuid
import logging
import asyncio
import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict

from . import persistence
from .models import GameState, LobbyPlayer, GameInterface
from .engine_context import EngineContext
from .ai_engine import AIEngine

CARTRIDGE_MAP = {
    "foster-protocol": "cartridges.foster_protocol.logic"
}

class GameEngine:
    def __init__(self):
        self.ai = AIEngine()
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

    async def join_game(self, game_id: str, user_id: str, user_name: str) -> dict:
        """
        Attempts to add a player to the game.
        Returns a dict containing status, player_count, max, and current_cost.
        """
        game = await persistence.db.get_game_by_id(game_id)
        if not game: 
            return {"status": "error"}

        cartridge = await self._load_cartridge(game.story_id)
        
        max_players = getattr(cartridge, "MAX_PLAYERS", 8)
        cost_func = getattr(cartridge, "calculate_start_cost", lambda n: max(4, n))

        # Check if already joined
        existing = next((p for p in game.players if p.id == user_id), None)
        if existing:
            current_count = len(game.players)
            cost = cost_func(current_count)
            return {
                "status": "joined", 
                "player_count": current_count, 
                "cost": cost, 
                "max": max_players
            }

        # Check limit
        if len(game.players) >= max_players:
             return {"status": "full", "max": max_players}

        player = LobbyPlayer(id=user_id, name=user_name)
        await persistence.db.add_player_to_game(game_id, player)
        
        # Calculate state after join
        current_count = len(game.players) + 1
        cost = cost_func(current_count)
        
        return {
            "status": "joined", 
            "player_count": current_count, 
            "cost": cost, 
            "max": max_players
        }

    async def register_interface_data(self, game_id: str, interface_data: dict):
        interface = GameInterface(**interface_data)
        await persistence.db.update_game_interface(game_id, interface)

    async def launch_match(self, game_id: str) -> dict:
        game = await persistence.db.get_game_by_id(game_id)
        if not game: return {"error": "no_game"}

        cartridge = await self._load_cartridge(game.story_id)
        
        # --- ECONOMY CHECK ---
        cost_func = getattr(cartridge, "calculate_start_cost", lambda n: max(4, n))
        cost = cost_func(len(game.players))
        
        # 1. DEDUCT (The Gate)
        # We try to take the money first. If they don't have it, we stop here.
        if not await persistence.db.deduct_balance_if_sufficient(game.host_id, cost):
            return {"error": "insufficient_funds", "cost": cost}
        
        # 2. ATTEMPT START (Safe Mode)
        # If anything crashes below, we MUST refund the user.
        try:
            result = {}
            
            if hasattr(cartridge, 'on_game_start'):
                result = await cartridge.on_game_start(game.model_dump())
                if 'metadata' in result:
                     await persistence.db.update_game_metadata(game_id, result['metadata'], game.version)

            await persistence.db.set_game_active(game_id)
            return result

        except Exception as e:
            # 3. CATASTROPHIC FAILURE -> REFUND
            logging.critical(f"GAME_START_FAILED: Game {game_id}, Host {game.host_id}, Cost {cost}. Error: {e}")
            
            try:
                new_bal = await persistence.db.adjust_user_balance(game.host_id, cost)
                logging.info(f"REFUND_SUCCESSFUL: User {game.host_id} refunded {cost}. New Balance: {new_bal}")
            except Exception as refund_err:
                # If this fails, we have a major DB issue, but we log it for manual audit.
                logging.critical(f"REFUND_FAILED: User {game.host_id} could NOT be refunded {cost}. Error: {refund_err}")
            
            return {"error": "startup_failed", "detail": str(e)}

    async def trigger_post_start(self, game_id: str):
        """
        Lifecycle hook called by the Interface (Discord) AFTER channels are created.
        Acquires lock to ensure safe state updates during the wakeup protocol.
        """
        # 1. Acquire Lock (Safety against eager player input)
        async with self.locks[game_id]:
            game = await persistence.db.get_game_by_id(game_id)
            if not game: return

            cartridge = await self._load_cartridge(game.story_id)
            
            if hasattr(cartridge, 'post_game_start'):
                trigger_data = {
                    "user_id": "system",
                    "channel_id": "system",
                    "interface": game.interface.model_dump(),
                    "metadata": game.metadata
                }
                
                ctx = EngineContext(
                    game_id=game.id,
                    _dispatcher=self._dispatch_message_to_interfaces,
                    _scheduler=self._schedule_background_task,
                    _ender=self.end_game,
                    trigger_data=trigger_data
                )
                
                # 2. Execute Hook
                patch = await cartridge.post_game_start(game.metadata, ctx, Toolbox(self.ai))

                # 3. Save State Updates (e.g. Chat Logs from Intros)
                if patch and "metadata" in patch:
                    await self._apply_state_patch(game.id, patch["metadata"])

    async def end_game(self, game_id: str):
        await persistence.db.mark_game_ended(game_id)
        
        game = await persistence.db.get_game_by_id(game_id)
        if not game: return
        
        for interface in self.interfaces:
            if hasattr(interface, 'lock_channels'):
                await interface.lock_channels(game_id, game.interface.model_dump())

    async def dispatch_input(self, channel_id: str, user_id: str, user_name: str, user_input: str, game_id: str):
        async with self.locks[game_id]:
            game = await persistence.db.get_game_by_id(game_id)
            if not game or game.status != 'active':
                return
            
            trigger_data = {
                "channel_id": str(channel_id),
                "user_id": str(user_id),
                "user_name": str(user_name),
                "interface": game.interface.model_dump(),
                "metadata": game.metadata 
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
                # --- EXTRACT OPS ---
                if "channel_ops" in patch:
                    ops = patch.pop("channel_ops")
                    if ops:
                        for interface in self.interfaces:
                            if hasattr(interface, 'execute_channel_ops'):
                                await interface.execute_channel_ops(game.id, ops)
                
                # Check for metadata key or use root
                state_update = patch
                if "metadata" in patch:
                    state_update = patch["metadata"]

                if state_update: 
                    await self._apply_state_patch(game.id, state_update)

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
                    # Assume simple patch for background tasks
                    await self._apply_state_patch(game_id, patch)
        except Exception as e:
            logging.error(f"Background Task Error (Game {game_id}): {e}")

    async def _apply_state_patch(self, game_id: str, patch: Dict[str, Any]):
        try:
            await persistence.db.update_game_metadata_fields(game_id, patch)
        except Exception as e:
            logging.error(f"State Patch Failed: {e}")
            raise e

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
        module_path = CARTRIDGE_MAP.get(story_id, CARTRIDGE_MAP["foster-protocol"])
        module = importlib.import_module(module_path)
        return module.FosterProtocol()

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